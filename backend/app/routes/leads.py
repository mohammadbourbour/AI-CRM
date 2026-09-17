from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.exceptions import (
    FollowUpConflictError,
    InvalidStatusTransitionError,
    QualificationFailedError,
)
from app.models import Priority
from app.pii import mask_email
from app.schemas import (
    FollowUpApproveResponse,
    FollowUpDraftResponse,
    FollowUpRejectResponse,
    LeadCreate,
    LeadResponse,
    LeadUpdate,
    WebhookLeadPayload,
)
from app.services import followup_service, lead_service, qualification_service
from app.services.normalization_service import NormalizationError, normalize_lead_payload

logger = logging.getLogger(__name__)

router = APIRouter()


def _webhook_secret_matches(provided: str | None, expected: str) -> bool:
    if provided is None or len(provided) != len(expected):
        return False
    return secrets.compare_digest(provided, expected)


def require_webhook_secret(
    x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
) -> None:
    expected = get_settings().webhook_secret
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="WEBHOOK_SECRET is not configured",
        )
    if not _webhook_secret_matches(x_webhook_secret, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret",
        )


def _get_or_404(db: Session, lead_id: int):
    lead = lead_service.get_lead(db, lead_id)
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return lead


@router.post("", response_model=LeadResponse)
def create_lead(
    payload: LeadCreate,
    response: Response,
    db: Session = Depends(get_db),
) -> LeadResponse:
    try:
        normalized = normalize_lead_payload(payload)
    except NormalizationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    lead, created = lead_service.create_lead(db, normalized)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return LeadResponse.model_validate(lead)


@router.get("", response_model=list[LeadResponse])
def list_leads(
    priority: Priority | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[LeadResponse]:
    leads = lead_service.list_leads(db, priority=priority.value if priority else None)
    return [LeadResponse.model_validate(lead) for lead in leads]


@router.get("/{lead_id}", response_model=LeadResponse)
def get_lead(lead_id: int, db: Session = Depends(get_db)) -> LeadResponse:
    return LeadResponse.model_validate(_get_or_404(db, lead_id))


@router.patch("/{lead_id}", response_model=LeadResponse)
def update_lead(lead_id: int, payload: LeadUpdate, db: Session = Depends(get_db)) -> LeadResponse:
    lead = _get_or_404(db, lead_id)
    try:
        updated = lead_service.update_lead(db, lead, payload)
    except InvalidStatusTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message) from exc
    return LeadResponse.model_validate(updated)


@router.post("/{lead_id}/qualify", response_model=LeadResponse)
def qualify_lead(lead_id: int, db: Session = Depends(get_db)) -> LeadResponse:
    lead = _get_or_404(db, lead_id)
    try:
        qualified = qualification_service.qualify_lead(db, lead)
    except QualificationFailedError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.message,
        ) from exc
    return LeadResponse.model_validate(qualified)


@router.post("/{lead_id}/followup/draft", response_model=FollowUpDraftResponse)
def create_followup_draft(lead_id: int, db: Session = Depends(get_db)) -> FollowUpDraftResponse:
    lead = _get_or_404(db, lead_id)
    try:
        updated = followup_service.generate_draft(db, lead)
    except FollowUpConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message) from exc
    except QualificationFailedError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.message,
        ) from exc
    assert updated.draft_message is not None
    return FollowUpDraftResponse(
        lead_id=updated.id,
        follow_up_status=updated.follow_up_status,
        draft_message=updated.draft_message,
        follow_up_due_at=updated.follow_up_due_at,
    )


@router.post("/{lead_id}/approve-followup", response_model=FollowUpApproveResponse)
def approve_followup(lead_id: int, db: Session = Depends(get_db)) -> FollowUpApproveResponse:
    lead = _get_or_404(db, lead_id)
    try:
        updated, send_result = followup_service.approve_and_send(db, lead)
    except FollowUpConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message) from exc
    assert updated.approved_at is not None
    return FollowUpApproveResponse(
        lead_id=updated.id,
        follow_up_status=updated.follow_up_status,
        approved_at=updated.approved_at,
        send_result=send_result,
        status=updated.status,
    )


@router.post("/{lead_id}/reject-followup", response_model=FollowUpRejectResponse)
def reject_followup(lead_id: int, db: Session = Depends(get_db)) -> FollowUpRejectResponse:
    lead = _get_or_404(db, lead_id)
    try:
        updated = followup_service.reject_draft(db, lead)
    except FollowUpConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message) from exc
    return FollowUpRejectResponse(
        lead_id=updated.id,
        follow_up_status=updated.follow_up_status,
        status=updated.status,
    )


webhook_router = APIRouter()


@webhook_router.post(
    "/leads",
    response_model=LeadResponse,
    dependencies=[Depends(require_webhook_secret)],
)
def ingest_webhook_lead(
    payload: WebhookLeadPayload,
    db: Session = Depends(get_db),
) -> LeadResponse:
    logger.info(
        "webhook_received email=%s source=%s external_id=%s",
        mask_email(str(payload.email)),
        payload.source,
        payload.external_id,
    )
    try:
        normalized = normalize_lead_payload(payload)
    except NormalizationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    lead, created = lead_service.create_lead(db, normalized)
    logger.info(
        "webhook_lead_id=%s created=%s email=%s",
        lead.id,
        created,
        mask_email(lead.email),
    )
    return LeadResponse.model_validate(lead)
