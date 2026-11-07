from datetime import datetime, timezone, timedelta
from decimal import Decimal
import secrets

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, Field

from database import get_db
from models import (
    Party,
    Item,
    StockMovement,
    LedgerEntry,
    Payment,
    User,
    CommissiondarLoan,
    CommissiondarLoanRepayment,
    MillCommissiondarLoan,
    MillCommissiondarLoanRepayment,
    BrokerCommission,
    CommissiondarStockMovement,
    LoginLog,
    IssueReport,
    Business,
    LoginChallenge,
)
from auth import (
    create_access_token,
    get_current_user,
    verify_password,
    create_otp_challenge,
    verify_otp,
    OTP_CHALLENGES,
    hash_password,
    verify_msg91_access_token,
)

app = FastAPI()

# ---------------------------------------------------------------
# CORS
# ---------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://rice-mill-ledger.onrender.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------
# Request models
# ---------------------------------------------------------------

class FarmerCreate(BaseModel):
    name: str
    village: str


class IntakeCreate(BaseModel):
    farmer_id: int
    item_id: int
    quantity: float = Field(gt=0)
    rate: float = Field(gt=0)
    moisture_pct: float | None = Field(default=None, ge=0, le=100)
    broker_id: int | None = None
    commission_amount: float | None = Field(default=None, gt=0)


class PaymentCreate(BaseModel):
    farmer_id: int
    amount: float = Field(gt=0)
    mode: str | None = None


class LoginRequest(BaseModel):
    phone: str
    password: str
    second_password: str


class OTPVerifyRequest(BaseModel):
    challenge_id: str
    access_token: str


class MillerRegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    phone: str = Field(min_length=10, max_length=20)
    business_name: str = Field(min_length=1, max_length=200)
    password: str
    second_password: str


class CommissiondarRegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    phone: str = Field(min_length=10, max_length=20)
    password: str
    second_password: str


class LoanCreate(BaseModel):
    farmer_id: int
    principal: float = Field(gt=0)
    interest_rate_pa: float = Field(default=0, ge=0)


class RepaymentCreate(BaseModel):
    loan_id: int
    amount: float = Field(gt=0)


class MillLoanCreate(BaseModel):
    commissiondar_id: int
    principal: float = Field(gt=0)
    interest_rate_pa: float = Field(default=0, ge=0)


class MillRepaymentCreate(BaseModel):
    loan_id: int
    amount: float = Field(gt=0)


class ExportCreate(BaseModel):
    buyer_id: int
    item_id: int
    quantity: float = Field(gt=0)
    rate: float = Field(gt=0)


class CommissionPay(BaseModel):
    commission_id: int


class CommissiondarReceive(BaseModel):
    farmer_id: int
    item_id: int
    quantity: float = Field(gt=0)
    rate: float | None = Field(default=None, gt=0)


class CommissiondarDeliver(BaseModel):
    business_id: int
    item_id: int
    quantity: float = Field(gt=0)
    rate: float = Field(gt=0)


class IssueReportCreate(BaseModel):
    description: str = Field(min_length=1)


# ---------------------------------------------------------------
# Common helpers
# ---------------------------------------------------------------

def farmer_balance(db: Session, farmer: Party, business_id: int):
    """
    Outstanding balance =
    opening balance + non-voided ledger debits - credits.
    """
    ledger_balance = db.query(
        func.coalesce(
            func.sum(LedgerEntry.debit - LedgerEntry.credit),
            0
        )
    ).filter(
        LedgerEntry.party_id == farmer.id,
        LedgerEntry.business_id == business_id,
        LedgerEntry.is_void == False
    ).scalar()

    return Decimal(str(farmer.opening_balance or 0)) + Decimal(
        str(ledger_balance or 0)
    )


def get_active_farmer(
    db: Session,
    farmer_id: int,
    business_id: int
):
    farmer = db.query(Party).filter(
        Party.id == farmer_id,
        Party.business_id == business_id,
        Party.party_type == "farmer",
        Party.is_active == True
    ).first()

    if not farmer:
        raise HTTPException(
            status_code=404,
            detail="Farmer not found or inactive"
        )

    return farmer


def get_active_item(
    db: Session,
    item_id: int,
    business_id: int
):
    item = db.query(Item).filter(
        Item.id == item_id,
        Item.business_id == business_id,
        Item.is_active == True
    ).first()

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Item not found or inactive"
        )

    return item


