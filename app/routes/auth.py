from datetime import datetime, timedelta, timezone
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.core import Business, LoginChallenge, LoginLog, User
from app.models.party import Party
from app.schemas.auth import (
    CommissiondarRegisterRequest,
    LoginRequest,
    MillerRegisterRequest,
    OTPVerifyRequest,
)
from app.utils.phone import extract_digits, normalize_phone_digits

router = APIRouter()


@router.post("/api/register/miller", status_code=201)
def register_miller(
    data: MillerRegisterRequest,
    db: Session = Depends(get_db),
):
    name = data.name.strip()
    phone = data.phone.strip()
    business_name = data.business_name.strip()

    if not name or not phone or not business_name:
        raise HTTPException(
            status_code=422,
            detail="Name, phone and business name are required",
        )

    if not data.password:
        raise HTTPException(
            status_code=422,
            detail="Password is required",
        )
    if db.query(User).filter(User.phone == phone).first():
        raise HTTPException(
            status_code=409,
            detail="Phone number is already registered",
        )

    try:
        business = Business(
            name=business_name,
            business_type="mill",
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
            approval_status="pending",
        )
        db.add(user)
        db.commit()

        return {
            "message": "Miller registration submitted. Await Admin approval.",
            "approval_status": "pending",
        }

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Phone number is already registered",
        )

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Miller registration failed",
        )


@router.post("/api/register/commissiondar", status_code=201)
def register_commissiondar(
    data: CommissiondarRegisterRequest,
    db: Session = Depends(get_db),
):
    name = data.name.strip()
    phone = data.phone.strip()

    if not name or not phone:
        raise HTTPException(
            status_code=422,
            detail="Name and phone are required",
        )

    if not data.password:
        raise HTTPException(
            status_code=422,
            detail="Password is required",
        )

    if db.query(User).filter(User.phone == phone).first():
        raise HTTPException(
            status_code=409,
            detail="Phone number is already registered",
        )

    try:
        business = Business(
            name=f"{name} Commissiondar Account",
            business_type="commissiondar",
        )
        db.add(business)
        db.flush()

        party = Party(
            business_id=business.id,
            name=name,
            phone=phone,
            party_type="commissiondar",
            opening_balance=0,
            is_active=True,
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
            approval_status="pending",
        )
        db.add(user)
        db.commit()

        return {
            "message": "Commissiondar registration submitted. Await Admin approval.",
            "approval_status": "pending",
        }

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Phone number is already registered",
        )

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Commissiondar registration failed",
        )


@router.post("/api/login")
def login(
    data: LoginRequest,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(
        User.phone == data.phone
    ).first()

    # 1. Verify user exists
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid phone number or password",
        )

    # 2. Verify the single password
    if not user.password_hash or not verify_password(
        data.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid phone number or password",
        )

    # 3. Check account approval status
    if user.approval_status == "pending":
        raise HTTPException(
            status_code=403,
            detail="Your registration is pending Admin approval",
        )

    if user.approval_status == "rejected":
        raise HTTPException(
            status_code=403,
            detail="Your registration has been rejected",
        )

    if user.approval_status != "approved":
        raise HTTPException(
            status_code=403,
            detail="Your account cannot log in",
        )

    # 4. Invalidate previous unused challenges for this user
    db.query(LoginChallenge).filter(
        LoginChallenge.user_id == user.id,
        LoginChallenge.used == False,
    ).delete(synchronize_session=False)

    # 5. Create a new persistent login challenge
    challenge_id = secrets.token_urlsafe(32)

    challenge = LoginChallenge(
        challenge_id=challenge_id,
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        used=False,
    )

    try:
        db.add(challenge)
        db.commit()

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to create login challenge",
        )

    return {
        "message": "Password verified. MSG91 OTP required.",
        "challenge_id": challenge_id,
    }


@router.post("/api/verify-otp")
def verify_login_otp(
    data: OTPVerifyRequest,
    db: Session = Depends(get_db),
):
    # 1. Find the login challenge
    challenge = db.query(LoginChallenge).filter(
        LoginChallenge.challenge_id == data.challenge_id
    ).first()

    if not challenge or challenge.used:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired login challenge",
        )

    now = datetime.now(timezone.utc)

    if challenge.expires_at <= now:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired login challenge",
        )

    # 2. Find the user
    user = db.query(User).filter(
        User.id == challenge.user_id
    ).first()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User account not found",
        )

    if user.approval_status != "approved":
        raise HTTPException(
            status_code=403,
            detail="Your account is not approved",
        )

    # 3. Verify MSG91 widget access token
    verified_identifier = security.verify_msg91_access_token(
        data.access_token
    )

    # 4. Normalize phone numbers
    verified_phone = normalize_phone_digits(verified_identifier)
    stored_phone = extract_digits(user.phone)

    if verified_phone != stored_phone:
        raise HTTPException(
            status_code=401,
            detail="Verified phone number does not match your account",
        )

    # 5. Atomically consume the challenge and record login
    try:
        result = db.query(LoginChallenge).filter(
            LoginChallenge.id == challenge.id,
            LoginChallenge.used.is_(False),
            LoginChallenge.expires_at > datetime.now(timezone.utc),
        ).update(
            {LoginChallenge.used: True},
            synchronize_session=False,
        )

        if result != 1:
            db.rollback()
            raise HTTPException(
                status_code=401,
                detail="Invalid, expired, or already-used login challenge",
            )

        # Refresh account status before issuing token
        db.refresh(user)

        if user.approval_status != "approved":
            db.rollback()
            raise HTTPException(
                status_code=403,
                detail="Your account is not approved",
            )

        log = LoginLog(
            phone=user.phone,
            user_id=user.id,
            success=True,
        )

        db.add(log)
        db.commit()

    except HTTPException:
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to record login",
        )

    # 6. Generate JWT access token
    token = create_access_token(user)

    return {
        "message": "Login successful",
        "access_token": token,
        "token_type": "bearer",
    }
