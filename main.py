from datetime import datetime, timezone, timedelta, date
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
    CommissiondarMill,
    CommissiondarMillFarmer,
    CommissiondarMillCommission,
    CommissiondarMillCommissionReceipt,
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
class CommissiondarMillCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class CommissiondarMillUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None

class CommissiondarMillCommissionCreate(BaseModel):
    commission_amount: Decimal = Field(gt=0)
    earned_at: date | None = None
    note: str | None = None


class CommissiondarMillCommissionReceiptCreate(BaseModel):
    amount: Decimal = Field(gt=0)
    received_at: date | None = None
    note: str | None = None



class GrainTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    unit: str = Field(default="quintal", min_length=1, max_length=30)
class ItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    unit: str = Field(min_length=1, max_length=50)


class ItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, min_length=1, max_length=50)

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
    second_password: str | None = None

class OTPVerifyRequest(BaseModel):
    challenge_id: str
    access_token: str


class MillerRegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    phone: str = Field(min_length=10, max_length=20)
    business_name: str = Field(min_length=1, max_length=200)
    password: str
    second_password: str | None = None


class CommissiondarRegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    phone: str = Field(min_length=10, max_length=20)
    password: str
    second_password: str | None = None


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
    farmer_id: int
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

    if not data.password:
     raise HTTPException(
        status_code=422,
        detail="Password is required"
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
            second_password_hash=None,
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

    if not data.password:
      raise HTTPException(
        status_code=422,
        detail="Password is required"
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
            second_password_hash=None,
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

    # 1. Verify user exists
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid phone number or password"
        )

    # 2. Verify the single password
    if not user.password_hash or not verify_password(
        data.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid phone number or password"
        )

    # 3. Check account approval status
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

    # 4. Invalidate previous unused challenges for this user
    db.query(LoginChallenge).filter(
        LoginChallenge.user_id == user.id,
        LoginChallenge.used == False
    ).delete(synchronize_session=False)

    # 5. Create a new persistent login challenge
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
        "message": "Password verified. MSG91 OTP required.",
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
    # -----------------------------------------
    # Existing Commissiondar loan calculations
    # -----------------------------------------
    loans = db.query(CommissiondarLoan).filter(
        CommissiondarLoan.commissiondar_id == current_user.party_id,
        CommissiondarLoan.is_void == False
    ).all()

    total_lent = sum(
        float(loan.principal) for loan in loans
    )

    total_outstanding = 0.0

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

    # -----------------------------------------
    # Commissiondar's own mill commission ledger
    # -----------------------------------------
    commissions = db.query(CommissiondarMillCommission).filter(
        CommissiondarMillCommission.commissiondar_id == current_user.party_id,
        CommissiondarMillCommission.is_void == False
    ).all()

    total_commissions_earned = 0.0
    total_commissions_received = 0.0
    latest_commission = None

    for commission in commissions:
        received = db.query(
            func.coalesce(
                func.sum(CommissiondarMillCommissionReceipt.amount),
                0
            )
        ).filter(
            CommissiondarMillCommissionReceipt.commission_id == commission.id,
            CommissiondarMillCommissionReceipt.commissiondar_id == current_user.party_id,
            CommissiondarMillCommissionReceipt.is_void == False
        ).scalar()

        earned_amount = float(commission.commission_amount)
        received_amount = float(received or 0)
        pending_amount = earned_amount - received_amount

        total_commissions_earned += earned_amount
        total_commissions_received += received_amount

        # Latest recorded commission = highest commission ID
        if (
            latest_commission is None
            or commission.id > latest_commission["id"]
        ):
            latest_commission = {
                "id": commission.id,
                "mill_id": commission.mill_id,
                "commission_amount": round(earned_amount, 2),
                "received_amount": round(received_amount, 2),
                "pending_amount": round(pending_amount, 2),
                "earned_at": str(commission.earned_at),
                "note": commission.note
            }

    commissions_pending = (
        total_commissions_earned - total_commissions_received
    )

    # -----------------------------------------
    # Existing farmer count
    # -----------------------------------------
    farmer_count = db.query(func.count(Party.id)).filter(
        Party.business_id == current_user.business_id,
        Party.party_type == "farmer",
        Party.is_active == True
    ).scalar() or 0

    # -----------------------------------------
    # Commissiondar's own mills and associations
    # -----------------------------------------
    active_mills = db.query(CommissiondarMill).filter(
        CommissiondarMill.commissiondar_id == current_user.party_id,
        CommissiondarMill.business_id == current_user.business_id,
        CommissiondarMill.is_active == True
    ).all()

    total_mills = len(active_mills)

    associated_farmer_count = db.query(
        func.count(func.distinct(CommissiondarMillFarmer.farmer_id))
    ).filter(
        CommissiondarMillFarmer.commissiondar_id == current_user.party_id,
        CommissiondarMillFarmer.is_active == True
    ).scalar() or 0

    # -----------------------------------------
    # Latest loan
    # -----------------------------------------
    latest_loan = db.query(CommissiondarLoan).filter(
        CommissiondarLoan.commissiondar_id == current_user.party_id,
        CommissiondarLoan.is_void == False
    ).order_by(
        CommissiondarLoan.issued_at.desc(),
        CommissiondarLoan.id.desc()
    ).first()

    # -----------------------------------------
    # Dashboard response
    # -----------------------------------------
    return {
        "active_loans": len(loans),
        "total_lent_out": round(total_lent, 2),
        "total_outstanding": round(total_outstanding, 2),

        "commissions_earned": round(total_commissions_earned, 2),
        "commissions_received": round(total_commissions_received, 2),
        "commissions_pending": round(commissions_pending, 2),

        "total_farmers": farmer_count,
        "total_mills": total_mills,
        "associated_farmers": associated_farmer_count,

        "latest_loan": (
            {
                "id": latest_loan.id,
                "farmer_id": latest_loan.farmer_id,
                "principal": float(latest_loan.principal),
                "issued_at": str(latest_loan.issued_at)
            }
            if latest_loan else None
        ),

        "latest_commission": latest_commission
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
    # Exactly one grain identifier must be provided.
    if (data.grain_type_id is None) == (data.item_id is None):
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of grain_type_id or item_id"
        )

    # Validate farmer within this Commissiondar's own account.
    farmer = get_active_farmer(
        db,
        data.farmer_id,
        current_user.business_id
    )

    mill_name = data.mill_name.strip()

    if not mill_name:
        raise HTTPException(
            status_code=400,
            detail="Mill name cannot be empty"
        )

    # Validate the selected grain.
    if data.grain_type_id is not None:
        grain = db.query(GrainType).filter(
            GrainType.id == data.grain_type_id,
            GrainType.is_active == True,
            GrainType.owner_business_id == current_user.business_id
        ).first()

        if not grain:
            raise HTTPException(
                status_code=404,
                detail="Grain type not found in your account"
            )

        stock_filter = (
            CommissiondarStockMovement.grain_type_id == data.grain_type_id
        )

    else:
        item = db.query(Item).filter(
            Item.id == data.item_id,
            Item.business_id == current_user.business_id,
            Item.is_active == True
        ).first()

        if not item:
            raise HTTPException(
                status_code=404,
                detail="Item not found in your account"
            )

        stock_filter = (
            CommissiondarStockMovement.item_id == data.item_id
        )

    # Calculate available stock for this exact grain.
    available_stock = db.query(
        func.coalesce(
            func.sum(CommissiondarStockMovement.quantity),
            0
        )
    ).filter(
        CommissiondarStockMovement.commissiondar_id == current_user.party_id,
        CommissiondarStockMovement.is_void == False,
        stock_filter
    ).scalar()

    available_stock = Decimal(str(available_stock or 0))
    delivery_quantity = Decimal(str(data.quantity))

    if delivery_quantity > available_stock:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Insufficient stock for this delivery",
                "available_stock": float(available_stock),
                "requested_quantity": float(delivery_quantity)
            }
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
        "Failed to record stock delivery"
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
        "message": "Stock delivered successfully"
    }