def commit_transaction(db: Session, error_message: str):
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=error_message
        )


# ---------------------------------------------------------------
# Authentication dependencies
# ---------------------------------------------------------------

def require_commissiondar(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> User:
    party = db.query(Party).filter(
        Party.id == current_user.party_id,
        Party.business_id == current_user.business_id,
        Party.party_type == "commissiondar",
        Party.is_active == True
    ).first()

    if not party:
        raise HTTPException(
            status_code=403,
            detail="Only active commissiondars can access this"
        )

    return current_user


def require_owner(
    current_user: User = Depends(get_current_user)
) -> User:
    if current_user.role != "owner":
        raise HTTPException(
            status_code=403,
            detail="Only the mill owner can do this"
        )

    return current_user


# ---------------------------------------------------------------
# Basic endpoint
# ---------------------------------------------------------------

@app.get("/")
def root():
    return {
        "message": "Grain Ledger API is running"
    }


# ---------------------------------------------------------------
# Registration
# ---------------------------------------------------------------

@app.post("/api/register/miller", status_code=201)
def register_miller(
    data: MillerRegisterRequest,
    db: Session = Depends(get_db)
):
    name = data.name.strip()
    phone = data.phone.strip()
    business_name = data.business_name.strip()

    if not name or not phone or not business_name:
        raise HTTPException(
            status_code=422,
            detail="Name, phone and business name are required"
        )

    if not data.password or not data.second_password:
        raise HTTPException(
            status_code=422,
            detail="Both passwords are required"
        )

    if db.query(User).filter(User.phone == phone).first():
        raise HTTPException(
            status_code=409,
            detail="Phone number is already registered"
        )

    try:
        business = Business(
            name=business_name,
            business_type="mill"
        )
        db.add(business)
        db.flush()

        user = User(
            business_id=business.id,
            name=name,
            phone=phone,
            role="owner",
            password_hash=hash_password(data.password),
            second_password_hash=hash_password(data.second_password),
            approval_status="pending"
        )
        db.add(user)
        db.commit()

        return {
            "message": "Miller registration submitted. Await Admin approval.",
            "approval_status": "pending"
        }

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Phone number is already registered"
        )

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Miller registration failed"
        )


@app.post("/api/register/commissiondar", status_code=201)
def register_commissiondar(
    data: CommissiondarRegisterRequest,
    db: Session = Depends(get_db)
):
    name = data.name.strip()
    phone = data.phone.strip()

    if not name or not phone:
        raise HTTPException(
            status_code=422,
            detail="Name and phone are required"
        )

    if not data.password or not data.second_password:
        raise HTTPException(
            status_code=422,
            detail="Both passwords are required"
        )

    if db.query(User).filter(User.phone == phone).first():
        raise HTTPException(
            status_code=409,
            detail="Phone number is already registered"
        )

    try:
        business = Business(
            name=f"{name} Commissiondar Account",
            business_type="commissiondar"
        )
        db.add(business)
        db.flush()

        party = Party(
            business_id=business.id,
            name=name,
            phone=phone,
            party_type="commissiondar",
            opening_balance=0,
            is_active=True
        )
        db.add(party)
        db.flush()

        user = User(
            business_id=business.id,
            name=name,
            phone=phone,
            role="party",
            party_id=party.id,
            password_hash=hash_password(data.password),
            second_password_hash=hash_password(data.second_password),
            approval_status="pending"
        )
        db.add(user)
        db.commit()

        return {
            "message": "Commissiondar registration submitted. Await Admin approval.",
            "approval_status": "pending"
        }

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Phone number is already registered"
        )

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Commissiondar registration failed"
        )


# ---------------------------------------------------------------
# Login
# ---------------------------------------------------------------

