from fastapi import Depends, HTTPException
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import ALGORITHM, SECRET_KEY
from app.core.database import get_db
from app.core.security import oauth2_scheme
from app.models.core import User
from app.models.party import Party


def get_current_user(
    credentials=Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials

    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )

        user_id = payload.get("sub")

        if user_id is None:
            raise credentials_exception

        user_id = int(user_id)

    except (JWTError, ValueError, TypeError):
        raise credentials_exception

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    if user is None:
        raise credentials_exception

    if user.approval_status != "approved":
        raise HTTPException(
            status_code=403,
            detail="Your account is not approved",
        )

    return user


def require_commissiondar(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    party = db.query(Party).filter(
        Party.id == current_user.party_id,
        Party.business_id == current_user.business_id,
        Party.party_type == "commissiondar",
        Party.is_active == True,
    ).first()

    if not party:
        raise HTTPException(
            status_code=403,
            detail="Only active commissiondars can access this",
        )

    return current_user


def require_owner(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != "owner":
        raise HTTPException(
            status_code=403,
            detail="Only the mill owner can do this",
        )

    return current_user


def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin only",
        )

    return current_user
