from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    String,
)
from sqlalchemy import func

from app.core.database import Base


class Business(Base):
    __tablename__ = "businesses"

    id = Column(BigInteger, primary_key=True)
    name = Column(String, nullable=False)
    business_type = Column(String, nullable=False)
    phone = Column(String)
    address = Column(String)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "business_type IN ('mill', 'store', 'commissiondar', 'system')",
            name="businesses_business_type_check",
        ),
    )


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)

    business_id = Column(
        BigInteger,
        ForeignKey("businesses.id"),
        nullable=False,
    )

    name = Column(String, nullable=False)
    phone = Column(String, nullable=False, unique=True)

    # owner = Miller
    # party = Commissiondar
    # staff = Staff
    # admin = Grain Ledger Admin
    role = Column(String, nullable=False)

    party_id = Column(
        BigInteger,
        ForeignKey("parties.id"),
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Authentication
    password_hash = Column(String(255), nullable=True)
    second_password_hash = Column(String(255), nullable=True)

    # Registration approval
    approval_status = Column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )

    # Admin who approved or rejected this account
    reviewed_by = Column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True,
    )

    reviewed_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('owner', 'staff', 'party', 'admin')",
            name="users_role_check",
        ),
        CheckConstraint(
            "approval_status IN ('pending', 'approved', 'rejected')",
            name="users_approval_status_check",
        ),
    )


class LoginLog(Base):
    __tablename__ = "login_logs"

    id = Column(BigInteger, primary_key=True)
    phone = Column(String, nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    success = Column(Boolean, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class IssueReport(Base):
    __tablename__ = "issue_reports"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    description = Column(String, nullable=False)
    status = Column(String, nullable=False, default="open")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class LoginChallenge(Base):
    __tablename__ = "login_challenges"

    id = Column(BigInteger, primary_key=True)

    challenge_id = Column(
        String(128),
        nullable=False,
        unique=True,
        index=True,
    )

    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
    )

    used = Column(
        Boolean,
        nullable=False,
        default=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