@app.post("/api/login")
def login(
    data: LoginRequest,
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(
        User.phone == data.phone
    ).first()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid phone number or password"
        )

    if not user.password_hash or not verify_password(
        data.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid phone number or password"
        )

    if not user.second_password_hash or not verify_password(
        data.second_password,
        user.second_password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid phone number or password"
        )

    if user.approval_status == "pending":
        raise HTTPException(
            status_code=403,
            detail="Your registration is pending Admin approval"
        )

    if user.approval_status == "rejected":
        raise HTTPException(
            status_code=403,
            detail="Your registration has been rejected"
        )

    if user.approval_status != "approved":
        raise HTTPException(
            status_code=403,
            detail="Your account cannot log in"
        )

    # Invalidate previous unused challenges for this user
    db.query(LoginChallenge).filter(
        LoginChallenge.user_id == user.id,
        LoginChallenge.used == False
    ).delete(synchronize_session=False)

    # Create a new persistent login challenge
    challenge_id = secrets.token_urlsafe(32)

    challenge = LoginChallenge(
        challenge_id=challenge_id,
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        used=False
    )

    try:
        db.add(challenge)
        db.commit()

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to create login challenge"
        )

    return {
        "message": "Passwords verified. MSG91 OTP required.",
        "challenge_id": challenge_id
    }


@app.post("/api/verify-otp")
def verify_login_otp(
    data: OTPVerifyRequest,
    db: Session = Depends(get_db)
):
    # 1. Find the login challenge
    challenge = db.query(LoginChallenge).filter(
        LoginChallenge.challenge_id == data.challenge_id
    ).first()

    if not challenge or challenge.used:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired login challenge"
        )

    now = datetime.now(timezone.utc)

    if challenge.expires_at <= now:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired login challenge"
        )

    # 2. Find the user
    user = db.query(User).filter(
        User.id == challenge.user_id
    ).first()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User account not found"
        )

    if user.approval_status != "approved":
        raise HTTPException(
            status_code=403,
            detail="Your account is not approved"
        )

    # 3. Verify MSG91 widget access token
    verified_identifier = verify_msg91_access_token(
        data.access_token
    )

    # 4. Normalize phone numbers
    verified_phone = "".join(
        character for character in verified_identifier
        if character.isdigit()
    )

    if len(verified_phone) == 12 and verified_phone.startswith("91"):
        verified_phone = verified_phone[2:]

    stored_phone = "".join(
        character for character in user.phone
        if character.isdigit()
    )

    if verified_phone != stored_phone:
        raise HTTPException(
            status_code=401,
            detail="Verified phone number does not match your account"
        )

    # 5. Atomically consume the challenge and record login
    try:
        result = db.query(LoginChallenge).filter(
            LoginChallenge.id == challenge.id,
            LoginChallenge.used.is_(False),
            LoginChallenge.expires_at > datetime.now(timezone.utc)
        ).update(
            {LoginChallenge.used: True},
            synchronize_session=False
        )

        if result != 1:
            db.rollback()
            raise HTTPException(
                status_code=401,
                detail="Invalid, expired, or already-used login challenge"
            )

        # Refresh account status before issuing token
        db.refresh(user)

        if user.approval_status != "approved":
            db.rollback()
            raise HTTPException(
                status_code=403,
                detail="Your account is not approved"
            )

        log = LoginLog(
            phone=user.phone,
            user_id=user.id,
            success=True
        )

        db.add(log)
        db.commit()

    except HTTPException:
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to record login"
        )

    # 6. Generate JWT access token
    token = create_access_token(user)

    return {
        "message": "Login successful",
        "access_token": token,
        "token_type": "bearer"
    }


# ---------------------------------------------------------------
# Intake
# ---------------------------------------------------------------

