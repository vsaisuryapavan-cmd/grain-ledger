from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db, engine, Base
from models import Party

# Creates any tables that don't already exist (safe to run even if they do)
Base.metadata.create_all(bind=engine)

app = FastAPI()

class FarmerCreate(BaseModel):
    name: str
    village: str
    business_id: int = 1   # temporary: assumes one mill for now

@app.get("/")
def root():
    return {"message": "Grain Ledger API is running"}

@app.get("/api/farmers")
def list_farmers(db: Session = Depends(get_db)):
    return db.query(Party).filter(Party.party_type == "farmer").all()

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