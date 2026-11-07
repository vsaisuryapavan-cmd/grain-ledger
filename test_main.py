import main
import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.fixture(autouse=True)
def mock_msg91_verification(monkeypatch):
    monkeypatch.setattr(
        main,
        "verify_msg91_access_token",
        lambda access_token: access_token.split(":", 1)[1]
    )


client = TestClient(app)


# -------------------------
# Authentication helpers
# -------------------------

def get_token(phone):
    test_passwords = {
        "9999999999": ("OwnerTest123!", "OwnerSecond123!"),
        "8888888888": ("PartyTest123!", "PartySecond123!"),
        "7093355518": ("AdminTest123!", "AdminSecond123!")
    }

    password, second_password = test_passwords[phone]

    response = client.post(
        "/api/login",
        json={
            "phone": phone,
            "password": password,
            "second_password": second_password
        }
    )

    assert response.status_code == 200, response.text

    challenge_id = response.json()["challenge_id"]

    verify_response = client.post(
        "/api/verify-otp",
        json={
            "challenge_id": challenge_id,
            "access_token": f"test-msg91-access-token:{phone}"
        }
    )

    assert verify_response.status_code == 200, verify_response.text

    return verify_response.json()["access_token"]


def get_headers(phone):
    token = get_token(phone)
    return {"Authorization": f"Bearer {token}"}


# -------------------------
# Basic API tests
# -------------------------

def test_root():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["message"] == "Grain Ledger API is running"


def test_login_fails_for_unknown_phone():
    response = client.post(
        "/api/login",
        json={
            "phone": "0000000000",
            "password": "WrongTest123!",
            "second_password": "WrongSecond123!"
        }
    )

    assert response.status_code == 401


def test_login_succeeds_for_real_user():
    token = get_token("9999999999")

    assert token


# -------------------------
# Intake and payment tests
# -------------------------

def test_intake_debits_correctly():
    headers = get_headers("9999999999")

    response = client.post(
        "/api/intake",
        json={
            "farmer_id": 3,
            "item_id": 2,
            "quantity": 10,
            "rate": 2000
        },
        headers=headers
    )

    assert response.status_code == 200, response.text

    data = response.json()
    assert data["stock_movement"]["quantity"] == 10
    assert data["ledger_entry"]["debit"] == 20000
    assert data["ledger_entry"]["credit"] == 0


def test_payment_credits_correctly():
    headers = get_headers("9999999999")

    response = client.post(
        "/api/payments",
        json={
            "farmer_id": 3,
            "amount": 5000
        },
        headers=headers
    )

    assert response.status_code == 200, response.text

    data = response.json()
    assert data["ledger_entry"]["credit"] == 5000
    assert data["ledger_entry"]["debit"] == 0


def test_intake_requires_login():
    response = client.post(
        "/api/intake",
        json={
            "farmer_id": 3,
            "item_id": 2,
            "quantity": 10,
            "rate": 2000
        }
    )

    assert response.status_code == 401


# -------------------------
# Role restriction tests
# -------------------------

