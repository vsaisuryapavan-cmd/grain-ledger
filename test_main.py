from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["message"] == "Grain Ledger API is running"


def test_login_fails_for_unknown_phone():
    response = client.post("/api/login", json={"phone": "0000000000"})
    assert response.status_code == 404


def test_login_succeeds_for_real_user():
    response = client.post("/api/login", json={"phone": "9999999999"})
    assert response.status_code == 200
    assert "access_token" in response.json()

def test_intake_debits_correctly():
    token = client.post("/api/login", json={"phone": "9999999999"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/intake", json={
        "farmer_id": 1,
        "item_id": 1,
        "quantity": 10,
        "rate": 2000
    }, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["stock_movement"]["quantity"] == 10
    assert data["ledger_entry"]["debit"] == 20000   # 10 * 2000
    assert data["ledger_entry"]["credit"] == 0


def test_payment_credits_correctly():
    token = client.post("/api/login", json={"phone": "9999999999"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/payments", json={
        "farmer_id": 1,
        "amount": 5000
    }, headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["ledger_entry"]["credit"] == 5000
    assert data["ledger_entry"]["debit"] == 0


def test_intake_requires_login():
    response = client.post("/api/intake", json={
        "farmer_id": 1,
        "item_id": 1,
        "quantity": 10,
        "rate": 2000
    })  # no Authorization header at all

    assert response.status_code == 401


def test_commissiondar_blocked_from_mill_loans():
    token = client.post("/api/login", json={"phone": "8888888888"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/mill-loans", json={
        "commissiondar_id": 4,
        "principal": 10000,
        "interest_rate_pa": 10
    }, headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "Only the mill owner can do this"


def test_miller_blocked_from_commissiondar_loans():
    token = client.post("/api/login", json={"phone": "9999999999"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/commissiondar-loans", json={
        "farmer_id": 1,
        "principal": 10000,
        "interest_rate_pa": 10
    }, headers=headers)

    assert response.status_code == 403
    assert response.json()["detail"] == "Only commissiondars can access this"

def test_farmer_balance_nets_correctly():
    token = client.post("/api/login", json={"phone": "9999999999"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    before = client.get("/api/farmers").json()
    farmer_before = next(f for f in before if f["id"] == 1)
    owed_before = farmer_before["owed"]

    client.post("/api/intake", json={
        "farmer_id": 1, "item_id": 1, "quantity": 5, "rate": 1000
    }, headers=headers)

    client.post("/api/payments", json={
        "farmer_id": 1, "amount": 2000
    }, headers=headers)

    after = client.get("/api/farmers").json()
    farmer_after = next(f for f in after if f["id"] == 1)
    owed_after = farmer_after["owed"]

    assert owed_after == owed_before + 5000 - 2000