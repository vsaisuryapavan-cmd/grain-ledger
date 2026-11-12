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
    GrainType,
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
    "http://localhost:5173",
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
    name: str = Field(min_length=1, max_length=150)
    village: str = Field(min_length=1, max_length=150)
    associated_commissiondar_id: int | None = None


class FarmerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    village: str | None = Field(default=None, min_length=1, max_length=150)
    associated_commissiondar_id: int | None = None


class CommissiondarContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    phone: str | None = Field(default=None, max_length=20)
    village: str | None = Field(default=None, max_length=150)


class CommissiondarContactUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    phone: str | None = Field(default=None, max_length=20)
    village: str | None = Field(default=None, max_length=150)
    is_active: bool | None = None


class CommissiondarFarmerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    village: str | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, max_length=20)


class GrainTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    unit: str = Field(default="quintal", min_length=1, max_length=30)


class IntakeCreate(BaseModel):
    farmer_id: int
    item_id: int
    quantity: float = Field(gt=0)
    rate: float = Field(gt=0)
    moisture_pct: float | None = Field(default=None, ge=0, le=100)
    broker_id: int | None = None
    # Legacy total commission remains supported for old clients.
    commission_amount: float | None = Field(default=None, ge=0)
    packet_count: int | None = Field(default=None, gt=0)
    packet_price: float | None = Field(default=None, gt=0)
    commission_type: str | None = Field(default=None, pattern="^(fixed|percentage)$")
    commission_rate: float | None = Field(default=None, ge=0)


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
    item_id: int | None = None
    grain_type_id: int | None = None
    quantity: float = Field(gt=0)
    rate: float | None = Field(default=None, gt=0)


