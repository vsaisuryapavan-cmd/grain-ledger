
import uuid

from tests.test_main import client, get_headers


def create_farmer(headers):
    response = client.post(
        "/api/commissiondar/farmers",
        json={
            "name": f"Dashboard Farmer {uuid.uuid4().hex[:8]}",
            "village": "Dashboard Village",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def create_grain_type(headers):
    response = client.post(
        "/api/commissiondar/grain-types",
        json={
            "name": f"Dashboard Grain {uuid.uuid4().hex[:8]}",
            "unit": "quintal",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def receive_stock(headers, farmer_id, grain_type_id, quantity, rate=None):
    payload = {
        "farmer_id": farmer_id,
        "grain_type_id": grain_type_id,
        "quantity": quantity,
    }

    if rate is not None:
        payload["rate"] = rate

    response = client.post(
        "/api/commissiondar-stock/receive",
        json=payload,
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response


def get_farmer_dashboard(headers, farmer_id):
    return client.get(
        f"/api/commissiondar/farmers/{farmer_id}/dashboard",
        headers=headers,
    )


def test_farmer_dashboard_shows_purchase_and_settlement():
    headers = get_headers("8888888888")
    farmer_id = create_farmer(headers)
    grain_type_id = create_grain_type(headers)

    receive_stock(
        headers,
        farmer_id,
        grain_type_id,
        quantity=10,
        rate=2000,
    )

    response = get_farmer_dashboard(headers, farmer_id)

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["farmer"]["id"] == farmer_id
    assert data["farmer"]["name"].startswith("Dashboard Farmer")

    settlement = data["settlement"]

    assert settlement["status"] != "incomplete_purchase_rates"
    assert settlement["payable_by"] == "commissiondar"
    assert settlement["payable_to"] == "farmer"
    assert settlement["amount"] == 20000


def test_farmer_dashboard_includes_loan_advance_in_settlement():
    headers = get_headers("8888888888")
    farmer_id = create_farmer(headers)
    grain_type_id = create_grain_type(headers)

    receive_stock(
        headers,
        farmer_id,
        grain_type_id,
        quantity=10,
        rate=2000,
    )

    loan_response = client.post(
        "/api/commissiondar-loans",
        json={
            "farmer_id": farmer_id,
            "principal": 5000,
            "interest_rate_pa": 0,
        },
        headers=headers,
    )

    assert loan_response.status_code == 200, loan_response.text

    response = get_farmer_dashboard(headers, farmer_id)

    assert response.status_code == 200, response.text

    settlement = response.json()["settlement"]

    assert settlement["payable_by"] == "commissiondar"
    assert settlement["payable_to"] == "farmer"
    assert settlement["amount"] == 15000


def test_farmer_dashboard_marks_missing_purchase_rate_incomplete():
    headers = get_headers("8888888888")
    farmer_id = create_farmer(headers)
    grain_type_id = create_grain_type(headers)

    receive_stock(
        headers,
        farmer_id,
        grain_type_id,
        quantity=5,
    )

    response = get_farmer_dashboard(headers, farmer_id)

    assert response.status_code == 200, response.text

    settlement = response.json()["settlement"]

    assert settlement["status"] == "incomplete_purchase_rates"
    assert settlement["amount"] is None
    assert settlement["payable_by"] is None
    assert settlement["payable_to"] is None


def test_farmer_dashboard_does_not_show_negative_settlement():
    headers = get_headers("8888888888")
    farmer_id = create_farmer(headers)
    grain_type_id = create_grain_type(headers)

    receive_stock(
        headers,
        farmer_id,
        grain_type_id,
        quantity=2,
        rate=2000,
    )

    loan_response = client.post(
        "/api/commissiondar-loans",
        json={
            "farmer_id": farmer_id,
            "principal": 10000,
            "interest_rate_pa": 0,
        },
        headers=headers,
    )

    assert loan_response.status_code == 200, loan_response.text

    response = get_farmer_dashboard(headers, farmer_id)

    assert response.status_code == 200, response.text

    settlement = response.json()["settlement"]

    assert settlement["payable_by"] == "farmer"
    assert settlement["payable_to"] == "commissiondar"
    assert settlement["amount"] == 6000
    assert settlement["amount"] >= 0


def test_commissiondar_cannot_view_another_business_farmer():
    commissiondar_headers = get_headers("8888888888")
    miller_headers = get_headers("9999999999")

    miller_farmer = client.post(
        "/api/farmers",
        json={
            "name": f"Miller Farmer {uuid.uuid4().hex[:8]}",
            "village": "Miller Village",
        },
        headers=miller_headers,
    )

    assert miller_farmer.status_code == 200, miller_farmer.text

    farmer_id = miller_farmer.json()["id"]

    response = get_farmer_dashboard(
        commissiondar_headers,
        farmer_id,
    )

    assert response.status_code == 404
