import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.exceptions import QualificationFailedError
from app.models import IntentLevel, ProductFit, Priority
from app.providers.llm import parse_qualification
from app.services.qualification_service import compute_priority
from tests.conftest import COLD_PAYLOAD, HOT_PAYLOAD, WARM_PAYLOAD


def test_priority_hot() -> None:
    assert compute_priority(IntentLevel.HIGH, ProductFit.HIGH) == Priority.HOT


def test_priority_warm_medium_intent() -> None:
    assert compute_priority(IntentLevel.MEDIUM, ProductFit.LOW) == Priority.WARM


def test_priority_warm_high_fit() -> None:
    assert compute_priority(IntentLevel.LOW, ProductFit.HIGH) == Priority.WARM


def test_priority_cold() -> None:
    assert compute_priority(IntentLevel.LOW, ProductFit.LOW) == Priority.COLD
    assert compute_priority(IntentLevel.LOW, ProductFit.UNKNOWN) == Priority.COLD


def test_qualification_schema_rejects_invalid_json() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_qualification("not-json")


def test_qualification_schema_rejects_missing_fields() -> None:
    with pytest.raises(ValidationError):
        parse_qualification(json.dumps({"industry": "saas", "intent": "high"}))


def test_mock_qualification_hot_warm_cold(client: TestClient) -> None:
    hot_id = client.post("/api/leads", json=HOT_PAYLOAD).json()["id"]
    warm_id = client.post("/api/leads", json=WARM_PAYLOAD).json()["id"]
    cold_id = client.post("/api/leads", json=COLD_PAYLOAD).json()["id"]

    hot = client.post(f"/api/leads/{hot_id}/qualify")
    warm = client.post(f"/api/leads/{warm_id}/qualify")
    cold = client.post(f"/api/leads/{cold_id}/qualify")

    assert hot.status_code == 200
    assert hot.json()["priority"] == "hot"
    assert hot.json()["status"] == "qualified"
    assert hot.json()["qualification_error"] is None

    assert warm.status_code == 200
    assert warm.json()["priority"] == "warm"

    assert cold.status_code == 200
    assert cold.json()["priority"] == "cold"


def test_failed_qualification_keeps_status_and_stores_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingLLM:
        def qualify_lead(self, lead):  # noqa: ANN001
            raise QualificationFailedError("LLM returned invalid qualification JSON")

        def generate_followup_draft(self, lead) -> str:  # noqa: ANN001
            return "unused"

    monkeypatch.setattr(
        "app.services.qualification_service.get_llm_provider",
        lambda: FailingLLM(),
    )
    lead_id = client.post("/api/leads", json=HOT_PAYLOAD).json()["id"]
    response = client.post(f"/api/leads/{lead_id}/qualify")
    assert response.status_code == 503

    stored = client.get(f"/api/leads/{lead_id}").json()
    assert stored["status"] == "new"
    assert stored["priority"] is None
    assert stored["qualification_error"]
