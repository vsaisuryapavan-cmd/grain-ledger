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