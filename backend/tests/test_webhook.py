from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.schemas import LeadCreate
from app.services.lead_service import create_lead
from tests.conftest import HOT_PAYLOAD


def test_webhook_requires_secret(client: TestClient) -> None:
    missing = client.post("/api/webhooks/leads", json=HOT_PAYLOAD)
    assert missing.status_code == 401

    wrong = client.post(
        "/api/webhooks/leads",
        json=HOT_PAYLOAD,
        headers={"X-Webhook-Secret": "wrong-secret-value"},
    )
    assert wrong.status_code == 401


def test_webhook_creates_lead(client: TestClient, webhook_headers: dict[str, str]) -> None:
    response = client.post("/api/webhooks/leads", json=HOT_PAYLOAD, headers=webhook_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["external_id"] == "demo-hot-001"
    assert body["email"] == "john@northwind.example"


def test_duplicate_webhook_returns_existing_lead(
    client: TestClient, webhook_headers: dict[str, str]
) -> None:
    first = client.post("/api/webhooks/leads", json=HOT_PAYLOAD, headers=webhook_headers)
    second = client.post("/api/webhooks/leads", json=HOT_PAYLOAD, headers=webhook_headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    listed = client.get("/api/leads")
    matches = [row for row in listed.json() if row["external_id"] == "demo-hot-001"]
    assert len(matches) == 1


def test_create_lead_recovers_from_integrity_error() -> None:
    db = MagicMock()
    db.commit.side_effect = IntegrityError(
        "INSERT INTO leads",
        {},
        Exception("UNIQUE constraint failed: leads.external_id"),
    )
    existing = MagicMock()
    existing.id = 42
    existing.external_id = "ext-race-1"
    db.scalars.return_value.first.return_value = existing

    data = LeadCreate(
        name="Jane Doe",
        email="jane@example.com",
        company="Acme",
        message="Need a walkthrough of the platform",
        external_id="ext-race-1",
    )
    lead, created = create_lead(db, data)
    assert created is False
    assert lead.id == 42
    db.add.assert_called_once()
    db.rollback.assert_called_once()
    db.scalars.assert_called_once()
