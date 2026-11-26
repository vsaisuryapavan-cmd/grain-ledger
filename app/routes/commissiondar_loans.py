from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_commissiondar
from app.models.commissiondar import (
    CommissiondarLoan,
    CommissiondarLoanRepayment,
)
from app.models.core import User
from app.models.party import Party
from app.schemas.commissiondar import LoanCreate, RepaymentCreate

router = APIRouter()


@router.post("/api/commissiondar-loans")
def create_loan(
    data: LoanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar),
):
    farmer = db.query(Party).filter(
        Party.id == data.farmer_id,
        Party.business_id == current_user.business_id,
        Party.party_type == "farmer",
        Party.is_active == True,
    ).first()

    if not farmer:
        raise HTTPException(
            status_code=404,
            detail="Farmer not found or inactive",
        )

    try:
        loan = CommissiondarLoan(
            commissiondar_id=current_user.party_id,
            farmer_id=data.farmer_id,
            principal=data.principal,
            interest_rate_pa=data.interest_rate_pa,
        )

        db.add(loan)
        db.commit()
        db.refresh(loan)

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to create loan",
        )

    return loan


@router.get("/api/commissiondar-loans")
def list_my_loans(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar),
):
    loans = db.query(CommissiondarLoan).filter(
        CommissiondarLoan.commissiondar_id == current_user.party_id,
        CommissiondarLoan.is_void == False,
    ).all()

    result = []

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

        farmer = db.query(Party).filter(
            Party.id == loan.farmer_id,
            Party.business_id == current_user.business_id,
            Party.party_type == "farmer",
        ).first()
        result.append({
            "id": loan.id,
            "farmer_id": loan.farmer_id,
            "farmer_name": farmer.name if farmer else None,
            "principal": loan.principal,
            "interest_rate_pa": loan.interest_rate_pa,
            "interest_accrued": round(interest, 2),
            "total_repaid": repaid,
            "outstanding": round(
                float(loan.principal) + interest - float(repaid or 0),
                2,
            ),
            "status": loan.status,
        })

    return result


@router.post("/api/commissiondar-loans/repay")
def repay_loan(
    data: RepaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_commissiondar),
):
    loan = db.query(CommissiondarLoan).filter(
        CommissiondarLoan.id == data.loan_id,
        CommissiondarLoan.commissiondar_id == current_user.party_id,
        CommissiondarLoan.is_void == False,
    ).first()

    if not loan:
        raise HTTPException(
            status_code=404,
            detail="Loan not found",
        )

    try:
        repayment = CommissiondarLoanRepayment(
            loan_id=data.loan_id,
            amount=data.amount,
        )

        db.add(repayment)
        db.commit()
        db.refresh(repayment)

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to record repayment",
        )

    return repayment
