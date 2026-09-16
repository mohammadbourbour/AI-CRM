from __future__ import annotations

import json
import logging
from urllib.parse import quote

import httpx

from app.config import Settings, get_settings
from app.exceptions import SheetsExportError

logger = logging.getLogger(__name__)

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"


def _access_token(settings: Settings) -> str:
    """Mint a service-account token. Lazy-imports google-auth so disabled mode stays light."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account
    except ImportError as exc:
        raise SheetsExportError(
            "google-auth is not installed; pip install -r requirements.txt"
        ) from exc

    raw_json = settings.google_sheets_credentials_json.strip()
    path = settings.google_sheets_credentials_file.strip()
    try:
        if raw_json:
            info = json.loads(raw_json)
            creds = service_account.Credentials.from_service_account_info(
                info, scopes=[SHEETS_SCOPE]
            )
        elif path:
            creds = service_account.Credentials.from_service_account_file(
                path, scopes=[SHEETS_SCOPE]
            )
        else:
            raise SheetsExportError("Google Sheets credentials are not configured")
        creds.refresh(Request())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SheetsExportError(f"Invalid Google Sheets credentials: {exc}") from exc
    if not creds.token:
        raise SheetsExportError("Google Sheets token refresh returned empty token")
    return creds.token


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _quoted_range(worksheet: str, cells: str = "A1") -> str:
    safe_name = worksheet.replace("'", "''")
    return quote(f"'{safe_name}'!{cells}", safe="!'")


def _ensure_worksheet(client: httpx.Client, spreadsheet_id: str, worksheet: str, token: str) -> None:
    meta = client.get(
        f"{SHEETS_API}/{spreadsheet_id}",
        params={"fields": "sheets.properties.title"},
        headers=_headers(token),
        timeout=15.0,
    )
    if meta.status_code == 404:
        raise SheetsExportError("Google spreadsheet not found")
    if meta.status_code >= 400:
        raise SheetsExportError(f"Google Sheets metadata failed: HTTP {meta.status_code}")
    titles = [
        sheet.get("properties", {}).get("title")
        for sheet in meta.json().get("sheets", [])
    ]
    if worksheet in titles:
        return
    added = client.post(
        f"{SHEETS_API}/{spreadsheet_id}:batchUpdate",
        headers=_headers(token),
        json={"requests": [{"addSheet": {"properties": {"title": worksheet}}}]},
        timeout=15.0,
    )
    if added.status_code >= 400:
        raise SheetsExportError(f"Could not create worksheet {worksheet!r}: HTTP {added.status_code}")
    logger.info("google_sheets_worksheet_created name=%s", worksheet)


def replace_worksheet(headers: list[str], rows: list[list[str]]) -> dict:
    """Overwrite the configured worksheet with header + data rows.

    Empty credentials are the caller's problem — this function assumes Sheets is enabled.
    """
    settings = get_settings()
    spreadsheet_id = settings.google_sheets_spreadsheet_id.strip()
    worksheet = settings.google_sheets_worksheet.strip() or "Qualified Leads"
    token = _access_token(settings)
    encoded = _quoted_range(worksheet, "A:Z")
    values = [headers, *rows]
    try:
        with httpx.Client() as client:
            _ensure_worksheet(client, spreadsheet_id, worksheet, token)
            cleared = client.post(
                f"{SHEETS_API}/{spreadsheet_id}/values/{encoded}:clear",
                headers=_headers(token),
                json={},
                timeout=15.0,
            )
            if cleared.status_code >= 400:
                raise SheetsExportError(f"Google Sheets clear failed: HTTP {cleared.status_code}")
            written = client.put(
                f"{SHEETS_API}/{spreadsheet_id}/values/{_quoted_range(worksheet, 'A1')}",
                params={"valueInputOption": "RAW"},
                headers=_headers(token),
                json={"values": values},
                timeout=20.0,
            )
            if written.status_code >= 400:
                raise SheetsExportError(f"Google Sheets write failed: HTTP {written.status_code}")
            body = written.json()
    except httpx.HTTPError as exc:
        raise SheetsExportError(f"Google Sheets request failed: {exc}") from exc
    logger.info(
        "google_sheets_export_ok spreadsheet_id=%s rows=%s",
        spreadsheet_id,
        len(rows),
    )
    return {
        "spreadsheet_id": spreadsheet_id,
        "worksheet": worksheet,
        "updated_range": body.get("updatedRange"),
        "updated_rows": body.get("updatedRows"),
    }