@app.post("/api/intake")
def record_intake(
    data: IntakeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    get_active_item(
        db,
        data.item_id,
        current_user.business_id
    )

    get_active_farmer(
        db,
        data.farmer_id,
        current_user.business_id
    )

    broker = None

    if data.broker_id is not None:
        broker = db.query(Party).filter(
            Party.id == data.broker_id,
            Party.business_id == current_user.business_id,
            Party.party_type == "commissiondar",
            Party.is_active == True
        ).first()

        if not broker:
            raise HTTPException(
                status_code=404,
                detail="Commissiondar not found or inactive"
            )

        if data.commission_amount is None:
            raise HTTPException(
                status_code=400,
                detail="Commission amount is required when a broker is selected"
            )

    elif data.commission_amount is not None:
        raise HTTPException(
            status_code=400,
            detail="Select a broker before entering commission amount"
        )

    try:
        movement = StockMovement(
            business_id=current_user.business_id,
            item_id=data.item_id,
            party_id=data.farmer_id,
            movement_type="purchase",
            quantity=data.quantity,
            rate=data.rate,
            moisture_pct=data.moisture_pct,
            broker_id=data.broker_id,
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
                commission_amount=data.commission_amount,
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
            detail="Failed to record intake"
        )

    return {
        "stock_movement": movement,
        "ledger_entry": ledger,
        "broker_commission": commission
    }


# ---------------------------------------------------------------
# Payments
# ---------------------------------------------------------------

@app.post("/api/payments")
def record_payment(
    data: PaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    get_active_farmer(
        db,
        data.farmer_id,
        current_user.business_id
    )

    mode = data.mode.strip().lower() if data.mode else None

    if mode == "":
        mode = None

    try:
        payment = Payment(
            business_id=current_user.business_id,
            party_id=data.farmer_id,
            direction="paid",
            amount=data.amount,
            mode=mode,
            created_by=current_user.id,
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

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to record payment"
        )

    return {
        "payment": payment,
        "ledger_entry": ledger
    }


# ---------------------------------------------------------------
# Exports
# ---------------------------------------------------------------

@app.post("/api/exports")
def record_export(
    data: ExportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner)
):
    get_active_item(
        db,
        data.item_id,
        current_user.business_id
    )

    buyer = db.query(Party).filter(
        Party.id == data.buyer_id,
        Party.business_id == current_user.business_id,
        Party.party_type.in_(["buyer", "customer"]),
        Party.is_active == True
    ).first()

    if not buyer:
        raise HTTPException(
            status_code=404,
            detail="Buyer not found or inactive"
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
            detail="Failed to record export"
        )

    return {
        "stock_movement": movement,
        "ledger_entry": ledger
    }


# ---------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------

@app.get("/api/dashboard")
def dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner)
):
    business_id = current_user.business_id

    total_stock = db.query(
        func.coalesce(
            func.sum(StockMovement.quantity),
            0
        )
    ).filter(
        StockMovement.business_id == business_id,
        StockMovement.is_void == False
    ).scalar()

    ledger_balance = db.query(
        func.coalesce(
            func.sum(LedgerEntry.debit - LedgerEntry.credit),
            0
        )
    ).filter(
        LedgerEntry.business_id == business_id,
        LedgerEntry.is_void == False
    ).scalar()

    opening_balances = db.query(
        func.coalesce(
            func.sum(Party.opening_balance),
            0
        )
    ).filter(
        Party.business_id == business_id,
        Party.is_active == True
    ).scalar()

    total_owed = Decimal(str(ledger_balance or 0)) + Decimal(
        str(opening_balances or 0)
    )

    today = datetime.now(timezone.utc).date()

    today_intake = db.query(
        func.coalesce(
            func.sum(StockMovement.quantity),
            0
        )
    ).filter(
        StockMovement.business_id == business_id,
        StockMovement.movement_type == "purchase",
        StockMovement.is_void == False,
        func.date(StockMovement.moved_at) == today
    ).scalar()

    return {
        "total_stock": total_stock,
        "total_owed": float(total_owed),
        "today_intake": today_intake,
    }


# ---------------------------------------------------------------
# Profit
# ---------------------------------------------------------------

@app.get("/api/profit")
def profit_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner)
):
    revenue = db.query(
        func.coalesce(
            func.sum(
                StockMovement.quantity * StockMovement.rate
            ),
            0
        )
    ).filter(
        StockMovement.business_id == current_user.business_id,
        StockMovement.movement_type == "sale",
        StockMovement.is_void == False
    ).scalar()

    cost = db.query(
        func.coalesce(
            func.sum(
                StockMovement.quantity * StockMovement.rate
            ),
            0
        )
    ).filter(
        StockMovement.business_id == current_user.business_id,
        StockMovement.movement_type == "purchase",
        StockMovement.is_void == False
    ).scalar()

    commissions_paid = db.query(
        func.coalesce(
            func.sum(BrokerCommission.commission_amount),
            0
        )
    ).filter(
        BrokerCommission.business_id == current_user.business_id,
        BrokerCommission.is_paid == True,
        BrokerCommission.is_void == False
    ).scalar()

    revenue = abs(float(revenue or 0))
    cost = float(cost or 0)
    commissions_paid = float(commissions_paid or 0)

    profit = revenue - cost - commissions_paid

    return {
        "revenue": round(revenue, 2),
        "cost_of_paddy": round(cost, 2),
        "commissions_paid": round(commissions_paid, 2),
        "profit": round(profit, 2),
    }


