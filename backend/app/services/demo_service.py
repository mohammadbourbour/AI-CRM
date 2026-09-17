from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.exceptions import QualificationFailedError
from app.models import Lead, PipelineRun, Priority
from app.providers.n8n import post_lead_intake
from app.schemas import LeadCreate, LeadResponse, PipelineStage
from app.services import followup_service, lead_service, qualification_service
from app.services.normalization_service import NormalizationError, normalize_lead_payload
from app.services.notification_service import format_qualification_result_html, notify_qualification_result

STAGE_DEFS: list[dict[str, str]] = [
    {
        "id": "intake",
        "label_fa": "ورود لید",
        "label_en": "Intake",
        "n8n_node": "Lead Intake Webhook",
    },
    {
        "id": "validate",
        "label_fa": "اعتبارسنجی",
        "label_en": "Validate",
        "n8n_node": "Validate Incoming Lead",
    },
    {
        "id": "enrich",
        "label_fa": "غنی‌سازی محلی",
        "label_en": "Enrich",
        "n8n_node": "Optional Lead Enrichment",
    },
    {
        "id": "crm",
        "label_fa": "ثبت در CRM",
        "label_en": "Persist",
        "n8n_node": "Create Lead in CRM",
    },
    {
        "id": "qualify",
        "label_fa": "تحلیل AI + امتیاز قطعی",
        "label_en": "Qualify",
        "n8n_node": "AI Agent → Backend Qualify Lead",
    },
    {
        "id": "sheets",
        "label_fa": "خروجی Sheets",
        "label_en": "Sheets",
        "n8n_node": "Create sheet / Append or update row",
    },
    {
        "id": "route",
        "label_fa": "مسیریابی",
        "label_en": "Route",
        "n8n_node": "Priority Is Hot?",
    },
    {
        "id": "draft",
        "label_fa": "پیش‌نویس HITL",
        "label_en": "Draft",
        "n8n_node": "Draft Follow-up (HITL)",
    },
    {
        "id": "telegram",
        "label_fa": "کانال تلگرام",
        "label_en": "Telegram",
        "n8n_node": "Bot → channel (qualification result)",
    },
]

SAMPLES: dict[str, dict[str, str]] = {
    "hot": {
        "name": "John Smith",
        "email": "john@northwind.example",
        "company": "Northwind Energy",
        "company_size": "500-1000",
        "source": "website",
        "message": (
            "We are evaluating an AI solution for predictive maintenance "
            "across multiple facilities."
        ),
        "job_title": "Director of Operations",
    },
    "warm": {
        "name": "Priya Shah",
        "email": "priya@orbitsaas.example",
        "company": "Orbit SaaS",
        "source": "linkedin",
        "message": (
            "We are a SaaS company scaling onboarding and looking at automation "
            "for customer success seats."
        ),
        "job_title": "Head of Customer Success",
    },
    "cold": {
        "name": "Alex Chen",
        "email": "alex@generic.example",
        "company": "Generic LLC",
        "source": "website",
        "message": "Just browsing. Can you send general pricing information?",
        "job_title": "Intern",
    },
    "invalid": {
        "name": " ",
        "email": "not-an-email",
        "company": "",
        "source": "website",
        "message": "",
        "job_title": "",
    },
}


def blank_stages() -> list[dict[str, Any]]:
    return [
        {
            "id": item["id"],
            "label_fa": item["label_fa"],
            "label_en": item["label_en"],
            "n8n_node": item["n8n_node"],
            "status": "pending",
            "detail": None,
        }
        for item in STAGE_DEFS
    ]


def _set_stage(stages: list[dict[str, Any]], stage_id: str, status: str, detail: str | None) -> None:
    for item in stages:
        if item["id"] == stage_id:
            item["status"] = status
            item["detail"] = detail
            return


def enrich_contact(email: str, job_title: str | None) -> dict[str, Any]:
    domain = email.split("@", 1)[1] if "@" in email else ""
    title = (job_title or "").strip()
    lowered = title.lower()
    seniority = "unknown"
    if any(
        token in lowered
        for token in ("chief", "cto", "ceo", "cfo", "coo", "vp", "vice president", "director", "head", "founder")
    ):
        seniority = "executive"
    elif any(token in lowered for token in ("manager", "lead", "principal", "supervisor")):
        seniority = "manager"
    elif any(token in lowered for token in ("intern", "student", "junior")):
        seniority = "junior"
    elif title:
        seniority = "ic"
    return {
        "email_domain": domain or None,
        "guessed_website": f"https://www.{domain}" if domain else None,
        "job_title": title or None,
        "seniority": seniority,
        "enrichment_source": "deterministic_local",
        "enrichment_api": "disabled",
    }


