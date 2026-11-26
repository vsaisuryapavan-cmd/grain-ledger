from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_owner
from app.models.core import User
from app.models.miller import (
    BrokerCommission,
    Item,
    LedgerEntry,
    StockMovement,
)
from app.models.party import Party
from app.schemas.miller import (
    ExportCreate,
    IntakeCreate,
    ItemCreate,
    ItemUpdate,
)
from app.services.db_helpers import get_active_farmer, get_active_item

router = APIRouter()


@router.post("/api/intake")
def record_intake(
    data: IntakeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    get_active_item(
        db,
        data.item_id,
        current_user.business_id,
    )

    farmer = get_active_farmer(
        db,
        data.farmer_id,
        current_user.business_id,
    )
    if (
        farmer.associated_commissiondar_id is not None
        and data.broker_id is not None
        and data.broker_id != farmer.associated_commissiondar_id
    ):
        raise HTTPException(
            status_code=400,
            detail="This farmer is associated with a different Commissiondar",
        )
    selected_broker_id = data.broker_id or farmer.associated_commissiondar_id

    broker = None

    if selected_broker_id is not None:
        broker = db.query(Party).filter(
            Party.id == selected_broker_id,
            Party.business_id == current_user.business_id,
            Party.party_type == "commissiondar",
            Party.is_active == True,
        ).first()

        if not broker:
            raise HTTPException(
                status_code=404,
                detail="Commissiondar not found or inactive",
            )

        if data.commission_type is not None:
            if data.packet_count is None or data.commission_rate is None:
                raise HTTPException(
                    status_code=400,
                    detail="Packet count and commission rate are required",
                )
            if data.commission_type == "fixed":
                commission_per_packet = Decimal(str(data.commission_rate))
            else:
                if data.packet_price is None:
                    raise HTTPException(
                        status_code=400,
                        detail="Packet price is required for percentage commission",
                    )
                if data.commission_rate > 100:
                    raise HTTPException(
                        status_code=400,
                        detail="Commission percentage cannot exceed 100",
                    )
                commission_per_packet = (
                    Decimal(str(data.packet_price))
                    * Decimal(str(data.commission_rate))
                ) / Decimal("100")
            calculated_commission = commission_per_packet * Decimal(str(data.packet_count))
        else:
            if data.commission_amount is None:
                raise HTTPException(
                    status_code=400,
                    detail="Commission details are required when a Commissiondar is selected",
                )
            commission_per_packet = None
            calculated_commission = Decimal(str(data.commission_amount))
    elif any(
        value is not None
        for value in (
            data.commission_amount,
            data.packet_count,
            data.packet_price,
            data.commission_type,
            data.commission_rate,
        )
    ):
        raise HTTPException(
            status_code=400,
            detail="Select a Commissiondar before entering commission details",
        )
    else:
        commission_per_packet = None
        calculated_commission = None

    try:
        movement = StockMovement(
            business_id=current_user.business_id,
            item_id=data.item_id,
            party_id=data.farmer_id,
            movement_type="purchase",
            quantity=data.quantity,
            rate=data.rate,
            moisture_pct=data.moisture_pct,
            broker_id=(broker.id if broker else None),
            packet_count=data.packet_count,
            packet_price=data.packet_price,
            commission_type=data.commission_type,
            commission_rate=data.commission_rate,
            commission_per_packet=commission_per_packet,
            created_by=current_user.id,
        )

        db.add(movement)
        db.flush()

        ledger = LedgerEntry(
            business_id=current_user.business_id,
            party_id=data.farmer_id,
            debit=Decimal(str(data.quantity)) * Decimal(str(data.rate)),
            movement_id=movement.id,
        )

        db.add(ledger)

        commission = None

        if broker is not None:
            commission = BrokerCommission(
                business_id=current_user.business_id,
                commissiondar_id=broker.id,
                farmer_id=data.farmer_id,
                movement_id=movement.id,
                commission_amount=calculated_commission,
                packet_count=data.packet_count,
                packet_price=data.packet_price,
                commission_type=data.commission_type,
                commission_rate=data.commission_rate,
                commission_per_packet=commission_per_packet,
            )

            db.add(commission)

        db.commit()

        db.refresh(movement)
        db.refresh(ledger)

        if commission:
            db.refresh(commission)

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to record intake",
        )

    return {
        "stock_movement": movement,
        "ledger_entry": ledger,
        "broker_commission": commission,
    }


