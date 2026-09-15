from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.exceptions import InvalidStatusTransitionError
from app.models import ALLOWED_STATUS_TRANSITIONS, Lead, LeadStatus, Priority, utc_now
from app.schemas import LeadCreate, LeadUpdate

logger = logging.getLogger(__name__)


def get_lead(db: Session, lead_id: int) -> Lead | None:
    return db.get(Lead, lead_id)


def list_leads(db: Session, priority: str | None = None) -> list[Lead]:
    stmt = select(Lead).order_by(Lead.created_at.desc())
    if priority:
        stmt = stmt.where(Lead.priority == Priority(priority))
    return list(db.scalars(stmt).all())


def create_lead(db: Session, data: LeadCreate) -> tuple[Lead, bool]:
    """Insert a lead. On unique external_id conflict, return the existing row.

    created=True means this call inserted a new row.
    created=False means an IntegrityError was recovered by re-query.
    """
    lead = Lead(
        external_id=data.external_id,
        name=data.name,
        email=str(data.email),
        company=data.company,
        company_size=data.company_size,
        source=data.source,
        message=data.message,
        assigned_to=data.assigned_to,
        status=LeadStatus.NEW,
    )
    db.add(lead)
    try:
        db.commit()
        db.refresh(lead)
        logger.info(
            "lead_created id=%s external_id=%s source=%s",
            lead.id,
            lead.external_id,
            lead.source,
        )
        return lead, True
    except IntegrityError:
        db.rollback()
        if not data.external_id:
            raise
        existing = db.scalars(
            select(Lead).where(Lead.external_id == data.external_id)
        ).first()
        if existing is None:
            raise
        logger.info(
            "lead_idempotent_hit external_id=%s id=%s",
            data.external_id,
            existing.id,
        )
        return existing, False


def update_lead(db: Session, lead: Lead, patch: LeadUpdate) -> Lead:
    updates = patch.model_dump(exclude_unset=True)
    new_status = updates.get("status")
    if new_status is not None and new_status != lead.status:
        allowed = ALLOWED_STATUS_TRANSITIONS.get(lead.status, set())
        if new_status not in allowed:
            raise InvalidStatusTransitionError(
                f"Cannot transition status from {lead.status.value} to {new_status.value}"
            )
    for field, value in updates.items():
        setattr(lead, field, value)
    lead.updated_at = utc_now()
    db.commit()
    db.refresh(lead)
    return lead