# ---------------------------------------------------------------
# Commissiondar loans
# ---------------------------------------------------------------

@app.post("/api/commissiondar-loans")
def create_loan(
    data: LoanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar)
):
    farmer = db.query(Party).filter(
        Party.id == data.farmer_id,
        Party.party_type == "farmer",
        Party.is_active == True
    ).first()

    if not farmer:
        raise HTTPException(
            status_code=404,
            detail="Farmer not found or inactive"
        )

    try:
        loan = CommissiondarLoan(
            commissiondar_id=current_user.party_id,
            farmer_id=data.farmer_id,
            principal=data.principal,
            interest_rate_pa=data.interest_rate_pa,
        )

        db.add(loan)
        db.commit()
        db.refresh(loan)

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to create loan"
        )

    return loan


@app.get("/api/commissiondar-loans")
def list_my_loans(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar)
):
    loans = db.query(CommissiondarLoan).filter(
        CommissiondarLoan.commissiondar_id == current_user.party_id,
        CommissiondarLoan.is_void == False
    ).all()

    result = []

    for loan in loans:
        days_elapsed = max(
            0,
            (datetime.now(timezone.utc).date() - loan.issued_at).days
        )

        interest = (
            float(loan.principal)
            * float(loan.interest_rate_pa)
            / 100
            * days_elapsed
            / 365
        )

        repaid = db.query(
            func.coalesce(
                func.sum(CommissiondarLoanRepayment.amount),
                0
            )
        ).filter(
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
            "outstanding": round(
                float(loan.principal) + interest - float(repaid or 0),
                2
            ),
            "status": loan.status,
        })

    return result


@app.post("/api/commissiondar-loans/repay")
def repay_loan(
    data: RepaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar)
):
    loan = db.query(CommissiondarLoan).filter(
        CommissiondarLoan.id == data.loan_id,
        CommissiondarLoan.commissiondar_id == current_user.party_id,
        CommissiondarLoan.is_void == False
    ).first()

    if not loan:
        raise HTTPException(
            status_code=404,
            detail="Loan not found"
        )

    try:
        repayment = CommissiondarLoanRepayment(
            loan_id=data.loan_id,
            amount=data.amount
        )

        db.add(repayment)
        db.commit()
        db.refresh(repayment)

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to record repayment"
        )

    return repayment


@app.get("/api/commissiondar-dashboard")
def commissiondar_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar)
):
    loans = db.query(CommissiondarLoan).filter(
        CommissiondarLoan.commissiondar_id == current_user.party_id,
        CommissiondarLoan.is_void == False
    ).all()

    total_lent = sum(
        float(loan.principal) for loan in loans
    )

    total_outstanding = 0

    for loan in loans:
        days_elapsed = max(
            0,
            (datetime.now(timezone.utc).date() - loan.issued_at).days
        )

        interest = (
            float(loan.principal)
            * float(loan.interest_rate_pa)
            / 100
            * days_elapsed
            / 365
        )

        repaid = db.query(
            func.coalesce(
                func.sum(CommissiondarLoanRepayment.amount),
                0
            )
        ).filter(
            CommissiondarLoanRepayment.loan_id == loan.id,
            CommissiondarLoanRepayment.is_void == False
        ).scalar()

        total_outstanding += (
            float(loan.principal)
            + interest
            - float(repaid or 0)
        )

    commissions_pending = db.query(
        func.coalesce(
            func.sum(BrokerCommission.commission_amount),
            0
        )
    ).filter(
        BrokerCommission.commissiondar_id == current_user.party_id,
        BrokerCommission.is_paid == False,
        BrokerCommission.is_void == False
    ).scalar()

    return {
        "active_loans": len(loans),
        "total_lent_out": round(total_lent, 2),
        "total_outstanding": round(total_outstanding, 2),
        "commissions_pending": commissions_pending,
    }


# ---------------------------------------------------------------
# Mill-to-commissiondar loans
# ---------------------------------------------------------------

