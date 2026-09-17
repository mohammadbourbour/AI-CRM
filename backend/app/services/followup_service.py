from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy.orm import Session

from app.exceptions import FollowUpConflictError, QualificationFailedError
from app.models import FollowUpStatus, Lead, LeadStatus, utc_now
from app.providers.llm import LLMProvider, get_llm_provider

logger = logging.getLogger(__name__)

APPROVABLE = {FollowUpStatus.DRAFT_READY, FollowUpStatus.AWAITING_APPROVAL}


def generate_draft(db: Session, lead: Lead, llm: LLMProvider | None = None) -> Lead:
    if lead.follow_up_status in {FollowUpStatus.APPROVED, FollowUpStatus.SENT}:
        raise FollowUpConflictError(
            f"Follow-up already {lead.follow_up_status.value}; draft cannot be regenerated"
        )
    logger.info("followup_draft_start lead_id=%s", lead.id)
    provider = llm or get_llm_provider()
    try:
        draft = provider.generate_followup_draft(lead)
    except QualificationFailedError:
        logger.warning("followup_draft_failure lead_id=%s", lead.id)
        raise
    lead.draft_message = draft
    lead.follow_up_status = FollowUpStatus.AWAITING_APPROVAL
    lead.follow_up_due_at = utc_now() + timedelta(hours=24)
    lead.updated_at = utc_now()
    db.commit()
    db.refresh(lead)
    logger.info("followup_draft_ready lead_id=%s status=%s", lead.id, lead.follow_up_status.value)
    return lead


def approve_and_send(db: Session, lead: Lead) -> tuple[Lead, str]:
    if lead.follow_up_status == FollowUpStatus.SENT:
        raise FollowUpConflictError("Follow-up already sent")
    if lead.follow_up_status == FollowUpStatus.APPROVED:
        raise FollowUpConflictError("Follow-up already approved")
    if lead.follow_up_status not in APPROVABLE or not lead.draft_message:
        raise FollowUpConflictError(
            "Follow-up cannot be sent until a draft exists and is explicitly approved"
        )

    logger.info("followup_approval lead_id=%s", lead.id)
    now = utc_now()
    lead.follow_up_status = FollowUpStatus.APPROVED
    lead.approved_at = now
    # Mock send: no real email. Documented as a safe stand-in.
    send_result = "mock_sent"
    lead.follow_up_status = FollowUpStatus.SENT
    if lead.status == LeadStatus.QUALIFIED:
        lead.status = LeadStatus.CONTACTED
    lead.updated_at = now
    db.commit()
    db.refresh(lead)
    logger.info(
        "followup_mock_sent lead_id=%s status=%s follow_up_status=%s",
        lead.id,
        lead.status.value,
        lead.follow_up_status.value,
    )
    return lead, send_result


def reject_draft(db: Session, lead: Lead) -> Lead:
    """Human rejection: keep the draft for audit, do not send, mark skipped."""
    if lead.follow_up_status == FollowUpStatus.SENT:
        raise FollowUpConflictError("Follow-up already sent")
    if lead.follow_up_status not in APPROVABLE or not lead.draft_message:
        raise FollowUpConflictError(
            "Follow-up cannot be rejected until a draft exists and is awaiting approval"
        )
    logger.info("followup_rejected lead_id=%s", lead.id)
    lead.follow_up_status = FollowUpStatus.SKIPPED
    lead.updated_at = utc_now()
    db.commit()
    db.refresh(lead)
    return lead
