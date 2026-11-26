from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_commissiondar
from app.models.commissiondar import (
    CommissiondarMill,
    CommissiondarMillCommission,
    CommissiondarMillCommissionReceipt,
    CommissiondarMillFarmer,
)
from app.models.core import User
from app.models.party import Party
from app.schemas.commissiondar import (
    CommissiondarMillCommissionCreate,
    CommissiondarMillCommissionReceiptCreate,
    CommissiondarMillCreate,
    CommissiondarMillUpdate,
)
from app.services.db_helpers import commit_transaction

router = APIRouter()


@router.get("/api/commissiondar/mills/{mill_id}/farmers")
def list_farmers_for_commissiondar_mill(
    mill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar),
):
    # Confirm that this mill belongs to the logged-in Commissiondar.
    mill = db.query(CommissiondarMill).filter(
        CommissiondarMill.id == mill_id,
        CommissiondarMill.commissiondar_id == current_user.party_id,
        CommissiondarMill.business_id == current_user.business_id,
    ).first()

    if not mill:
        raise HTTPException(status_code=404, detail="Mill not found")

    associations = (
        db.query(CommissiondarMillFarmer, Party)
        .join(
            Party,
            Party.id == CommissiondarMillFarmer.farmer_id,
        )
        .filter(
            CommissiondarMillFarmer.mill_id == mill_id,
            CommissiondarMillFarmer.commissiondar_id == current_user.party_id,
            CommissiondarMillFarmer.is_active == True,
            Party.business_id == current_user.business_id,
            Party.party_type == "farmer",
            Party.is_active == True,
        )
        .order_by(Party.name.asc())
        .all()
    )

    return {
        "mill_id": mill.id,
        "mill_name": mill.name,
        "farmer_count": len(associations),
        "farmers": [
            {
                "id": farmer.id,
                "name": farmer.name,
                "phone": farmer.phone,
                "village": farmer.village,
            }
            for association, farmer in associations
        ],
    }


@router.post("/api/commissiondar/mills/{mill_id}/farmers/{farmer_id}", status_code=201)
def add_farmer_to_commissiondar_mill(
    mill_id: int,
    farmer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar),
):
    # The mill must belong to this Commissiondar and be active.
    mill = db.query(CommissiondarMill).filter(
        CommissiondarMill.id == mill_id,
        CommissiondarMill.commissiondar_id == current_user.party_id,
        CommissiondarMill.business_id == current_user.business_id,
        CommissiondarMill.is_active == True,
    ).first()

    if not mill:
        raise HTTPException(status_code=404, detail="Active mill not found")

    # The farmer must belong to this Commissiondar's own directory.
    farmer = db.query(Party).filter(
        Party.id == farmer_id,
        Party.business_id == current_user.business_id,
        Party.party_type == "farmer",
        Party.is_active == True,
    ).first()

    if not farmer:
        raise HTTPException(
            status_code=404,
            detail="Farmer not found in your farmer directory",
        )

    association = db.query(CommissiondarMillFarmer).filter(
        CommissiondarMillFarmer.mill_id == mill_id,
        CommissiondarMillFarmer.farmer_id == farmer_id,
        CommissiondarMillFarmer.commissiondar_id == current_user.party_id,
    ).first()

    if association and association.is_active:
        raise HTTPException(
            status_code=409,
            detail="Farmer is already associated with this mill",
        )

    if association:
        # Reactivate a previously removed association.
        association.is_active = True
    else:
        association = CommissiondarMillFarmer(
            commissiondar_id=current_user.party_id,
            mill_id=mill_id,
            farmer_id=farmer_id,
            is_active=True,
        )
        db.add(association)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Farmer is already associated with this mill",
        )
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to associate farmer with mill",
        )

    return {
        "mill_id": mill_id,
        "mill_name": mill.name,
        "farmer_id": farmer.id,
        "farmer_name": farmer.name,
        "message": "Farmer associated with mill successfully",
    }


