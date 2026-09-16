import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["WEBHOOK_SECRET"] = "test-webhook-secret"
os.environ["OPENAI_API_KEY"] = ""
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""
os.environ["GOOGLE_SHEETS_CREDENTIALS_FILE"] = ""
os.environ["GOOGLE_SHEETS_CREDENTIALS_JSON"] = ""
os.environ["GOOGLE_SHEETS_SPREADSHEET_ID"] = ""
os.environ["LOG_LEVEL"] = "WARNING"

from app.config import get_settings

get_settings.cache_clear()

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client() -> TestClient:
    get_settings.cache_clear()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def webhook_headers() -> dict[str, str]:
    return {"X-Webhook-Secret": "test-webhook-secret"}


HOT_PAYLOAD = {
    "external_id": "demo-hot-001",
    "name": "John Smith",
    "email": "john@northwind.example",
    "company": "Northwind Energy",
    "company_size": "500-1000",
    "source": "website",
    "message": (
        "We are evaluating an AI solution for predictive maintenance "
        "across multiple facilities."
    ),
}

WARM_PAYLOAD = {
    "external_id": "demo-warm-001",
    "name": "Priya Shah",
    "email": "priya@orbitsaas.example",
    "company": "Orbit SaaS",
    "source": "linkedin",
    "message": (
        "We are a SaaS company scaling onboarding and looking at automation "
        "for customer success seats."
    ),
}

COLD_PAYLOAD = {
    "external_id": "demo-cold-001",
    "name": "Alex Chen",
    "email": "alex@generic.example",
    "company": "Generic LLC",
    "source": "website",
    "message": "Just browsing. Can you send general pricing information?",
}
