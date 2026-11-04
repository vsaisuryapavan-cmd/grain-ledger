import os
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from pwdlib import PasswordHash
from database import get_db
from models import User
import secrets
import hashlib
import hmac
load_dotenv()
password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)

# OTP configuration
OTP_EXPIRY_MINUTES = 5
OTP_MAX_ATTEMPTS = 5

# Temporary in-memory OTP storage (development only)
OTP_CHALLENGES = {}

# Temporary hashing key for development OTP challenges
OTP_HASH_KEY = secrets.token_bytes(32)


def create_otp_challenge(user_id: int) -> str:

    app_env = os.getenv("APP_ENV", "production")
    delivery_mode = os.getenv("OTP_DELIVERY_MODE", "disabled")

    if app_env != "development" or delivery_mode != "console":
        raise RuntimeError("Console OTP is only available in development")

    challenge_id = secrets.token_urlsafe(32)

    otp = f"{secrets.randbelow(1_000_000):06d}"

    otp_hash = hmac.new(
        OTP_HASH_KEY,
        f"{challenge_id}:{otp}".encode(),
        hashlib.sha256
    ).hexdigest()

    OTP_CHALLENGES[challenge_id] = {
        "user_id": user_id,
        "otp_hash": otp_hash,
        "expires_at": datetime.now(timezone.utc)
        + timedelta(minutes=OTP_EXPIRY_MINUTES),
        "attempts": 0
    }

    print(f"\n[DEVELOPMENT OTP] {otp}\n")

    return challenge_id


def verify_otp(challenge_id: str, submitted_otp: str) -> bool:

    challenge = OTP_CHALLENGES.get(challenge_id)

    if challenge is None:
        return False

    if datetime.now(timezone.utc) >= challenge["expires_at"]:
        del OTP_CHALLENGES[challenge_id]
        return False

    if challenge["attempts"] >= OTP_MAX_ATTEMPTS:
        del OTP_CHALLENGES[challenge_id]
        return False

    submitted_hash = hmac.new(
        OTP_HASH_KEY,
        f"{challenge_id}:{submitted_otp}".encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(
        challenge["otp_hash"],
        submitted_hash
    ):
        challenge["attempts"] += 1

        if challenge["attempts"] >= OTP_MAX_ATTEMPTS:
            del OTP_CHALLENGES[challenge_id]

        return False

    del OTP_CHALLENGES[challenge_id]

    return True
SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is not configured")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

oauth2_scheme = HTTPBearer()


def create_access_token(user: User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": str(user.id),
        "business_id": user.business_id,
        "role": user.role,
        "party_id": user.party_id,
        "exp": expire,
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:

    token = credentials.credentials

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id = payload.get("sub")

        if user_id is None:
            raise credentials_exception

        user_id = int(user_id)

    except (JWTError, ValueError, TypeError):
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()

    if user is None:
        raise credentials_exception

    return user
