from app.config import get_settings
from app.pii import mask_email
from app.providers.llm import MockLLMProvider, get_llm_provider, model_supports_json_schema
from app.providers.telegram import send_message
from app.services.notification_service import notify_hot_lead
from tests.conftest import HOT_PAYLOAD


def test_missing_openai_uses_mock_provider() -> None:
    settings = get_settings()
    assert settings.openai_enabled is False
    provider = get_llm_provider()
    assert isinstance(provider, MockLLMProvider)


def test_json_schema_model_detection() -> None:
    assert model_supports_json_schema("gpt-4o-mini") is True
    assert model_supports_json_schema("gpt-4.1") is True
    assert model_supports_json_schema("gpt-3.5-turbo") is False


def test_missing_telegram_does_not_crash() -> None:
    settings = get_settings()
    assert settings.telegram_enabled is False
    assert send_message("hello") is False


def test_hot_notify_without_telegram_credentials(client) -> None:  # noqa: ANN001
    lead_id = client.post("/api/leads", json=HOT_PAYLOAD).json()["id"]
    qualified = client.post(f"/api/leads/{lead_id}/qualify")
    assert qualified.status_code == 200
    assert qualified.json()["priority"] == "hot"
    from app.models import Lead
    from app.db import SessionLocal

    assert SessionLocal is not None
    db = SessionLocal()
    try:
        lead = db.get(Lead, lead_id)
        assert lead is not None
        assert notify_hot_lead(lead) is False
    finally:
        db.close()


def test_mask_email() -> None:
    assert mask_email("john@northwind.example") == "j***@northwind.example"
    assert mask_email(None) == "***"
