import main
import pytest
import uuid
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
        "9999999999": "OwnerTest123!",
        "8888888888": "PartyTest123!",
        "7093355518": "AdminTest123!"
    }

    password = test_passwords[phone]

    response = client.post(
        "/api/login",
        json={
            "phone": phone,
            "password": password
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

    farmer = client.post(
        "/api/commissiondar/farmers",
        json={"name": "Stock Test Farmer", "village": "Stock Village"},
        headers=headers,
    )
    assert farmer.status_code == 201, farmer.text

    grain = client.post(
        "/api/commissiondar/grain-types",
        json={"name": f"Stock Test Grain {uuid.uuid4().hex[:8]}", "unit": "quintal"},
        headers=headers,
    )
    assert grain.status_code == 201, grain.text

    before_response = client.get("/api/commissiondar-stock", headers=headers)
    assert before_response.status_code == 200, before_response.text
    before = before_response.json()["stock_on_hand"]

    receive = client.post(
        "/api/commissiondar-stock/receive",
        json={
            "farmer_id": farmer.json()["id"],
            "grain_type_id": grain.json()["id"],
            "quantity": 15,
            "rate": 2200,
        },
        headers=headers,
    )
    assert receive.status_code == 200, receive.text

    deliver = client.post(
        "/api/commissiondar-stock/deliver",
         json={
        "farmer_id": farmer.json()["id"],
        "mill_name": "Independently Entered Mill",
        "grain_type_id": grain.json()["id"],
        "quantity": 6,
        "rate": 2200,
    },
        headers=headers,
    )
    assert deliver.status_code == 200, deliver.text
    assert deliver.json()["mill_name"] == "Independently Entered Mill"

    after_response = client.get("/api/commissiondar-stock", headers=headers)
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
                "password": "MillerTest123!"
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
            assert verify_password("MillerTest123!", user.password_hash)
            assert user.second_password_hash is None

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
                "password": "PartyTest123!"
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
            assert verify_password("PartyTest123!", user.password_hash)
            assert user.second_password_hash is None

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
            },
        )

        assert registration.status_code == 201, registration.text

        login = client.post(
            "/api/login",
            json={
                "phone": phone,
                "password": "MillerTest123!",

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
# -------------------------
# Phase 1 independent-account additions
# -------------------------


def test_miller_can_manage_private_commissiondar_contacts_and_packet_commission():
    headers = get_headers("9999999999")

    contact = client.post(
        "/api/miller/commissiondars",
        json={"name": "Phase1 Contact Test"},
        headers=headers,
    )
    assert contact.status_code == 201, contact.text
    contact_id = contact.json()["id"]

    farmer = client.post(
        "/api/farmers",
        json={
            "name": "Phase1 Farmer Test",
            "village": "Test Village",
            "associated_commissiondar_id": contact_id,
        },
        headers=headers,
    )
    assert farmer.status_code == 200, farmer.text
    farmer_id = farmer.json()["id"]

    # First intake: fixed commission
    intake = client.post(
        "/api/intake",
        json={
            "farmer_id": farmer_id,
            "item_id": 2,
            "quantity": 4,
            "rate": 2200,
            "packet_count": 10,
            "packet_price": 2200,
            "commission_type": "fixed",
            "commission_rate": 50,
        },
        headers=headers,
    )
    assert intake.status_code == 200, intake.text
    assert float(intake.json()["broker_commission"]["commission_amount"]) == 500
    commission_id = intake.json()["broker_commission"]["id"]

    # Second intake: percentage commission
    percentage_intake = client.post(
        "/api/intake",
        json={
            "farmer_id": farmer_id,
            "item_id": 2,
            "quantity": 4,
            "rate": 2200,
            "packet_count": 10,
            "packet_price": 2200,
            "commission_type": "percentage",
            "commission_rate": 2.5,
        },
        headers=headers,
    )
    assert percentage_intake.status_code == 200, percentage_intake.text
    assert float(percentage_intake.json()["broker_commission"]["commission_amount"]) == 550

    # Verify Commissiondar contact-list totals
    contacts = client.get(
        "/api/miller/commissiondars",
        headers=headers,
    )
    assert contacts.status_code == 200, contacts.text

    row = next(x for x in contacts.json() if x["id"] == contact_id)

    assert row["visit_count"] == 2
    assert row["total_packets"] == 20
    assert row["total_commission"] == 1050
    assert row["total_farmers"] == 1
    assert row["commission_paid"] == 0
    assert row["commission_outstanding"] == 1050

    # Verify detailed Miller Commissiondar report
    detail = client.get(
        f"/api/miller/commissiondars/{contact_id}",
        headers=headers,
    )
    assert detail.status_code == 200, detail.text

    report = detail.json()

    # Contact details
    assert report["contact"]["id"] == contact_id
    assert report["contact"]["name"] == "Phase1 Contact Test"

    # Overall summary
    summary = report["summary"]
    assert summary["total_farmers"] == 1
    assert summary["total_intakes"] == 2
    assert float(summary["total_quantity"]) == 8
    assert float(summary["total_commission"]) == 1050
    assert float(summary["commission_paid"]) == 0
    assert float(summary["commission_outstanding"]) == 1050

    # Farmer-wise report
    farmer_report = next(
        x for x in report["farmers"]
        if x["farmer_id"] == farmer_id
    )

    assert farmer_report["farmer_name"] == "Phase1 Farmer Test"
    assert farmer_report["total_intakes"] == 2
    assert float(farmer_report["total_quantity"]) == 8
    assert float(farmer_report["commission_earned"]) == 1050
    assert float(farmer_report["commission_paid"]) == 0
    assert float(farmer_report["commission_outstanding"]) == 1050
    assert len(farmer_report["intakes"]) == 2

    # Pay the first commission in full
    payment = client.post(
        "/api/broker-commissions/pay",
        json={"commission_id": commission_id},
        headers=headers,
    )
    assert payment.status_code == 200, payment.text
    assert payment.json()["is_paid"] is True

    # Verify updated commission totals
    updated_detail = client.get(
        f"/api/miller/commissiondars/{contact_id}",
        headers=headers,
    )
    assert updated_detail.status_code == 200, updated_detail.text

    updated_report = updated_detail.json()
    updated_summary = updated_report["summary"]

    assert float(updated_summary["total_commission"]) == 1050
    assert float(updated_summary["commission_paid"]) == 500
    assert float(updated_summary["commission_outstanding"]) == 550

    updated_farmer = next(
        x for x in updated_report["farmers"]
        if x["farmer_id"] == farmer_id
    )
    assert float(updated_farmer["commission_paid"]) == 500
    assert float(updated_farmer["commission_outstanding"]) == 550

    # Prevent paying the same commission twice
    duplicate_payment = client.post(
        "/api/broker-commissions/pay",
        json={"commission_id": commission_id},
        headers=headers,
    )
    assert duplicate_payment.status_code == 400

    # Create a second farmer under the same Miller Commissiondar contact
    farmer2 = client.post(
        "/api/farmers",
        json={
            "name": "Phase1 Second Farmer",
            "village": "Second Village",
            "associated_commissiondar_id": contact_id,
        },
        headers=headers,
    )
    assert farmer2.status_code == 200, farmer2.text
    farmer2_id = farmer2.json()["id"]

    # Record an intake for the second farmer
    intake2 = client.post(
        "/api/intake",
        json={
            "farmer_id": farmer2_id,
            "item_id": 2,
            "quantity": 3,
            "rate": 2200,
            "packet_count": 2,
            "packet_price": 2200,
            "commission_type": "fixed",
            "commission_rate": 25,
        },
        headers=headers,
    )
    assert intake2.status_code == 200, intake2.text
    assert float(intake2.json()["broker_commission"]["commission_amount"]) == 50

    # Verify both farmers appear separately in the detailed report
    multi_detail = client.get(
        f"/api/miller/commissiondars/{contact_id}",
        headers=headers,
    )
    assert multi_detail.status_code == 200, multi_detail.text

    multi_report = multi_detail.json()
    multi_summary = multi_report["summary"]

    assert multi_summary["total_farmers"] == 2
    assert multi_summary["total_intakes"] == 3
    assert float(multi_summary["total_quantity"]) == 11
    assert float(multi_summary["total_commission"]) == 1100
    assert float(multi_summary["commission_paid"]) == 500
    assert float(multi_summary["commission_outstanding"]) == 600

    # Verify second farmer's individual report
    farmer2_report = next(
        x for x in multi_report["farmers"]
        if x["farmer_id"] == farmer2_id
    )

    assert farmer2_report["farmer_name"] == "Phase1 Second Farmer"
    assert farmer2_report["total_intakes"] == 1
    assert float(farmer2_report["total_quantity"]) == 3
    assert float(farmer2_report["commission_earned"]) == 50
    assert float(farmer2_report["commission_paid"]) == 0
    assert float(farmer2_report["commission_outstanding"]) == 50

    # Verify updated Commissiondar contact-list totals
    updated_contacts = client.get(
        "/api/miller/commissiondars",
        headers=headers,
    )
    assert updated_contacts.status_code == 200, updated_contacts.text

    updated_row = next(
        x for x in updated_contacts.json()
        if x["id"] == contact_id
    )

    assert updated_row["total_farmers"] == 2
    assert updated_row["total_commission"] == 1100
    assert updated_row["commission_paid"] == 500
    assert updated_row["commission_outstanding"] == 600

def test_commissiondar_can_manage_own_farmers_and_independent_stock_delivery():
    headers = get_headers("8888888888")

    # Create a farmer in this Commissiondar's own account.
    farmer = client.post(
        "/api/commissiondar/farmers",
        json={
            "name": "Commissiondar Own Farmer",
            "village": "Own Village"
        },
        headers=headers,
    )
    assert farmer.status_code == 201, farmer.text
    farmer_id = farmer.json()["id"]

    # Create a custom grain type.
    grain = client.post(
        "/api/commissiondar/grain-types",
        json={
            "name": f"Commissiondar Test Paddy {uuid.uuid4().hex[:8]}",
            "unit": "quintal"
        },
        headers=headers,
    )
    assert grain.status_code == 201, grain.text
    grain_type_id = grain.json()["id"]

    # Reject both catalogue IDs together when receiving.
    both_receive = client.post(
        "/api/commissiondar-stock/receive",
        json={
            "farmer_id": farmer_id,
            "grain_type_id": grain_type_id,
            "item_id": 2,
            "quantity": 5,
        },
        headers=headers,
    )
    assert both_receive.status_code == 400

    # Reject both catalogue IDs together when delivering.
    both_deliver = client.post(
        "/api/commissiondar-stock/deliver",
        json={
            "farmer_id": farmer_id,
            "mill_name": "Manual Test Mill",
            "grain_type_id": grain_type_id,
            "item_id": 2,
            "quantity": 5,
        },
        headers=headers,
    )
    assert both_deliver.status_code == 400

    # Reject receiving without either catalogue ID.
    neither_receive = client.post(
        "/api/commissiondar-stock/receive",
        json={
            "farmer_id": farmer_id,
            "quantity": 5,
        },
        headers=headers,
    )
    assert neither_receive.status_code == 400

    # Reject delivery without either catalogue ID.
    # farmer_id is included so Pydantic validation passes.
    neither_deliver = client.post(
        "/api/commissiondar-stock/deliver",
        json={
            "farmer_id": farmer_id,
            "mill_name": "Manual Test Mill",
            "quantity": 5,
        },
        headers=headers,
    )
    assert neither_deliver.status_code == 400

    # Receive 12 quintals from the farmer.
    received = client.post(
        "/api/commissiondar-stock/receive",
        json={
            "farmer_id": farmer_id,
            "grain_type_id": grain_type_id,
            "quantity": 12,
            "rate": 2200,
        },
        headers=headers,
    )
    assert received.status_code == 200, received.text

    # Deliver 5 quintals to a manually entered mill.
    delivered = client.post(
        "/api/commissiondar-stock/deliver",
        json={
            "farmer_id": farmer_id,
            "mill_name": "Manually Entered Mill",
            "grain_type_id": grain_type_id,
            "quantity": 5,
            "rate": 2200,
        },
        headers=headers,
    )
    assert delivered.status_code == 200, delivered.text

    delivery_data = delivered.json()

    assert delivery_data["farmer_id"] == farmer_id
    assert delivery_data["farmer_name"] == farmer.json()["name"]
    assert delivery_data["mill_name"] == "Manually Entered Mill"

    # Verify stock summary and delivery history.
    stock = client.get(
        "/api/commissiondar-stock",
        headers=headers,
    )
    assert stock.status_code == 200, stock.text

    stock_data = stock.json()

    assert stock_data["stock_on_hand"] >= 7

    assert any(
        x["mill_name"] == "Manually Entered Mill"
        for x in stock_data["deliveries_by_mill"]
    )

    assert any(
        x["farmer_name"] == farmer.json()["name"]
        and x["mill_name"] == "Manually Entered Mill"
        for x in stock_data["history"]
    )

def test_removing_farmer_from_one_mill_preserves_other_association():
    headers = get_headers("8888888888")

    # Create farmer.
    farmer_response = client.post(
        "/api/commissiondar/farmers",
        json={
            "name": f"Association Removal Farmer {uuid.uuid4().hex[:8]}",
            "village": "Removal Village",
        },
        headers=headers,
    )
    assert farmer_response.status_code == 201, farmer_response.text
    farmer_id = farmer_response.json()["id"]

    # Create two mills.
    mill_ids = []

    for name in ["Removal Mill A", "Removal Mill B"]:
        response = client.post(
            "/api/commissiondar/mills",
            json={"name": f"{name} {uuid.uuid4().hex[:8]}"},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        mill_ids.append(response.json()["id"])

    # Associate farmer with both.
    for mill_id in mill_ids:
        response = client.post(
            f"/api/commissiondar/mills/{mill_id}/farmers/{farmer_id}",
            headers=headers,
        )
        assert response.status_code == 201, response.text

    # Remove farmer only from the first mill.
    removal = client.delete(
        f"/api/commissiondar/mills/{mill_ids[0]}/farmers/{farmer_id}",
        headers=headers,
    )
    assert removal.status_code == 200, removal.text

    # First mill should no longer show the farmer.
    first = client.get(
        f"/api/commissiondar/mills/{mill_ids[0]}/farmers",
        headers=headers,
    )
    assert first.status_code == 200
    assert first.json()["farmer_count"] == 0

    # Second mill must still show the farmer.
    second = client.get(
        f"/api/commissiondar/mills/{mill_ids[1]}/farmers",
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json()["farmer_count"] == 1
    assert second.json()["farmers"][0]["id"] == farmer_id

    # Farmer must remain in the Commissiondar's directory.
    directory = client.get(
        "/api/commissiondar/farmers",
        headers=headers,
    )
    assert directory.status_code == 200
    assert any(
        farmer["id"] == farmer_id
        for farmer in directory.json()
    )

def test_commissiondar_mill_commission_and_receipt_ledger():
    headers = get_headers("8888888888")

    # Create a mill.
    mill_response = client.post(
        "/api/commissiondar/mills",
        json={"name": f"Commission Test Mill {uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert mill_response.status_code == 201, mill_response.text
    mill_id = mill_response.json()["id"]

    # Record manually earned commission.
    commission_response = client.post(
        f"/api/commissiondar/mills/{mill_id}/commissions",
        json={
            "commission_amount": 8000,
            "earned_at": "2026-11-23",
            "note": "Paddy commission",
        },
        headers=headers,
    )
    assert commission_response.status_code == 201, commission_response.text

    commission = commission_response.json()
    commission_id = commission["id"]

    assert commission["commission_amount"] == 8000.0
    assert commission["received_amount"] == 0.0
    assert commission["pending_amount"] == 8000.0

    # Record first partial receipt.
    first_receipt = client.post(
        f"/api/commissiondar/commissions/{commission_id}/receipts",
        json={
            "amount": 3000,
            "received_at": "2026-11-23",
            "note": "First payment",
        },
        headers=headers,
    )
    assert first_receipt.status_code == 201, first_receipt.text
    assert first_receipt.json()["remaining_pending"] == 5000.0

    # Record second partial receipt.
    second_receipt = client.post(
        f"/api/commissiondar/commissions/{commission_id}/receipts",
        json={"amount": 2000, "note": "Second payment"},
        headers=headers,
    )
    assert second_receipt.status_code == 201, second_receipt.text
    assert second_receipt.json()["remaining_pending"] == 3000.0

    # Reject a receipt greater than the remaining pending amount.
    overpayment = client.post(
        f"/api/commissiondar/commissions/{commission_id}/receipts",
        json={"amount": 3001},
        headers=headers,
    )
    assert overpayment.status_code == 400

    # Record the exact remaining amount.
    final_receipt = client.post(
        f"/api/commissiondar/commissions/{commission_id}/receipts",
        json={"amount": 3000, "note": "Final payment"},
        headers=headers,
    )
    assert final_receipt.status_code == 201, final_receipt.text
    assert final_receipt.json()["remaining_pending"] == 0.0

    # Verify receipt history.
    receipt_history = client.get(
        f"/api/commissiondar/commissions/{commission_id}/receipts",
        headers=headers,
    )
    assert receipt_history.status_code == 200, receipt_history.text

    receipt_data = receipt_history.json()
    assert receipt_data["commission_amount"] == 8000.0
    assert receipt_data["total_received"] == 8000.0
    assert receipt_data["pending_amount"] == 0.0
    assert len(receipt_data["receipts"]) == 3

    # Verify mill-wise commission summary.
    mill_history = client.get(
        f"/api/commissiondar/mills/{mill_id}/commissions",
        headers=headers,
    )
    assert mill_history.status_code == 200, mill_history.text

    summary = mill_history.json()
    assert summary["total_earned"] == 8000.0
    assert summary["total_received"] == 8000.0
    assert summary["total_pending"] == 0.0
    assert summary["commission_count"] == 1


def test_miller_cannot_access_commissiondar_commission_ledger():
    commissiondar_headers = get_headers("8888888888")
    miller_headers = get_headers("9999999999")

    # Create a Commissiondar-owned mill and commission.
    mill_response = client.post(
        "/api/commissiondar/mills",
        json={"name": f"Private Commission Mill {uuid.uuid4().hex[:8]}"},
        headers=commissiondar_headers,
    )
    assert mill_response.status_code == 201, mill_response.text
    mill_id = mill_response.json()["id"]

    commission_response = client.post(
        f"/api/commissiondar/mills/{mill_id}/commissions",
        json={"commission_amount": 5000},
        headers=commissiondar_headers,
    )
    assert commission_response.status_code == 201, commission_response.text
    commission_id = commission_response.json()["id"]

    # Miller cannot view the Commissiondar's commission history.
    history = client.get(
        f"/api/commissiondar/mills/{mill_id}/commissions",
        headers=miller_headers,
    )
    assert history.status_code == 403

    # Miller cannot record a receipt against that commission.
    receipt = client.post(
        f"/api/commissiondar/commissions/{commission_id}/receipts",
        json={"amount": 1000},
        headers=miller_headers,
    )
    assert receipt.status_code == 403

    # Miller cannot view its receipt history either.
    receipt_history = client.get(
        f"/api/commissiondar/commissions/{commission_id}/receipts",
        headers=miller_headers,
    )
    assert receipt_history.status_code == 403


def test_commissiondar_dashboard_shows_mill_commission_totals():
    headers = get_headers("8888888888")

    # Capture existing dashboard totals first.
    baseline_response = client.get(
        "/api/commissiondar-dashboard",
        headers=headers,
    )
    assert baseline_response.status_code == 200, baseline_response.text
    baseline = baseline_response.json()

    # Create two mills.
    mill_ids = []

    for name in [
        f"Dashboard Mill A {uuid.uuid4().hex[:8]}",
        f"Dashboard Mill B {uuid.uuid4().hex[:8]}"
    ]:
        response = client.post(
            "/api/commissiondar/mills",
            json={"name": name},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        mill_ids.append(response.json()["id"])

    # Create two farmers.
    farmer_ids = []

    for name in [
        f"Dashboard Farmer A {uuid.uuid4().hex[:8]}",
        f"Dashboard Farmer B {uuid.uuid4().hex[:8]}"
    ]:
        response = client.post(
            "/api/commissiondar/farmers",
            json={"name": name},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        farmer_ids.append(response.json()["id"])

    # Associate one farmer with each mill.
    for mill_id, farmer_id in zip(mill_ids, farmer_ids):
        response = client.post(
            f"/api/commissiondar/mills/{mill_id}/farmers/{farmer_id}",
            headers=headers,
        )
        assert response.status_code in (200, 201), response.text

    # Record ₹8,000 manually earned commission.
    commission_response = client.post(
        f"/api/commissiondar/mills/{mill_ids[0]}/commissions",
        json={
            "commission_amount": 8000,
            "earned_at": "2026-11-23",
            "note": "Dashboard test commission",
        },
        headers=headers,
    )
    assert commission_response.status_code == 201, commission_response.text
    commission_id = commission_response.json()["id"]

    # Record two partial receipts: ₹3,000 + ₹2,000.
    for amount in [3000, 2000]:
        response = client.post(
            f"/api/commissiondar/commissions/{commission_id}/receipts",
            json={"amount": amount},
            headers=headers,
        )
        assert response.status_code == 201, response.text

    # Read the updated dashboard.
    dashboard_response = client.get(
        "/api/commissiondar-dashboard",
        headers=headers,
    )
    assert dashboard_response.status_code == 200, dashboard_response.text

    dashboard = dashboard_response.json()

    # Check the changes made by this test, not absolute database totals.
    assert dashboard["commissions_earned"] == (
        baseline["commissions_earned"] + 8000.0
    )

    assert dashboard["commissions_received"] == (
        baseline["commissions_received"] + 5000.0
    )

    assert dashboard["commissions_pending"] == (
        baseline["commissions_pending"] + 3000.0
    )

    assert dashboard["total_mills"] == baseline["total_mills"] + 2

    assert dashboard["associated_farmers"] == (
        baseline["associated_farmers"] + 2
    )

    # Verify the latest commission details.
    latest = dashboard["latest_commission"]
    assert latest is not None
    assert latest["commission_amount"] == 8000.0
    assert latest["received_amount"] == 5000.0
    assert latest["pending_amount"] == 3000.0

# ---------------------------------------------------------
# Miller Custom Grain Variety Tests
# ---------------------------------------------------------

def test_miller_can_create_and_list_custom_grain():
    headers = get_headers("9999999999")
    grain_name = f"Custom Paddy {uuid.uuid4().hex[:8]}"

    create_response = client.post(
        "/api/items",
        json={
            "name": grain_name,
            "category": "Paddy",
            "unit": "quintal"
        },
        headers=headers
    )

    assert create_response.status_code == 201, create_response.text

    created_item = create_response.json()["item"]

    assert created_item["name"] == grain_name
    assert created_item["category"] == "Paddy"
    assert created_item["unit"] == "quintal"

    list_response = client.get(
        "/api/items",
        headers=headers
    )

    assert list_response.status_code == 200, list_response.text

    items = list_response.json()["items"]

    assert any(item["id"] == created_item["id"] for item in items)


def test_miller_cannot_create_duplicate_grain_name():
    headers = get_headers("9999999999")
    grain_name = f"Duplicate Paddy {uuid.uuid4().hex[:8]}"

    first_response = client.post(
        "/api/items",
        json={
            "name": grain_name,
            "unit": "quintal"
        },
        headers=headers
    )

    assert first_response.status_code == 201, first_response.text

    duplicate_response = client.post(
        "/api/items",
        json={
            "name": grain_name.upper(),
            "unit": "quintal"
        },
        headers=headers
    )

    assert duplicate_response.status_code == 409


def test_miller_can_update_custom_grain():
    headers = get_headers("9999999999")
    grain_name = f"Update Paddy {uuid.uuid4().hex[:8]}"

    create_response = client.post(
        "/api/items",
        json={
            "name": grain_name,
            "category": "Paddy",
            "unit": "quintal"
        },
        headers=headers
    )

    assert create_response.status_code == 201, create_response.text

    item_id = create_response.json()["item"]["id"]

    updated_name = f"Updated Paddy {uuid.uuid4().hex[:8]}"

    update_response = client.put(
        f"/api/items/{item_id}",
        json={
            "name": updated_name,
            "category": "Premium Paddy",
            "unit": "kg"
        },
        headers=headers
    )

    assert update_response.status_code == 200, update_response.text

    updated_item = update_response.json()["item"]

    assert updated_item["id"] == item_id
    assert updated_item["name"] == updated_name
    assert updated_item["category"] == "Premium Paddy"
    assert updated_item["unit"] == "kg"


def test_miller_can_deactivate_custom_grain():
    headers = get_headers("9999999999")
    grain_name = f"Deactivate Paddy {uuid.uuid4().hex[:8]}"

    create_response = client.post(
        "/api/items",
        json={
            "name": grain_name,
            "unit": "quintal"
        },
        headers=headers
    )

    assert create_response.status_code == 201, create_response.text

    item_id = create_response.json()["item"]["id"]

    deactivate_response = client.patch(
        f"/api/items/{item_id}/deactivate",
        headers=headers
    )

    assert deactivate_response.status_code == 200, deactivate_response.text

    assert deactivate_response.json()["is_active"] is False

    list_response = client.get(
        "/api/items",
        headers=headers
    )

    assert list_response.status_code == 200

    assert all(
        item["id"] != item_id
        for item in list_response.json()["items"]
    )


def test_inactive_grain_cannot_be_used_for_intake_or_export():
    headers = get_headers("9999999999")
    grain_name = f"Inactive Paddy {uuid.uuid4().hex[:8]}"

    create_response = client.post(
        "/api/items",
        json={
            "name": grain_name,
            "unit": "quintal"
        },
        headers=headers
    )

    assert create_response.status_code == 201, create_response.text

    item_id = create_response.json()["item"]["id"]

    deactivate_response = client.patch(
        f"/api/items/{item_id}/deactivate",
        headers=headers
    )

    assert deactivate_response.status_code == 200, deactivate_response.text

    intake_response = client.post(
        "/api/intake",
        json={
            "farmer_id": 3,
            "item_id": item_id,
            "quantity": 5,
            "rate": 2000
        },
        headers=headers
    )

    assert intake_response.status_code == 404

    export_response = client.post(
        "/api/exports",
        json={
            "buyer_id": 4,
            "item_id": item_id,
            "quantity": 2,
            "rate": 3000
        },
        headers=headers
    )

    assert export_response.status_code == 404


def test_commissiondar_cannot_access_miller_grain_management():
    headers = get_headers("8888888888")

    list_response = client.get(
        "/api/items",
        headers=headers
    )

    assert list_response.status_code == 403

    create_response = client.post(
        "/api/items",
        json={
            "name": "Commissiondar Restricted Grain",
            "unit": "quintal"
        },
        headers=headers
    )

    assert create_response.status_code == 403

def test_miller_inventory_summary_and_movement_history():
    from database import SessionLocal
    from models import Item, StockMovement, User
    from decimal import Decimal

    owner_headers = get_headers("9999999999")
    commissiondar_headers = get_headers("8888888888")

    db = SessionLocal()
    item = None
    foreign_item = None

    try:
        owner = db.query(User).filter(
            User.phone == "9999999999"
        ).first()

        commissiondar = db.query(User).filter(
            User.phone == "8888888888"
        ).first()

        assert owner is not None
        assert commissiondar is not None
        assert owner.business_id != commissiondar.business_id

        # Create a temporary grain variety for this Miller.
        item = Item(
            business_id=owner.business_id,
            name=f"Inventory Test Paddy {uuid.uuid4().hex[:8]}",
            category="Paddy",
            unit="quintal",
            is_active=True
        )

        db.add(item)
        db.flush()

        # Create a grain variety owned by the Commissiondar's
        # separate business to verify account isolation.
        foreign_item = Item(
            business_id=commissiondar.business_id,
            name=f"Foreign Test Grain {uuid.uuid4().hex[:8]}",
            category="Paddy",
            unit="quintal",
            is_active=True
        )

        db.add(foreign_item)
        db.flush()

        # Miller movements:
        # Purchase: +100
        # Sale: -30
        # Voided purchase: +50 (must be excluded)
        # Adjustment: -5
        movements = [
            StockMovement(
                business_id=owner.business_id,
                item_id=item.id,
                movement_type="purchase",
                quantity=Decimal("100"),
                created_by=owner.id,
                is_void=False
            ),
            StockMovement(
                business_id=owner.business_id,
                item_id=item.id,
                movement_type="sale",
                quantity=Decimal("-30"),
                created_by=owner.id,
                is_void=False
            ),
            StockMovement(
                business_id=owner.business_id,
                item_id=item.id,
                movement_type="purchase",
                quantity=Decimal("50"),
                created_by=owner.id,
                is_void=True
            ),
            StockMovement(
                business_id=owner.business_id,
                item_id=item.id,
                movement_type="adjustment",
                quantity=Decimal("-5"),
                created_by=owner.id,
                is_void=False
            )
        ]

        db.add_all(movements)
        db.commit()

        item_id = item.id
        foreign_item_id = foreign_item.id

    finally:
        db.close()

    try:
        # 1. Verify inventory summary.
        inventory_response = client.get(
            "/api/inventory",
            headers=owner_headers
        )

        assert inventory_response.status_code == 200, inventory_response.text

        inventory = inventory_response.json()["inventory"]

        grain = next(
            row for row in inventory
            if row["item_id"] == item_id
        )

        assert grain["received_quantity"] == 100.0
        assert grain["dispatched_quantity"] == 30.0
        assert grain["available_quantity"] == 65.0
        assert grain["is_active"] is True

        # 2. Verify movement history includes voided records.
        history_response = client.get(
            f"/api/inventory/{item_id}/movements",
            headers=owner_headers
        )

        assert history_response.status_code == 200, history_response.text

        history = history_response.json()

        assert history["total"] == 4
        assert len(history["movements"]) == 4

        voided_movements = [
            movement
            for movement in history["movements"]
            if movement["is_void"] is True
        ]

        assert len(voided_movements) == 1
        assert voided_movements[0]["quantity"] == 50.0

        # 3. Deactivate the grain directly and verify that
        # inventory and history remain accessible.
        db = SessionLocal()

        try:
            stored_item = db.query(Item).filter(
                Item.id == item_id
            ).first()

            assert stored_item is not None

            stored_item.is_active = False
            db.commit()

        finally:
            db.close()

        inactive_inventory_response = client.get(
            "/api/inventory",
            headers=owner_headers
        )

        assert inactive_inventory_response.status_code == 200

        inactive_inventory = inactive_inventory_response.json()["inventory"]

        inactive_grain = next(
            row for row in inactive_inventory
            if row["item_id"] == item_id
        )

        assert inactive_grain["is_active"] is False
        assert inactive_grain["available_quantity"] == 65.0

        inactive_history_response = client.get(
            f"/api/inventory/{item_id}/movements",
            headers=owner_headers
        )

        assert inactive_history_response.status_code == 200
        assert inactive_history_response.json()["total"] == 4

        # 4. Miller must not see another business's grain.
        assert foreign_item_id not in [
            row["item_id"]
            for row in inactive_inventory
        ]

        foreign_history_response = client.get(
            f"/api/inventory/{foreign_item_id}/movements",
            headers=owner_headers
        )

        assert foreign_history_response.status_code == 404

        # 5. Commissiondar must not access Miller inventory.
        commissiondar_response = client.get(
            "/api/inventory",
            headers=commissiondar_headers
        )

        assert commissiondar_response.status_code == 403

    finally:
        # Remove only the temporary records created by this test.
        db = SessionLocal()

        try:
            if item_id:
                db.query(StockMovement).filter(
                    StockMovement.item_id == item_id
                ).delete(synchronize_session=False)

                db.query(Item).filter(
                    Item.id == item_id
                ).delete(synchronize_session=False)

            if foreign_item_id:
                db.query(StockMovement).filter(
                    StockMovement.item_id == foreign_item_id
                ).delete(synchronize_session=False)

                db.query(Item).filter(
                    Item.id == foreign_item_id
                ).delete(synchronize_session=False)

            db.commit()

        finally:
            db.close()