@router.delete("/api/commissiondar/mills/{mill_id}/farmers/{farmer_id}")
def remove_farmer_from_commissiondar_mill(
    mill_id: int,
    farmer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar),
):
    # Confirm ownership of the mill.
    mill = db.query(CommissiondarMill).filter(
        CommissiondarMill.id == mill_id,
        CommissiondarMill.commissiondar_id == current_user.party_id,
        CommissiondarMill.business_id == current_user.business_id,
    ).first()

    if not mill:
        raise HTTPException(status_code=404, detail="Mill not found")

    association = db.query(CommissiondarMillFarmer).filter(
        CommissiondarMillFarmer.mill_id == mill_id,
        CommissiondarMillFarmer.farmer_id == farmer_id,
        CommissiondarMillFarmer.commissiondar_id == current_user.party_id,
        CommissiondarMillFarmer.is_active == True,
    ).first()

    if not association:
        raise HTTPException(
            status_code=404,
            detail="Active farmer association not found",
        )

    # Remove only the association, never the farmer directory record.
    association.is_active = False

    commit_transaction(
        db,
        "Failed to remove farmer from mill",
    )

    return {
        "mill_id": mill_id,
        "farmer_id": farmer_id,
        "message": "Farmer removed from mill successfully",
    }


@router.get("/api/commissiondar/mills")
def list_commissiondar_mills(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar),
):
    query = db.query(CommissiondarMill).filter(
        CommissiondarMill.commissiondar_id == current_user.party_id,
        CommissiondarMill.business_id == current_user.business_id,
    )

    if not include_inactive:
        query = query.filter(CommissiondarMill.is_active == True)

    mills = query.order_by(CommissiondarMill.name.asc()).all()

    return [
        {
            "id": mill.id,
            "name": mill.name,
            "is_active": mill.is_active,
            "created_at": mill.created_at,
        }
        for mill in mills
    ]


@router.post("/api/commissiondar/mills", status_code=201)
def create_commissiondar_mill(
    data: CommissiondarMillCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar),
):
    name = data.name.strip()

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Mill name cannot be empty",
        )

    existing = db.query(CommissiondarMill).filter(
        CommissiondarMill.commissiondar_id == current_user.party_id,
        func.lower(CommissiondarMill.name) == name.lower(),
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="This mill name already exists",
        )

    mill = CommissiondarMill(
        commissiondar_id=current_user.party_id,
        business_id=current_user.business_id,
        name=name,
        is_active=True,
    )

    db.add(mill)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This mill name already exists",
        )
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to create mill",
        )

    db.refresh(mill)

    return {
        "id": mill.id,
        "name": mill.name,
        "is_active": mill.is_active,
        "message": "Mill added successfully",
    }


@router.put("/api/commissiondar/mills/{mill_id}")
def update_commissiondar_mill(
    mill_id: int,
    data: CommissiondarMillUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar),
):
    mill = db.query(CommissiondarMill).filter(
        CommissiondarMill.id == mill_id,
        CommissiondarMill.commissiondar_id == current_user.party_id,
        CommissiondarMill.business_id == current_user.business_id,
    ).first()

    if not mill:
        raise HTTPException(
            status_code=404,
            detail="Mill not found",
        )

    if data.name is None and data.is_active is None:
        raise HTTPException(
            status_code=400,
            detail="No update fields provided",
        )

    if data.name is not None:
        name = data.name.strip()

        if not name:
            raise HTTPException(
                status_code=400,
                detail="Mill name cannot be empty",
            )

        duplicate = db.query(CommissiondarMill).filter(
            CommissiondarMill.commissiondar_id == current_user.party_id,
            CommissiondarMill.id != mill_id,
            func.lower(CommissiondarMill.name) == name.lower(),
        ).first()

        if duplicate:
            raise HTTPException(
                status_code=409,
                detail="This mill name already exists",
            )

        mill.name = name

    if data.is_active is not None:
        mill.is_active = data.is_active

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Could not update mill because of a duplicate name",
        )
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to update mill",
        )

    db.refresh(mill)

    return {
        "id": mill.id,
        "name": mill.name,
        "is_active": mill.is_active,
        "message": "Mill updated successfully",
    }


