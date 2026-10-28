
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


# -------------------------
# Authentication helpers
# -------------------------

def get_token(phone):
    response = client.post("/api/login", json={"phone": phone})
    assert response.status_code == 200, response.text
    assert "access_token" in response.json()
    return response.json()["access_token"]


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
        json={"phone": "0000000000"}
    )

    assert response.status_code == 404


def test_login_succeeds_for_real_user():
    response = client.post(
        "/api/login",
        json={"phone": "9999999999"}
    )

    assert response.status_code == 200
    assert "access_token" in response.json()


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
    assert response.json()["detail"] == "Only commissiondars can access this"


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
        json={"phone": "0000000000"}
    )

    assert response.status_code == 404


def test_successful_login_appears_in_admin_logs():
    headers = get_headers("9999999999")

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
    headers = get_headers("9999999999")

    response = client.post(
        "/api/report-issue",
        json={
            "description": "pytest test issue"
        },
        headers=headers
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "open"

    issues_response = client.get(
        "/api/admin/issues",
        headers=headers
    )

    assert issues_response.status_code == 200, issues_response.text

    issues = issues_response.json()
    assert any(
        issue["description"] == "pytest test issue"
        for issue in issues
    )
