from fastapi.testclient import TestClient

from tests.conftest import HOT_PAYLOAD


def test_valid_lead_creation(client: TestClient) -> None:
    payload = {k: v for k, v in HOT_PAYLOAD.items() if k != "external_id"}
    response = client.post("/api/leads", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "John Smith"
    assert body["email"] == "john@northwind.example"
    assert body["status"] == "new"
    assert body["follow_up_status"] == "not_started"
    assert body["qualification_error"] is None


def test_invalid_lead_payload(client: TestClient) -> None:
    response = client.post(
        "/api/leads",
        json={"name": "No Email", "company": "Acme", "message": "hello world"},
    )
    assert response.status_code == 422


def test_invalid_email_payload(client: TestClient) -> None:
    response = client.post(
        "/api/leads",
        json={
            "name": "Bad Email",
            "email": "not-an-email",
            "company": "Acme",
            "message": "hello world",
        },
    )
    assert response.status_code == 422


def test_lead_listing_and_retrieval(client: TestClient) -> None:
    created = client.post(
        "/api/leads",
        json={
            "name": "Sam Rivera",
            "email": "sam@example.com",
            "company": "Rivera Co",
            "message": "Need a demo next month",
        },
    )
    assert created.status_code == 201
    lead_id = created.json()["id"]

    listed = client.get("/api/leads")
    assert listed.status_code == 200
    ids = [item["id"] for item in listed.json()]
    assert lead_id in ids

    fetched = client.get(f"/api/leads/{lead_id}")
    assert fetched.status_code == 200
    assert fetched.json()["company"] == "Rivera Co"


def test_lead_not_found(client: TestClient) -> None:
    response = client.get("/api/leads/99999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Lead not found"
