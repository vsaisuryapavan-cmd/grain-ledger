from decimal import Decimal
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.miller import LedgerEntry
from app.models.party import Party


def farmer_balance(db: Session, farmer: Party, business_id: int):
    """
    Outstanding balance =
    opening balance + non-voided ledger debits - credits.
    """
    ledger_balance = db.query(
        func.coalesce(
            func.sum(LedgerEntry.debit - LedgerEntry.credit),
            0,
        )
    ).filter(
        LedgerEntry.party_id == farmer.id,
        LedgerEntry.business_id == business_id,
        LedgerEntry.is_void == False,
    ).scalar()

    return Decimal(str(farmer.opening_balance or 0)) + Decimal(
        str(ledger_balance or 0)
    )
