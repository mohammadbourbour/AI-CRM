from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.exceptions import QualificationFailedError
from app.models import IntentLevel, Lead, LeadStatus, Priority, ProductFit, utc_now
from app.pii import mask_email
from app.providers.llm import LLMProvider, get_llm_provider
from app.schemas import AIQualificationResult
from app.services.notification_service import notify_qualification_result

logger = logging.getLogger(__name__)


def compute_priority(intent: IntentLevel, product_fit: ProductFit) -> Priority:
    """Deterministic routing. LLM-suggested priority is never persisted as-is."""
    if intent == IntentLevel.HIGH and product_fit == ProductFit.HIGH:
        return Priority.HOT
    if intent in (IntentLevel.MEDIUM, IntentLevel.HIGH) or product_fit in (
        ProductFit.MEDIUM,
        ProductFit.HIGH,
    ):
        return Priority.WARM
    return Priority.COLD


def _persist_qualification_error(db: Session, lead: Lead, message: str) -> None:
    lead.qualification_error = message
    lead.updated_at = utc_now()
    db.commit()
    db.refresh(lead)


def qualify_lead(
    db: Session,
    lead: Lead,
    llm: LLMProvider | None = None,
    *,
    notify: bool = True,
) -> Lead:
    logger.info(
        "qualification_start lead_id=%s email=%s",
        lead.id,
        mask_email(lead.email),
    )
    provider = llm or get_llm_provider()
    try:
        result: AIQualificationResult = provider.qualify_lead(lead)
    except QualificationFailedError as exc:
        logger.warning("qualification_failure lead_id=%s error=%s", lead.id, exc.message)
        _persist_qualification_error(db, lead, exc.message)
        raise
    except Exception as exc:
        message = f"Unexpected qualification failure: {exc}"
        logger.exception("qualification_failure lead_id=%s", lead.id)
        _persist_qualification_error(db, lead, message)
        raise QualificationFailedError(message) from exc

    computed = compute_priority(result.intent, result.product_fit)
    logger.info(
        "qualification_priority lead_id=%s llm_priority=%s computed_priority=%s",
        lead.id,
        result.priority.value,
        computed.value,
    )

    lead.industry = result.industry
    lead.intent = result.intent
    lead.product_fit = result.product_fit
    lead.priority = computed
    lead.ai_summary = result.summary
    lead.pain_points = result.pain_points
    lead.recommended_next_action = result.recommended_next_action
    lead.qualification_error = None
    if lead.status == LeadStatus.NEW:
        lead.status = LeadStatus.QUALIFIED
    lead.updated_at = utc_now()
    db.commit()
    db.refresh(lead)

    logger.info(
        "qualification_success lead_id=%s priority=%s status=%s",
        lead.id,
        lead.priority.value if lead.priority else None,
        lead.status.value,
    )

    if notify:
        notify_qualification_result(lead)

    return lead
