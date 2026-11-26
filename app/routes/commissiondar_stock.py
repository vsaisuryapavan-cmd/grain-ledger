from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_commissiondar
from app.models.commissiondar import CommissiondarStockMovement, GrainType
from app.models.core import User
from app.models.miller import Item
from app.models.party import Party
from app.schemas.commissiondar import (
    CommissiondarDeliver,
    CommissiondarReceive,
    GrainTypeCreate,
)
from app.services.db_helpers import commit_transaction, get_active_farmer

router = APIRouter()


@router.get("/api/commissiondar/grain-types")
def list_commissiondar_grain_types(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar),
):
    rows = db.query(GrainType).filter(
        GrainType.is_active == True,
        (
            (GrainType.owner_business_id == current_user.business_id)
            | (GrainType.owner_business_id.is_(None))
        ),
    ).order_by(GrainType.name.asc()).all()
    return [{"id": x.id, "name": x.name, "unit": x.unit} for x in rows]


@router.post("/api/commissiondar/grain-types", status_code=201)
def create_commissiondar_grain_type(
    data: GrainTypeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar),
):
    grain = GrainType(
        name=data.name.strip(),
        unit=data.unit.strip(),
        owner_business_id=current_user.business_id,
        created_by_user_id=current_user.id,
        is_active=True,
    )
    db.add(grain)
    commit_transaction(db, "Failed to create grain type")
    db.refresh(grain)
    return {"id": grain.id, "name": grain.name, "unit": grain.unit}


@router.post("/api/commissiondar-stock/receive")
def receive_from_farmer(
    data: CommissiondarReceive,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar),
):
    if (data.grain_type_id is None) == (data.item_id is None):
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of grain_type_id or item_id",
        )
    farmer = db.query(Party).filter(
        Party.id == data.farmer_id,
        Party.business_id == current_user.business_id,
        Party.party_type == "farmer",
        Party.is_active == True,
    ).first()
    if not farmer:
        raise HTTPException(
            status_code=404,
            detail="Farmer not found or inactive in this Commissiondar account",
        )

    grain_type = None
    if data.grain_type_id is not None:
        grain_type = db.query(GrainType).filter(
            GrainType.id == data.grain_type_id,
            GrainType.is_active == True,
            (GrainType.owner_business_id == current_user.business_id)
            | (GrainType.owner_business_id.is_(None)),
        ).first()
        if not grain_type:
            raise HTTPException(status_code=404, detail="Grain type not found")
    elif data.item_id is not None:
        item = db.query(Item).filter(
            Item.id == data.item_id,
            Item.business_id == current_user.business_id,
            Item.is_active == True,
        ).first()
        if not item:
            raise HTTPException(
                status_code=404,
                detail="Item not found in this Commissiondar account",
            )
    else:
        raise HTTPException(status_code=400, detail="Provide grain_type_id or item_id")

    movement = CommissiondarStockMovement(
        commissiondar_id=current_user.party_id,
        farmer_id=data.farmer_id,
        item_id=data.item_id,
        grain_type_id=data.grain_type_id,
        movement_type="received_from_farmer",
        quantity=data.quantity,
        rate=data.rate,
    )
    db.add(movement)
    commit_transaction(db, "Failed to record stock receipt")
    db.refresh(movement)
    return movement


@router.post("/api/commissiondar-stock/deliver")
def deliver_to_mill(
    data: CommissiondarDeliver,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar),
):
    # Exactly one grain identifier must be provided.
    if (data.grain_type_id is None) == (data.item_id is None):
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of grain_type_id or item_id",
        )

    # Validate farmer within this Commissiondar's own account.
    farmer = get_active_farmer(
        db,
        data.farmer_id,
        current_user.business_id,
    )

    mill_name = data.mill_name.strip()

    if not mill_name:
        raise HTTPException(
            status_code=400,
            detail="Mill name cannot be empty",
        )

    # Validate the selected grain.
    if data.grain_type_id is not None:
        grain = db.query(GrainType).filter(
            GrainType.id == data.grain_type_id,
            GrainType.is_active == True,
            GrainType.owner_business_id == current_user.business_id,
        ).first()

        if not grain:
            raise HTTPException(
                status_code=404,
                detail="Grain type not found in your account",
            )

        stock_filter = (
            CommissiondarStockMovement.grain_type_id == data.grain_type_id
        )

    else:
        item = db.query(Item).filter(
            Item.id == data.item_id,
            Item.business_id == current_user.business_id,
            Item.is_active == True,
        ).first()

        if not item:
            raise HTTPException(
                status_code=404,
                detail="Item not found in your account",
            )

        stock_filter = (
            CommissiondarStockMovement.item_id == data.item_id
        )

    # Calculate available stock for this exact grain.
    available_stock = db.query(
        func.coalesce(
            func.sum(CommissiondarStockMovement.quantity),
            0,
        )
    ).filter(
        CommissiondarStockMovement.commissiondar_id == current_user.party_id,
        CommissiondarStockMovement.is_void == False,
        stock_filter,
    ).scalar()

    available_stock = Decimal(str(available_stock or 0))
    delivery_quantity = Decimal(str(data.quantity))

    if delivery_quantity > available_stock:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Insufficient stock for this delivery",
                "available_stock": float(available_stock),
                "requested_quantity": float(delivery_quantity),
            },
        )

    # Save the delivery with both farmer and mill information.
    movement = CommissiondarStockMovement(
        commissiondar_id=current_user.party_id,
        farmer_id=farmer.id,
        mill_name=mill_name,
        item_id=data.item_id,
        grain_type_id=data.grain_type_id,
        movement_type="delivered_to_mill",
        quantity=-delivery_quantity,
        rate=data.rate,
    )

    db.add(movement)
    commit_transaction(
        db,
        "Failed to record stock delivery",
    )

    db.refresh(movement)

    return {
        "id": movement.id,
        "farmer_id": farmer.id,
        "farmer_name": farmer.name,
        "mill_name": movement.mill_name,
        "item_id": movement.item_id,
        "grain_type_id": movement.grain_type_id,
        "quantity": float(delivery_quantity),
        "rate": float(movement.rate) if movement.rate is not None else None,
        "movement_type": movement.movement_type,
        "message": "Stock delivered successfully",
    }