def sample_payload_dict(sample: str) -> dict[str, Any]:
    """JSON body posted to n8n. Invalid sample is intentionally malformed."""
    if sample not in SAMPLES:
        raise ValueError(f"Unknown sample {sample!r}. Use hot, warm, cold, or invalid.")
    stamp = uuid.uuid4().hex[:8]
    if sample == "invalid":
        return {
            "name": " ",
            "email": "not-an-email",
            "company": "",
            "message": "",
            "source": "website",
            "external_id": f"demo-invalid-{stamp}",
        }
    raw = SAMPLES[sample]
    body: dict[str, Any] = {
        "name": raw["name"],
        "email": raw["email"],
        "company": raw["company"],
        "source": raw.get("source", "unknown"),
        "message": raw["message"],
        "external_id": f"demo-{sample}-{stamp}",
    }
    if raw.get("company_size"):
        body["company_size"] = raw["company_size"]
    if raw.get("job_title"):
        body["job_title"] = raw["job_title"]
    return body


def sheet_row_from_lead(lead: Lead) -> dict[str, Any]:
    def _val(value: Any) -> Any:
        return value.value if hasattr(value, "value") else value

    return {
        "id": lead.id,
        "external_id": lead.external_id,
        "name": lead.name,
        "email": lead.email,
        "company": lead.company,
        "source": lead.source,
        "priority": _val(lead.priority),
        "status": _val(lead.status),
        "industry": lead.industry,
        "intent": _val(lead.intent),
        "product_fit": _val(lead.product_fit),
        "recommended_next_action": lead.recommended_next_action,
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
    }


def _apply_telegram_stage(stages: list[dict[str, Any]], telegram_status: str) -> None:
    if telegram_status == "sent":
        _set_stage(stages, "telegram", "done", "Analysis result posted to the Telegram channel.")
    elif telegram_status == "failed":
        _set_stage(stages, "telegram", "failed", "Telegram call failed. Qualification is still in CRM.")
    elif telegram_status == "not_applicable":
        _set_stage(stages, "telegram", "skipped", "No CRM lead — nothing to post.")
    else:
        _set_stage(
            stages,
            "telegram",
            "skipped",
            "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID empty — skipped, not faked as sent.",
        )


def stages_from_n8n_result(outcome: dict[str, Any]) -> list[dict[str, Any]]:
    stages = blank_stages()
    kind = str(outcome.get("outcome") or "")
    errors = outcome.get("errors") or []
    err = ", ".join(str(item) for item in errors) if errors else None
    channels = outcome.get("channels") or {}
    _set_stage(stages, "intake", "done", "n8n Lead Intake Webhook received the payload from the dashboard.")
    if kind == "validation_failed":
        _set_stage(stages, "validate", "failed", err or "invalid payload")
        for stage_id in ("enrich", "crm", "qualify", "sheets", "route", "draft", "telegram"):
            _set_stage(stages, stage_id, "skipped", "Stopped in n8n before CRM write.")
        return stages
    if kind in {"failed", "qualification_failed"}:
        _set_stage(stages, "validate", "done", "Payload passed n8n validation.")
        _set_stage(stages, "enrich", "done", "Local enrichment in n8n.")
        crm_status = "done" if outcome.get("lead_id") else "failed"
        _set_stage(stages, "crm", crm_status, err or kind)
        _set_stage(stages, "qualify", "failed" if kind == "qualification_failed" else "skipped", err or kind)
        for stage_id in ("sheets", "route", "draft", "telegram"):
            _set_stage(stages, stage_id, "skipped", "n8n stopped on review path.")
        return stages

    _set_stage(stages, "validate", "done", "n8n Validate Incoming Lead passed.")
    _set_stage(stages, "enrich", "done", "n8n Optional Lead Enrichment (local only).")
    _set_stage(stages, "crm", "done", f"CRM id={outcome.get('lead_id')}.")
    _set_stage(stages, "qualify", "done", "n8n called backend /qualify (deterministic priority).")
    sheets = str(channels.get("google_sheets") or "skipped_unconfigured")
    if sheets == "exported":
        _set_stage(stages, "sheets", "done", "n8n Google Sheets upserted this lead.")
    elif sheets == "failed":
        _set_stage(stages, "sheets", "failed", "n8n Sheets node failed. Check the Google credential.")
    else:
        _set_stage(
            stages,
            "sheets",
            "skipped",
            "GOOGLE_SHEETS_SPREADSHEET_ID empty or Sheets credential missing — not marked exported.",
        )
    routed = outcome.get("routed") or outcome.get("priority") or "unknown"
    _set_stage(stages, "route", "done", f"n8n routed {routed}.")
    if str(routed) == "hot":
        _set_stage(
            stages,
            "draft",
            "done",
            f"Follow-up {outcome.get('follow_up_status') or 'awaiting_approval'} — customer send still blocked.",
        )
    else:
        _set_stage(stages, "draft", "skipped", "Warm/cold leads are not auto-drafted.")
    return stages


