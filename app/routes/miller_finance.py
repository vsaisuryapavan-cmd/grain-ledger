from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_owner
from app.models.core import User
from app.models.miller import (
    BrokerCommission,
    LedgerEntry,
    MillCommissiondarLoan,
    MillCommissiondarLoanRepayment,
    Payment,
    StockMovement,
)
from app.models.party import Party
from app.schemas.miller import (
    CommissionPay,
    MillLoanCreate,
    MillRepaymentCreate,
    PaymentCreate,
)
from app.services.db_helpers import get_active_farmer

router = APIRouter()


@router.post("/api/payments")
def record_payment(
    data: PaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    get_active_farmer(
        db,
        data.farmer_id,
        current_user.business_id,
    )

    mode = data.mode.strip().lower() if data.mode else None

    if mode == "":
        mode = None

    try:
        payment = Payment(
            business_id=current_user.business_id,
            party_id=data.farmer_id,
            direction="paid",
            amount=data.amount,
            mode=mode,
            created_by=current_user.id,
        )

        db.add(payment)
        db.flush()

        ledger = LedgerEntry(
            business_id=current_user.business_id,
            party_id=data.farmer_id,
            credit=data.amount,
            payment_id=payment.id,
        )

        db.add(ledger)
        db.commit()

        db.refresh(payment)
        db.refresh(ledger)

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to record payment",
        )

    return {
        "payment": payment,
        "ledger_entry": ledger,
    }


@router.get("/api/dashboard")
def dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    business_id = current_user.business_id

    total_stock = db.query(
        func.coalesce(
            func.sum(StockMovement.quantity),
            0,
        )
    ).filter(
        StockMovement.business_id == business_id,
        StockMovement.is_void == False,
    ).scalar()

    ledger_balance = db.query(
        func.coalesce(
            func.sum(LedgerEntry.debit - LedgerEntry.credit),
            0,
        )
    ).filter(
        LedgerEntry.business_id == business_id,
        LedgerEntry.is_void == False,
    ).scalar()

    opening_balances = db.query(
        func.coalesce(
            func.sum(Party.opening_balance),
            0,
        )
    ).filter(
        Party.business_id == business_id,
        Party.is_active == True,
    ).scalar()

    total_owed = Decimal(str(ledger_balance or 0)) + Decimal(
        str(opening_balances or 0)
    )

    today = datetime.now(timezone.utc).date()

    today_intake = db.query(
        func.coalesce(
            func.sum(StockMovement.quantity),
            0,
        )
    ).filter(
        StockMovement.business_id == business_id,
        StockMovement.movement_type == "purchase",
        StockMovement.is_void == False,
        func.date(StockMovement.moved_at) == today,
    ).scalar()

    seven_days_ago = today - timedelta(days=6)
    last_seven_days_intake = db.query(
        func.coalesce(func.sum(StockMovement.quantity), 0)
    ).filter(
        StockMovement.business_id == business_id,
        StockMovement.movement_type == "purchase",
        StockMovement.is_void == False,
        func.date(StockMovement.moved_at) >= seven_days_ago,
        func.date(StockMovement.moved_at) <= today,
    ).scalar() or 0
    total_farmers = db.query(func.count(Party.id)).filter(
        Party.business_id == business_id,
        Party.party_type == "farmer",
        Party.is_active == True,
    ).scalar() or 0
    last_seven_days_records = db.query(StockMovement).filter(
        StockMovement.business_id == business_id,
        StockMovement.movement_type == "purchase",
        StockMovement.is_void == False,
        func.date(StockMovement.moved_at) >= seven_days_ago,
        func.date(StockMovement.moved_at) <= today,
    ).order_by(StockMovement.moved_at.desc()).all()
    return {
        "total_stock": total_stock,
        "total_owed": float(total_owed),
        "today_intake": today_intake,
        "total_farmers": int(total_farmers),
        "last_seven_days_intake": float(last_seven_days_intake),
        "last_seven_days_records": last_seven_days_records,
        "total_commissiondars": db.query(func.count(Party.id)).filter(
            Party.business_id == business_id,
            Party.party_type == "commissiondar",
            Party.is_active == True,
        ).scalar() or 0,
    }