@app.get("/api/commissiondar-stock")
def my_stock(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar)
):
    # Base query: only this Commissiondar's stock movements.
    query = db.query(CommissiondarStockMovement).filter(
        CommissiondarStockMovement.commissiondar_id == current_user.party_id,
        CommissiondarStockMovement.is_void == False
    )

    # Total stock received from farmers.
    received = db.query(
        func.coalesce(
            func.sum(CommissiondarStockMovement.quantity),
            0
        )
    ).filter(
        CommissiondarStockMovement.commissiondar_id == current_user.party_id,
        CommissiondarStockMovement.movement_type == "received_from_farmer",
        CommissiondarStockMovement.is_void == False
    ).scalar() or 0

    # Total stock delivered to mills.
    delivered = db.query(
        func.coalesce(
            func.sum(-CommissiondarStockMovement.quantity),
            0
        )
    ).filter(
        CommissiondarStockMovement.commissiondar_id == current_user.party_id,
        CommissiondarStockMovement.movement_type == "delivered_to_mill",
        CommissiondarStockMovement.is_void == False
    ).scalar() or 0

    # Stock history with farmer names.
    history_rows = (
        db.query(
            CommissiondarStockMovement,
            Party.name
        )
        .outerjoin(
            Party,
            Party.id == CommissiondarStockMovement.farmer_id
        )
        .filter(
            CommissiondarStockMovement.commissiondar_id == current_user.party_id,
            CommissiondarStockMovement.is_void == False
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
            "created_at": movement.created_at
        })

    # Calculate available stock separately for each grain type/item.
    stock_groups = db.query(
        CommissiondarStockMovement.grain_type_id,
        CommissiondarStockMovement.item_id,
        func.sum(
            CommissiondarStockMovement.quantity
        ).label("available_quantity")
    ).filter(
        CommissiondarStockMovement.commissiondar_id == current_user.party_id,
        CommissiondarStockMovement.is_void == False
    ).group_by(
        CommissiondarStockMovement.grain_type_id,
        CommissiondarStockMovement.item_id
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
            )
        })

    # Delivery summary grouped by mill name.
    by_mill = db.query(
        CommissiondarStockMovement.mill_name,
        func.sum(
            -CommissiondarStockMovement.quantity
        ).label("quantity_delivered"),
        func.count(
            CommissiondarStockMovement.id
        ).label("delivery_count")
    ).filter(
        CommissiondarStockMovement.commissiondar_id == current_user.party_id,
        CommissiondarStockMovement.movement_type == "delivered_to_mill",
        CommissiondarStockMovement.is_void == False,
        CommissiondarStockMovement.mill_name.isnot(None)
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
            "delivery_count": int(row.delivery_count)
        })

    return {
        "total_received": float(received),
        "total_delivered": float(delivered),
        "stock_on_hand": float(received - delivered),
        "stock_by_type": stock_by_type,
        "deliveries_by_mill": deliveries_by_mill,
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
        paid_commissions = db.query(
            func.coalesce(func.sum(BrokerCommission.commission_amount), 0)
        ).filter(
            BrokerCommission.business_id == current_user.business_id,
            BrokerCommission.commissiondar_id == contact.id,
            BrokerCommission.is_paid == True,
            BrokerCommission.is_void == False
        ).scalar() or 0

        associated_farmers = db.query(Party.id).filter(
            Party.business_id == current_user.business_id,
            Party.party_type == "farmer",
            Party.associated_commissiondar_id == contact.id
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
            BrokerCommission.farmer_id.isnot(None)
        ).all()

        farmer_ids.update(row[0] for row in commission_farmer_ids)
        loans = db.query(MillCommissiondarLoan).filter(MillCommissiondarLoan.business_id == current_user.business_id, MillCommissiondarLoan.commissiondar_id == contact.id, MillCommissiondarLoan.is_void == False).all()
        loan_principal = sum((Decimal(str(x.principal)) for x in loans), Decimal("0"))
        loan_repaid = Decimal("0")
        for loan in loans:
            loan_repaid += Decimal(str(db.query(func.coalesce(func.sum(MillCommissiondarLoanRepayment.amount), 0)).filter(MillCommissiondarLoanRepayment.loan_id == loan.id, MillCommissiondarLoanRepayment.is_void == False).scalar() or 0))
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
            "mill_loans_outstanding_principal": float(loan_principal - loan_repaid)
        })
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
def get_miller_commissiondar_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner)
):
    contact = db.query(Party).filter(
        Party.id == contact_id,
        Party.business_id == current_user.business_id,
        Party.party_type == "commissiondar"
    ).first()

    if not contact:
        raise HTTPException(
            status_code=404,
            detail="Commissiondar contact not found"
        )

    business_id = current_user.business_id

    # 1. Get all valid purchase movements for this contact
    movements = db.query(StockMovement).filter(
        StockMovement.business_id == business_id,
        StockMovement.broker_id == contact.id,
        StockMovement.movement_type == "purchase",
        StockMovement.is_void == False
    ).order_by(
        StockMovement.moved_at.desc()
    ).all()

    # 2. Get all commission records for this contact
    commissions = db.query(BrokerCommission).filter(
        BrokerCommission.business_id == business_id,
        BrokerCommission.commissiondar_id == contact.id,
        BrokerCommission.is_void == False
    ).all()

    # 3. Collect farmer IDs from associations, intakes and commissions
    farmer_ids = {
        farmer.id
        for farmer in db.query(Party).filter(
            Party.business_id == business_id,
            Party.party_type == "farmer",
            Party.associated_commissiondar_id == contact.id
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
        Party.id.in_(farmer_ids)
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
            Decimal("0")
        )

        farmer_commission_records = farmer_commissions.get(
            farmer_id, []
        )

        earned = sum(
            (
                Decimal(str(c.commission_amount or 0))
                for c in farmer_commission_records
            ),
            Decimal("0")
        )

        paid = sum(
            (
                Decimal(str(c.commission_amount or 0))
                for c in farmer_commission_records
                if c.is_paid
            ),
            Decimal("0")
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
            "intakes": farmer_intakes
        })

    # 7. Calculate remaining commission
    total_outstanding = (
        total_commission - total_commission_paid
    )

    # 8. Preserve existing Miller-to-Commissiondar loans
    loans = db.query(MillCommissiondarLoan).filter(
        MillCommissiondarLoan.business_id == business_id,
        MillCommissiondarLoan.commissiondar_id == contact.id,
        MillCommissiondarLoan.is_void == False
    ).all()

    return {
        "contact": {
            "id": contact.id,
            "name": contact.name,
            "phone": contact.phone,
            "village": contact.village,
            "is_active": contact.is_active
        },
        "summary": {
            "total_farmers": len(farmer_reports),
            "total_intakes": len(movements),
            "total_quantity": float(total_quantity),
            "total_commission": float(total_commission),
            "commission_paid": float(total_commission_paid),
            "commission_outstanding": float(total_outstanding)
        },
        "farmers": farmer_reports,
        "intakes": movements,
        "loans": loans
    }


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
# Commissiondar: Farmers associated with My Mills
# ---------------------------------------------------------------

