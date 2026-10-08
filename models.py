from sqlalchemy import Column, BigInteger, String, Numeric, Boolean, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.sql import func
from database import Base


class Business(Base):
    __tablename__ = "businesses"

    id            = Column(BigInteger, primary_key=True)
    name          = Column(String, nullable=False)
    business_type = Column(String, nullable=False)
    phone         = Column(String)
    address       = Column(String)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())


class Party(Base):
    __tablename__ = "parties"

    id              = Column(BigInteger, primary_key=True)
    business_id     = Column(BigInteger, ForeignKey("businesses.id"), nullable=False)
    name            = Column(String, nullable=False)
    phone           = Column(String)
    village         = Column(String)
    party_type      = Column(String, nullable=False)
    opening_balance = Column(Numeric(14, 2), nullable=False, default=0)
    is_active       = Column(Boolean, nullable=False, default=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "party_type IN ('farmer', 'customer', 'supplier', 'buyer', 'commissiondar')",
            name="parties_party_type_check"
        ),
    )


class Item(Base):
    __tablename__ = "items"

    id            = Column(BigInteger, primary_key=True)
    business_id   = Column(BigInteger, ForeignKey("businesses.id"), nullable=False)
    name          = Column(String, nullable=False)
    category      = Column(String)
    unit          = Column(String, nullable=False)
    sku           = Column(String)
    sale_price    = Column(Numeric(12, 2))
    gst_rate      = Column(Numeric(5, 2), default=0)
    reorder_level = Column(Numeric(12, 3))
    is_active     = Column(Boolean, nullable=False, default=True)


class User(Base):
    __tablename__ = "users"

    id          = Column(BigInteger, primary_key=True)
    business_id = Column(BigInteger, ForeignKey("businesses.id"), nullable=False)
    name        = Column(String, nullable=False)
    phone       = Column(String, nullable=False, unique=True)
    role        = Column(String, nullable=False)
    party_id    = Column(BigInteger, ForeignKey("parties.id"))
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id            = Column(BigInteger, primary_key=True)
    business_id   = Column(BigInteger, ForeignKey("businesses.id"), nullable=False)
    item_id       = Column(BigInteger, ForeignKey("items.id"), nullable=False)
    party_id      = Column(BigInteger, ForeignKey("parties.id"))
    movement_type = Column(String, nullable=False)
    quantity      = Column(Numeric(14, 3), nullable=False)
    rate          = Column(Numeric(12, 2))
    moisture_pct  = Column(Numeric(5, 2))
    moved_at      = Column(DateTime(timezone=True), server_default=func.now())
    note          = Column(String)
    created_by    = Column(BigInteger, ForeignKey("users.id"))
    broker_id     = Column(BigInteger, ForeignKey("parties.id"))
    is_void       = Column(Boolean, nullable=False, default=False)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id          = Column(BigInteger, primary_key=True)
    business_id = Column(BigInteger, ForeignKey("businesses.id"), nullable=False)
    party_id    = Column(BigInteger, ForeignKey("parties.id"), nullable=False)
    entry_date  = Column(DateTime, server_default=func.now())
    debit       = Column(Numeric(14, 2), nullable=False, default=0)
    credit      = Column(Numeric(14, 2), nullable=False, default=0)
    movement_id = Column(BigInteger, ForeignKey("stock_movements.id"))
    payment_id  = Column(BigInteger)
    note        = Column(String)
    is_void     = Column(Boolean, nullable=False, default=False)


class Payment(Base):
    __tablename__ = "payments"

    id          = Column(BigInteger, primary_key=True)
    business_id = Column(BigInteger, ForeignKey("businesses.id"), nullable=False)
    party_id    = Column(BigInteger, ForeignKey("parties.id"), nullable=False)
    direction   = Column(String, nullable=False)
    amount      = Column(Numeric(14, 2), nullable=False)
    mode        = Column(String)  # optional, as decided earlier
    paid_at     = Column(DateTime(timezone=True), server_default=func.now())
    note        = Column(String)
    created_by  = Column(BigInteger, ForeignKey("users.id"))
    is_void     = Column(Boolean, nullable=False, default=False)


class CommissiondarLoan(Base):
    __tablename__ = "commissiondar_loans"

    id               = Column(BigInteger, primary_key=True)
    commissiondar_id = Column(BigInteger, ForeignKey("parties.id"), nullable=False)
    farmer_id        = Column(BigInteger, ForeignKey("parties.id"), nullable=False)
    principal        = Column(Numeric(14, 2), nullable=False)
    interest_rate_pa = Column(Numeric(5, 2), nullable=False, default=0)
    issued_at        = Column(DateTime, server_default=func.now())
    status           = Column(String, nullable=False, default="open")
    note             = Column(String)
    is_void          = Column(Boolean, nullable=False, default=False)


class CommissiondarLoanRepayment(Base):
    __tablename__ = "commissiondar_loan_repayments"

    id        = Column(BigInteger, primary_key=True)
    loan_id   = Column(BigInteger, ForeignKey("commissiondar_loans.id"), nullable=False)
    amount    = Column(Numeric(14, 2), nullable=False)
    paid_at   = Column(DateTime, server_default=func.now())
    note      = Column(String)
    is_void   = Column(Boolean, nullable=False, default=False)