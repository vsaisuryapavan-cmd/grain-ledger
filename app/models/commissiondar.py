from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy import func

from app.core.database import Base


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
        nullable=True,
    )

    created_by_user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint(
            "LENGTH(TRIM(name)) > 0",
            name="grain_types_name_not_empty",
        ),
        CheckConstraint(
            "LENGTH(TRIM(unit)) > 0",
            name="grain_types_unit_not_empty",
        ),
        Index(
            "uq_grain_types_global_name",
            func.lower(name),
            unique=True,
            postgresql_where=(owner_business_id.is_(None)),
        ),
        Index(
            "uq_grain_types_business_name",
            owner_business_id,
            func.lower(name),
            unique=True,
            postgresql_where=(owner_business_id.isnot(None)),
        ),
    )


class CommissiondarLoan(Base):
    __tablename__ = "commissiondar_loans"

    id = Column(BigInteger, primary_key=True)
    commissiondar_id = Column(
        BigInteger,
        ForeignKey("parties.id"),
        nullable=False,
    )
    farmer_id = Column(
        BigInteger,
        ForeignKey("parties.id"),
        nullable=False,
    )
    principal = Column(Numeric(14, 2), nullable=False)
    interest_rate_pa = Column(
        Numeric(5, 2),
        nullable=False,
        default=0,
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
        nullable=False,
    )
    amount = Column(Numeric(14, 2), nullable=False)
    paid_at = Column(Date, server_default=func.now())
    note = Column(String)
    is_void = Column(Boolean, nullable=False, default=False)


class CommissiondarStockMovement(Base):
    __tablename__ = "commissiondar_stock_movements"

    id = Column(BigInteger, primary_key=True)

    commissiondar_id = Column(
        BigInteger,
        ForeignKey("parties.id"),
        nullable=False,
    )
    farmer_id = Column(BigInteger, ForeignKey("parties.id"))
    business_id = Column(BigInteger, ForeignKey("businesses.id"))

    # Retained temporarily for old backend compatibility.
    item_id = Column(
        BigInteger,
        ForeignKey("items.id"),
        nullable=True,
    )

    # New independent grain catalogue reference.
    grain_type_id = Column(
        BigInteger,
        ForeignKey("grain_types.id", ondelete="RESTRICT"),
        nullable=True,
    )

    movement_type = Column(String, nullable=False)
    mill_name = Column(String(200))
    quantity = Column(Numeric(14, 3), nullable=False)
    rate = Column(Numeric(12, 2))

    movement_id = Column(
        BigInteger,
        ForeignKey("stock_movements.id"),
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    is_void = Column(Boolean, nullable=False, default=False)


class CommissiondarMill(Base):
    __tablename__ = "commissiondar_mills"

    id = Column(BigInteger, primary_key=True)

    commissiondar_id = Column(
        BigInteger,
        ForeignKey("parties.id"),
        nullable=False,
    )
    business_id = Column(
        BigInteger,
        ForeignKey("businesses.id"),
        nullable=False,
    )

    name = Column(String(200), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "commissiondar_id",
            "name",
            name="uq_commissiondar_mill_name",
        ),
        CheckConstraint(
            "LENGTH(TRIM(name)) > 0",
            name="commissiondar_mill_name_not_empty",
        ),
    )


class CommissiondarMillFarmer(Base):
    __tablename__ = "commissiondar_mill_farmers"

    id = Column(BigInteger, primary_key=True)

    commissiondar_id = Column(
        BigInteger,
        ForeignKey("parties.id"),
        nullable=False,
    )
    mill_id = Column(
        BigInteger,
        ForeignKey("commissiondar_mills.id"),
        nullable=False,
    )
    farmer_id = Column(
        BigInteger,
        ForeignKey("parties.id"),
        nullable=False,
    )

    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "mill_id",
            "farmer_id",
            name="uq_commissiondar_mill_farmer",
        ),
    )


class CommissiondarMillCommission(Base):
    __tablename__ = "commissiondar_mill_commissions"

    id = Column(BigInteger, primary_key=True)

    commissiondar_id = Column(
        BigInteger,
        ForeignKey("parties.id"),
        nullable=False,
    )
    mill_id = Column(
        BigInteger,
        ForeignKey("commissiondar_mills.id"),
        nullable=False,
    )

    commission_amount = Column(Numeric(14, 2), nullable=False)

    earned_at = Column(
        Date,
        server_default=func.now(),
        nullable=False,
    )
    note = Column(String)

    is_void = Column(Boolean, nullable=False, default=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "commission_amount > 0",
            name="commissiondar_mill_commission_positive",
        ),
    )


class CommissiondarMillCommissionReceipt(Base):
    __tablename__ = "commissiondar_mill_commission_receipts"

    id = Column(BigInteger, primary_key=True)

    commissiondar_id = Column(
        BigInteger,
        ForeignKey("parties.id"),
        nullable=False,
    )
    commission_id = Column(
        BigInteger,
        ForeignKey("commissiondar_mill_commissions.id"),
        nullable=False,
    )

    amount = Column(Numeric(14, 2), nullable=False)

    received_at = Column(
        Date,
        server_default=func.now(),
        nullable=False,
    )
    note = Column(String)

    is_void = Column(Boolean, nullable=False, default=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="commissiondar_mill_receipt_positive",
        ),
    )