@app.get("/api/commissiondar/mills/{mill_id}/farmers")
def list_farmers_for_commissiondar_mill(
    mill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar)
):
    # Confirm that this mill belongs to the logged-in Commissiondar.
    mill = db.query(CommissiondarMill).filter(
        CommissiondarMill.id == mill_id,
        CommissiondarMill.commissiondar_id == current_user.party_id,
        CommissiondarMill.business_id == current_user.business_id
    ).first()

    if not mill:
        raise HTTPException(status_code=404, detail="Mill not found")

    associations = (
        db.query(CommissiondarMillFarmer, Party)
        .join(
            Party,
            Party.id == CommissiondarMillFarmer.farmer_id
        )
        .filter(
            CommissiondarMillFarmer.mill_id == mill_id,
            CommissiondarMillFarmer.commissiondar_id == current_user.party_id,
            CommissiondarMillFarmer.is_active == True,
            Party.business_id == current_user.business_id,
            Party.party_type == "farmer",
            Party.is_active == True
        )
        .order_by(Party.name.asc())
        .all()
    )

    return {
        "mill_id": mill.id,
        "mill_name": mill.name,
        "farmer_count": len(associations),
        "farmers": [
            {
                "id": farmer.id,
                "name": farmer.name,
                "phone": farmer.phone,
                "village": farmer.village
            }
            for association, farmer in associations
        ]
    }


