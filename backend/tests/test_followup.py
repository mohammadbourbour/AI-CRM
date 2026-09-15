from fastapi.testclient import TestClient

from tests.conftest import HOT_PAYLOAD


def test_followup_requires_approval(client: TestClient) -> None:
    lead_id = client.post("/api/leads", json=HOT_PAYLOAD).json()["id"]
    denied = client.post(f"/api/leads/{lead_id}/approve-followup")
    assert denied.status_code == 409
    assert "approved" in denied.json()["detail"].lower() or "draft" in denied.json()["detail"].lower()


def test_followup_draft_then_approve(client: TestClient) -> None:
    lead_id = client.post("/api/leads", json=HOT_PAYLOAD).json()["id"]
    client.post(f"/api/leads/{lead_id}/qualify")
    draft = client.post(f"/api/leads/{lead_id}/followup/draft")
    assert draft.status_code == 200
    body = draft.json()
    assert body["follow_up_status"] == "awaiting_approval"
    assert body["draft_message"]

    approved = client.post(f"/api/leads/{lead_id}/approve-followup")
    assert approved.status_code == 200
    result = approved.json()
    assert result["follow_up_status"] == "sent"
    assert result["send_result"] == "mock_sent"
    assert result["status"] == "contacted"


def test_followup_cannot_approve_twice(client: TestClient) -> None:
    lead_id = client.post("/api/leads", json=HOT_PAYLOAD).json()["id"]
    client.post(f"/api/leads/{lead_id}/qualify")
    client.post(f"/api/leads/{lead_id}/followup/draft")
    first = client.post(f"/api/leads/{lead_id}/approve-followup")
    second = client.post(f"/api/leads/{lead_id}/approve-followup")
    assert first.status_code == 200
    assert second.status_code == 409