class CommissiondarDeliver(BaseModel):
    mill_name: str = Field(min_length=1, max_length=200)
    item_id: int | None = None
    grain_type_id: int | None = None
    quantity: float = Field(gt=0)
    rate: float | None = Field(default=None, gt=0)


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
    current_user: User = Depends(require_owner)
):
    get_active_item(
        db,
        data.item_id,
        current_user.business_id
    )

    farmer = get_active_farmer(
        db,
        data.farmer_id,
        current_user.business_id
    )
    if farmer.associated_commissiondar_id is not None and data.broker_id is not None and data.broker_id != farmer.associated_commissiondar_id:
        raise HTTPException(status_code=400, detail="This farmer is associated with a different Commissiondar")
    selected_broker_id = data.broker_id or farmer.associated_commissiondar_id

    broker = None

    if selected_broker_id is not None:
        broker = db.query(Party).filter(
            Party.id == selected_broker_id,
            Party.business_id == current_user.business_id,
            Party.party_type == "commissiondar",
            Party.is_active == True
        ).first()

        if not broker:
            raise HTTPException(
                status_code=404,
                detail="Commissiondar not found or inactive"
            )

        if data.commission_type is not None:
            if data.packet_count is None or data.commission_rate is None:
                raise HTTPException(status_code=400, detail="Packet count and commission rate are required")
            if data.commission_type == "fixed":
                commission_per_packet = Decimal(str(data.commission_rate))
            else:
                if data.packet_price is None:
                    raise HTTPException(status_code=400, detail="Packet price is required for percentage commission")
                if data.commission_rate > 100:
                    raise HTTPException(status_code=400, detail="Commission percentage cannot exceed 100")
                commission_per_packet = (Decimal(str(data.packet_price)) * Decimal(str(data.commission_rate))) / Decimal("100")
            calculated_commission = commission_per_packet * Decimal(str(data.packet_count))
        else:
            if data.commission_amount is None:
                raise HTTPException(status_code=400, detail="Commission details are required when a Commissiondar is selected")
            commission_per_packet = None
            calculated_commission = Decimal(str(data.commission_amount))
    elif any(value is not None for value in (data.commission_amount, data.packet_count, data.packet_price, data.commission_type, data.commission_rate)):
        raise HTTPException(status_code=400, detail="Select a Commissiondar before entering commission details")
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
    current_user: User = Depends(require_owner)
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

    seven_days_ago = today - timedelta(days=6)
    last_seven_days_intake = db.query(func.coalesce(func.sum(StockMovement.quantity), 0)).filter(
        StockMovement.business_id == business_id,
        StockMovement.movement_type == "purchase",
        StockMovement.is_void == False,
        func.date(StockMovement.moved_at) >= seven_days_ago,
        func.date(StockMovement.moved_at) <= today
    ).scalar() or 0
    total_farmers = db.query(func.count(Party.id)).filter(Party.business_id == business_id, Party.party_type == "farmer", Party.is_active == True).scalar() or 0
    last_seven_days_records = db.query(StockMovement).filter(
        StockMovement.business_id == business_id,
        StockMovement.movement_type == "purchase",
        StockMovement.is_void == False,
        func.date(StockMovement.moved_at) >= seven_days_ago,
        func.date(StockMovement.moved_at) <= today
    ).order_by(StockMovement.moved_at.desc()).all()
    return {
        "total_stock": total_stock,
        "total_owed": float(total_owed),
        "today_intake": today_intake,
        "total_farmers": int(total_farmers),
        "last_seven_days_intake": float(last_seven_days_intake),
        "last_seven_days_records": last_seven_days_records,
        "total_commissiondars": db.query(func.count(Party.id)).filter(Party.business_id == business_id, Party.party_type == "commissiondar", Party.is_active == True).scalar() or 0,
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
        Party.business_id == current_user.business_id,
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

        farmer = db.query(Party).filter(Party.id == loan.farmer_id, Party.business_id == current_user.business_id, Party.party_type == "farmer").first()
        result.append({
            "id": loan.id,
            "farmer_id": loan.farmer_id,
            "farmer_name": farmer.name if farmer else None,
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

    # Miller-side commission records are intentionally not read here. The two
    # business accounts are independent; pending commission is zero until the
    # Commissiondar records its own commission receivables in its own account.
    commissions_pending = 0.0
    farmer_count = db.query(func.count(Party.id)).filter(
        Party.business_id == current_user.business_id,
        Party.party_type == "farmer",
        Party.is_active == True
    ).scalar() or 0
    latest_loan = db.query(CommissiondarLoan).filter(
        CommissiondarLoan.commissiondar_id == current_user.party_id,
        CommissiondarLoan.is_void == False
    ).order_by(CommissiondarLoan.issued_at.desc(), CommissiondarLoan.id.desc()).first()


    return {
        "active_loans": len(loans),
        "total_lent_out": round(total_lent, 2),
        "total_outstanding": round(total_outstanding, 2),
        "commissions_pending": commissions_pending,
        "total_farmers": farmer_count,
        "latest_loan": ({"id": latest_loan.id, "farmer_id": latest_loan.farmer_id, "principal": float(latest_loan.principal), "issued_at": str(latest_loan.issued_at)} if latest_loan else None),
        "latest_commission": None,
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
    if (data.grain_type_id is None) == (data.item_id is None):
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of grain_type_id or item_id"
        )
    farmer = db.query(Party).filter(
        Party.id == data.farmer_id,
        Party.business_id == current_user.business_id,
        Party.party_type == "farmer",
        Party.is_active == True
    ).first()
    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer not found or inactive in this Commissiondar account")

    grain_type = None
    if data.grain_type_id is not None:
        grain_type = db.query(GrainType).filter(
            GrainType.id == data.grain_type_id,
            GrainType.is_active == True,
            (GrainType.owner_business_id == current_user.business_id) | (GrainType.owner_business_id.is_(None))
        ).first()
        if not grain_type:
            raise HTTPException(status_code=404, detail="Grain type not found")
    elif data.item_id is not None:
        item = db.query(Item).filter(
            Item.id == data.item_id,
            Item.business_id == current_user.business_id,
            Item.is_active == True
        ).first()
        if not item:
            raise HTTPException(status_code=404, detail="Item not found in this Commissiondar account")
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


@app.post("/api/commissiondar-stock/deliver")
def deliver_to_mill(
    data: CommissiondarDeliver,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar)
):
    if (data.grain_type_id is None) == (data.item_id is None):
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of grain_type_id or item_id"
        )
    mill_name = data.mill_name.strip()
    if not mill_name:
        raise HTTPException(status_code=400, detail="Mill name cannot be empty")
    if data.grain_type_id is not None:
        grain_type = db.query(GrainType).filter(
            GrainType.id == data.grain_type_id,
            GrainType.is_active == True,
            (GrainType.owner_business_id == current_user.business_id) | (GrainType.owner_business_id.is_(None))
        ).first()
        if not grain_type:
            raise HTTPException(status_code=404, detail="Grain type not found")
    elif data.item_id is not None:
        item = db.query(Item).filter(
            Item.id == data.item_id,
            Item.business_id == current_user.business_id,
            Item.is_active == True
        ).first()
        if not item:
            raise HTTPException(status_code=404, detail="Item not found in this Commissiondar account")
    else:
        raise HTTPException(status_code=400, detail="Provide grain_type_id or item_id")

    movement = CommissiondarStockMovement(
        commissiondar_id=current_user.party_id,
        mill_name=mill_name,
        item_id=data.item_id,
        grain_type_id=data.grain_type_id,
        movement_type="delivered_to_mill",
        quantity=-Decimal(str(data.quantity)),
        rate=data.rate,
    )
    db.add(movement)
    commit_transaction(db, "Failed to record stock delivery")
    db.refresh(movement)
    return movement


@app.get("/api/commissiondar-stock")
def my_stock(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar)
):
    query = db.query(CommissiondarStockMovement).filter(
        CommissiondarStockMovement.commissiondar_id == current_user.party_id,
        CommissiondarStockMovement.is_void == False
    )
    received = db.query(func.coalesce(func.sum(CommissiondarStockMovement.quantity), 0)).filter(
        CommissiondarStockMovement.commissiondar_id == current_user.party_id,
        CommissiondarStockMovement.movement_type == "received_from_farmer",
        CommissiondarStockMovement.is_void == False
    ).scalar() or 0
    delivered = db.query(func.coalesce(func.sum(-CommissiondarStockMovement.quantity), 0)).filter(
        CommissiondarStockMovement.commissiondar_id == current_user.party_id,
        CommissiondarStockMovement.movement_type == "delivered_to_mill",
        CommissiondarStockMovement.is_void == False
    ).scalar() or 0
    history = query.order_by(CommissiondarStockMovement.created_at.desc()).all()
    stock_groups = db.query(
        CommissiondarStockMovement.grain_type_id,
        CommissiondarStockMovement.item_id,
        func.sum(CommissiondarStockMovement.quantity).label("available_quantity")
    ).filter(
        CommissiondarStockMovement.commissiondar_id == current_user.party_id,
        CommissiondarStockMovement.is_void == False
    ).group_by(CommissiondarStockMovement.grain_type_id, CommissiondarStockMovement.item_id).all()
    stock_by_type = []
    for group in stock_groups:
        grain = db.query(GrainType).filter(GrainType.id == group.grain_type_id).first() if group.grain_type_id else None
        item = db.query(Item).filter(Item.id == group.item_id).first() if group.item_id else None
        stock_by_type.append({"grain_type_id": group.grain_type_id, "item_id": group.item_id, "name": grain.name if grain else (item.name if item else "Unknown"), "unit": grain.unit if grain else (item.unit if item else None), "available_quantity": float(group.available_quantity or 0)})
    by_mill = db.query(
        CommissiondarStockMovement.mill_name,
        func.sum(-CommissiondarStockMovement.quantity).label("quantity_delivered"),
        func.count(CommissiondarStockMovement.id).label("delivery_count")
    ).filter(
        CommissiondarStockMovement.commissiondar_id == current_user.party_id,
        CommissiondarStockMovement.movement_type == "delivered_to_mill",
        CommissiondarStockMovement.is_void == False,
        CommissiondarStockMovement.mill_name.isnot(None)
    ).group_by(CommissiondarStockMovement.mill_name).all()
    return {
        "total_received": float(received),
        "total_delivered": float(delivered),
        "stock_on_hand": float(received - delivered),
        "stock_by_type": stock_by_type,
        "deliveries_by_mill": [{"mill_name": row.mill_name, "quantity_delivered": float(row.quantity_delivered or 0), "delivery_count": int(row.delivery_count)} for row in by_mill],
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
# Miller-owned Commissiondar contacts (not login accounts)
# ---------------------------------------------------------------

@app.post("/api/miller/commissiondars", status_code=201)
def create_miller_commissiondar_contact(data: CommissiondarContactCreate, db: Session = Depends(get_db), current_user: User = Depends(require_owner)):
    contact = Party(business_id=current_user.business_id, name=data.name.strip(), phone=(data.phone or None), village=(data.village or None), party_type="commissiondar", opening_balance=Decimal("0"), is_active=True)
    db.add(contact)
    commit_transaction(db, "Failed to create Commissiondar contact")
    db.refresh(contact)
    return {"id": contact.id, "name": contact.name, "phone": contact.phone, "village": contact.village}


@app.get("/api/miller/commissiondars")
def list_miller_commissiondar_contacts(db: Session = Depends(get_db), current_user: User = Depends(require_owner)):
    contacts = db.query(Party).filter(Party.business_id == current_user.business_id, Party.party_type == "commissiondar").order_by(Party.name.asc()).all()
    result = []
    for contact in contacts:
        movements = db.query(StockMovement).filter(StockMovement.business_id == current_user.business_id, StockMovement.broker_id == contact.id, StockMovement.movement_type == "purchase", StockMovement.is_void == False).all()
        commissions = db.query(func.coalesce(func.sum(BrokerCommission.commission_amount), 0)).filter(BrokerCommission.business_id == current_user.business_id, BrokerCommission.commissiondar_id == contact.id, BrokerCommission.is_void == False).scalar() or 0
        loans = db.query(MillCommissiondarLoan).filter(MillCommissiondarLoan.business_id == current_user.business_id, MillCommissiondarLoan.commissiondar_id == contact.id, MillCommissiondarLoan.is_void == False).all()
        loan_principal = sum((Decimal(str(x.principal)) for x in loans), Decimal("0"))
        loan_repaid = Decimal("0")
        for loan in loans:
            loan_repaid += Decimal(str(db.query(func.coalesce(func.sum(MillCommissiondarLoanRepayment.amount), 0)).filter(MillCommissiondarLoanRepayment.loan_id == loan.id, MillCommissiondarLoanRepayment.is_void == False).scalar() or 0))
        result.append({"id": contact.id, "name": contact.name, "phone": contact.phone, "village": contact.village, "is_active": contact.is_active, "visit_count": len(movements), "total_packets": float(sum((m.packet_count or 0) for m in movements)), "total_quantity": float(sum((m.quantity or 0) for m in movements)), "total_commission": float(commissions), "mill_loans_count": len(loans), "mill_loans_total_principal": float(loan_principal), "mill_loans_total_repaid": float(loan_repaid), "mill_loans_outstanding_principal": float(loan_principal - loan_repaid)})
    return result


@app.put("/api/miller/commissiondars/{contact_id}")
def update_miller_commissiondar_contact(contact_id: int, data: CommissiondarContactUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_owner)):
    contact = db.query(Party).filter(Party.id == contact_id, Party.business_id == current_user.business_id, Party.party_type == "commissiondar").first()
    if not contact:
        raise HTTPException(status_code=404, detail="Commissiondar contact not found")
    for field in ("name", "phone", "village", "is_active"):
        value = getattr(data, field)
        if value is not None:
            setattr(contact, field, value.strip() if isinstance(value, str) else value)
    commit_transaction(db, "Failed to update Commissiondar contact")
    return {"id": contact.id, "name": contact.name, "phone": contact.phone, "village": contact.village, "is_active": contact.is_active}