@app.post("/api/commissiondar/mills/{mill_id}/farmers/{farmer_id}", status_code=201)
def add_farmer_to_commissiondar_mill(
    mill_id: int,
    farmer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar)
):
    # The mill must belong to this Commissiondar and be active.
    mill = db.query(CommissiondarMill).filter(
        CommissiondarMill.id == mill_id,
        CommissiondarMill.commissiondar_id == current_user.party_id,
        CommissiondarMill.business_id == current_user.business_id,
        CommissiondarMill.is_active == True
    ).first()

    if not mill:
        raise HTTPException(status_code=404, detail="Active mill not found")

    # The farmer must belong to this Commissiondar's own directory.
    farmer = db.query(Party).filter(
        Party.id == farmer_id,
        Party.business_id == current_user.business_id,
        Party.party_type == "farmer",
        Party.is_active == True
    ).first()

    if not farmer:
        raise HTTPException(
            status_code=404,
            detail="Farmer not found in your farmer directory"
        )

    association = db.query(CommissiondarMillFarmer).filter(
        CommissiondarMillFarmer.mill_id == mill_id,
        CommissiondarMillFarmer.farmer_id == farmer_id,
        CommissiondarMillFarmer.commissiondar_id == current_user.party_id
    ).first()

    if association and association.is_active:
        raise HTTPException(
            status_code=409,
            detail="Farmer is already associated with this mill"
        )

    if association:
        # Reactivate a previously removed association.
        association.is_active = True
    else:
        association = CommissiondarMillFarmer(
            commissiondar_id=current_user.party_id,
            mill_id=mill_id,
            farmer_id=farmer_id,
            is_active=True
        )
        db.add(association)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Farmer is already associated with this mill"
        )
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to associate farmer with mill"
        )

    return {
        "mill_id": mill_id,
        "mill_name": mill.name,
        "farmer_id": farmer.id,
        "farmer_name": farmer.name,
        "message": "Farmer associated with mill successfully"
    }


