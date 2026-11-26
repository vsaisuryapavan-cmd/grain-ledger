from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_admin
from app.models.core import Business, IssueReport, LoginLog, User
from app.schemas.admin import IssueReportCreate

router = APIRouter()


@router.post("/api/report-issue")
def report_issue(
    data: IssueReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        issue = IssueReport(
            user_id=current_user.id,
            description=data.description.strip(),
        )

        if not issue.description:
            raise HTTPException(
                status_code=400,
                detail="Issue description cannot be empty",
            )

        db.add(issue)
        db.commit()
        db.refresh(issue)

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to submit issue report",
        )

    return issue


@router.get("/api/admin/dashboard-summary")
def admin_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    # User registration counts
    total_millers = (
        db.query(func.count(User.id))
        .filter(User.role == "owner")
        .scalar() or 0
    )

    total_commissiondars = (
        db.query(func.count(User.id))
        .filter(User.role == "party")
        .scalar() or 0
    )

    approved_registrations = (
        db.query(func.count(User.id))
        .filter(
            User.role.in_(["owner", "party"]),
            User.approval_status == "approved",
        )
        .scalar() or 0
    )

    pending_registrations = (
        db.query(func.count(User.id))
        .filter(
            User.role.in_(["owner", "party"]),
            User.approval_status == "pending",
        )
        .scalar() or 0
    )

    rejected_registrations = (
        db.query(func.count(User.id))
        .filter(
            User.role.in_(["owner", "party"]),
            User.approval_status == "rejected",
        )
        .scalar() or 0
    )

    # Business counts (exclude system businesses)
    total_businesses = (
        db.query(func.count(Business.id))
        .filter(
            Business.business_type.in_(["mill", "commissiondar"])
        )
        .scalar() or 0
    )

    # Login activity
    total_login_attempts = (
        db.query(func.count(LoginLog.id)).scalar() or 0
    )

    successful_logins = (
        db.query(func.count(LoginLog.id))
        .filter(LoginLog.success == True)
        .scalar() or 0
    )

    failed_logins = (
        db.query(func.count(LoginLog.id))
        .filter(LoginLog.success == False)
        .scalar() or 0
    )

    # Issue reports
    total_issues = (
        db.query(func.count(IssueReport.id)).scalar() or 0
    )

    open_issues = (
        db.query(func.count(IssueReport.id))
        .filter(IssueReport.status == "open")
        .scalar() or 0
    )

    return {
        "users": {
            "total_millers": total_millers,
            "total_commissiondars": total_commissiondars,
        },
        "registrations": {
            "approved": approved_registrations,
            "pending": pending_registrations,
            "rejected": rejected_registrations,
        },
        "businesses": {
            "total": total_businesses,
        },
        "login_activity": {
            "total_attempts": total_login_attempts,
            "successful": successful_logins,
            "failed": failed_logins,
        },
        "issues": {
            "total": total_issues,
            "open": open_issues,
        },
    }


@router.get("/api/admin/login-logs")
def login_logs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return db.query(LoginLog).order_by(
        LoginLog.created_at.desc()
    ).limit(100).all()


@router.get("/api/admin/issues")
def list_issues(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return db.query(IssueReport).order_by(
        IssueReport.created_at.desc()
    ).all()


@router.get("/api/admin/registrations/pending")
def list_pending_registrations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    registrations = (
        db.query(User, Business.name.label("business_name"))
        .join(Business, User.business_id == Business.id)
        .filter(
            User.approval_status == "pending",
            User.role.in_(["owner", "party"]),
        )
        .order_by(User.created_at.asc())
        .all()
    )

    return [
        {
            "user_id": user.id,
            "name": user.name,
            "phone": user.phone,
            "role": user.role,
            "business_id": user.business_id,
            "business_name": business_name,
            "party_id": user.party_id,
            "approval_status": user.approval_status,
            "created_at": user.created_at,
        }
        for user, business_name in registrations
    ]


def review_registration(
    user_id: int,
    decision: str,
    db: Session,
    current_user: User,
):
    user = (
        db.query(User)
        .filter(User.id == user_id)
        .with_for_update()
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="Registration not found",
        )

    if user.role not in ["owner", "party"]:
        raise HTTPException(
            status_code=400,
            detail="This account cannot be reviewed as a registration",
        )

    if user.approval_status != "pending":
        raise HTTPException(
            status_code=409,
            detail="This registration has already been reviewed",
        )

    user.approval_status = decision
    user.reviewed_by = current_user.id
    user.reviewed_at = datetime.now(timezone.utc)

    db.commit()

    return {
        "message": f"Registration {decision} successfully",
        "user_id": user.id,
        "approval_status": user.approval_status,
        "reviewed_by": user.reviewed_by,
        "reviewed_at": user.reviewed_at,
    }


@router.post("/api/admin/registrations/{user_id}/approve")
def approve_registration(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return review_registration(
        user_id=user_id,
        decision="approved",
        db=db,
        current_user=current_user,
    )


@router.post("/api/admin/registrations/{user_id}/reject")
def reject_registration(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return review_registration(
        user_id=user_id,
        decision="rejected",
        db=db,
        current_user=current_user,
    )
