from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_commissiondar
from app.models.core import User
from app.models.party import Party
from app.schemas.commissiondar import CommissiondarFarmerCreate
from app.services.db_helpers import commit_transaction

router = APIRouter()


@router.get("/api/commissiondar/farmers")
def list_commissiondar_farmers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar),
):
    farmers = db.query(Party).filter(
        Party.business_id == current_user.business_id,
        Party.party_type == "farmer",
        Party.is_active == True,
    ).order_by(Party.name.asc()).all()
    return [
        {
            "id": f.id,
            "name": f.name,
            "phone": f.phone,
            "village": f.village,
        }
        for f in farmers
    ]


@router.post("/api/commissiondar/farmers", status_code=201)
def create_commissiondar_farmer(
    data: CommissiondarFarmerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar),
):
    farmer = Party(
        business_id=current_user.business_id,
        name=data.name.strip(),
        phone=data.phone,
        village=(data.village or None),
        party_type="farmer",
        opening_balance=Decimal("0"),
        is_active=True,
    )
    db.add(farmer)
    commit_transaction(db, "Failed to create Commissiondar farmer")
    db.refresh(farmer)
    return {
        "id": farmer.id,
        "name": farmer.name,
        "phone": farmer.phone,
        "village": farmer.village,
    }