@app.delete("/api/commissiondar/mills/{mill_id}/farmers/{farmer_id}")
def remove_farmer_from_commissiondar_mill(
    mill_id: int,
    farmer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar)
):
    # Confirm ownership of the mill.
    mill = db.query(CommissiondarMill).filter(
        CommissiondarMill.id == mill_id,
        CommissiondarMill.commissiondar_id == current_user.party_id,
        CommissiondarMill.business_id == current_user.business_id
    ).first()

    if not mill:
        raise HTTPException(status_code=404, detail="Mill not found")

    association = db.query(CommissiondarMillFarmer).filter(
        CommissiondarMillFarmer.mill_id == mill_id,
        CommissiondarMillFarmer.farmer_id == farmer_id,
        CommissiondarMillFarmer.commissiondar_id == current_user.party_id,
        CommissiondarMillFarmer.is_active == True
    ).first()

    if not association:
        raise HTTPException(
            status_code=404,
            detail="Active farmer association not found"
        )

    # Remove only the association, never the farmer directory record.
    association.is_active = False

    commit_transaction(
        db,
        "Failed to remove farmer from mill"
    )

    return {
        "mill_id": mill_id,
        "farmer_id": farmer_id,
        "message": "Farmer removed from mill successfully"
    }


# ---------------------------------------------------------------
# Commissiondar: My Mills
# ---------------------------------------------------------------

@app.get("/api/commissiondar/mills")
def list_commissiondar_mills(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar)
):
    query = db.query(CommissiondarMill).filter(
        CommissiondarMill.commissiondar_id == current_user.party_id,
        CommissiondarMill.business_id == current_user.business_id
    )

    if not include_inactive:
        query = query.filter(CommissiondarMill.is_active == True)

    mills = query.order_by(CommissiondarMill.name.asc()).all()

    return [
        {
            "id": mill.id,
            "name": mill.name,
            "is_active": mill.is_active,
            "created_at": mill.created_at
        }
        for mill in mills
    ]


@app.post("/api/commissiondar/mills", status_code=201)
def create_commissiondar_mill(
    data: CommissiondarMillCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar)
):
    name = data.name.strip()

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Mill name cannot be empty"
        )

    existing = db.query(CommissiondarMill).filter(
        CommissiondarMill.commissiondar_id == current_user.party_id,
        func.lower(CommissiondarMill.name) == name.lower()
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail="This mill name already exists"
        )

    mill = CommissiondarMill(
        commissiondar_id=current_user.party_id,
        business_id=current_user.business_id,
        name=name,
        is_active=True
    )

    db.add(mill)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This mill name already exists"
        )
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to create mill"
        )

    db.refresh(mill)

    return {
        "id": mill.id,
        "name": mill.name,
        "is_active": mill.is_active,
        "message": "Mill added successfully"
    }


@app.put("/api/commissiondar/mills/{mill_id}")
def update_commissiondar_mill(
    mill_id: int,
    data: CommissiondarMillUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar)
):
    mill = db.query(CommissiondarMill).filter(
        CommissiondarMill.id == mill_id,
        CommissiondarMill.commissiondar_id == current_user.party_id,
        CommissiondarMill.business_id == current_user.business_id
    ).first()

    if not mill:
        raise HTTPException(
            status_code=404,
            detail="Mill not found"
        )

    if data.name is None and data.is_active is None:
        raise HTTPException(
            status_code=400,
            detail="No update fields provided"
        )

    if data.name is not None:
        name = data.name.strip()

        if not name:
            raise HTTPException(
                status_code=400,
                detail="Mill name cannot be empty"
            )

        duplicate = db.query(CommissiondarMill).filter(
            CommissiondarMill.commissiondar_id == current_user.party_id,
            CommissiondarMill.id != mill_id,
            func.lower(CommissiondarMill.name) == name.lower()
        ).first()

        if duplicate:
            raise HTTPException(
                status_code=409,
                detail="This mill name already exists"
            )

        mill.name = name

    if data.is_active is not None:
        mill.is_active = data.is_active

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Could not update mill because of a duplicate name"
        )
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to update mill"
        )

    db.refresh(mill)

    return {
        "id": mill.id,
        "name": mill.name,
        "is_active": mill.is_active,
        "message": "Mill updated successfully"
    }