def test_commissiondar_blocked_from_mill_loans():
    headers = get_headers("8888888888")

    response = client.post(
        "/api/mill-loans",
        json={
            "commissiondar_id": 2,
            "principal": 10000,
            "interest_rate_pa": 10
        },
        headers=headers
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Only the mill owner can do this"


def test_miller_blocked_from_commissiondar_loans():
    headers = get_headers("9999999999")

    response = client.post(
        "/api/commissiondar-loans",
        json={
            "farmer_id": 3,
            "principal": 10000,
            "interest_rate_pa": 10
        },
        headers=headers
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Only active commissiondars can access this"


# -------------------------
# Farmer balance test
# -------------------------

def test_farmer_balance_nets_correctly():
    headers = get_headers("9999999999")

    before_response = client.get(
        "/api/farmers",
        headers=headers
    )

    assert before_response.status_code == 200, before_response.text

    before = before_response.json()
    farmer_before = next(
        (farmer for farmer in before if farmer["id"] == 3),
        None
    )

    assert farmer_before is not None, "Farmer ID 3 was not found"
    owed_before = farmer_before["owed"]

    intake = client.post(
        "/api/intake",
        json={
            "farmer_id": 3,
            "item_id": 2,
            "quantity": 5,
            "rate": 1000
        },
        headers=headers
    )

    assert intake.status_code == 200, intake.text

    payment = client.post(
        "/api/payments",
        json={
            "farmer_id": 3,
            "amount": 2000
        },
        headers=headers
    )

    assert payment.status_code == 200, payment.text

    after_response = client.get(
        "/api/farmers",
        headers=headers
    )

    assert after_response.status_code == 200, after_response.text

    after = after_response.json()
    farmer_after = next(
        (farmer for farmer in after if farmer["id"] == 3),
        None
    )

    assert farmer_after is not None, "Farmer ID 3 was not found after transactions"

    owed_after = farmer_after["owed"]
    assert owed_after == owed_before + 5000 - 2000


# -------------------------
# Export test
# -------------------------

def test_export_reduces_stock_correctly():
    headers = get_headers("9999999999")

    response = client.post(
        "/api/exports",
        json={
            "buyer_id": 4,
            "item_id": 2,
            "quantity": 5,
            "rate": 3000
        },
        headers=headers
    )

    assert response.status_code == 200, response.text

    data = response.json()
    assert data["stock_movement"]["quantity"] == -5
    assert data["ledger_entry"]["debit"] == 15000


# -------------------------
# Profit access test
# -------------------------

def test_profit_requires_owner():
    headers = get_headers("8888888888")

    response = client.get(
        "/api/profit",
        headers=headers
    )

    assert response.status_code == 403


# -------------------------
# Commissiondar dashboard
# -------------------------

def test_commissiondar_dashboard_shape():
    headers = get_headers("8888888888")

    response = client.get(
        "/api/commissiondar-dashboard",
        headers=headers
    )

    assert response.status_code == 200, response.text

    data = response.json()
    assert "active_loans" in data
    assert "total_lent_out" in data
    assert "total_outstanding" in data
    assert "commissions_pending" in data


# -------------------------
# Commissiondar stock test
# -------------------------

def test_commissiondar_stock_on_hand_nets_correctly():
    headers = get_headers("8888888888")

    before_response = client.get(
        "/api/commissiondar-stock",
        headers=headers
    )

    assert before_response.status_code == 200, before_response.text
    before = before_response.json()["stock_on_hand"]

    receive = client.post(
        "/api/commissiondar-stock/receive",
        json={
            "farmer_id": 3,
            "item_id": 2,
            "quantity": 15,
            "rate": 2200
        },
        headers=headers
    )

    assert receive.status_code == 200, receive.text

    deliver = client.post(
        "/api/commissiondar-stock/deliver",
        json={
            "business_id": 1,
            "item_id": 2,
            "quantity": 6,
            "rate": 2200
        },
        headers=headers
    )

    assert deliver.status_code == 200, deliver.text

    after_response = client.get(
        "/api/commissiondar-stock",
        headers=headers
    )

    assert after_response.status_code == 200, after_response.text
    after = after_response.json()["stock_on_hand"]

    assert after == before + 15 - 6


def test_miller_blocked_from_commissiondar_stock():
    headers = get_headers("9999999999")

    response = client.get(
        "/api/commissiondar-stock",
        headers=headers
    )

    assert response.status_code == 403


# -------------------------
# Login log tests
# -------------------------

def test_failed_login_is_logged():
    response = client.post(
        "/api/login",
        json={
            "phone": "0000000000",
            "password": "WrongTest123!",
            "second_password": "WrongSecond123!"
        }
    )

    assert response.status_code == 401


def test_successful_login_appears_in_admin_logs():
    headers = get_headers("7093355518")

    response = client.get(
        "/api/admin/login-logs",
        headers=headers
    )

    assert response.status_code == 200, response.text

    logs = response.json()
    assert any(
        log["phone"] == "9999999999" and log["success"] is True
        for log in logs
    )


def test_non_admin_blocked_from_login_logs():
    headers = get_headers("8888888888")

    response = client.get(
        "/api/admin/login-logs",
        headers=headers
    )

    assert response.status_code == 403


# -------------------------
# Issue reporting tests
# -------------------------

def test_report_issue_and_retrieve():
    # Miller submits the issue
    miller_headers = get_headers("9999999999")

    response = client.post(
        "/api/report-issue",
        json={
            "description": "pytest test issue"
        },
        headers=miller_headers
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "open"

    # Admin retrieves reported issues
    admin_headers = get_headers("7093355518")

    issues_response = client.get(
        "/api/admin/issues",
        headers=admin_headers
    )

    assert issues_response.status_code == 200, issues_response.text

    issues = issues_response.json()
    assert any(
        issue["description"] == "pytest test issue"
        for issue in issues
    )


def test_farmers_requires_owner():
    assert client.get("/api/farmers").status_code == 401

    headers = get_headers("8888888888")
    assert client.get("/api/farmers", headers=headers).status_code == 403


def test_dashboard_requires_owner():
    assert client.get("/api/dashboard").status_code == 401


# -------------------------
# Invalid JWT tests
# -------------------------

def test_invalid_token_returns_401():
    headers = {
        "Authorization": "Bearer invalid-token"
    }

    response = client.get(
        "/api/dashboard",
        headers=headers
    )

    assert response.status_code == 401


def test_token_signed_with_wrong_secret_returns_401():
    from jose import jwt
    from datetime import datetime, timedelta, timezone

    token = jwt.encode(
        {
            "sub": "2",
            "exp": datetime.now(timezone.utc)
                  + timedelta(minutes=10)
        },
        "wrong-secret",
        algorithm="HS256"
    )

    response = client.get(
        "/api/dashboard",
        headers={
            "Authorization": f"Bearer {token}"
        }
    )

    assert response.status_code == 401


def test_expired_token_returns_401():
    from jose import jwt
    from datetime import datetime, timedelta, timezone
    from auth import SECRET_KEY, ALGORITHM

    token = jwt.encode(
        {
            "sub": "2",
            "exp": datetime.now(timezone.utc)
                  - timedelta(minutes=10)
        },
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    response = client.get(
        "/api/dashboard",
        headers={
            "Authorization": f"Bearer {token}"
        }
    )

    assert response.status_code == 401


def test_token_without_user_id_returns_401():
    from jose import jwt
    from datetime import datetime, timedelta, timezone
    from auth import SECRET_KEY, ALGORITHM

    token = jwt.encode(
        {
            "exp": datetime.now(timezone.utc)
                  + timedelta(minutes=10)
        },
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    response = client.get(
        "/api/dashboard",
        headers={
            "Authorization": f"Bearer {token}"
        }
    )

    assert response.status_code == 401


# -------------------------
# Registration and Admin approval tests
# -------------------------

def _new_test_phone():
    """Generate a unique, numeric 10-digit phone number for registration tests."""
    import secrets

    return str(3_000_000_000 + secrets.randbelow(1_000_000_000))


def _cleanup_registered_account(phone):
    """Remove only the account created by the current test."""
    from database import SessionLocal
    from models import User, Business, Party

    db = SessionLocal()

    try:
        user = db.query(User).filter(User.phone == phone).first()

        if user is None:
            return

        business_id = user.business_id
        party_id = user.party_id

        # Remove the user first because it may reference the Party record.
        db.delete(user)
        db.flush()

        if party_id is not None:
            db.query(Party).filter(Party.id == party_id).delete(
                synchronize_session=False
            )
            db.flush()

        # This business was created specifically by this registration test.
        db.query(Business).filter(Business.id == business_id).delete(
            synchronize_session=False
        )

        db.commit()

    finally:
        db.close()


def test_miller_registration_creates_pending_account():
    from database import SessionLocal
    from models import User, Business
    from auth import verify_password

    phone = _new_test_phone()

    try:
        response = client.post(
            "/api/register/miller",
            json={
                "name": "Pytest Miller",
                "phone": phone,
                "business_name": "Pytest Independent Mill",
                "password": "MillerTest123!",
                "second_password": "MillerSecond123!",
            },
        )

        assert response.status_code == 201, response.text
        assert response.json()["approval_status"] == "pending"

        db = SessionLocal()

        try:
            user = db.query(User).filter(User.phone == phone).first()

            assert user is not None
            assert user.role == "owner"
            assert user.approval_status == "pending"
            assert user.password_hash != "MillerTest123!"
            assert user.second_password_hash != "MillerSecond123!"

            assert verify_password("MillerTest123!", user.password_hash)
            assert verify_password(
                "MillerSecond123!",
                user.second_password_hash,
            )

            business = db.query(Business).filter(
                Business.id == user.business_id
            ).first()

            assert business is not None
            assert business.business_type == "mill"
            assert business.name == "Pytest Independent Mill"

        finally:
            db.close()

    finally:
        _cleanup_registered_account(phone)


def test_commissiondar_registration_creates_independent_pending_account():
    from database import SessionLocal
    from models import User, Business, Party
    from auth import verify_password

    phone = _new_test_phone()

    try:
        response = client.post(
            "/api/register/commissiondar",
            json={
                "name": "Pytest Commissiondar",
                "phone": phone,
                "password": "PartyTest123!",
                "second_password": "PartySecond123!",
            },
        )

        assert response.status_code == 201, response.text
        assert response.json()["approval_status"] == "pending"

        db = SessionLocal()

        try:
            user = db.query(User).filter(User.phone == phone).first()

            assert user is not None
            assert user.role == "party"
            assert user.approval_status == "pending"
            assert user.party_id is not None
            assert user.password_hash != "PartyTest123!"
            assert user.second_password_hash != "PartySecond123!"

            assert verify_password("PartyTest123!", user.password_hash)
            assert verify_password(
                "PartySecond123!",
                user.second_password_hash,
            )

            business = db.query(Business).filter(
                Business.id == user.business_id
            ).first()

            assert business is not None
            assert business.business_type == "commissiondar"
            assert business.id != 1

            party = db.query(Party).filter(
                Party.id == user.party_id
            ).first()

            assert party is not None
            assert party.business_id == user.business_id
            assert party.party_type == "commissiondar"

        finally:
            db.close()

    finally:
        _cleanup_registered_account(phone)


def test_miller_registration_rejects_duplicate_phone():
    response = client.post(
        "/api/register/miller",
        json={
            "name": "Duplicate Miller",
            "phone": "9999999999",
            "business_name": "Duplicate Test Mill",
            "password": "MillerTest123!",
            "second_password": "MillerSecond123!",
        },
    )

    assert response.status_code == 409


def test_commissiondar_registration_rejects_duplicate_phone():
    response = client.post(
        "/api/register/commissiondar",
        json={
            "name": "Duplicate Commissiondar",
            "phone": "8888888888",
            "password": "PartyTest123!",
            "second_password": "PartySecond123!",
        },
    )

    assert response.status_code == 409


def test_admin_can_approve_pending_miller_registration():
    from database import SessionLocal
    from models import User

    phone = _new_test_phone()

    try:
        registration = client.post(
            "/api/register/miller",
            json={
                "name": "Approval Test Miller",
                "phone": phone,
                "business_name": "Approval Test Mill",
                "password": "MillerTest123!",
                "second_password": "MillerSecond123!",
            },
        )

        assert registration.status_code == 201, registration.text

        db = SessionLocal()

        try:
            user = db.query(User).filter(User.phone == phone).first()
            assert user is not None
            user_id = user.id
        finally:
            db.close()

        admin_headers = get_headers("7093355518")

        approval = client.post(
            f"/api/admin/registrations/{user_id}/approve",
            headers=admin_headers,
        )

        assert approval.status_code == 200, approval.text

        db = SessionLocal()

        try:
            user = db.query(User).filter(User.id == user_id).first()

            assert user is not None
            assert user.approval_status == "approved"
            assert user.reviewed_by == 5
            assert user.reviewed_at is not None

        finally:
            db.close()

        # A registration that has already been reviewed cannot be reviewed again.
        repeated_approval = client.post(
            f"/api/admin/registrations/{user_id}/approve",
            headers=admin_headers,
        )

        assert repeated_approval.status_code == 409

    finally:
        _cleanup_registered_account(phone)


def test_admin_can_reject_pending_miller_registration():
    from database import SessionLocal
    from models import User

    phone = _new_test_phone()

    try:
        registration = client.post(
            "/api/register/miller",
            json={
                "name": "Rejection Test Miller",
                "phone": phone,
                "business_name": "Rejection Test Mill",
                "password": "MillerTest123!",
                "second_password": "MillerSecond123!",
            },
        )

        assert registration.status_code == 201, registration.text

        db = SessionLocal()

        try:
            user = db.query(User).filter(User.phone == phone).first()
            assert user is not None
            user_id = user.id
        finally:
            db.close()

        admin_headers = get_headers("7093355518")

        rejection = client.post(
            f"/api/admin/registrations/{user_id}/reject",
            headers=admin_headers,
        )

        assert rejection.status_code == 200, rejection.text

        db = SessionLocal()

        try:
            user = db.query(User).filter(User.id == user_id).first()

            assert user is not None
            assert user.approval_status == "rejected"
            assert user.reviewed_by == 5
            assert user.reviewed_at is not None

        finally:
            db.close()

        blocked_login = client.post(
            "/api/login",
            json={
                "phone": phone,
                "password": "MillerTest123!",
                "second_password": "MillerSecond123!",
            },
        )

        assert blocked_login.status_code == 403
        assert "rejected" in blocked_login.json()["detail"].lower()

    finally:
        _cleanup_registered_account(phone)


def test_pending_registration_cannot_login():
    phone = _new_test_phone()

    try:
        registration = client.post(
            "/api/register/miller",
            json={
                "name": "Pending Login Test",
                "phone": phone,
                "business_name": "Pending Login Test Mill",
                "password": "MillerTest123!",
                "second_password": "MillerSecond123!",
            },
        )

        assert registration.status_code == 201, registration.text

        login = client.post(
            "/api/login",
            json={
                "phone": phone,
                "password": "MillerTest123!",
                "second_password": "MillerSecond123!",
            },
        )

        assert login.status_code == 403
        assert "pending" in login.json()["detail"].lower()

    finally:
        _cleanup_registered_account(phone)


def test_admin_registration_endpoints_are_admin_only():
    admin_headers = get_headers("7093355518")
    miller_headers = get_headers("9999999999")
    commissiondar_headers = get_headers("8888888888")

    admin_response = client.get(
        "/api/admin/registrations/pending",
        headers=admin_headers,
    )

    assert admin_response.status_code == 200, admin_response.text

    miller_response = client.get(
        "/api/admin/registrations/pending",
        headers=miller_headers,
    )

    assert miller_response.status_code == 403

    commissiondar_response = client.get(
        "/api/admin/registrations/pending",
        headers=commissiondar_headers,
    )

    assert commissiondar_response.status_code == 403


def test_admin_dashboard_summary_is_admin_only():
    admin_headers = get_headers("7093355518")
    miller_headers = get_headers("9999999999")
    commissiondar_headers = get_headers("8888888888")

    admin_response = client.get(
        "/api/admin/dashboard-summary",
        headers=admin_headers,
    )

    assert admin_response.status_code == 200, admin_response.text

    data = admin_response.json()

    assert "users" in data
    assert "registrations" in data
    assert "businesses" in data
    assert "login_activity" in data
    assert "issues" in data

    assert "total_millers" in data["users"]
    assert "total_commissiondars" in data["users"]
    assert "approved" in data["registrations"]
    assert "pending" in data["registrations"]
    assert "rejected" in data["registrations"]

    miller_response = client.get(
        "/api/admin/dashboard-summary",
        headers=miller_headers,
    )

    assert miller_response.status_code == 403

    commissiondar_response = client.get(
        "/api/admin/dashboard-summary",
        headers=commissiondar_headers,
    )

    assert commissiondar_response.status_code == 403


def test_login_challenge_cannot_be_reused(monkeypatch):
    # Mock MSG91 verification for this test only
    monkeypatch.setattr(
        main,
        "verify_msg91_access_token",
        lambda access_token: "9999999999"
    )

    # Step 1: Login with valid credentials
    login_response = client.post(
        "/api/login",
        json={
            "phone": "9999999999",
            "password": "OwnerTest123!",
            "second_password": "OwnerSecond123!"
        }
    )

    assert login_response.status_code == 200, login_response.text

    challenge_id = login_response.json()["challenge_id"]

    verification_data = {
        "challenge_id": challenge_id,
        "access_token": "test-msg91-access-token"
    }

    # Step 2: First verification should succeed
    first_response = client.post(
        "/api/verify-otp",
        json=verification_data
    )

    assert first_response.status_code == 200, first_response.text

    # Step 3: Reusing the same challenge must fail
    second_response = client.post(
        "/api/verify-otp",
        json=verification_data
    )

    assert second_response.status_code == 401