@app.post("/api/mill-loans")
def create_mill_loan(
    data: MillLoanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner)
):
    commissiondar = db.query(Party).filter(
        Party.id == data.commissiondar_id,
        Party.business_id == current_user.business_id,
        Party.party_type == "commissiondar",
        Party.is_active == True
    ).first()

    if not commissiondar:
        raise HTTPException(
            status_code=404,
            detail="Commissiondar not found or inactive"
        )

    try:
        loan = MillCommissiondarLoan(
            business_id=current_user.business_id,
            commissiondar_id=data.commissiondar_id,
            principal=data.principal,
            interest_rate_pa=data.interest_rate_pa,
        )

        db.add(loan)
        db.commit()
        db.refresh(loan)

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to create mill loan"
        )

    return loan


@app.get("/api/mill-loans")
def list_mill_loans(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner)
):
    loans = db.query(MillCommissiondarLoan).filter(
        MillCommissiondarLoan.business_id == current_user.business_id,
        MillCommissiondarLoan.is_void == False
    ).all()

    result = []

    for loan in loans:
        days_elapsed = max(
            0,
            (datetime.now(timezone.utc).date() - loan.issued_at).days
        )

        interest = (
            float(loan.principal)
            * float(loan.interest_rate_pa)
            / 100
            * days_elapsed
            / 365
        )

        repaid = db.query(
            func.coalesce(
                func.sum(MillCommissiondarLoanRepayment.amount),
                0
            )
        ).filter(
            MillCommissiondarLoanRepayment.loan_id == loan.id,
            MillCommissiondarLoanRepayment.is_void == False
        ).scalar()

        result.append({
            "id": loan.id,
            "commissiondar_id": loan.commissiondar_id,
            "principal": loan.principal,
            "interest_rate_pa": loan.interest_rate_pa,
            "interest_accrued": round(interest, 2),
            "total_repaid": repaid,
            "outstanding": round(
                float(loan.principal) + interest - float(repaid or 0),
                2
            ),
            "status": loan.status,
        })

    return result


@app.post("/api/mill-loans/repay")
def repay_mill_loan(
    data: MillRepaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner)
):
    loan = db.query(MillCommissiondarLoan).filter(
        MillCommissiondarLoan.id == data.loan_id,
        MillCommissiondarLoan.business_id == current_user.business_id,
        MillCommissiondarLoan.is_void == False
    ).first()

    if not loan:
        raise HTTPException(
            status_code=404,
            detail="Loan not found"
        )

    try:
        repayment = MillCommissiondarLoanRepayment(
            loan_id=data.loan_id,
            amount=data.amount
        )

        db.add(repayment)
        db.commit()
        db.refresh(repayment)

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to record mill loan repayment"
        )

    return repayment


# ---------------------------------------------------------------
# Broker commissions
# ---------------------------------------------------------------

@app.get("/api/broker-commissions")
def list_commissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner)
):
    return db.query(BrokerCommission).filter(
        BrokerCommission.business_id == current_user.business_id,
        BrokerCommission.is_void == False
    ).all()


@app.post("/api/broker-commissions/pay")
def pay_commission(
    data: CommissionPay,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner)
):
    commission = db.query(BrokerCommission).filter(
        BrokerCommission.id == data.commission_id,
        BrokerCommission.business_id == current_user.business_id,
        BrokerCommission.is_void == False
    ).first()

    if not commission:
        raise HTTPException(
            status_code=404,
            detail="Commission not found"
        )

    if commission.is_paid:
        raise HTTPException(
            status_code=400,
            detail="Commission is already paid"
        )

    try:
        commission.is_paid = True
        db.commit()
        db.refresh(commission)

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to update commission payment"
        )

    return commission


# ---------------------------------------------------------------
# Commissiondar stock tracking
# ---------------------------------------------------------------

@app.post("/api/commissiondar-stock/receive")
def receive_from_farmer(
    data: CommissiondarReceive,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar)
):
    farmer = db.query(Party).filter(
        Party.id == data.farmer_id,
        Party.party_type == "farmer",
        Party.is_active == True
    ).first()

    if not farmer:
        raise HTTPException(
            status_code=404,
            detail="Farmer not found or inactive"
        )

    item = db.query(Item).filter(
        Item.id == data.item_id,
        Item.is_active == True
    ).first()

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Item not found or inactive"
        )

    try:
        movement = CommissiondarStockMovement(
            commissiondar_id=current_user.party_id,
            farmer_id=data.farmer_id,
            item_id=data.item_id,
            movement_type="received_from_farmer",
            quantity=data.quantity,
            rate=data.rate,
        )

        db.add(movement)
        db.commit()
        db.refresh(movement)

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to record stock receipt"
        )

    return movement


