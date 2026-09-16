from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import FollowUpStatus, IntentLevel, LeadStatus, Priority, ProductFit


class LeadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    company: str = Field(min_length=1, max_length=255)
    company_size: str | None = Field(default=None, max_length=64)
    source: str = Field(default="unknown", max_length=64)
    message: str = Field(min_length=1)
    external_id: str | None = Field(default=None, max_length=128)
    assigned_to: str | None = Field(default=None, max_length=255)
    job_title: str | None = Field(default=None, max_length=128)


class WebhookLeadPayload(LeadCreate):
    pass


class LeadUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    company: str | None = Field(default=None, min_length=1, max_length=255)
    company_size: str | None = Field(default=None, max_length=64)
    source: str | None = Field(default=None, max_length=64)
    message: str | None = Field(default=None, min_length=1)
    assigned_to: str | None = Field(default=None, max_length=255)
    status: LeadStatus | None = None
    follow_up_status: FollowUpStatus | None = None


class AIQualificationResult(BaseModel):
    """Strict schema for LLM qualification output. Backend still recomputes priority."""

    industry: str = Field(min_length=1, max_length=128)
    intent: IntentLevel
    product_fit: ProductFit
    priority: Priority
    pain_points: list[str] = Field(min_length=1)
    summary: str = Field(min_length=1)
    recommended_next_action: str = Field(min_length=1)


class LeadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str | None
    name: str
    email: EmailStr
    company: str
    company_size: str | None
    source: str
    message: str
    industry: str | None
    intent: IntentLevel | None
    product_fit: ProductFit | None
    priority: Priority | None
    status: LeadStatus
    ai_summary: str | None
    pain_points: list[str] | None
    recommended_next_action: str | None
    assigned_to: str | None
    qualification_error: str | None
    follow_up_due_at: datetime | None
    follow_up_status: FollowUpStatus
    draft_message: str | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class FollowUpDraftResponse(BaseModel):
    lead_id: int
    follow_up_status: FollowUpStatus
    draft_message: str
    follow_up_due_at: datetime | None


class FollowUpApproveResponse(BaseModel):
    lead_id: int
    follow_up_status: FollowUpStatus
    approved_at: datetime
    send_result: str
    status: LeadStatus


class FollowUpRejectResponse(BaseModel):
    lead_id: int
    follow_up_status: FollowUpStatus
    status: LeadStatus
    decision: str = "rejected"


class HealthResponse(BaseModel):
    status: str
    openai: str
    telegram: str
    google_sheets: str


class SheetsExportResponse(BaseModel):
    outcome: str
    exported: int
    spreadsheet_id: str | None = None
    worksheet: str
    reason: str | None = None


class PipelineStage(BaseModel):
    id: str
    label_fa: str
    label_en: str
    n8n_node: str
    status: str
    detail: str | None = None


class DemoRunRequest(BaseModel):
    sample: str | None = Field(default="hot", max_length=32)
    lead: LeadCreate | None = None
    via: str | None = Field(default="crm", max_length=16)


class DemoRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sample: str
    status: str
    via: str = "crm"
    lead_id: int | None
    telegram_status: str
    n8n_outcome: str | None = None
    sheets_status: str | None = None
    telegram_preview: str | None = None
    sheets_row: dict[str, Any] | None = None
    n8n_executions_url: str | None = None
    stages: list[PipelineStage]
    lead: LeadResponse | None = None
    enrichment: dict[str, Any] | None = None
    created_at: datetime


class DemoMetaResponse(BaseModel):
    stages: list[PipelineStage]
    samples: list[str]
    n8n_webhook_configured: bool
    n8n_public_url: str
    n8n_executions_url: str
    n8n_sheets_configured: bool
    telegram: str
    openai: str
    google_sheets: str
