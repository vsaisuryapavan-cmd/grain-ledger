
from sqlalchemy import (
    Column,
    BigInteger,
    String,
    Numeric,
    Boolean,
    DateTime,
    Date,
    ForeignKey,
    CheckConstraint,
    UniqueConstraint,
    Index,

)
from sqlalchemy import func
from database import Base


class Business(Base):
    __tablename__ = "businesses"

    id = Column(BigInteger, primary_key=True)
    name = Column(String, nullable=False)
    business_type = Column(String, nullable=False)
    phone = Column(String)
    address = Column(String)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "business_type IN ('mill', 'store', 'commissiondar', 'system')",
            name="businesses_business_type_check"
        ),
    )


class Party(Base):
    __tablename__ = "parties"

    id = Column(BigInteger, primary_key=True)
    business_id = Column(
        BigInteger,
        ForeignKey("businesses.id"),
        nullable=False
    )
    name = Column(String, nullable=False)
    phone = Column(String)
    village = Column(String)
    party_type = Column(String, nullable=False)
    # Miller-owned farmer -> Miller-owned Commissiondar contact association.
    # This never references a Commissiondar login account.
    associated_commissiondar_id = Column(
        BigInteger,
        ForeignKey("parties.id"),
        nullable=True
    )
    opening_balance = Column(
        Numeric(14, 2),
        nullable=False,
        default=0
    )
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "party_type IN ('farmer', 'customer', 'supplier', 'buyer', 'commissiondar')",
            name="parties_party_type_check"
        ),
    )


class Item(Base):
    __tablename__ = "items"

    id = Column(BigInteger, primary_key=True)
    business_id = Column(
        BigInteger,
        ForeignKey("businesses.id"),
        nullable=False
    )
    name = Column(String, nullable=False)
    category = Column(String)
    unit = Column(String, nullable=False)
    sku = Column(String)
    sale_price = Column(Numeric(12, 2))
    gst_rate = Column(Numeric(5, 2), default=0)
    reorder_level = Column(Numeric(12, 3))
    is_active = Column(Boolean, nullable=False, default=True)


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True)

    business_id = Column(
        BigInteger,
        ForeignKey("businesses.id"),
        nullable=False
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
        ForeignKey("parties.id")
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    # Authentication
    password_hash = Column(String(255), nullable=True)
    second_password_hash = Column(String(255), nullable=True)

    # Registration approval
    approval_status = Column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending"
    )

    # Admin who approved or rejected this account
    reviewed_by = Column(
        BigInteger,
        ForeignKey("users.id"),
        nullable=True
    )

    reviewed_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('owner', 'staff', 'party', 'admin')",
            name="users_role_check"
        ),
        CheckConstraint(
            "approval_status IN ('pending', 'approved', 'rejected')",
            name="users_approval_status_check"
        ),
    )


