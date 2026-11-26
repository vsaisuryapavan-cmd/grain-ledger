from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Numeric,
    String,
)
from sqlalchemy import func

from app.core.database import Base


class Party(Base):
    __tablename__ = "parties"

    id = Column(BigInteger, primary_key=True)
    business_id = Column(
        BigInteger,
        ForeignKey("businesses.id"),
        nullable=False,
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
        nullable=True,
    )
    opening_balance = Column(
        Numeric(14, 2),
        nullable=False,
        default=0,
    )
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "party_type IN ('farmer', 'customer', 'supplier', 'buyer', 'commissiondar')",
            name="parties_party_type_check",
        ),
    )
