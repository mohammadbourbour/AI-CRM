import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.exceptions import SheetsExportError
from app.services.export_service import HEADERS, lead_to_row
from tests.conftest import HOT_PAYLOAD, WARM_PAYLOAD


def test_export_skipped_when_sheets_unconfigured(client: TestClient) -> None:
    settings = get_settings()
    assert settings.google_sheets_enabled is False
    response = client.post("/api/exports/google-sheets")
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "skipped_unconfigured"
    assert body["exported"] == 0
    assert body["spreadsheet_id"] is None
    assert "service-account" in body["reason"].lower() or "disabled" in body["reason"].lower()


def test_unqualified_leads_are_not_exported(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.export_service.get_settings",
        lambda: type(
            "S",
            (),
            {
                "google_sheets_enabled": True,
                "google_sheets_worksheet": "Qualified Leads",
                "google_sheets_spreadsheet_id": "sheet-demo",
            },
        )(),
    )
    captured: dict = {}

    def fake_replace(headers, rows):  # noqa: ANN001
        captured["headers"] = headers
        captured["rows"] = rows
        return {"spreadsheet_id": "sheet-demo", "worksheet": "Qualified Leads"}

    monkeypatch.setattr("app.providers.sheets.replace_worksheet", fake_replace)
    client.post("/api/leads", json=HOT_PAYLOAD)
    response = client.post("/api/exports/google-sheets")
    assert response.status_code == 200
    assert response.json()["outcome"] == "exported"
    assert response.json()["exported"] == 0
    assert captured["rows"] == []
    assert captured["headers"] == HEADERS


def test_qualified_leads_are_written_to_sheets(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.export_service.get_settings",
        lambda: type(
            "S",
            (),
            {
                "google_sheets_enabled": True,
                "google_sheets_worksheet": "Qualified Leads",
                "google_sheets_spreadsheet_id": "sheet-demo",
            },
        )(),
    )
    captured: dict = {}

    def fake_replace(headers, rows):  # noqa: ANN001
        captured["rows"] = rows
        return {"spreadsheet_id": "sheet-demo", "worksheet": "Qualified Leads"}

    monkeypatch.setattr("app.providers.sheets.replace_worksheet", fake_replace)

    hot_id = client.post("/api/leads", json=HOT_PAYLOAD).json()["id"]
    warm_id = client.post("/api/leads", json=WARM_PAYLOAD).json()["id"]
    assert client.post(f"/api/leads/{hot_id}/qualify").status_code == 200
    assert client.post(f"/api/leads/{warm_id}/qualify").status_code == 200

    response = client.post("/api/exports/google-sheets")
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "exported"
    assert body["exported"] == 2
    assert body["spreadsheet_id"] == "sheet-demo"
    emails = {row[3] for row in captured["rows"]}
    assert "john@northwind.example" in emails
    assert "priya@orbitsaas.example" in emails
    hot_row = next(row for row in captured["rows"] if row[0] == str(hot_id))
    assert hot_row[6] == "hot"
    assert hot_row[7] == "qualified"


def test_sheets_api_failure_returns_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.services.export_service.get_settings",
        lambda: type(
            "S",
            (),
            {
                "google_sheets_enabled": True,
                "google_sheets_worksheet": "Qualified Leads",
                "google_sheets_spreadsheet_id": "sheet-demo",
            },
        )(),
    )
    def fail_replace(headers, rows):  # noqa: ANN001, ARG001
        raise SheetsExportError("Google Sheets write failed: HTTP 403")

    monkeypatch.setattr("app.providers.sheets.replace_worksheet", fail_replace)
    hot_id = client.post("/api/leads", json=HOT_PAYLOAD).json()["id"]
    client.post(f"/api/leads/{hot_id}/qualify")
    response = client.post("/api/exports/google-sheets")
    assert response.status_code == 503
    assert "403" in response.json()["detail"]


def test_lead_to_row_uses_enum_values() -> None:
    lead = type(
        "Lead",
        (),
        {
            "id": 9,
            "external_id": "x",
            "name": "A",
            "email": "a@b.example",
            "company": "Co",
            "source": "website",
            "priority": type("P", (), {"value": "hot"})(),
            "status": type("S", (), {"value": "qualified"})(),
            "industry": "saas",
            "intent": type("I", (), {"value": "high"})(),
            "product_fit": type("F", (), {"value": "high"})(),
            "recommended_next_action": "Call",
            "created_at": None,
        },
    )()
    row = lead_to_row(lead)
    assert row[6] == "hot"
    assert row[7] == "qualified"
    assert row[-1] == ""