@app.delete("/api/commissiondar/mills/{mill_id}")
def deactivate_commissiondar_mill(
    mill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar)
):
    mill = db.query(CommissiondarMill).filter(
        CommissiondarMill.id == mill_id,
        CommissiondarMill.commissiondar_id == current_user.party_id,
        CommissiondarMill.business_id == current_user.business_id
    ).first()

    if not mill:
        raise HTTPException(
            status_code=404,
            detail="Mill not found"
        )

    if not mill.is_active:
        raise HTTPException(
            status_code=400,
            detail="Mill is already inactive"
        )

    mill.is_active = False

    commit_transaction(
        db,
        "Failed to deactivate mill"
    )

    return {
        "id": mill.id,
        "name": mill.name,
        "is_active": False,
        "message": "Mill deactivated successfully"
    }


# ---------------------------------------------------------------
# Items
# ---------------------------------------------------------------

# ---------------------------------------------------------------
# ---------------------------------------------------------------
# Miller Grain Items
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


@app.post("/api/items", status_code=201)
def create_item(
    data: ItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner)
):
    name = data.name.strip()
    unit = data.unit.strip()
    category = data.category.strip() if data.category else None

    if not name or not unit:
        raise HTTPException(
            status_code=400,
            detail="Grain variety name and unit cannot be empty"
        )

    existing_item = db.query(Item).filter(
        Item.business_id == current_user.business_id,
        func.lower(Item.name) == name.lower()
    ).first()

    if existing_item:
        raise HTTPException(
            status_code=409,
            detail="This grain variety already exists"
        )

    item = Item(
        business_id=current_user.business_id,
        name=name,
        category=category,
        unit=unit,
        is_active=True
    )

    db.add(item)

    try:
        db.commit()
        db.refresh(item)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This grain variety already exists"
        )

    return {
        "message": "Grain variety created successfully",
        "item": {
            "id": item.id,
            "name": item.name,
            "category": item.category,
            "unit": item.unit
        }
    }


@app.put("/api/items/{item_id}")
def update_item(
    item_id: int,
    data: ItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner)
):
    item = get_active_item(
        db,
        item_id,
        current_user.business_id
    )

    updates = data.model_dump(exclude_unset=True)

    if not updates:
        raise HTTPException(
            status_code=400,
            detail="No fields provided for update"
        )

    if "name" in updates and updates["name"] is not None:
        updates["name"] = updates["name"].strip()

        if not updates["name"]:
            raise HTTPException(
                status_code=400,
                detail="Grain variety name cannot be empty"
            )

        existing_item = db.query(Item).filter(
            Item.business_id == current_user.business_id,
            func.lower(Item.name) == updates["name"].lower(),
            Item.id != item_id
        ).first()

        if existing_item:
            raise HTTPException(
                status_code=409,
                detail="This grain variety already exists"
            )

    if "unit" in updates and updates["unit"] is not None:
        updates["unit"] = updates["unit"].strip()

        if not updates["unit"]:
            raise HTTPException(
                status_code=400,
                detail="Unit cannot be empty"
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
            detail="This grain variety already exists"
        )

    return {
        "message": "Grain variety updated successfully",
        "item": {
            "id": item.id,
            "name": item.name,
            "category": item.category,
            "unit": item.unit
        }
    }


@app.patch("/api/items/{item_id}/deactivate")
def deactivate_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner)
):
    item = get_active_item(
        db,
        item_id,
        current_user.business_id
    )

    item.is_active = False
    db.commit()

    return {
        "message": "Grain variety deactivated successfully",
        "item_id": item.id,
        "name": item.name,
        "is_active": False
    }
# ---------------------------------------------------------------
# Miller Inventory
# ---------------------------------------------------------------