@app.get("/api/miller/commissiondars/{contact_id}")
def get_miller_commissiondar_contact(contact_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_owner)):
    contact = db.query(Party).filter(Party.id == contact_id, Party.business_id == current_user.business_id, Party.party_type == "commissiondar").first()
    if not contact:
        raise HTTPException(status_code=404, detail="Commissiondar contact not found")
    return {"contact": {"id": contact.id, "name": contact.name}, "intakes": db.query(StockMovement).filter(StockMovement.business_id == current_user.business_id, StockMovement.broker_id == contact.id, StockMovement.is_void == False).order_by(StockMovement.moved_at.desc()).all(), "loans": db.query(MillCommissiondarLoan).filter(MillCommissiondarLoan.business_id == current_user.business_id, MillCommissiondarLoan.commissiondar_id == contact.id, MillCommissiondarLoan.is_void == False).all()}


# ---------------------------------------------------------------
# Commissiondar-owned farmer and grain management
# ---------------------------------------------------------------

@app.get("/api/commissiondar/farmers")
def list_commissiondar_farmers(db: Session = Depends(get_db), current_user: User = Depends(require_commissiondar)):
    farmers = db.query(Party).filter(Party.business_id == current_user.business_id, Party.party_type == "farmer", Party.is_active == True).order_by(Party.name.asc()).all()
    return [{"id": f.id, "name": f.name, "phone": f.phone, "village": f.village} for f in farmers]


