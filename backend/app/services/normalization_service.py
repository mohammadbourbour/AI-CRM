from __future__ import annotations

from pydantic import ValidationError

from app.schemas import LeadCreate

KNOWN_SOURCES = frozenset(
    {"website", "form", "webhook", "referral", "outbound", "linkedin", "unknown"}
)


class NormalizationError(ValueError):
    pass


def _clean(value: str) -> str:
    return " ".join(value.strip().split())


def normalize_lead_payload(payload: LeadCreate) -> LeadCreate:
    name = _clean(payload.name)
    company = _clean(payload.company)
    message = payload.message.strip()
    if not name:
        raise NormalizationError("name is required")
    if not company:
        raise NormalizationError("company is required")
    if not message:
        raise NormalizationError("message is required")

    source = (payload.source or "unknown").strip().lower()
    if source not in KNOWN_SOURCES:
        source = "unknown"

    company_size = payload.company_size.strip() if payload.company_size else None
    if company_size == "":
        company_size = None

    external_id = payload.external_id.strip() if payload.external_id else None
    if external_id == "":
        external_id = None

    assigned_to = payload.assigned_to.strip() if payload.assigned_to else None
    if assigned_to == "":
        assigned_to = None

    try:
        return LeadCreate(
            name=name,
            email=str(payload.email).strip().lower(),
            company=company,
            company_size=company_size,
            source=source,
            message=message,
            external_id=external_id,
            assigned_to=assigned_to,
        )
    except ValidationError as exc:
        raise NormalizationError(str(exc)) from exc