@app.get("/api/inventory")
def get_miller_inventory(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner)
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
        func.sum(StockMovement.quantity)
    ).filter(
        StockMovement.business_id == current_user.business_id,
        StockMovement.is_void == False
    ).group_by(
        StockMovement.item_id,
        StockMovement.movement_type
    ).all()

    # Prepare totals for every item, including items with no movements.
    totals = {
        item.id: {
            "received_quantity": 0.0,
            "dispatched_quantity": 0.0,
            "available_quantity": 0.0
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
                "available_quantity": totals[item.id]["available_quantity"]
            }
            for item in items
        ]
    }


@app.get("/api/inventory/{item_id}/movements")
def get_miller_inventory_movements(
    item_id: int,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner)
):
    if limit < 1 or limit > 500:
        raise HTTPException(
            status_code=400,
            detail="Limit must be between 1 and 500"
        )

    if offset < 0:
        raise HTTPException(
            status_code=400,
            detail="Offset cannot be negative"
        )

    # Verify that this grain variety belongs to the logged-in Miller.
    # Do not require is_active: inactive varieties still have history.
    item = db.query(Item).filter(
        Item.id == item_id,
        Item.business_id == current_user.business_id
    ).first()

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Grain variety not found"
        )

    movement_query = db.query(StockMovement).filter(
        StockMovement.business_id == current_user.business_id,
        StockMovement.item_id == item_id
    )

    total_count = movement_query.count()

    movements = movement_query.order_by(
        StockMovement.moved_at.desc(),
        StockMovement.id.desc()
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
            "is_active": item.is_active
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
                "is_void": movement.is_void
            }
            for movement in movements
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

# ---------------------------------------------------------------
# Commissiondar: Manual Mill Commission Ledger
# ---------------------------------------------------------------

@app.post(
    "/api/commissiondar/mills/{mill_id}/commissions",
    status_code=201
)
def create_commissiondar_mill_commission(
    mill_id: int,
    data: CommissiondarMillCommissionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar)
):
    # Only the logged-in Commissiondar's active mill is allowed.
    mill = db.query(CommissiondarMill).filter(
        CommissiondarMill.id == mill_id,
        CommissiondarMill.commissiondar_id == current_user.party_id,
        CommissiondarMill.business_id == current_user.business_id,
        CommissiondarMill.is_active == True
    ).first()

    if not mill:
        raise HTTPException(status_code=404, detail="Active mill not found")

    commission = CommissiondarMillCommission(
        commissiondar_id=current_user.party_id,
        mill_id=mill.id,
        commission_amount=data.commission_amount,
        earned_at=data.earned_at or date.today(),
        note=data.note.strip() if data.note else None,
        is_void=False
    )

    db.add(commission)
    commit_transaction(db, "Failed to record commission")
    db.refresh(commission)

    return {
        "id": commission.id,
        "mill_id": mill.id,
        "mill_name": mill.name,
        "commission_amount": float(commission.commission_amount),
        "earned_at": commission.earned_at,
        "note": commission.note,
        "received_amount": 0.0,
        "pending_amount": float(commission.commission_amount),
        "message": "Commission recorded successfully"
    }


@app.get("/api/commissiondar/mills/{mill_id}/commissions")
def list_commissiondar_mill_commissions(
    mill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar)
):
    mill = db.query(CommissiondarMill).filter(
        CommissiondarMill.id == mill_id,
        CommissiondarMill.commissiondar_id == current_user.party_id,
        CommissiondarMill.business_id == current_user.business_id
    ).first()

    if not mill:
        raise HTTPException(status_code=404, detail="Mill not found")

    commissions = db.query(CommissiondarMillCommission).filter(
        CommissiondarMillCommission.mill_id == mill.id,
        CommissiondarMillCommission.commissiondar_id == current_user.party_id,
        CommissiondarMillCommission.is_void == False
    ).order_by(
        CommissiondarMillCommission.earned_at.desc(),
        CommissiondarMillCommission.id.desc()
    ).all()

    commission_ids = [item.id for item in commissions]

    receipts = []
    if commission_ids:
        receipts = db.query(CommissiondarMillCommissionReceipt).filter(
            CommissiondarMillCommissionReceipt.commission_id.in_(commission_ids),
            CommissiondarMillCommissionReceipt.commissiondar_id == current_user.party_id,
            CommissiondarMillCommissionReceipt.is_void == False
        ).order_by(
            CommissiondarMillCommissionReceipt.received_at.desc(),
            CommissiondarMillCommissionReceipt.id.desc()
        ).all()

    receipts_by_commission = {}
    for receipt in receipts:
        receipts_by_commission.setdefault(receipt.commission_id, []).append(receipt)

    result = []
    total_earned = Decimal("0.00")
    total_received = Decimal("0.00")

    for commission in commissions:
        commission_receipts = receipts_by_commission.get(commission.id, [])

        received = sum(
            (receipt.amount for receipt in commission_receipts),
            Decimal("0.00")
        )

        earned = commission.commission_amount
        pending = earned - received

        total_earned += earned
        total_received += received

        result.append({
            "id": commission.id,
            "commission_amount": float(earned),
            "earned_at": commission.earned_at,
            "note": commission.note,
            "received_amount": float(received),
            "pending_amount": float(pending),
            "receipts": [
                {
                    "id": receipt.id,
                    "amount": float(receipt.amount),
                    "received_at": receipt.received_at,
                    "note": receipt.note
                }
                for receipt in commission_receipts
            ]
        })

    return {
        "mill_id": mill.id,
        "mill_name": mill.name,
        "total_earned": float(total_earned),
        "total_received": float(total_received),
        "total_pending": float(total_earned - total_received),
        "commission_count": len(result),
        "commissions": result
    }