class GrainType(Base):
    __tablename__ = "grain_types"

    id = Column(BigInteger, primary_key=True)
    name = Column(String, nullable=False)
    unit = Column(String, nullable=False, default="quintal")

    # NULL = global grain type.
    # Business ID = private Commissiondar grain type.
    owner_business_id = Column(
        BigInteger,
        ForeignKey("businesses.id", ondelete="RESTRICT"),
        nullable=True
    )

    created_by_user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint(
            "LENGTH(TRIM(name)) > 0",
            name="grain_types_name_not_empty"
        ),
        CheckConstraint(
            "LENGTH(TRIM(unit)) > 0",
            name="grain_types_unit_not_empty"
        ),
        Index(
            "uq_grain_types_global_name",
            func.lower(name),
            unique=True,
            postgresql_where=(owner_business_id.is_(None))
        ),
        Index(
            "uq_grain_types_business_name",
            owner_business_id,
            func.lower(name),
            unique=True,
            postgresql_where=(owner_business_id.isnot(None))
        ),
    )


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(BigInteger, primary_key=True)
    business_id = Column(
        BigInteger,
        ForeignKey("businesses.id"),
        nullable=False
    )
    item_id = Column(
        BigInteger,
        ForeignKey("items.id"),
        nullable=False
    )
    party_id = Column(BigInteger, ForeignKey("parties.id"))
    movement_type = Column(String, nullable=False)
    quantity = Column(Numeric(14, 3), nullable=False)
    rate = Column(Numeric(12, 2))
    moisture_pct = Column(Numeric(5, 2))
    packet_count = Column(Numeric(14, 3))
    packet_price = Column(Numeric(12, 2))
    commission_type = Column(String(20))
    commission_rate = Column(Numeric(12, 2))
    commission_per_packet = Column(Numeric(12, 2))
    moved_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    note = Column(String)
    created_by = Column(BigInteger, ForeignKey("users.id"))
    broker_id = Column(BigInteger, ForeignKey("parties.id"))
    is_void = Column(Boolean, nullable=False, default=False)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id = Column(BigInteger, primary_key=True)
    business_id = Column(
        BigInteger,
        ForeignKey("businesses.id"),
        nullable=False
    )
    party_id = Column(
        BigInteger,
        ForeignKey("parties.id"),
        nullable=False
    )
    entry_date = Column(Date, server_default=func.now())
    debit = Column(Numeric(14, 2), nullable=False, default=0)
    credit = Column(Numeric(14, 2), nullable=False, default=0)
    movement_id = Column(BigInteger, ForeignKey("stock_movements.id"))
    payment_id = Column(BigInteger)
    note = Column(String)
    is_void = Column(Boolean, nullable=False, default=False)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(BigInteger, primary_key=True)
    business_id = Column(
        BigInteger,
        ForeignKey("businesses.id"),
        nullable=False
    )
    party_id = Column(
        BigInteger,
        ForeignKey("parties.id"),
        nullable=False
    )
    direction = Column(String, nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    mode = Column(String)
    paid_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    note = Column(String)
    created_by = Column(BigInteger, ForeignKey("users.id"))
    is_void = Column(Boolean, nullable=False, default=False)


class CommissiondarLoan(Base):
    __tablename__ = "commissiondar_loans"

    id = Column(BigInteger, primary_key=True)
    commissiondar_id = Column(
        BigInteger,
        ForeignKey("parties.id"),
        nullable=False
    )
    farmer_id = Column(
        BigInteger,
        ForeignKey("parties.id"),
        nullable=False
    )
    principal = Column(Numeric(14, 2), nullable=False)
    interest_rate_pa = Column(
        Numeric(5, 2),
        nullable=False,
        default=0
    )
    issued_at = Column(Date, server_default=func.now())
    status = Column(String, nullable=False, default="open")
    note = Column(String)
    is_void = Column(Boolean, nullable=False, default=False)


class CommissiondarLoanRepayment(Base):
    __tablename__ = "commissiondar_loan_repayments"

    id = Column(BigInteger, primary_key=True)
    loan_id = Column(
        BigInteger,
        ForeignKey("commissiondar_loans.id"),
        nullable=False
    )
    amount = Column(Numeric(14, 2), nullable=False)
    paid_at = Column(Date, server_default=func.now())
    note = Column(String)
    is_void = Column(Boolean, nullable=False, default=False)


class MillCommissiondarLoan(Base):
    __tablename__ = "mill_commissiondar_loans"

    id = Column(BigInteger, primary_key=True)
    business_id = Column(
        BigInteger,
        ForeignKey("businesses.id"),
        nullable=False
    )
    commissiondar_id = Column(
        BigInteger,
        ForeignKey("parties.id"),
        nullable=False
    )
    principal = Column(Numeric(14, 2), nullable=False)
    interest_rate_pa = Column(
        Numeric(5, 2),
        nullable=False,
        default=0
    )
    issued_at = Column(Date, server_default=func.now())
    status = Column(String, nullable=False, default="open")
    note = Column(String)
    is_void = Column(Boolean, nullable=False, default=False)


class MillCommissiondarLoanRepayment(Base):
    __tablename__ = "mill_commissiondar_loan_repayments"

    id = Column(BigInteger, primary_key=True)
    loan_id = Column(
        BigInteger,
        ForeignKey("mill_commissiondar_loans.id"),
        nullable=False
    )
    amount = Column(Numeric(14, 2), nullable=False)
    paid_at = Column(Date, server_default=func.now())
    note = Column(String)
    is_void = Column(Boolean, nullable=False, default=False)


class BrokerCommission(Base):
    __tablename__ = "broker_commissions"

    id = Column(BigInteger, primary_key=True)
    business_id = Column(
        BigInteger,
        ForeignKey("businesses.id"),
        nullable=False
    )
    commissiondar_id = Column(
        BigInteger,
        ForeignKey("parties.id"),
        nullable=False
    )
    farmer_id = Column(BigInteger, ForeignKey("parties.id"))
    movement_id = Column(
        BigInteger,
        ForeignKey("stock_movements.id")
    )
    commission_amount = Column(Numeric(12, 2), nullable=False)
    packet_count = Column(Numeric(14, 3))
    packet_price = Column(Numeric(12, 2))
    commission_type = Column(String(20))
    commission_rate = Column(Numeric(12, 2))
    commission_per_packet = Column(Numeric(12, 2))
    is_paid = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    is_void = Column(Boolean, nullable=False, default=False)


class CommissiondarStockMovement(Base):
    __tablename__ = "commissiondar_stock_movements"

    id = Column(BigInteger, primary_key=True)

    commissiondar_id = Column(
        BigInteger,
        ForeignKey("parties.id"),
        nullable=False
    )
    farmer_id = Column(BigInteger, ForeignKey("parties.id"))
    business_id = Column(BigInteger, ForeignKey("businesses.id"))

    # Retained temporarily for old backend compatibility.
    item_id = Column(
        BigInteger,
        ForeignKey("items.id"),
        nullable=True
    )

    # New independent grain catalogue reference.
    grain_type_id = Column(
        BigInteger,
        ForeignKey("grain_types.id", ondelete="RESTRICT"),
        nullable=True
    )

    movement_type = Column(String, nullable=False)
    mill_name = Column(String(200))
    quantity = Column(Numeric(14, 3), nullable=False)
    rate = Column(Numeric(12, 2))

    movement_id = Column(
        BigInteger,
        ForeignKey("stock_movements.id")
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    is_void = Column(Boolean, nullable=False, default=False)


class LoginLog(Base):
    __tablename__ = "login_logs"

    id = Column(BigInteger, primary_key=True)
    phone = Column(String, nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    success = Column(Boolean, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


class IssueReport(Base):
    __tablename__ = "issue_reports"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id"))
    description = Column(String, nullable=False)
    status = Column(String, nullable=False, default="open")
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


class LoginChallenge(Base):
    __tablename__ = "login_challenges"

    id = Column(BigInteger, primary_key=True)

    challenge_id = Column(
        String(128),
        nullable=False,
        unique=True,
        index=True
    )

    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    expires_at = Column(
        DateTime(timezone=True),
        nullable=False
    )

    used = Column(
        Boolean,
        nullable=False,
        default=False
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )