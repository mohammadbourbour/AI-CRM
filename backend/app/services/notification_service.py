from __future__ import annotations

import html
import logging

from app.models import Lead, Priority
from app.providers import telegram as telegram_provider

logger = logging.getLogger(__name__)

_PRIORITY_LABEL = {
    Priority.HOT: "🔥 HOT",
    Priority.WARM: "🟠 WARM",
    Priority.COLD: "🔵 COLD",
}

_PRIORITY_HEADLINE = {
    Priority.HOT: "Action needed today",
    Priority.WARM: "Keep in the pipeline",
    Priority.COLD: "Low priority",
}


def _esc(value: object) -> str:
    if value is None:
        return "—"
    if hasattr(value, "value"):
        return html.escape(str(value.value))
    return html.escape(str(value))


def format_hot_lead_message(lead: Lead) -> str:
    """Plain-text hot-lead alert kept for the existing notify helper."""
    pain = ", ".join(lead.pain_points or [])
    return (
        "HOT lead\n"
        f"Name: {lead.name}\n"
        f"Company: {lead.company}\n"
        f"Industry: {lead.industry or 'n/a'}\n"
        f"Priority: {lead.priority.value if lead.priority else 'n/a'}\n"
        f"Intent: {lead.intent.value if lead.intent else 'n/a'}\n"
        f"Product fit: {lead.product_fit.value if lead.product_fit else 'n/a'}\n"
        f"Summary: {lead.ai_summary or ''}\n"
        f"Next action: {lead.recommended_next_action or 'n/a'}\n"
        f"Pain points: {pain or 'n/a'}"
    )


def format_qualification_result_html(lead: Lead) -> str:
    """Sales-channel post: analysis for the team, never a customer message."""
    priority = lead.priority if isinstance(lead.priority, Priority) else None
    badge = _PRIORITY_LABEL.get(priority, _esc(lead.priority))
    headline = _PRIORITY_HEADLINE.get(priority, "Lead qualification")
    pain = ", ".join(lead.pain_points or []) or "—"
    follow = getattr(lead.follow_up_status, "value", lead.follow_up_status)
    if priority == Priority.HOT or follow == "awaiting_approval":
        hitl = (
            "\n\n<i>A follow-up draft is waiting for human approval. "
            "This is a sales-team alert, not a customer message.</i>"
        )
    else:
        hitl = "\n\n<i>This is a sales-team alert, not a customer message.</i>"
    return (
        f"{badge}  <b>{headline}</b>\n\n"
        f"<b>{_esc(lead.name)}</b> · {_esc(lead.company)}\n"
        f"CRM <code>#{lead.id}</code> · {_esc(lead.status)}\n"
        f"{_esc(lead.email)}\n"
        f"Industry: {_esc(lead.industry)}\n"
        f"Intent: {_esc(lead.intent)} · Fit: {_esc(lead.product_fit)}\n\n"
        f"<b>Summary</b>\n{_esc(lead.ai_summary)}\n\n"
        f"<b>Next action</b>\n{_esc(lead.recommended_next_action)}\n\n"
        f"<b>Pain points</b>\n{_esc(pain)}"
        f"{hitl}"
    )


def notify_hot_lead(lead: Lead) -> bool:
    """Best-effort notify. Never raises; Telegram outages must not fail qualification."""
    text = format_hot_lead_message(lead)
    logger.info("notification_attempt lead_id=%s channel=telegram", lead.id)
    sent = telegram_provider.send_message(text, parse_mode=None)
    if sent:
        logger.info("notification_success lead_id=%s channel=telegram", lead.id)
    else:
        logger.info("notification_skipped_or_failed lead_id=%s channel=telegram", lead.id)
    return sent


def notify_qualification_result(lead: Lead) -> str:
    """Post the analysis result to the configured Telegram chat/channel.

    Returns sent | skipped_unconfigured | failed. Never raises.
    """
    from app.config import get_settings

    if not get_settings().telegram_enabled:
        logger.info("qualification_telegram skipped_unconfigured lead_id=%s", lead.id)
        return "skipped_unconfigured"
    if lead.priority == Priority.COLD:
        logger.info("qualification_telegram skipped_cold lead_id=%s", lead.id)
        return "skipped_cold"
    text = format_qualification_result_html(lead)
    logger.info("qualification_telegram_attempt lead_id=%s", lead.id)
    sent = telegram_provider.send_message(text)
    if sent:
        logger.info("qualification_telegram_sent lead_id=%s", lead.id)
        return "sent"
    logger.info("qualification_telegram_failed lead_id=%s", lead.id)
    return "failed"


def format_followup_decision_html(lead: Lead, decision: str) -> str:
    """Sales-channel copy of the HITL decision (approved draft or rejection)."""
    draft = lead.draft_message or "—"
    if len(draft) > 2500:
        draft = draft[:2500] + "…"
    if decision == "approved":
        title = "Follow-up approved"
        note = "Posted to the sales channel. This is not a customer-channel send."
    else:
        title = "Follow-up rejected"
        note = "The customer was not contacted. The draft remains in CRM for audit."
    return (
        f"<b>{title}</b>\n\n"
        f"<b>{_esc(lead.name)}</b> · {_esc(lead.company)}\n"
        f"CRM <code>#{lead.id}</code> · {_esc(lead.status)}\n"
        f"Follow-up: {_esc(lead.follow_up_status)}\n\n"
        f"<b>Draft</b>\n{_esc(draft)}\n\n"
        f"<i>{note}</i>"
    )


def notify_followup_decision(lead: Lead, decision: str) -> str:
    """Post HITL accept/reject to Telegram. Never raises."""
    from app.config import get_settings

    if not get_settings().telegram_enabled:
        logger.info("followup_telegram skipped_unconfigured lead_id=%s decision=%s", lead.id, decision)
        return "skipped_unconfigured"
    text = format_followup_decision_html(lead, decision)
    logger.info("followup_telegram_attempt lead_id=%s decision=%s", lead.id, decision)
    sent = telegram_provider.send_message(text)
    if sent:
        logger.info("followup_telegram_sent lead_id=%s decision=%s", lead.id, decision)
        return "sent"
    logger.info("followup_telegram_failed lead_id=%s decision=%s", lead.id, decision)
    return "failed"