@router.delete("/api/commissiondar/mills/{mill_id}")
def deactivate_commissiondar_mill(
    mill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar),
):
    mill = db.query(CommissiondarMill).filter(
        CommissiondarMill.id == mill_id,
        CommissiondarMill.commissiondar_id == current_user.party_id,
        CommissiondarMill.business_id == current_user.business_id,
    ).first()

    if not mill:
        raise HTTPException(
            status_code=404,
            detail="Mill not found",
        )

    if not mill.is_active:
        raise HTTPException(
            status_code=400,
            detail="Mill is already inactive",
        )

    mill.is_active = False

    commit_transaction(
        db,
        "Failed to deactivate mill",
    )

    return {
        "id": mill.id,
        "name": mill.name,
        "is_active": False,
        "message": "Mill deactivated successfully",
    }


@router.post(
    "/api/commissiondar/mills/{mill_id}/commissions",
    status_code=201,
)
def create_commissiondar_mill_commission(
    mill_id: int,
    data: CommissiondarMillCommissionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar),
):
    # Only the logged-in Commissiondar's active mill is allowed.
    mill = db.query(CommissiondarMill).filter(
        CommissiondarMill.id == mill_id,
        CommissiondarMill.commissiondar_id == current_user.party_id,
        CommissiondarMill.business_id == current_user.business_id,
        CommissiondarMill.is_active == True,
    ).first()

    if not mill:
        raise HTTPException(status_code=404, detail="Active mill not found")

    commission = CommissiondarMillCommission(
        commissiondar_id=current_user.party_id,
        mill_id=mill.id,
        commission_amount=data.commission_amount,
        earned_at=data.earned_at or date.today(),
        note=data.note.strip() if data.note else None,
        is_void=False,
    )

    db.add(commission)
    commit_transaction(db, "Failed to record commission")
    db.refresh(commission)

    return {
        "id": commission.id,
        "mill_id": mill.id,
        "mill_name": mill.name,
        "commission_amount": float(commission.commission_amount),
        "earned_at": commission.earned_at,
        "note": commission.note,
        "received_amount": 0.0,
        "pending_amount": float(commission.commission_amount),
        "message": "Commission recorded successfully",
    }


@router.get("/api/commissiondar/mills/{mill_id}/commissions")
def list_commissiondar_mill_commissions(
    mill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar),
):
    mill = db.query(CommissiondarMill).filter(
        CommissiondarMill.id == mill_id,
        CommissiondarMill.commissiondar_id == current_user.party_id,
        CommissiondarMill.business_id == current_user.business_id,
    ).first()

    if not mill:
        raise HTTPException(status_code=404, detail="Mill not found")

    commissions = db.query(CommissiondarMillCommission).filter(
        CommissiondarMillCommission.mill_id == mill.id,
        CommissiondarMillCommission.commissiondar_id == current_user.party_id,
        CommissiondarMillCommission.is_void == False,
    ).order_by(
        CommissiondarMillCommission.earned_at.desc(),
        CommissiondarMillCommission.id.desc(),
    ).all()

    commission_ids = [item.id for item in commissions]

    receipts = []
    if commission_ids:
        receipts = db.query(CommissiondarMillCommissionReceipt).filter(
            CommissiondarMillCommissionReceipt.commission_id.in_(commission_ids),
            CommissiondarMillCommissionReceipt.commissiondar_id == current_user.party_id,
            CommissiondarMillCommissionReceipt.is_void == False,
        ).order_by(
            CommissiondarMillCommissionReceipt.received_at.desc(),
            CommissiondarMillCommissionReceipt.id.desc(),
        ).all()

    receipts_by_commission = {}
    for receipt in receipts:
        receipts_by_commission.setdefault(receipt.commission_id, []).append(receipt)

    result = []
    total_earned = Decimal("0.00")
    total_received = Decimal("0.00")

    for commission in commissions:
        commission_receipts = receipts_by_commission.get(commission.id, [])

        received = sum(
            (receipt.amount for receipt in commission_receipts),
            Decimal("0.00"),
        )

        earned = commission.commission_amount
        pending = earned - received

        total_earned += earned
        total_received += received

        result.append({
            "id": commission.id,
            "commission_amount": float(earned),
            "earned_at": commission.earned_at,
            "note": commission.note,
            "received_amount": float(received),
            "pending_amount": float(pending),
            "receipts": [
                {
                    "id": receipt.id,
                    "amount": float(receipt.amount),
                    "received_at": receipt.received_at,
                    "note": receipt.note,
                }
                for receipt in commission_receipts
            ],
        })

    return {
        "mill_id": mill.id,
        "mill_name": mill.name,
        "total_earned": float(total_earned),
        "total_received": float(total_received),
        "total_pending": float(total_earned - total_received),
        "commission_count": len(result),
        "commissions": result,
    }


