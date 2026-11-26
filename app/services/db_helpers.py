from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.miller import Item
from app.models.party import Party


def get_active_farmer(
    db: Session,
    farmer_id: int,
    business_id: int,
):
    farmer = db.query(Party).filter(
        Party.id == farmer_id,
        Party.business_id == business_id,
        Party.party_type == "farmer",
        Party.is_active == True,
    ).first()

    if not farmer:
        raise HTTPException(
            status_code=404,
            detail="Farmer not found or inactive",
        )

    return farmer


def get_active_item(
    db: Session,
    item_id: int,
    business_id: int,
):
    item = db.query(Item).filter(
        Item.id == item_id,
        Item.business_id == business_id,
        Item.is_active == True,
    ).first()

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Item not found or inactive",
        )

    return item


def commit_transaction(db: Session, error_message: str):
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=error_message,
        )
