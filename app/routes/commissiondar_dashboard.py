from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_commissiondar
from app.models.commissiondar import (
    CommissiondarLoan,
    CommissiondarLoanRepayment,
    CommissiondarMill,
    CommissiondarMillCommission,
    CommissiondarMillCommissionReceipt,
    CommissiondarMillFarmer,
)
from app.models.core import User
from app.models.party import Party

router = APIRouter()


@router.get("/api/commissiondar-dashboard")
def commissiondar_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar),
):
    # -----------------------------------------
    # Existing Commissiondar loan calculations
    # -----------------------------------------
    loans = db.query(CommissiondarLoan).filter(
        CommissiondarLoan.commissiondar_id == current_user.party_id,
        CommissiondarLoan.is_void == False,
    ).all()

    total_lent = sum(
        float(loan.principal) for loan in loans
    )

    total_outstanding = 0.0

    for loan in loans:
        days_elapsed = max(
            0,
            (datetime.now(timezone.utc).date() - loan.issued_at).days,
        )

        interest = (
            float(loan.principal)
            * float(loan.interest_rate_pa)
            / 100
            * days_elapsed
            / 365
        )

        repaid = db.query(
            func.coalesce(
                func.sum(CommissiondarLoanRepayment.amount),
                0,
            )
        ).filter(
            CommissiondarLoanRepayment.loan_id == loan.id,
            CommissiondarLoanRepayment.is_void == False,
        ).scalar()

        total_outstanding += (
            float(loan.principal)
            + interest
            - float(repaid or 0)
        )

    # -----------------------------------------
    # Commissiondar's own mill commission ledger
    # -----------------------------------------
    commissions = db.query(CommissiondarMillCommission).filter(
        CommissiondarMillCommission.commissiondar_id == current_user.party_id,
        CommissiondarMillCommission.is_void == False,
    ).all()

    total_commissions_earned = 0.0
    total_commissions_received = 0.0
    latest_commission = None

    for commission in commissions:
        received = db.query(
            func.coalesce(
                func.sum(CommissiondarMillCommissionReceipt.amount),
                0,
            )
        ).filter(
            CommissiondarMillCommissionReceipt.commission_id == commission.id,
            CommissiondarMillCommissionReceipt.commissiondar_id == current_user.party_id,
            CommissiondarMillCommissionReceipt.is_void == False,
        ).scalar()

        earned_amount = float(commission.commission_amount)
        received_amount = float(received or 0)
        pending_amount = earned_amount - received_amount

        total_commissions_earned += earned_amount
        total_commissions_received += received_amount

        # Latest recorded commission = highest commission ID
        if (
            latest_commission is None
            or commission.id > latest_commission["id"]
        ):
            latest_commission = {
                "id": commission.id,
                "mill_id": commission.mill_id,
                "commission_amount": round(earned_amount, 2),
                "received_amount": round(received_amount, 2),
                "pending_amount": round(pending_amount, 2),
                "earned_at": str(commission.earned_at),
                "note": commission.note,
            }

    commissions_pending = (
        total_commissions_earned - total_commissions_received
    )

    # -----------------------------------------
    # Existing farmer count
    # -----------------------------------------
    farmer_count = db.query(func.count(Party.id)).filter(
        Party.business_id == current_user.business_id,
        Party.party_type == "farmer",
        Party.is_active == True,
    ).scalar() or 0

    # -----------------------------------------
    # Commissiondar's own mills and associations
    # -----------------------------------------
    active_mills = db.query(CommissiondarMill).filter(
        CommissiondarMill.commissiondar_id == current_user.party_id,
        CommissiondarMill.business_id == current_user.business_id,
        CommissiondarMill.is_active == True,
    ).all()

    total_mills = len(active_mills)

    associated_farmer_count = db.query(
        func.count(func.distinct(CommissiondarMillFarmer.farmer_id))
    ).filter(
        CommissiondarMillFarmer.commissiondar_id == current_user.party_id,
        CommissiondarMillFarmer.is_active == True,
    ).scalar() or 0

    # -----------------------------------------
    # Latest loan
    # -----------------------------------------
    latest_loan = db.query(CommissiondarLoan).filter(
        CommissiondarLoan.commissiondar_id == current_user.party_id,
        CommissiondarLoan.is_void == False,
    ).order_by(
        CommissiondarLoan.issued_at.desc(),
        CommissiondarLoan.id.desc(),
    ).first()

    # -----------------------------------------
    # Dashboard response
    # -----------------------------------------
    return {
        "active_loans": len(loans),
        "total_lent_out": round(total_lent, 2),
        "total_outstanding": round(total_outstanding, 2),
        "commissions_earned": round(total_commissions_earned, 2),
        "commissions_received": round(total_commissions_received, 2),
        "commissions_pending": round(commissions_pending, 2),
        "total_farmers": farmer_count,
        "total_mills": total_mills,
        "associated_farmers": associated_farmer_count,
        "latest_loan": (
            {
                "id": latest_loan.id,
                "farmer_id": latest_loan.farmer_id,
                "principal": float(latest_loan.principal),
                "issued_at": str(latest_loan.issued_at),
            }
            if latest_loan else None
        ),
        "latest_commission": latest_commission,
    }