def _payload_from_sample(sample: str) -> LeadCreate:
    raw = SAMPLES[sample]
    stamp = uuid.uuid4().hex[:8]
    if sample == "invalid":
        return LeadCreate.model_construct(
            name=" ",
            email="broken@",
            company="",
            message="",
            source="website",
            external_id=f"demo-invalid-{stamp}",
        )
    return LeadCreate(
        name=raw["name"],
        email=raw["email"],
        company=raw["company"],
        company_size=raw.get("company_size"),
        source=raw.get("source", "unknown"),
        message=raw["message"],
        external_id=f"demo-{sample}-{stamp}",
        job_title=raw.get("job_title"),
    )


def run_demo(db: Session, sample: str = "hot", lead_in: LeadCreate | None = None) -> tuple[PipelineRun, dict[str, Any] | None]:
    """Execute the CRM path n8n uses, recording each visual stage."""
    settings = get_settings()
    chosen = "custom" if lead_in is not None else sample
    if lead_in is None:
        if sample not in SAMPLES:
            raise ValueError(f"Unknown sample {sample!r}. Use hot, warm, cold, or invalid.")
        lead_in = _payload_from_sample(sample)

    run = PipelineRun(
        id=str(uuid.uuid4()),
        sample=chosen,
        status="running",
        via="crm",
        stages=blank_stages(),
        telegram_status="pending",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    stages = list(run.stages)
    enrichment: dict[str, Any] | None = None

    _set_stage(stages, "intake", "done", "Webhook intake received (same contract as n8n lead-intake).")
    run.stages = stages
    db.commit()

    try:
        normalized = normalize_lead_payload(lead_in)
    except NormalizationError as exc:
        _set_stage(stages, "validate", "failed", str(exc))
        for stage_id in ("enrich", "crm", "qualify", "sheets", "route", "draft", "telegram"):
            _set_stage(stages, stage_id, "skipped", "Stopped: payload rejected before CRM write.")
        run.stages = stages
        run.status = "failed"
        run.telegram_status = "not_applicable"
        db.commit()
        db.refresh(run)
        return run, None

    _set_stage(stages, "validate", "done", "Name, email, company, and message passed validation.")
    enrichment = enrich_contact(str(normalized.email), lead_in.job_title)
    seniority = enrichment["seniority"]
    _set_stage(
        stages,
        "enrich",
        "done",
        f"Local only: domain={enrichment.get('email_domain') or 'n/a'}, seniority={seniority}.",
    )

    lead, created = lead_service.create_lead(db, normalized)
    run.lead_id = lead.id
    _set_stage(
        stages,
        "crm",
        "done",
        f"CRM id={lead.id} ({'inserted' if created else 'existing external_id'}).",
    )

    try:
        qualified = qualification_service.qualify_lead(db, lead, notify=False)
    except QualificationFailedError as exc:
        _set_stage(stages, "qualify", "failed", exc.message)
        run.stages = stages
        run.status = "failed"
        run.telegram_status = "not_applicable"
        db.commit()
        db.refresh(run)
        return run, enrichment

    provider = "groq" if settings.groq_enabled else "mock"
    _set_stage(
        stages,
        "qualify",
        "done",
        (
            f"LLM={provider}; persisted priority={qualified.priority.value if qualified.priority else 'n/a'} "
            "(deterministic rules, not the model hint)."
        ),
    )

    if settings.google_sheets_enabled:
        _set_stage(
            stages,
            "sheets",
            "ready",
            "Credentials present. Per-lead upsert runs on the official n8n Sheets nodes.",
        )
    else:
        _set_stage(
            stages,
            "sheets",
            "skipped",
            "GOOGLE_SHEETS_SPREADSHEET_ID / service account empty — not marked exported.",
        )

    priority = qualified.priority.value if qualified.priority else "unknown"
    _set_stage(stages, "route", "done", f"Routed {priority}.")

    if qualified.priority == Priority.HOT:
        drafted = followup_service.generate_draft(db, qualified)
        _set_stage(
            stages,
            "draft",
            "done",
            f"Follow-up {drafted.follow_up_status.value} — customer send still blocked.",
        )
        qualified = drafted
    else:
        _set_stage(stages, "draft", "skipped", "Warm/cold leads are not auto-drafted.")

    telegram_status = notify_qualification_result(qualified)
    run.telegram_status = telegram_status
    if telegram_status == "sent":
        _set_stage(stages, "telegram", "done", "Result posted to the Telegram channel by the bot.")
    elif telegram_status == "failed":
        _set_stage(stages, "telegram", "failed", "Bot call failed. Qualification still saved in CRM.")
    else:
        _set_stage(
            stages,
            "telegram",
            "skipped",
            "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID empty — skipped, not faked as sent.",
        )

    sheets_stage = next((item for item in stages if item["id"] == "sheets"), None)
    run.sheets_status = (sheets_stage or {}).get("status")
    run.n8n_outcome = None
    run.stages = stages
    run.status = "completed"
    db.commit()
    db.refresh(run)
    db.refresh(qualified)
    return run, enrichment


def run_demo_via_n8n(
    db: Session, sample: str = "hot", lead_in: LeadCreate | None = None
) -> tuple[PipelineRun, dict[str, Any] | None]:
    """Send the sample to n8n; n8n calls CRM. Dashboard only records what n8n returns."""
    settings = get_settings()
    chosen = "custom" if lead_in is not None else sample
    if lead_in is None:
        payload = sample_payload_dict(sample)
        enrichment = enrich_contact(str(payload.get("email") or ""), payload.get("job_title"))
    else:
        payload = lead_in.model_dump(exclude_none=True)
        enrichment = enrich_contact(str(payload.get("email") or ""), payload.get("job_title"))

    run = PipelineRun(
        id=str(uuid.uuid4()),
        sample=chosen,
        status="running",
        via="n8n",
        stages=blank_stages(),
        telegram_status="pending",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    outcome = post_lead_intake(payload)
    kind = str(outcome.get("outcome") or "unknown")
    stages = stages_from_n8n_result(outcome)
    lead_id = outcome.get("lead_id")
    run.lead_id = int(lead_id) if lead_id is not None else None
    run.n8n_outcome = kind
    channels = outcome.get("channels") or {}
    run.sheets_status = str(channels.get("google_sheets") or "skipped_unconfigured")

    if kind == "validation_failed":
        run.status = "failed"
        run.telegram_status = "not_applicable"
        _apply_telegram_stage(stages, run.telegram_status)
        run.stages = stages
        db.commit()
        db.refresh(run)
        return run, None
    if kind in {"failed", "qualification_failed"}:
        run.status = "failed"
        run.telegram_status = "not_applicable"
        _apply_telegram_stage(stages, run.telegram_status)
        run.stages = stages
        db.commit()
        db.refresh(run)
        return run, enrichment

    run.status = "completed"
    if settings.telegram_enabled:
        # Backend /qualify already posted; do not send a second copy.
        run.telegram_status = "sent"
    else:
        run.telegram_status = "skipped_unconfigured"
    n8n_alert = str(channels.get("telegram_sales_alert") or "")
    if n8n_alert == "sent":
        run.telegram_status = "sent"
    _apply_telegram_stage(stages, run.telegram_status)
    run.stages = stages
    db.commit()
    db.refresh(run)
    return run, enrichment


def latest_run(db: Session) -> PipelineRun | None:
    stmt = select(PipelineRun).order_by(PipelineRun.created_at.desc()).limit(1)
    return db.scalars(stmt).first()


def serialize_run(db: Session, run: PipelineRun, enrichment: dict[str, Any] | None = None) -> dict[str, Any]:
    lead = lead_service.get_lead(db, run.lead_id) if run.lead_id else None
    settings = get_settings()
    telegram_preview = format_qualification_result_html(lead) if lead else None
    sheets_row = sheet_row_from_lead(lead) if lead else None
    return {
        "id": run.id,
        "sample": run.sample,
        "status": run.status,
        "via": getattr(run, "via", None) or "crm",
        "lead_id": run.lead_id,
        "telegram_status": run.telegram_status,
        "n8n_outcome": getattr(run, "n8n_outcome", None),
        "sheets_status": getattr(run, "sheets_status", None),
        "telegram_preview": telegram_preview,
        "sheets_row": sheets_row,
        "n8n_executions_url": settings.n8n_executions_url,
        "stages": [PipelineStage.model_validate(item).model_dump() for item in run.stages],
        "lead": LeadResponse.model_validate(lead).model_dump(mode="json") if lead else None,
        "enrichment": enrichment,
        "created_at": run.created_at,
    }
