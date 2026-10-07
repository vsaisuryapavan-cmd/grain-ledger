from sqlalchemy import func
from models import Party, StockMovement, LedgerEntry
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from models import Party, StockMovement, LedgerEntry, Payment   
from datetime import datetime, timezone

from database import get_db, engine, Base
from models import Party, StockMovement, LedgerEntry

Base.metadata.create_all(bind=engine)

app = FastAPI()

class FarmerCreate(BaseModel):
    name: str
    village: str
    business_id: int = 1

class IntakeCreate(BaseModel):
    business_id: int = 1
    farmer_id: int
    item_id: int
    quantity: float
    rate: float
    moisture_pct: float | None = None

@app.get("/")
def root():
    return {"message": "Grain Ledger API is running"}

@app.get("/api/farmers")
def list_farmers(db: Session = Depends(get_db)):
    farmers = db.query(Party).filter(Party.party_type == "farmer").all()
    result = []
    for farmer in farmers:
        stock = db.query(func.coalesce(func.sum(StockMovement.quantity), 0)).filter(
            StockMovement.party_id == farmer.id,
            StockMovement.is_void == False
        ).scalar()

        balance = db.query(
            func.coalesce(func.sum(LedgerEntry.debit - LedgerEntry.credit), 0)
        ).filter(
            LedgerEntry.party_id == farmer.id,
            LedgerEntry.is_void == False
        ).scalar()

        result.append({
            "id": farmer.id,
            "name": farmer.name,
            "village": farmer.village,
            "stock": stock,
            "owed": balance + farmer.opening_balance,
        })
    return result

@app.post("/api/farmers")
def add_farmer(farmer: FarmerCreate, db: Session = Depends(get_db)):
    new_farmer = Party(
        business_id=farmer.business_id,
        name=farmer.name,
        village=farmer.village,
        party_type="farmer",
    )
    db.add(new_farmer)
    db.commit()
    db.refresh(new_farmer)
    return new_farmer

@app.post("/api/intake")
def record_intake(data: IntakeCreate, db: Session = Depends(get_db)):
    movement = StockMovement(
        business_id=data.business_id,
        item_id=data.item_id,
        party_id=data.farmer_id,
        movement_type="purchase",
        quantity=data.quantity,
        rate=data.rate,
        moisture_pct=data.moisture_pct,
    )
    db.add(movement)
    db.flush()  # saves movement so movement.id is available, without fully committing yet

    ledger = LedgerEntry(
        business_id=data.business_id,
        party_id=data.farmer_id,
        debit=data.quantity * data.rate,
        movement_id=movement.id,
    )
    db.add(ledger)
    db.commit()
    db.refresh(movement)
    db.refresh(ledger)

    return {"stock_movement": movement, "ledger_entry": ledger}
class PaymentCreate(BaseModel):
    business_id: int = 1
    farmer_id: int
    amount: float
    mode: str | None = None   # optional, matches your schema decision

@app.post("/api/payments")
def record_payment(data: PaymentCreate, db: Session = Depends(get_db)):
    mode = data.mode.lower() if data.mode else None   # normalize to lowercase

    payment = Payment(
        business_id=data.business_id,
        party_id=data.farmer_id,
        direction="paid",
        amount=data.amount,
        mode=mode,
    )
    db.add(payment)
    db.flush()

    ledger = LedgerEntry(
        business_id=data.business_id,
        party_id=data.farmer_id,
        credit=data.amount,
        payment_id=payment.id,
    )
    db.add(ledger)
    db.commit()
    db.refresh(payment)
    db.refresh(ledger)

    return {"payment": payment, "ledger_entry": ledger}

@app.get("/api/dashboard")
def dashboard(business_id: int = 1, db: Session = Depends(get_db)):
    total_stock = db.query(func.coalesce(func.sum(StockMovement.quantity), 0)).filter(
        StockMovement.business_id == business_id,
        StockMovement.is_void == False
    ).scalar()

    total_owed = db.query(func.coalesce(func.sum(LedgerEntry.debit - LedgerEntry.credit), 0)).filter(
        LedgerEntry.business_id == business_id,
        LedgerEntry.is_void == False
    ).scalar()

    today = datetime.now(timezone.utc).date()
    today_intake = db.query(func.coalesce(func.sum(StockMovement.quantity), 0)).filter(
        StockMovement.business_id == business_id,
        StockMovement.movement_type == "purchase",
        StockMovement.is_void == False,
        func.date(StockMovement.moved_at) == today
    ).scalar()

    return {
        "total_stock": total_stock,
        "total_owed": total_owed,
        "today_intake": today_intake,
    }