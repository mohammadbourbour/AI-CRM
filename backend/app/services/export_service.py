from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.config import get_settings
from app.exceptions import SheetsExportError
from app.models import Lead
from app.providers import sheets as sheets_provider
from app.schemas import SheetsExportResponse
from app.services import lead_service

logger = logging.getLogger(__name__)

HEADERS = [
    "id",
    "external_id",
    "name",
    "email",
    "company",
    "source",
    "priority",
    "status",
    "industry",
    "intent",
    "product_fit",
    "recommended_next_action",
    "created_at",
]


def _cell(value: object) -> str:
    if value is None:
        return ""
    if hasattr(value, "value"):
        return str(value.value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value)


def lead_to_row(lead: Lead) -> list[str]:
    return [
        _cell(lead.id),
        _cell(lead.external_id),
        _cell(lead.name),
        _cell(lead.email),
        _cell(lead.company),
        _cell(lead.source),
        _cell(lead.priority),
        _cell(lead.status),
        _cell(lead.industry),
        _cell(lead.intent),
        _cell(lead.product_fit),
        _cell(lead.recommended_next_action),
        _cell(lead.created_at),
    ]


def export_qualified_leads(db: Session) -> SheetsExportResponse:
    settings = get_settings()
    worksheet = settings.google_sheets_worksheet.strip() or "Qualified Leads"
    if not settings.google_sheets_enabled:
        logger.info("google_sheets_export skipped_unconfigured")
        return SheetsExportResponse(
            outcome="skipped_unconfigured",
            exported=0,
            spreadsheet_id=None,
            worksheet=worksheet,
            reason=(
                "Google Sheets export is disabled. Set GOOGLE_SHEETS_SPREADSHEET_ID "
                "and a service-account credential (file or JSON)."
            ),
        )

    leads = lead_service.list_qualified_leads(db)
    rows = [lead_to_row(lead) for lead in leads]
    try:
        result = sheets_provider.replace_worksheet(HEADERS, rows)
    except SheetsExportError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SheetsExportError(f"Google Sheets export failed: {exc}") from exc

    logger.info("google_sheets_export exported=%s", len(rows))
    return SheetsExportResponse(
        outcome="exported",
        exported=len(rows),
        spreadsheet_id=result.get("spreadsheet_id"),
        worksheet=result.get("worksheet") or worksheet,
        reason=None,
    )
