from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum as SAEnum, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [item.value for item in enum_cls]


class Base(DeclarativeBase):
    pass


class LeadStatus(str, enum.Enum):
    NEW = "new"
    QUALIFIED = "qualified"
    CONTACTED = "contacted"
    MEETING = "meeting"
    PROPOSAL = "proposal"
    WON = "won"
    LOST = "lost"


class Priority(str, enum.Enum):
    COLD = "cold"
    WARM = "warm"
    HOT = "hot"


class IntentLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ProductFit(str, enum.Enum):
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FollowUpStatus(str, enum.Enum):
    NOT_STARTED = "not_started"
    DRAFT_READY = "draft_ready"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    SENT = "sent"
    SKIPPED = "skipped"


ALLOWED_STATUS_TRANSITIONS: dict[LeadStatus, set[LeadStatus]] = {
    LeadStatus.NEW: set(),
    LeadStatus.QUALIFIED: {LeadStatus.CONTACTED, LeadStatus.LOST},
    LeadStatus.CONTACTED: {LeadStatus.MEETING, LeadStatus.PROPOSAL, LeadStatus.LOST},
    LeadStatus.MEETING: {LeadStatus.PROPOSAL, LeadStatus.LOST},
    LeadStatus.PROPOSAL: {LeadStatus.WON, LeadStatus.LOST},
    LeadStatus.WON: set(),
    LeadStatus.LOST: set(),
}


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (UniqueConstraint("external_id", name="uq_leads_external_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    company_size: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="unknown")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    intent: Mapped[IntentLevel | None] = mapped_column(
        SAEnum(IntentLevel, values_callable=enum_values, native_enum=False, length=32),
        nullable=True,
    )
    product_fit: Mapped[ProductFit | None] = mapped_column(
        SAEnum(ProductFit, values_callable=enum_values, native_enum=False, length=32),
        nullable=True,
    )
    priority: Mapped[Priority | None] = mapped_column(
        SAEnum(Priority, values_callable=enum_values, native_enum=False, length=32),
        nullable=True,
    )
    status: Mapped[LeadStatus] = mapped_column(
        SAEnum(LeadStatus, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
        default=LeadStatus.NEW,
    )
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    pain_points: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    recommended_next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qualification_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    follow_up_status: Mapped[FollowUpStatus] = mapped_column(
        SAEnum(FollowUpStatus, values_callable=enum_values, native_enum=False, length=32),
        nullable=False,
        default=FollowUpStatus.NOT_STARTED,
    )
    draft_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class PipelineRun(Base):
    """One client-demo pass through the same CRM APIs n8n calls."""

    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    sample: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    lead_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    telegram_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    stages: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
