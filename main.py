from datetime import datetime, timezone

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from database import get_db, engine, Base
from models import Party, StockMovement, LedgerEntry, Payment, User, CommissiondarLoan, CommissiondarLoanRepayment
from auth import create_access_token, get_current_user

Base.metadata.create_all(bind=engine)

app = FastAPI()


# ---------------------------------------------------------------
# Request/response models (all BaseModel classes together)
# ---------------------------------------------------------------

class FarmerCreate(BaseModel):
    name: str
    village: str
    business_id: int = 1


class IntakeCreate(BaseModel):
    farmer_id: int
    item_id: int
    quantity: float
    rate: float
    moisture_pct: float | None = None


class PaymentCreate(BaseModel):
    farmer_id: int
    amount: float
    mode: str | None = None   # optional, matches your schema decision


class LoginRequest(BaseModel):
    phone: str


class LoanCreate(BaseModel):
    farmer_id: int
    principal: float
    interest_rate_pa: float = 0


class RepaymentCreate(BaseModel):
    loan_id: int
    amount: float


# ---------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------

def require_commissiondar(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    party = db.query(Party).filter(Party.id == current_user.party_id).first()
    if not party or party.party_type != "commissiondar":
        raise HTTPException(status_code=403, detail="Only commissiondars can access this")
    return current_user


# ---------------------------------------------------------------
# Basic + auth endpoints
# ---------------------------------------------------------------

@app.get("/")
def root():
    return {"message": "Grain Ledger API is running"}


@app.post("/api/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.phone == data.phone).first()
    if not user:
        raise HTTPException(status_code=404, detail="No account found with this phone number")

    token = create_access_token(user)
    return {"access_token": token, "token_type": "bearer"}


# ---------------------------------------------------------------
# Farmers
# ---------------------------------------------------------------

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


# ---------------------------------------------------------------
# Intake
# ---------------------------------------------------------------

@app.post("/api/intake")
def record_intake(data: IntakeCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    movement = StockMovement(
        business_id=current_user.business_id,
        item_id=data.item_id,
        party_id=data.farmer_id,
        movement_type="purchase",
        quantity=data.quantity,
        rate=data.rate,
        moisture_pct=data.moisture_pct,
    )
    db.add(movement)
    db.flush()

    ledger = LedgerEntry(
        business_id=current_user.business_id,
        party_id=data.farmer_id,
        debit=data.quantity * data.rate,
        movement_id=movement.id,
    )
    db.add(ledger)
    db.commit()
    db.refresh(movement)
    db.refresh(ledger)

    return {"stock_movement": movement, "ledger_entry": ledger}


# ---------------------------------------------------------------
# Payments
# ---------------------------------------------------------------

@app.post("/api/payments")
def record_payment(data: PaymentCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    mode = data.mode.lower() if data.mode else None

    payment = Payment(
        business_id=current_user.business_id,
        party_id=data.farmer_id,
        direction="paid",
        amount=data.amount,
        mode=mode,
    )
    db.add(payment)
    db.flush()

    ledger = LedgerEntry(
        business_id=current_user.business_id,
        party_id=data.farmer_id,
        credit=data.amount,
        payment_id=payment.id,
    )
    db.add(ledger)
    db.commit()
    db.refresh(payment)
    db.refresh(ledger)

    return {"payment": payment, "ledger_entry": ledger}


# ---------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------

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


# ---------------------------------------------------------------
# Commissiondar loans (farmer side, private, never business_id)
# ---------------------------------------------------------------

@app.post("/api/commissiondar-loans")
def create_loan(data: LoanCreate, db: Session = Depends(get_db), current_user: User = Depends(require_commissiondar)):
    loan = CommissiondarLoan(
        commissiondar_id=current_user.party_id,
        farmer_id=data.farmer_id,
        principal=data.principal,
        interest_rate_pa=data.interest_rate_pa,
    )
    db.add(loan)
    db.commit()
    db.refresh(loan)
    return loan


@app.get("/api/commissiondar-loans")
def list_my_loans(db: Session = Depends(get_db), current_user: User = Depends(require_commissiondar)):
    loans = db.query(CommissiondarLoan).filter(
        CommissiondarLoan.commissiondar_id == current_user.party_id,
        CommissiondarLoan.is_void == False
    ).all()

    result = []
    for loan in loans:
        days_elapsed = (datetime.now(timezone.utc).date() - loan.issued_at.date()).days
        interest = float(loan.principal) * float(loan.interest_rate_pa) / 100 * days_elapsed / 365

        repaid = db.query(func.coalesce(func.sum(CommissiondarLoanRepayment.amount), 0)).filter(
            CommissiondarLoanRepayment.loan_id == loan.id,
            CommissiondarLoanRepayment.is_void == False
        ).scalar()

        result.append({
            "id": loan.id,
            "farmer_id": loan.farmer_id,
            "principal": loan.principal,
            "interest_rate_pa": loan.interest_rate_pa,
            "interest_accrued": round(interest, 2),
            "total_repaid": repaid,
            "outstanding": round(float(loan.principal) + interest - float(repaid), 2),
            "status": loan.status,
        })
    return result


@app.post("/api/commissiondar-loans/repay")
def repay_loan(data: RepaymentCreate, db: Session = Depends(get_db), current_user: User = Depends(require_commissiondar)):
    loan = db.query(CommissiondarLoan).filter(
        CommissiondarLoan.id == data.loan_id,
        CommissiondarLoan.commissiondar_id == current_user.party_id
    ).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    repayment = CommissiondarLoanRepayment(loan_id=data.loan_id, amount=data.amount)
    db.add(repayment)
    db.commit()
    db.refresh(repayment)
    return repayment