@router.post(
    "/api/commissiondar/commissions/{commission_id}/receipts",
    status_code=201,
)
def create_commissiondar_commission_receipt(
    commission_id: int,
    data: CommissiondarMillCommissionReceiptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar),
):
    # Lock the commission row while checking and recording a receipt.
    # This prevents concurrent receipts from exceeding the pending amount.
    commission = db.query(CommissiondarMillCommission).filter(
        CommissiondarMillCommission.id == commission_id,
        CommissiondarMillCommission.commissiondar_id == current_user.party_id,
        CommissiondarMillCommission.is_void == False,
    ).with_for_update().first()

    if not commission:
        raise HTTPException(status_code=404, detail="Commission entry not found")

    received = db.query(
        func.coalesce(
            func.sum(CommissiondarMillCommissionReceipt.amount),
            0,
        )
    ).filter(
        CommissiondarMillCommissionReceipt.commission_id == commission.id,
        CommissiondarMillCommissionReceipt.commissiondar_id == current_user.party_id,
        CommissiondarMillCommissionReceipt.is_void == False,
    ).scalar()

    received = received or Decimal("0.00")
    pending = commission.commission_amount - received

    if data.amount > pending:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Receipt amount exceeds pending commission",
                "pending_amount": float(pending),
            },
        )

    receipt = CommissiondarMillCommissionReceipt(
        commissiondar_id=current_user.party_id,
        commission_id=commission.id,
        amount=data.amount,
        received_at=data.received_at or date.today(),
        note=data.note.strip() if data.note else None,
        is_void=False,
    )

    db.add(receipt)
    commit_transaction(db, "Failed to record commission receipt")
    db.refresh(receipt)

    remaining = pending - receipt.amount

    return {
        "id": receipt.id,
        "commission_id": commission.id,
        "amount": float(receipt.amount),
        "received_at": receipt.received_at,
        "note": receipt.note,
        "remaining_pending": float(remaining),
        "message": "Commission receipt recorded successfully",
    }


@router.get("/api/commissiondar/commissions/{commission_id}/receipts")
def list_commissiondar_commission_receipts(
    commission_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar),
):
    commission = db.query(CommissiondarMillCommission).filter(
        CommissiondarMillCommission.id == commission_id,
        CommissiondarMillCommission.commissiondar_id == current_user.party_id,
    ).first()

    if not commission:
        raise HTTPException(status_code=404, detail="Commission entry not found")

    receipts = db.query(CommissiondarMillCommissionReceipt).filter(
        CommissiondarMillCommissionReceipt.commission_id == commission.id,
        CommissiondarMillCommissionReceipt.commissiondar_id == current_user.party_id,
        CommissiondarMillCommissionReceipt.is_void == False,
    ).order_by(
        CommissiondarMillCommissionReceipt.received_at.desc(),
        CommissiondarMillCommissionReceipt.id.desc(),
    ).all()

    total_received = sum(
        (receipt.amount for receipt in receipts),
        Decimal("0.00"),
    )

    return {
        "commission_id": commission.id,
        "commission_amount": float(commission.commission_amount),
        "total_received": float(total_received),
        "pending_amount": float(commission.commission_amount - total_received),
        "receipts": [
            {
                "id": receipt.id,
                "amount": float(receipt.amount),
                "received_at": receipt.received_at,
                "note": receipt.note,
            }
            for receipt in receipts
        ],
    }
