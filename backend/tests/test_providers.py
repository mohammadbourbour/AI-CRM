from app.config import get_settings
from app.pii import mask_email
from app.providers.llm import MockLLMProvider, get_llm_provider, model_supports_json_schema
from app.providers.telegram import send_message
from app.services.notification_service import (
    format_qualification_result_html,
    notify_hot_lead,
    notify_qualification_result,
)
from tests.conftest import HOT_PAYLOAD


def test_missing_groq_uses_mock_provider() -> None:
    settings = get_settings()
    assert settings.groq_enabled is False
    provider = get_llm_provider()
    assert isinstance(provider, MockLLMProvider)


def test_json_schema_model_detection() -> None:
    assert model_supports_json_schema("gpt-4o-mini") is True
    assert model_supports_json_schema("llama-3.1-8b-instant") is False


def test_missing_telegram_does_not_crash() -> None:
    settings = get_settings()
    assert settings.telegram_enabled is False
    assert send_message("hello") is False


def test_qualification_result_without_telegram_credentials(client) -> None:  # noqa: ANN001
    lead_id = client.post("/api/leads", json=HOT_PAYLOAD).json()["id"]
    qualified = client.post(f"/api/leads/{lead_id}/qualify")
    assert qualified.status_code == 200
    from app.db import SessionLocal
    from app.models import Lead

    assert SessionLocal is not None
    db = SessionLocal()
    try:
        lead = db.get(Lead, lead_id)
        assert lead is not None
        html = format_qualification_result_html(lead)
        assert "Lead qualification result" in html
        assert "HOT" in html
        assert "&" not in lead.name
        assert notify_qualification_result(lead) == "skipped_unconfigured"
        assert notify_hot_lead(lead) is False
    finally:
        db.close()


def test_mask_email() -> None:
    assert mask_email("john@northwind.example") == "j***@northwind.example"
    assert mask_email(None) == "***"
