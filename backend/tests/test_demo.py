from fastapi.testclient import TestClient

from tests.conftest import HOT_PAYLOAD


def test_dashboard_page(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "اتاق فرمان لید" in response.text
    assert "/assets/app.js" in response.text


def test_demo_meta(client: TestClient) -> None:
    response = client.get("/api/demo/meta")
    assert response.status_code == 200
    body = response.json()
    assert body["telegram"] == "disabled"
    assert body["openai"] == "mock"
    assert [stage["id"] for stage in body["stages"]][-1] == "telegram"
    assert "hot" in body["samples"]
    assert "invalid" in body["samples"]


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
