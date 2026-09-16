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


def test_followup_reject_requires_draft(client: TestClient) -> None:
    lead_id = client.post("/api/leads", json={**HOT_PAYLOAD, "external_id": "hot-reject-no-draft"}).json()["id"]
    denied = client.post(f"/api/leads/{lead_id}/reject-followup")
    assert denied.status_code == 409


def test_followup_draft_then_reject(client: TestClient) -> None:
    lead_id = client.post("/api/leads", json={**HOT_PAYLOAD, "external_id": "hot-reject-ok"}).json()["id"]
    client.post(f"/api/leads/{lead_id}/qualify")
    client.post(f"/api/leads/{lead_id}/followup/draft")
    rejected = client.post(f"/api/leads/{lead_id}/reject-followup")
    assert rejected.status_code == 200
    body = rejected.json()
    assert body["follow_up_status"] == "skipped"
    assert body["decision"] == "rejected"
    stored = client.get(f"/api/leads/{lead_id}").json()
    assert stored["status"] == "qualified"
    assert stored["follow_up_status"] == "skipped"
    assert stored["draft_message"]


def test_followup_cannot_approve_after_reject(client: TestClient) -> None:
    lead_id = client.post("/api/leads", json={**HOT_PAYLOAD, "external_id": "hot-reject-then-approve"}).json()["id"]
    client.post(f"/api/leads/{lead_id}/qualify")
    client.post(f"/api/leads/{lead_id}/followup/draft")
    assert client.post(f"/api/leads/{lead_id}/reject-followup").status_code == 200
    assert client.post(f"/api/leads/{lead_id}/approve-followup").status_code == 409


def test_followup_cannot_approve_twice(client: TestClient) -> None:
    lead_id = client.post("/api/leads", json={**HOT_PAYLOAD, "external_id": "hot-approve-twice"}).json()["id"]
    client.post(f"/api/leads/{lead_id}/qualify")
    client.post(f"/api/leads/{lead_id}/followup/draft")
    first = client.post(f"/api/leads/{lead_id}/approve-followup")
    second = client.post(f"/api/leads/{lead_id}/approve-followup")
    assert first.status_code == 200
    assert second.status_code == 409
