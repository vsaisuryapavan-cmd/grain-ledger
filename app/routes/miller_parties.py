from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_owner
from app.models.core import User
from app.models.miller import (
    BrokerCommission,
    MillCommissiondarLoan,
    MillCommissiondarLoanRepayment,
    StockMovement,
)
from app.models.party import Party
from app.schemas.miller import (
    CommissiondarContactCreate,
    CommissiondarContactUpdate,
    FarmerCreate,
    FarmerUpdate,
)
from app.services.db_helpers import commit_transaction
from app.services.miller_service import farmer_balance

router = APIRouter()


@router.post("/api/miller/commissiondars", status_code=201)
def create_miller_commissiondar_contact(
    data: CommissiondarContactCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    contact = Party(
        business_id=current_user.business_id,
        name=data.name.strip(),
        phone=(data.phone or None),
        village=(data.village or None),
        party_type="commissiondar",
        opening_balance=Decimal("0"),
        is_active=True,
    )
    db.add(contact)
    commit_transaction(db, "Failed to create Commissiondar contact")
    db.refresh(contact)
    return {
        "id": contact.id,
        "name": contact.name,
        "phone": contact.phone,
        "village": contact.village,
    }


@router.get("/api/miller/commissiondars")
def list_miller_commissiondar_contacts(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    contacts = db.query(Party).filter(
        Party.business_id == current_user.business_id,
        Party.party_type == "commissiondar",
    ).order_by(Party.name.asc()).all()
    result = []
    for contact in contacts:
        movements = db.query(StockMovement).filter(
            StockMovement.business_id == current_user.business_id,
            StockMovement.broker_id == contact.id,
            StockMovement.movement_type == "purchase",
            StockMovement.is_void == False,
        ).all()
        commissions = db.query(
            func.coalesce(func.sum(BrokerCommission.commission_amount), 0)
        ).filter(
            BrokerCommission.business_id == current_user.business_id,
            BrokerCommission.commissiondar_id == contact.id,
            BrokerCommission.is_void == False,
        ).scalar() or 0
        paid_commissions = db.query(
            func.coalesce(func.sum(BrokerCommission.commission_amount), 0)
        ).filter(
            BrokerCommission.business_id == current_user.business_id,
            BrokerCommission.commissiondar_id == contact.id,
            BrokerCommission.is_paid == True,
            BrokerCommission.is_void == False,
        ).scalar() or 0

        associated_farmers = db.query(Party.id).filter(
            Party.business_id == current_user.business_id,
            Party.party_type == "farmer",
            Party.associated_commissiondar_id == contact.id,
        ).all()

        farmer_ids = {
            movement.party_id
            for movement in movements
            if movement.party_id is not None
        }
        farmer_ids.update(row[0] for row in associated_farmers)

        commission_farmer_ids = db.query(BrokerCommission.farmer_id).filter(
            BrokerCommission.business_id == current_user.business_id,
            BrokerCommission.commissiondar_id == contact.id,
            BrokerCommission.is_void == False,
            BrokerCommission.farmer_id.isnot(None),
        ).all()

        farmer_ids.update(row[0] for row in commission_farmer_ids)
        loans = db.query(MillCommissiondarLoan).filter(
            MillCommissiondarLoan.business_id == current_user.business_id,
            MillCommissiondarLoan.commissiondar_id == contact.id,
            MillCommissiondarLoan.is_void == False,
        ).all()
        loan_principal = sum((Decimal(str(x.principal)) for x in loans), Decimal("0"))
        loan_repaid = Decimal("0")
        for loan in loans:
            loan_repaid += Decimal(
                str(
                    db.query(
                        func.coalesce(func.sum(MillCommissiondarLoanRepayment.amount), 0)
                    ).filter(
                        MillCommissiondarLoanRepayment.loan_id == loan.id,
                        MillCommissiondarLoanRepayment.is_void == False,
                    ).scalar()
                    or 0
                )
            )
        result.append({
            "id": contact.id,
            "name": contact.name,
            "phone": contact.phone,
            "village": contact.village,
            "is_active": contact.is_active,
            "visit_count": len(movements),
            "total_packets": float(sum((m.packet_count or 0) for m in movements)),
            "total_quantity": float(sum((m.quantity or 0) for m in movements)),
            # Commission summary
            "total_farmers": len(farmer_ids),
            "total_commission": float(commissions),
            "commission_paid": float(paid_commissions),
            "commission_outstanding": float(commissions) - float(paid_commissions),
            # Miller-to-Commissiondar loans
            "mill_loans_count": len(loans),
            "mill_loans_total_principal": float(loan_principal),
            "mill_loans_total_repaid": float(loan_repaid),
            "mill_loans_outstanding_principal": float(loan_principal - loan_repaid),
        })
    return result


@router.put("/api/miller/commissiondars/{contact_id}")
def update_miller_commissiondar_contact(
    contact_id: int,
    data: CommissiondarContactUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    contact = db.query(Party).filter(
        Party.id == contact_id,
        Party.business_id == current_user.business_id,
        Party.party_type == "commissiondar",
    ).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Commissiondar contact not found")
    for field in ("name", "phone", "village", "is_active"):
        value = getattr(data, field)
        if value is not None:
            setattr(contact, field, value.strip() if isinstance(value, str) else value)
    commit_transaction(db, "Failed to update Commissiondar contact")
    return {
        "id": contact.id,
        "name": contact.name,
        "phone": contact.phone,
        "village": contact.village,
        "is_active": contact.is_active,
    }


@router.get("/api/miller/commissiondars/{contact_id}")
def get_miller_commissiondar_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    contact = db.query(Party).filter(
        Party.id == contact_id,
        Party.business_id == current_user.business_id,
        Party.party_type == "commissiondar",
    ).first()

    if not contact:
        raise HTTPException(
            status_code=404,
            detail="Commissiondar contact not found",
        )

    business_id = current_user.business_id

    # 1. Get all valid purchase movements for this contact
    movements = db.query(StockMovement).filter(
        StockMovement.business_id == business_id,
        StockMovement.broker_id == contact.id,
        StockMovement.movement_type == "purchase",
        StockMovement.is_void == False,
    ).order_by(
        StockMovement.moved_at.desc()
    ).all()

    # 2. Get all commission records for this contact
    commissions = db.query(BrokerCommission).filter(
        BrokerCommission.business_id == business_id,
        BrokerCommission.commissiondar_id == contact.id,
        BrokerCommission.is_void == False,
    ).all()

    # 3. Collect farmer IDs from associations, intakes and commissions
    farmer_ids = {
        farmer.id
        for farmer in db.query(Party).filter(
            Party.business_id == business_id,
            Party.party_type == "farmer",
            Party.associated_commissiondar_id == contact.id,
        ).all()
    }

    farmer_ids.update(
        movement.party_id
        for movement in movements
        if movement.party_id is not None
    )

    farmer_ids.update(
        commission.farmer_id
        for commission in commissions
        if commission.farmer_id is not None
    )

    # 4. Fetch farmers belonging to this Miller business
    farmers = db.query(Party).filter(
        Party.business_id == business_id,
        Party.party_type == "farmer",
        Party.id.in_(farmer_ids),
    ).all() if farmer_ids else []

    farmer_map = {
        farmer.id: farmer
        for farmer in farmers
    }

    # 5. Group intake movements by farmer
    farmer_movements = {}

    for movement in movements:
        farmer_id = movement.party_id

        if farmer_id is not None:
            farmer_movements.setdefault(
                farmer_id, []
            ).append(movement)

    # 6. Group commissions by farmer
    farmer_commissions = {}

    for commission in commissions:
        farmer_id = commission.farmer_id

        if farmer_id is not None:
            farmer_commissions.setdefault(
                farmer_id, []
            ).append(commission)

    farmer_reports = []

    total_quantity = Decimal("0")
    total_commission = Decimal("0")
    total_commission_paid = Decimal("0")

    for farmer_id in farmer_ids:
        farmer = farmer_map.get(farmer_id)

        if not farmer:
            continue

        farmer_intakes = farmer_movements.get(
            farmer_id, []
        )

        farmer_quantity = sum(
            (
                Decimal(str(m.quantity or 0))
                for m in farmer_intakes
            ),
            Decimal("0"),
        )

        farmer_commission_records = farmer_commissions.get(
            farmer_id, []
        )

        earned = sum(
            (
                Decimal(str(c.commission_amount or 0))
                for c in farmer_commission_records
            ),
            Decimal("0"),
        )

        paid = sum(
            (
                Decimal(str(c.commission_amount or 0))
                for c in farmer_commission_records
                if c.is_paid
            ),
            Decimal("0"),
        )

        outstanding = earned - paid

        total_quantity += farmer_quantity
        total_commission += earned
        total_commission_paid += paid

        farmer_reports.append({
            "farmer_id": farmer.id,
            "farmer_name": farmer.name,
            "village": farmer.village,
            "total_intakes": len(farmer_intakes),
            "total_quantity": float(farmer_quantity),
            "commission_earned": float(earned),
            "commission_paid": float(paid),
            "commission_outstanding": float(outstanding),
            "intakes": farmer_intakes,
        })

    # 7. Calculate remaining commission
    total_outstanding = (
        total_commission - total_commission_paid
    )

    # 8. Preserve existing Miller-to-Commissiondar loans
    loans = db.query(MillCommissiondarLoan).filter(
        MillCommissiondarLoan.business_id == business_id,
        MillCommissiondarLoan.commissiondar_id == contact.id,
        MillCommissiondarLoan.is_void == False,
    ).all()

    return {
        "contact": {
            "id": contact.id,
            "name": contact.name,
            "phone": contact.phone,
            "village": contact.village,
            "is_active": contact.is_active,
        },
        "summary": {
            "total_farmers": len(farmer_reports),
            "total_intakes": len(movements),
            "total_quantity": float(total_quantity),
            "total_commission": float(total_commission),
            "commission_paid": float(total_commission_paid),
            "commission_outstanding": float(total_outstanding),
        },
        "farmers": farmer_reports,
        "intakes": movements,
        "loans": loans,
    }


@router.get("/api/farmers")
def list_farmers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    farmers = db.query(Party).filter(
        Party.business_id == current_user.business_id,
        Party.party_type == "farmer",
        Party.is_active == True,
    ).order_by(
        Party.name.asc()
    ).all()

    result = []

    for farmer in farmers:
        owed = farmer_balance(
            db,
            farmer,
            current_user.business_id,
        )

        associated_contact = None
        if farmer.associated_commissiondar_id:
            associated_contact = db.query(Party).filter(
                Party.id == farmer.associated_commissiondar_id,
                Party.business_id == current_user.business_id,
                Party.party_type == "commissiondar",
            ).first()
        result.append({
            "id": farmer.id,
            "name": farmer.name,
            "village": farmer.village,
            "associated_commissiondar_id": farmer.associated_commissiondar_id,
            "associated_commissiondar_name": associated_contact.name if associated_contact else None,
            "owed": float(owed),
        })

    return result


@router.post("/api/farmers")
def create_farmer(
    data: FarmerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    name = data.name.strip()
    village = data.village.strip()

    if not name or not village:
        raise HTTPException(
            status_code=400,
            detail="Farmer name and village cannot be empty",
        )

    associated_id = data.associated_commissiondar_id
    if associated_id is not None:
        contact = db.query(Party).filter(
            Party.id == associated_id,
            Party.business_id == current_user.business_id,
            Party.party_type == "commissiondar",
            Party.is_active == True,
        ).first()
        if not contact:
            raise HTTPException(
                status_code=404,
                detail="Commissiondar contact not found in this mill account",
            )

    try:
        farmer = Party(
            business_id=current_user.business_id,
            name=name,
            village=village,
            associated_commissiondar_id=associated_id,
            party_type="farmer",
            opening_balance=Decimal("0"),
            is_active=True,
        )

        db.add(farmer)
        db.commit()
        db.refresh(farmer)

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to create farmer",
        )

    return {
        "id": farmer.id,
        "name": farmer.name,
        "village": farmer.village,
        "associated_commissiondar_id": farmer.associated_commissiondar_id,
        "owed": 0.0,
    }


@router.put("/api/farmers/{farmer_id}")
def update_farmer(
    farmer_id: int,
    data: FarmerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    farmer = db.query(Party).filter(
        Party.id == farmer_id,
        Party.business_id == current_user.business_id,
        Party.party_type == "farmer",
        Party.is_active == True,
    ).first()
    if "associated_commissiondar_id" in data.model_fields_set:
        if data.associated_commissiondar_id is None:
            # Explicit null means remove the association.
            farmer.associated_commissiondar_id = None
        else:
            contact = db.query(Party).filter(
                Party.id == data.associated_commissiondar_id,
                Party.business_id == current_user.business_id,
                Party.party_type == "commissiondar",
                Party.is_active == True,
            ).first()

            if not contact:
                raise HTTPException(
                    status_code=404,
                    detail="Commissiondar contact not found in this mill account",
                )

            farmer.associated_commissiondar_id = contact.id
    if data.name is not None:
        farmer.name = data.name.strip()
    if data.village is not None:
        farmer.village = data.village.strip()
    commit_transaction(db, "Failed to update farmer")
    return {
        "id": farmer.id,
        "name": farmer.name,
        "village": farmer.village,
        "associated_commissiondar_id": farmer.associated_commissiondar_id,
    }