@app.post(
    "/api/commissiondar/commissions/{commission_id}/receipts",
    status_code=201
)
def create_commissiondar_commission_receipt(
    commission_id: int,
    data: CommissiondarMillCommissionReceiptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar)
):
    # Lock the commission row while checking and recording a receipt.
    # This prevents concurrent receipts from exceeding the pending amount.
    commission = db.query(CommissiondarMillCommission).filter(
    CommissiondarMillCommission.id == commission_id,
    CommissiondarMillCommission.commissiondar_id == current_user.party_id,
    CommissiondarMillCommission.is_void == False
).with_for_update().first()

    if not commission:
        raise HTTPException(status_code=404, detail="Commission entry not found")

    received = db.query(
        func.coalesce(
            func.sum(CommissiondarMillCommissionReceipt.amount),
            0
        )
    ).filter(
        CommissiondarMillCommissionReceipt.commission_id == commission.id,
        CommissiondarMillCommissionReceipt.commissiondar_id == current_user.party_id,
        CommissiondarMillCommissionReceipt.is_void == False
    ).scalar()

    received = received or Decimal("0.00")
    pending = commission.commission_amount - received

    if data.amount > pending:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Receipt amount exceeds pending commission",
                "pending_amount": float(pending)
            }
        )

    receipt = CommissiondarMillCommissionReceipt(
        commissiondar_id=current_user.party_id,
        commission_id=commission.id,
        amount=data.amount,
        received_at=data.received_at or date.today(),
        note=data.note.strip() if data.note else None,
        is_void=False
    )

    db.add(receipt)
    commit_transaction(db, "Failed to record commission receipt")
    db.refresh(receipt)

    remaining = pending - receipt.amount

    return {
        "id": receipt.id,
        "commission_id": commission.id,
        "amount": float(receipt.amount),
        "received_at": receipt.received_at,
        "note": receipt.note,
        "remaining_pending": float(remaining),
        "message": "Commission receipt recorded successfully"
    }


@app.get("/api/commissiondar/commissions/{commission_id}/receipts")
def list_commissiondar_commission_receipts(
    commission_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar)
):
    commission = db.query(CommissiondarMillCommission).filter(
        CommissiondarMillCommission.id == commission_id,
        CommissiondarMillCommission.commissiondar_id == current_user.party_id
    ).first()

    if not commission:
        raise HTTPException(status_code=404, detail="Commission entry not found")

    receipts = db.query(CommissiondarMillCommissionReceipt).filter(
        CommissiondarMillCommissionReceipt.commission_id == commission.id,
        CommissiondarMillCommissionReceipt.commissiondar_id == current_user.party_id,
        CommissiondarMillCommissionReceipt.is_void == False
    ).order_by(
        CommissiondarMillCommissionReceipt.received_at.desc(),
        CommissiondarMillCommissionReceipt.id.desc()
    ).all()

    total_received = sum(
        (receipt.amount for receipt in receipts),
        Decimal("0.00")
    )

    return {
        "commission_id": commission.id,
        "commission_amount": float(commission.commission_amount),
        "total_received": float(total_received),
        "pending_amount": float(commission.commission_amount - total_received),
        "receipts": [
            {
                "id": receipt.id,
                "amount": float(receipt.amount),
                "received_at": receipt.received_at,
                "note": receipt.note
            }
            for receipt in receipts
        ]
    }
