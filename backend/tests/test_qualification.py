import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.exceptions import QualificationFailedError
from app.models import IntentLevel, ProductFit, Priority
from app.providers.llm import parse_qualification
from app.schemas import AIQualificationResult
from app.services.qualification_service import _apply_buying_stage_guard, compute_priority
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


def test_buying_stage_guard_promotes_hot_demo_message() -> None:
    from types import SimpleNamespace

    lead = SimpleNamespace(message=HOT_PAYLOAD["message"], company=HOT_PAYLOAD["company"])
    scored = AIQualificationResult(
        industry="energy",
        intent=IntentLevel.MEDIUM,
        product_fit=ProductFit.HIGH,
        priority=Priority.WARM,
        pain_points=["evaluation"],
        summary="Evaluating a solution.",
        recommended_next_action="Discovery call",
    )
    promoted = _apply_buying_stage_guard(lead, scored)
    assert promoted.intent == IntentLevel.HIGH
    assert promoted.product_fit == ProductFit.HIGH
    assert compute_priority(promoted.intent, promoted.product_fit) == Priority.HOT


def test_qualification_schema_rejects_invalid_json() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_qualification("not-json")


def test_qualification_schema_rejects_missing_fields() -> None:
    with pytest.raises(ValidationError):
        parse_qualification(json.dumps({"industry": "saas", "intent": "high"}))


def test_parse_qualification_normalizes_llm_enum_labels() -> None:
    result = parse_qualification(
        json.dumps(
            {
                "industry": "energy",
                "intent": "Evaluation",
                "product_fit": "High",
                "priority": "Warm",
                "pain_points": "multi-site maintenance",
                "summary": "Evaluating predictive maintenance across facilities.",
                "recommended_next_action": "Book a discovery call",
            }
        )
    )
    assert result.intent == IntentLevel.HIGH
    assert result.product_fit == ProductFit.HIGH
    assert result.priority == Priority.WARM
    assert result.pain_points == ["multi-site maintenance"]


def test_parse_qualification_accepts_fenced_json() -> None:
    raw = """```json
{"industry":"saas","intent":"high","product_fit":"medium","priority":"warm",
 "pain_points":["onboarding"],"summary":"SaaS growth.","recommended_next_action":"Demo"}
```"""
    result = parse_qualification(raw)
    assert result.intent == IntentLevel.HIGH
    assert result.product_fit == ProductFit.MEDIUM


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