@app.post("/api/commissiondar/farmers", status_code=201)
def create_commissiondar_farmer(data: CommissiondarFarmerCreate, db: Session = Depends(get_db), current_user: User = Depends(require_commissiondar)):
    farmer = Party(business_id=current_user.business_id, name=data.name.strip(), phone=data.phone, village=(data.village or None), party_type="farmer", opening_balance=Decimal("0"), is_active=True)
    db.add(farmer)
    commit_transaction(db, "Failed to create Commissiondar farmer")
    db.refresh(farmer)
    return {"id": farmer.id, "name": farmer.name, "phone": farmer.phone, "village": farmer.village}


@app.get("/api/commissiondar/grain-types")
def list_commissiondar_grain_types(db: Session = Depends(get_db), current_user: User = Depends(require_commissiondar)):
    rows = db.query(GrainType).filter(GrainType.is_active == True, ((GrainType.owner_business_id == current_user.business_id) | (GrainType.owner_business_id.is_(None)))).order_by(GrainType.name.asc()).all()
    return [{"id": x.id, "name": x.name, "unit": x.unit} for x in rows]


@app.post("/api/commissiondar/grain-types", status_code=201)
def create_commissiondar_grain_type(data: GrainTypeCreate, db: Session = Depends(get_db), current_user: User = Depends(require_commissiondar)):
    grain = GrainType(name=data.name.strip(), unit=data.unit.strip(), owner_business_id=current_user.business_id, created_by_user_id=current_user.id, is_active=True)
    db.add(grain)
    commit_transaction(db, "Failed to create grain type")
    db.refresh(grain)
    return {"id": grain.id, "name": grain.name, "unit": grain.unit}


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

        associated_contact = None
        if farmer.associated_commissiondar_id:
            associated_contact = db.query(Party).filter(Party.id == farmer.associated_commissiondar_id, Party.business_id == current_user.business_id, Party.party_type == "commissiondar").first()
        result.append({
            "id": farmer.id,
            "name": farmer.name,
            "village": farmer.village,
            "associated_commissiondar_id": farmer.associated_commissiondar_id,
            "associated_commissiondar_name": associated_contact.name if associated_contact else None,
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

    associated_id = data.associated_commissiondar_id
    if associated_id is not None:
        contact = db.query(Party).filter(Party.id == associated_id, Party.business_id == current_user.business_id, Party.party_type == "commissiondar", Party.is_active == True).first()
        if not contact:
            raise HTTPException(status_code=404, detail="Commissiondar contact not found in this mill account")

    try:
        farmer = Party(
            business_id=current_user.business_id,
            name=name,
            village=village,
            associated_commissiondar_id=associated_id,
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
        "associated_commissiondar_id": farmer.associated_commissiondar_id,
        "owed": 0.0
    }

@app.put("/api/farmers/{farmer_id}")
def update_farmer(farmer_id: int, data: FarmerUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_owner)):
    farmer = db.query(Party).filter(Party.id == farmer_id, Party.business_id == current_user.business_id, Party.party_type == "farmer", Party.is_active == True).first()
    if "associated_commissiondar_id" in data.model_fields_set:
        if data.associated_commissiondar_id is None:
            # Explicit null means remove the association.
            farmer.associated_commissiondar_id = None
        else:
            contact = db.query(Party).filter(
                Party.id == data.associated_commissiondar_id,
                Party.business_id == current_user.business_id,
                Party.party_type == "commissiondar",
                Party.is_active == True
            ).first()

            if not contact:
                raise HTTPException(
                    status_code=404,
                    detail="Commissiondar contact not found in this mill account"
                )

            farmer.associated_commissiondar_id = contact.id
    if data.name is not None:
        farmer.name = data.name.strip()
    if data.village is not None:
        farmer.village = data.village.strip()
    commit_transaction(db, "Failed to update farmer")
    return {"id": farmer.id, "name": farmer.name, "village": farmer.village, "associated_commissiondar_id": farmer.associated_commissiondar_id}