@router.get("/api/commissiondar-stock")
def my_stock(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar),
):
    # Base query: only this Commissiondar's stock movements.
    query = db.query(CommissiondarStockMovement).filter(
        CommissiondarStockMovement.commissiondar_id == current_user.party_id,
        CommissiondarStockMovement.is_void == False,
    )

    # Total stock received from farmers.
    received = db.query(
        func.coalesce(
            func.sum(CommissiondarStockMovement.quantity),
            0,
        )
    ).filter(
        CommissiondarStockMovement.commissiondar_id == current_user.party_id,
        CommissiondarStockMovement.movement_type == "received_from_farmer",
        CommissiondarStockMovement.is_void == False,
    ).scalar() or 0

    # Total stock delivered to mills.
    delivered = db.query(
        func.coalesce(
            func.sum(-CommissiondarStockMovement.quantity),
            0,
        )
    ).filter(
        CommissiondarStockMovement.commissiondar_id == current_user.party_id,
        CommissiondarStockMovement.movement_type == "delivered_to_mill",
        CommissiondarStockMovement.is_void == False,
    ).scalar() or 0

    # Stock history with farmer names.
    history_rows = (
        db.query(
            CommissiondarStockMovement,
            Party.name,
        )
        .outerjoin(
            Party,
            Party.id == CommissiondarStockMovement.farmer_id,
        )
        .filter(
            CommissiondarStockMovement.commissiondar_id == current_user.party_id,
            CommissiondarStockMovement.is_void == False,
        )
        .order_by(
            CommissiondarStockMovement.created_at.desc()
        )
        .all()
    )

    history = []

    for movement, farmer_name in history_rows:
        history.append({
            "id": movement.id,
            "farmer_id": movement.farmer_id,
            "farmer_name": farmer_name,
            "mill_name": movement.mill_name,
            "item_id": movement.item_id,
            "grain_type_id": movement.grain_type_id,
            "movement_type": movement.movement_type,
            "quantity": float(movement.quantity),
            "rate": (
                float(movement.rate)
                if movement.rate is not None
                else None
            ),
            "created_at": movement.created_at,
        })

    # Calculate available stock separately for each grain type/item.
    stock_groups = db.query(
        CommissiondarStockMovement.grain_type_id,
        CommissiondarStockMovement.item_id,
        func.sum(
            CommissiondarStockMovement.quantity
        ).label("available_quantity"),
    ).filter(
        CommissiondarStockMovement.commissiondar_id == current_user.party_id,
        CommissiondarStockMovement.is_void == False,
    ).group_by(
        CommissiondarStockMovement.grain_type_id,
        CommissiondarStockMovement.item_id,
    ).all()

    stock_by_type = []

    for group in stock_groups:
        grain = (
            db.query(GrainType)
            .filter(GrainType.id == group.grain_type_id)
            .first()
            if group.grain_type_id
            else None
        )

        item = (
            db.query(Item)
            .filter(Item.id == group.item_id)
            .first()
            if group.item_id
            else None
        )

        stock_by_type.append({
            "grain_type_id": group.grain_type_id,
            "item_id": group.item_id,
            "name": (
                grain.name
                if grain
                else (item.name if item else "Unknown")
            ),
            "unit": (
                grain.unit
                if grain
                else (item.unit if item else None)
            ),
            "available_quantity": float(
                group.available_quantity or 0
            ),
        })

    # Delivery summary grouped by mill name.
    by_mill = db.query(
        CommissiondarStockMovement.mill_name,
        func.sum(
            -CommissiondarStockMovement.quantity
        ).label("quantity_delivered"),
        func.count(
            CommissiondarStockMovement.id
        ).label("delivery_count"),
    ).filter(
        CommissiondarStockMovement.commissiondar_id == current_user.party_id,
        CommissiondarStockMovement.movement_type == "delivered_to_mill",
        CommissiondarStockMovement.is_void == False,
        CommissiondarStockMovement.mill_name.isnot(None),
    ).group_by(
        CommissiondarStockMovement.mill_name
    ).all()

    deliveries_by_mill = []

    for row in by_mill:
        deliveries_by_mill.append({
            "mill_name": row.mill_name,
            "quantity_delivered": float(
                row.quantity_delivered or 0
            ),
            "delivery_count": int(row.delivery_count),
        })

    return {
        "total_received": float(received),
        "total_delivered": float(delivered),
        "stock_on_hand": float(received - delivered),
        "stock_by_type": stock_by_type,
        "deliveries_by_mill": deliveries_by_mill,
        "history": history,
    }
