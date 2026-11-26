from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
)
from sqlalchemy import func

from app.core.database import Base


class Item(Base):
    __tablename__ = "items"

    id = Column(BigInteger, primary_key=True)
    business_id = Column(
        BigInteger,
        ForeignKey("businesses.id"),
        nullable=False,
    )
    name = Column(String, nullable=False)
    category = Column(String)
    unit = Column(String, nullable=False)
    sku = Column(String)
    sale_price = Column(Numeric(12, 2))
    gst_rate = Column(Numeric(5, 2), default=0)
    reorder_level = Column(Numeric(12, 3))
    is_active = Column(Boolean, nullable=False, default=True)


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(BigInteger, primary_key=True)
    business_id = Column(
        BigInteger,
        ForeignKey("businesses.id"),
        nullable=False,
    )
    item_id = Column(
        BigInteger,
        ForeignKey("items.id"),
        nullable=False,
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
        server_default=func.now(),
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
        nullable=False,
    )
    party_id = Column(
        BigInteger,
        ForeignKey("parties.id"),
        nullable=False,
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
        nullable=False,
    )
    party_id = Column(
        BigInteger,
        ForeignKey("parties.id"),
        nullable=False,
    )
    direction = Column(String, nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    mode = Column(String)
    paid_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    note = Column(String)
    created_by = Column(BigInteger, ForeignKey("users.id"))
    is_void = Column(Boolean, nullable=False, default=False)


class MillCommissiondarLoan(Base):
    __tablename__ = "mill_commissiondar_loans"

    id = Column(BigInteger, primary_key=True)
    business_id = Column(
        BigInteger,
        ForeignKey("businesses.id"),
        nullable=False,
    )
    commissiondar_id = Column(
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


class MillCommissiondarLoanRepayment(Base):
    __tablename__ = "mill_commissiondar_loan_repayments"

    id = Column(BigInteger, primary_key=True)
    loan_id = Column(
        BigInteger,
        ForeignKey("mill_commissiondar_loans.id"),
        nullable=False,
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
        nullable=False,
    )
    commissiondar_id = Column(
        BigInteger,
        ForeignKey("parties.id"),
        nullable=False,
    )
    farmer_id = Column(BigInteger, ForeignKey("parties.id"))
    movement_id = Column(
        BigInteger,
        ForeignKey("stock_movements.id"),
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
        server_default=func.now(),
    )
    is_void = Column(Boolean, nullable=False, default=False)
