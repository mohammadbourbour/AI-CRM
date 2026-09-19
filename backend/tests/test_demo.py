from fastapi.testclient import TestClient
import pytest

from tests.conftest import HOT_PAYLOAD


def test_dashboard_page(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Lead operations" in response.text
    assert "/assets/app.js" in response.text
    assert "Approval queue" in response.text


def test_demo_meta(client: TestClient) -> None:
    response = client.get("/api/demo/meta")
    assert response.status_code == 200
    body = response.json()
    assert body["telegram"] == "disabled"
    assert body["groq"] == "mock"
    assert [stage["id"] for stage in body["stages"]][-1] == "telegram"
    assert "hot" in body["samples"]
    assert "invalid" in body["samples"]
    assert body["n8n_webhook_configured"] is False
    assert body["n8n_executions_url"].endswith("/home/executions")
    assert body["n8n_sheets_configured"] is False


def test_demo_hot_run_records_every_stage(client: TestClient) -> None:
    response = client.post("/api/demo/runs", json={"sample": "hot"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["lead"]["priority"] == "hot"
    assert body["lead"]["follow_up_status"] == "awaiting_approval"
    assert body["telegram_status"] == "skipped_unconfigured"
    by_id = {stage["id"]: stage for stage in body["stages"]}
    assert by_id["intake"]["status"] == "done"
    assert by_id["qualify"]["status"] == "done"
    assert by_id["draft"]["status"] == "done"
    assert by_id["telegram"]["status"] == "skipped"
    assert "empty" in by_id["telegram"]["detail"]


def test_demo_cold_skips_draft(client: TestClient) -> None:
    response = client.post("/api/demo/runs", json={"sample": "cold"})
    assert response.status_code == 200
    body = response.json()
    assert body["lead"]["priority"] == "cold"
    by_id = {stage["id"]: stage for stage in body["stages"]}
    assert by_id["draft"]["status"] == "skipped"


def test_demo_custom_lead(client: TestClient) -> None:
    payload = {**HOT_PAYLOAD, "external_id": "dashboard-custom-1", "name": "Dana Client"}
    response = client.post("/api/demo/runs", json={"sample": "hot", "lead": payload})
    assert response.status_code == 200
    assert response.json()["lead"]["name"] == "Dana Client"


def test_demo_invalid_never_creates_lead(client: TestClient) -> None:
    before = len(client.get("/api/leads").json())
    response = client.post("/api/demo/runs", json={"sample": "invalid"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["lead"] is None
    assert body["telegram_status"] == "not_applicable"
    by_id = {stage["id"]: stage for stage in body["stages"]}
    assert by_id["validate"]["status"] == "failed"
    assert by_id["crm"]["status"] == "skipped"
    assert len(client.get("/api/leads").json()) == before
    response = client.post("/api/demo/runs", json={"sample": "nuclear"})
    assert response.status_code == 422


def test_latest_run_after_demo(client: TestClient) -> None:
    created = client.post("/api/demo/runs", json={"sample": "warm"}).json()
    latest = client.get("/api/demo/runs/latest")
    assert latest.status_code == 200
    assert latest.json()["id"] == created["id"]
    assert latest.json()["via"] == "crm"


def test_demo_via_n8n_without_url(client: TestClient) -> None:
    response = client.post("/api/demo/runs", json={"sample": "hot", "via": "n8n"})
    assert response.status_code == 503
    assert "N8N_WEBHOOK_URL" in response.json()["detail"]


def test_demo_via_n8n_validation_failed(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.demo_service.post_lead_intake",
        lambda payload: {
            "outcome": "validation_failed",
            "errors": ["name is required"],
            "lead_id": None,
            "channels": {},
        },
    )
    before = len(client.get("/api/leads").json())
    response = client.post("/api/demo/runs", json={"sample": "invalid", "via": "n8n"})
    assert response.status_code == 200
    body = response.json()
    assert body["via"] == "n8n"
    assert body["status"] == "failed"
    assert body["lead"] is None
    assert body["n8n_outcome"] == "validation_failed"
    assert body["telegram_status"] == "not_applicable"
    assert len(client.get("/api/leads").json()) == before


def test_demo_via_n8n_hot_processed(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    created = client.post("/api/leads", json={**HOT_PAYLOAD, "external_id": "n8n-via-hot"}).json()
    client.post(f"/api/leads/{created['id']}/qualify")
    client.post(f"/api/leads/{created['id']}/followup/draft")

    def fake_intake(_payload: dict) -> dict:
        return {
            "outcome": "processed",
            "lead_id": created["id"],
            "routed": "hot",
            "priority": "hot",
            "follow_up_status": "awaiting_approval",
            "channels": {
                "google_sheets": "skipped_unconfigured",
                "telegram_sales_alert": "skipped_unconfigured",
            },
        }

    monkeypatch.setattr("app.services.demo_service.post_lead_intake", fake_intake)
    response = client.post("/api/demo/runs", json={"sample": "hot", "via": "n8n"})
    assert response.status_code == 200
    body = response.json()
    assert body["via"] == "n8n"
    assert body["n8n_outcome"] == "processed"
    assert body["lead"]["id"] == created["id"]
    assert body["lead"]["follow_up_status"] == "awaiting_approval"
    assert body["sheets_status"] == "skipped_unconfigured"
    assert body["telegram_preview"]
    assert body["sheets_row"]["id"] == created["id"]
    by_id = {stage["id"]: stage for stage in body["stages"]}
    assert by_id["intake"]["status"] == "done"
    assert by_id["draft"]["status"] == "done"
    assert by_id["sheets"]["status"] == "skipped"


def test_demo_via_n8n_unpublished(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.exceptions import N8nUnavailableError

    def boom(_payload: dict) -> dict:
        raise N8nUnavailableError(
            "n8n webhook is not registered. Open Lead Qualification in n8n and click Publish"
        )

    monkeypatch.setattr("app.services.demo_service.post_lead_intake", boom)
    response = client.post("/api/demo/runs", json={"sample": "hot", "via": "n8n"})
    assert response.status_code == 503
    assert "Publish" in response.json()["detail"]