@app.post("/api/commissiondar-stock/deliver")
def deliver_to_mill(
    data: CommissiondarDeliver,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar)
):
    item = db.query(Item).filter(
        Item.id == data.item_id,
        Item.business_id == data.business_id,
        Item.is_active == True
    ).first()

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Item not found or inactive for this business"
        )

    try:
        movement = CommissiondarStockMovement(
            commissiondar_id=current_user.party_id,
            business_id=data.business_id,
            item_id=data.item_id,
            movement_type="delivered_to_mill",
            quantity=-data.quantity,
            rate=data.rate,
        )

        db.add(movement)
        db.commit()
        db.refresh(movement)

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to record stock delivery"
        )

    return movement


@app.get("/api/commissiondar-stock")
def my_stock(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar)
):
    on_hand = db.query(
        func.coalesce(
            func.sum(CommissiondarStockMovement.quantity),
            0
        )
    ).filter(
        CommissiondarStockMovement.commissiondar_id == current_user.party_id,
        CommissiondarStockMovement.is_void == False
    ).scalar()

    history = db.query(CommissiondarStockMovement).filter(
        CommissiondarStockMovement.commissiondar_id == current_user.party_id,
        CommissiondarStockMovement.is_void == False
    ).order_by(
        CommissiondarStockMovement.created_at.desc()
    ).all()

    return {
        "stock_on_hand": on_hand,
        "history": history
    }


# ---------------------------------------------------------------
# Issue reports
# ---------------------------------------------------------------

@app.post("/api/report-issue")
def report_issue(
    data: IssueReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        issue = IssueReport(
            user_id=current_user.id,
            description=data.description.strip()
        )

        if not issue.description:
            raise HTTPException(
                status_code=400,
                detail="Issue description cannot be empty"
            )

        db.add(issue)
        db.commit()
        db.refresh(issue)

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to submit issue report"
        )

    return issue


# ---------------------------------------------------------------
# Admin
# ---------------------------------------------------------------

def require_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin only"
        )

    return current_user


@app.get("/api/admin/dashboard-summary")
def admin_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    # User registration counts
    total_millers = (
        db.query(func.count(User.id))
        .filter(User.role == "owner")
        .scalar() or 0
    )

    total_commissiondars = (
        db.query(func.count(User.id))
        .filter(User.role == "party")
        .scalar() or 0
    )

    approved_registrations = (
        db.query(func.count(User.id))
        .filter(
            User.role.in_(["owner", "party"]),
            User.approval_status == "approved"
        )
        .scalar() or 0
    )

    pending_registrations = (
        db.query(func.count(User.id))
        .filter(
            User.role.in_(["owner", "party"]),
            User.approval_status == "pending"
        )
        .scalar() or 0
    )

    rejected_registrations = (
        db.query(func.count(User.id))
        .filter(
            User.role.in_(["owner", "party"]),
            User.approval_status == "rejected"
        )
        .scalar() or 0
    )

    # Business counts (exclude system businesses)
    total_businesses = (
        db.query(func.count(Business.id))
        .filter(
            Business.business_type.in_(["mill", "commissiondar"])
        )
        .scalar() or 0
    )

    # Login activity
    total_login_attempts = (
        db.query(func.count(LoginLog.id)).scalar() or 0
    )

    successful_logins = (
        db.query(func.count(LoginLog.id))
        .filter(LoginLog.success == True)
        .scalar() or 0
    )

    failed_logins = (
        db.query(func.count(LoginLog.id))
        .filter(LoginLog.success == False)
        .scalar() or 0
    )

    # Issue reports
    total_issues = (
        db.query(func.count(IssueReport.id)).scalar() or 0
    )

    open_issues = (
        db.query(func.count(IssueReport.id))
        .filter(IssueReport.status == "open")
        .scalar() or 0
    )

    return {
        "users": {
            "total_millers": total_millers,
            "total_commissiondars": total_commissiondars
        },
        "registrations": {
            "approved": approved_registrations,
            "pending": pending_registrations,
            "rejected": rejected_registrations
        },
        "businesses": {
            "total": total_businesses
        },
        "login_activity": {
            "total_attempts": total_login_attempts,
            "successful": successful_logins,
            "failed": failed_logins
        },
        "issues": {
            "total": total_issues,
            "open": open_issues
        }
    }