@router.post("/api/exports")
def record_export(
    data: ExportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    get_active_item(
        db,
        data.item_id,
        current_user.business_id,
    )

    buyer = db.query(Party).filter(
        Party.id == data.buyer_id,
        Party.business_id == current_user.business_id,
        Party.party_type.in_(["buyer", "customer"]),
        Party.is_active == True,
    ).first()

    if not buyer:
        raise HTTPException(
            status_code=404,
            detail="Buyer not found or inactive",
        )

    try:
        movement = StockMovement(
            business_id=current_user.business_id,
            item_id=data.item_id,
            party_id=data.buyer_id,
            movement_type="sale",
            quantity=-data.quantity,
            rate=data.rate,
            created_by=current_user.id,
        )

        db.add(movement)
        db.flush()

        ledger = LedgerEntry(
            business_id=current_user.business_id,
            party_id=data.buyer_id,
            debit=Decimal(str(data.quantity)) * Decimal(str(data.rate)),
            movement_id=movement.id,
        )

        db.add(ledger)
        db.commit()

        db.refresh(movement)
        db.refresh(ledger)

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to record export",
        )

    return {
        "stock_movement": movement,
        "ledger_entry": ledger,
    }


@router.get("/api/items")
def list_items(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    items = db.query(Item).filter(
        Item.business_id == current_user.business_id,
        Item.is_active == True,
    ).order_by(
        Item.name.asc()
    ).all()

    return {
        "items": [
            {
                "id": item.id,
                "name": item.name,
                "category": item.category,
                "unit": item.unit,
            }
            for item in items
        ]
    }


@router.post("/api/items", status_code=201)
def create_item(
    data: ItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    name = data.name.strip()
    unit = data.unit.strip()
    category = data.category.strip() if data.category else None

    if not name or not unit:
        raise HTTPException(
            status_code=400,
            detail="Grain variety name and unit cannot be empty",
        )

    existing_item = db.query(Item).filter(
        Item.business_id == current_user.business_id,
        func.lower(Item.name) == name.lower(),
    ).first()

    if existing_item:
        raise HTTPException(
            status_code=409,
            detail="This grain variety already exists",
        )

    item = Item(
        business_id=current_user.business_id,
        name=name,
        category=category,
        unit=unit,
        is_active=True,
    )

    db.add(item)

    try:
        db.commit()
        db.refresh(item)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This grain variety already exists",
        )

    return {
        "message": "Grain variety created successfully",
        "item": {
            "id": item.id,
            "name": item.name,
            "category": item.category,
            "unit": item.unit,
        },
    }


@router.put("/api/items/{item_id}")
def update_item(
    item_id: int,
    data: ItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    item = get_active_item(
        db,
        item_id,
        current_user.business_id,
    )

    updates = data.model_dump(exclude_unset=True)

    if not updates:
        raise HTTPException(
            status_code=400,
            detail="No fields provided for update",
        )

    if "name" in updates and updates["name"] is not None:
        updates["name"] = updates["name"].strip()

        if not updates["name"]:
            raise HTTPException(
                status_code=400,
                detail="Grain variety name cannot be empty",
            )

        existing_item = db.query(Item).filter(
            Item.business_id == current_user.business_id,
            func.lower(Item.name) == updates["name"].lower(),
            Item.id != item_id,
        ).first()

        if existing_item:
            raise HTTPException(
                status_code=409,
                detail="This grain variety already exists",
            )

    if "unit" in updates and updates["unit"] is not None:
        updates["unit"] = updates["unit"].strip()

        if not updates["unit"]:
            raise HTTPException(
                status_code=400,
                detail="Unit cannot be empty",
            )

    if "category" in updates and updates["category"] is not None:
        updates["category"] = updates["category"].strip() or None

    for field, value in updates.items():
        setattr(item, field, value)

    try:
        db.commit()
        db.refresh(item)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This grain variety already exists",
        )

    return {
        "message": "Grain variety updated successfully",
        "item": {
            "id": item.id,
            "name": item.name,
            "category": item.category,
            "unit": item.unit,
        },
    }


@router.patch("/api/items/{item_id}/deactivate")
def deactivate_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    item = get_active_item(
        db,
        item_id,
        current_user.business_id,
    )

    item.is_active = False
    db.commit()

    return {
        "message": "Grain variety deactivated successfully",
        "item_id": item.id,
        "name": item.name,
        "is_active": False,
    }


@router.get("/api/inventory")
def get_miller_inventory(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    # Get every grain variety owned by this Miller.
    # Inactive varieties remain visible for historical records.
    items = db.query(Item).filter(
        Item.business_id == current_user.business_id
    ).order_by(
        Item.name.asc()
    ).all()

    # Aggregate only this Miller's non-void stock movements.
    movement_rows = db.query(
        StockMovement.item_id,
        StockMovement.movement_type,
        func.sum(StockMovement.quantity),
    ).filter(
        StockMovement.business_id == current_user.business_id,
        StockMovement.is_void == False,
    ).group_by(
        StockMovement.item_id,
        StockMovement.movement_type,
    ).all()

    # Prepare totals for every item, including items with no movements.
    totals = {
        item.id: {
            "received_quantity": 0.0,
            "dispatched_quantity": 0.0,
            "available_quantity": 0.0,
        }
        for item in items
    }

    for item_id, movement_type, quantity in movement_rows:
        if item_id not in totals:
            continue

        quantity = float(quantity or 0)

        # Available stock includes the signed quantity of every
        # non-void movement type.
        totals[item_id]["available_quantity"] += quantity

        if movement_type == "purchase":
            totals[item_id]["received_quantity"] += quantity

        elif movement_type == "sale":
            totals[item_id]["dispatched_quantity"] += abs(quantity)

    return {
        "inventory": [
            {
                "item_id": item.id,
                "name": item.name,
                "category": item.category,
                "unit": item.unit,
                "is_active": item.is_active,
                "received_quantity": totals[item.id]["received_quantity"],
                "dispatched_quantity": totals[item.id]["dispatched_quantity"],
                "available_quantity": totals[item.id]["available_quantity"],
            }
            for item in items
        ]
    }


@router.get("/api/inventory/{item_id}/movements")
def get_miller_inventory_movements(
    item_id: int,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    if limit < 1 or limit > 500:
        raise HTTPException(
            status_code=400,
            detail="Limit must be between 1 and 500",
        )

    if offset < 0:
        raise HTTPException(
            status_code=400,
            detail="Offset cannot be negative",
        )

    # Verify that this grain variety belongs to the logged-in Miller.
    # Do not require is_active: inactive varieties still have history.
    item = db.query(Item).filter(
        Item.id == item_id,
        Item.business_id == current_user.business_id,
    ).first()

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Grain variety not found",
        )

    movement_query = db.query(StockMovement).filter(
        StockMovement.business_id == current_user.business_id,
        StockMovement.item_id == item_id,
    )

    total_count = movement_query.count()

    movements = movement_query.order_by(
        StockMovement.moved_at.desc(),
        StockMovement.id.desc(),
    ).offset(
        offset
    ).limit(
        limit
    ).all()

    return {
        "item": {
            "item_id": item.id,
            "name": item.name,
            "category": item.category,
            "unit": item.unit,
            "is_active": item.is_active,
        },
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "movements": [
            {
                "id": movement.id,
                "movement_type": movement.movement_type,
                "quantity": float(movement.quantity),
                "rate": (
                    float(movement.rate)
                    if movement.rate is not None
                    else None
                ),
                "party_id": movement.party_id,
                "broker_id": movement.broker_id,
                "moved_at": movement.moved_at,
                "note": movement.note,
                "is_void": movement.is_void,
            }
            for movement in movements
        ],
    }