@router.get("/api/profit")
def profit_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    revenue = db.query(
        func.coalesce(
            func.sum(
                StockMovement.quantity * StockMovement.rate
            ),
            0,
        )
    ).filter(
        StockMovement.business_id == current_user.business_id,
        StockMovement.movement_type == "sale",
        StockMovement.is_void == False,
    ).scalar()

    cost = db.query(
        func.coalesce(
            func.sum(
                StockMovement.quantity * StockMovement.rate
            ),
            0,
        )
    ).filter(
        StockMovement.business_id == current_user.business_id,
        StockMovement.movement_type == "purchase",
        StockMovement.is_void == False,
    ).scalar()

    commissions_paid = db.query(
        func.coalesce(
            func.sum(BrokerCommission.commission_amount),
            0,
        )
    ).filter(
        BrokerCommission.business_id == current_user.business_id,
        BrokerCommission.is_paid == True,
        BrokerCommission.is_void == False,
    ).scalar()

    revenue = abs(float(revenue or 0))
    cost = float(cost or 0)
    commissions_paid = float(commissions_paid or 0)

    profit = revenue - cost - commissions_paid

    return {
        "revenue": round(revenue, 2),
        "cost_of_paddy": round(cost, 2),
        "commissions_paid": round(commissions_paid, 2),
        "profit": round(profit, 2),
    }


@router.post("/api/mill-loans")
def create_mill_loan(
    data: MillLoanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    commissiondar = db.query(Party).filter(
        Party.id == data.commissiondar_id,
        Party.business_id == current_user.business_id,
        Party.party_type == "commissiondar",
        Party.is_active == True,
    ).first()

    if not commissiondar:
        raise HTTPException(
            status_code=404,
            detail="Commissiondar not found or inactive",
        )

    try:
        loan = MillCommissiondarLoan(
            business_id=current_user.business_id,
            commissiondar_id=data.commissiondar_id,
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
            detail="Failed to create mill loan",
        )

    return loan


@router.get("/api/mill-loans")
def list_mill_loans(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    loans = db.query(MillCommissiondarLoan).filter(
        MillCommissiondarLoan.business_id == current_user.business_id,
        MillCommissiondarLoan.is_void == False,
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
                func.sum(MillCommissiondarLoanRepayment.amount),
                0,
            )
        ).filter(
            MillCommissiondarLoanRepayment.loan_id == loan.id,
            MillCommissiondarLoanRepayment.is_void == False,
        ).scalar()

        result.append({
            "id": loan.id,
            "commissiondar_id": loan.commissiondar_id,
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


@router.post("/api/mill-loans/repay")
def repay_mill_loan(
    data: MillRepaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    loan = db.query(MillCommissiondarLoan).filter(
        MillCommissiondarLoan.id == data.loan_id,
        MillCommissiondarLoan.business_id == current_user.business_id,
        MillCommissiondarLoan.is_void == False,
    ).first()

    if not loan:
        raise HTTPException(
            status_code=404,
            detail="Loan not found",
        )

    try:
        repayment = MillCommissiondarLoanRepayment(
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
            detail="Failed to record mill loan repayment",
        )

    return repayment


@router.get("/api/broker-commissions")
def list_commissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    return db.query(BrokerCommission).filter(
        BrokerCommission.business_id == current_user.business_id,
        BrokerCommission.is_void == False,
    ).all()


@router.post("/api/broker-commissions/pay")
def pay_commission(
    data: CommissionPay,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_owner),
):
    commission = db.query(BrokerCommission).filter(
        BrokerCommission.id == data.commission_id,
        BrokerCommission.business_id == current_user.business_id,
        BrokerCommission.is_void == False,
    ).first()

    if not commission:
        raise HTTPException(
            status_code=404,
            detail="Commission not found",
        )

    if commission.is_paid:
        raise HTTPException(
            status_code=400,
            detail="Commission is already paid",
        )

    try:
        commission.is_paid = True
        db.commit()
        db.refresh(commission)

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to update commission payment",
        )

    return commission