@app.get("/api/admin/login-logs")
def login_logs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    return db.query(LoginLog).order_by(
        LoginLog.created_at.desc()
    ).limit(100).all()


@app.get("/api/admin/issues")
def list_issues(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    return db.query(IssueReport).order_by(
        IssueReport.created_at.desc()
    ).all()


# ---------------------------------------------------------------
# Admin Registration Approval
# ---------------------------------------------------------------

@app.get("/api/admin/registrations/pending")
def list_pending_registrations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    registrations = (
        db.query(User, Business.name.label("business_name"))
        .join(Business, User.business_id == Business.id)
        .filter(
            User.approval_status == "pending",
            User.role.in_(["owner", "party"])
        )
        .order_by(User.created_at.asc())
        .all()
    )

    return [
        {
            "user_id": user.id,
            "name": user.name,
            "phone": user.phone,
            "role": user.role,
            "business_id": user.business_id,
            "business_name": business_name,
            "party_id": user.party_id,
            "approval_status": user.approval_status,
            "created_at": user.created_at
        }
        for user, business_name in registrations
    ]


def review_registration(
    user_id: int,
    decision: str,
    db: Session,
    current_user: User
):
    user = (
        db.query(User)
        .filter(User.id == user_id)
        .with_for_update()
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="Registration not found"
        )

    if user.role not in ["owner", "party"]:
        raise HTTPException(
            status_code=400,
            detail="This account cannot be reviewed as a registration"
        )

    if user.approval_status != "pending":
        raise HTTPException(
            status_code=409,
            detail="This registration has already been reviewed"
        )

    user.approval_status = decision
    user.reviewed_by = current_user.id
    user.reviewed_at = datetime.now(timezone.utc)

    db.commit()

    return {
        "message": f"Registration {decision} successfully",
        "user_id": user.id,
        "approval_status": user.approval_status,
        "reviewed_by": user.reviewed_by,
        "reviewed_at": user.reviewed_at
    }


@app.post("/api/admin/registrations/{user_id}/approve")
def approve_registration(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    return review_registration(
        user_id=user_id,
        decision="approved",
        db=db,
        current_user=current_user
    )


@app.post("/api/admin/registrations/{user_id}/reject")
def reject_registration(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    return review_registration(
        user_id=user_id,
        decision="rejected",
        db=db,
        current_user=current_user
    )


# ---------------------------------------------------------------
# Items
# ---------------------------------------------------------------

@app.get("/api/items")
def list_items(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner)
):
    items = db.query(Item).filter(
        Item.business_id == current_user.business_id,
        Item.is_active == True
    ).order_by(
        Item.name.asc()
    ).all()

    return {
        "items": [
            {
                "id": item.id,
                "name": item.name,
                "category": item.category,
                "unit": item.unit
            }
            for item in items
        ]
    }


# ---------------------------------------------------------------
# Farmers
# ---------------------------------------------------------------

@app.get("/api/farmers")
def list_farmers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner)
):
    farmers = db.query(Party).filter(
        Party.business_id == current_user.business_id,
        Party.party_type == "farmer",
        Party.is_active == True
    ).order_by(
        Party.name.asc()
    ).all()

    result = []

    for farmer in farmers:
        owed = farmer_balance(
            db,
            farmer,
            current_user.business_id
        )

        result.append({
            "id": farmer.id,
            "name": farmer.name,
            "owed": float(owed)
        })

    return result


# Create farmer
@app.post("/api/farmers")
def create_farmer(
    data: FarmerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner)
):
    name = data.name.strip()
    village = data.village.strip()

    if not name or not village:
        raise HTTPException(
            status_code=400,
            detail="Farmer name and village cannot be empty"
        )

    try:
        farmer = Party(
            business_id=current_user.business_id,
            name=name,
            village=village,
            party_type="farmer",
            opening_balance=Decimal("0"),
            is_active=True
        )

        db.add(farmer)
        db.commit()
        db.refresh(farmer)

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to create farmer"
        )

    return {
        "id": farmer.id,
        "name": farmer.name,
        "village": farmer.village,
        "owed": 0.0
    }