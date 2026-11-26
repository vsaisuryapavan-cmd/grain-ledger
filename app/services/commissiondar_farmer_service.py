
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.commissiondar import (
    CommissiondarLoan,
    CommissiondarLoanRepayment,
    CommissiondarStockMovement,
)
from app.models.core import Business
from app.models.miller import Payment


def get_farmer_account_summary(
    db: Session,
    commissiondar_id: int,
    business_id: int,
    farmer_id: int,
):
    """Calculate one farmer's stock, purchases, payments, loans and settlement."""

    # Verify this is a valid Commissiondar business.
    business = db.query(Business).filter(
        Business.id == business_id,
        Business.business_type == "commissiondar",
    ).first()

    if not business:
        raise ValueError("Invalid Commissiondar business")

    # Fetch only this Commissiondar's movements for this farmer.
    movements = db.query(CommissiondarStockMovement).filter(
        CommissiondarStockMovement.commissiondar_id == commissiondar_id,
        CommissiondarStockMovement.farmer_id == farmer_id,
        CommissiondarStockMovement.is_void == False,
    ).all()

    received_quantity = Decimal("0")
    delivered_quantity = Decimal("0")
    purchase_value = Decimal("0")
    quantity_without_rate = Decimal("0")

    for movement in movements:
        quantity = Decimal(str(movement.quantity or 0))

        if movement.movement_type == "received_from_farmer":
            received_quantity += quantity

            if movement.rate is None:
                quantity_without_rate += quantity
            else:
                purchase_value += (
                    quantity * Decimal(str(movement.rate))
                )

        elif movement.movement_type == "delivered_to_mill":
            delivered_quantity += abs(quantity)

    # Commissiondar payments made to this farmer.
    payments = db.query(
        func.coalesce(func.sum(Payment.amount), 0)
    ).filter(
        Payment.business_id == business_id,
        Payment.party_id == farmer_id,
        Payment.direction == "paid",
        Payment.is_void == False,
    ).scalar()

    total_payments = Decimal(str(payments or 0))

    # Calculate outstanding loans and advances.
    loans = db.query(CommissiondarLoan).filter(
        CommissiondarLoan.commissiondar_id == commissiondar_id,
        CommissiondarLoan.farmer_id == farmer_id,
        CommissiondarLoan.is_void == False,
    ).all()

    loan_outstanding = Decimal("0")
    today = datetime.now(timezone.utc).date()

    for loan in loans:
        days_elapsed = max(
            0,
            (today - loan.issued_at).days,
        )

        principal = Decimal(str(loan.principal))
        interest_rate = Decimal(str(loan.interest_rate_pa or 0))

        interest = (
            principal
            * interest_rate
            / Decimal("100")
            * Decimal(days_elapsed)
            / Decimal("365")
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

        loan_balance = (
            principal
            + interest
            - Decimal(str(repaid or 0))
        )

        loan_outstanding += max(
            Decimal("0"),
            loan_balance,
        )

    # Calculate final settlement.
    # Missing purchase rates mean the settlement is incomplete.
    if quantity_without_rate > 0:
        settlement = {
            "status": "incomplete_purchase_rates",
            "payable_by": None,
            "payable_to": None,
            "amount": None,
            "message": (
                f"Settlement incomplete: purchase rates are missing "
                f"for {quantity_without_rate} quantity"
            ),
        }

    else:
        # Positive: Commissiondar owes farmer.
        # Negative: Farmer owes Commissiondar.
        net_settlement = (
            purchase_value
            - total_payments
            - loan_outstanding
        )

        if net_settlement > 0:
            settlement = {
                "status": "commissiondar_owes_farmer",
                "payable_by": "commissiondar",
                "payable_to": "farmer",
                "amount": round(float(net_settlement), 2),
                "message": (
                    f"Commissiondar should pay farmer "
                    f"₹{net_settlement:,.2f}"
                ),
            }

        elif net_settlement < 0:
            amount_due = abs(net_settlement)

            settlement = {
                "status": "farmer_owes_commissiondar",
                "payable_by": "farmer",
                "payable_to": "commissiondar",
                "amount": round(float(amount_due), 2),
                "message": (
                    f"Farmer should pay Commissiondar "
                    f"₹{amount_due:,.2f}"
                ),
            }

        else:
            settlement = {
                "status": "settled",
                "payable_by": None,
                "payable_to": None,
                "amount": 0.0,
                "message": "Account settled",
            }

    return {
        "stock": {
            "received": float(received_quantity),
            "delivered_to_mills": float(delivered_quantity),
            "remaining": float(
                received_quantity - delivered_quantity
            ),
        },
        "purchases": {
            "total_value": round(float(purchase_value), 2),
            "quantity_without_rate": float(quantity_without_rate),
        },
        "payments": {
            "total_paid": round(float(total_payments), 2),
        },
        "loans": {
            "active_loans": len(loans),
            "outstanding": round(float(loan_outstanding), 2),
        },
        "settlement": settlement,
    }
