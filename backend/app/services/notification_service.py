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
    """Client-facing channel post: analysis result, not a customer message."""
    priority = lead.priority if isinstance(lead.priority, Priority) else None
    badge = _PRIORITY_LABEL.get(priority, _esc(lead.priority))
    pain = ", ".join(lead.pain_points or []) or "—"
    return (
        "<b>نتیجه تحلیل لید</b>\n"
        "<b>Lead qualification result</b>\n\n"
        f"اولویت / Priority: <b>{badge}</b>\n"
        f"CRM: <code>#{lead.id}</code>\n"
        f"نام / Name: {_esc(lead.name)}\n"
        f"شرکت / Company: {_esc(lead.company)}\n"
        f"ایمیل / Email: {_esc(lead.email)}\n"
        f"صنعت / Industry: {_esc(lead.industry)}\n"
        f"Intent: {_esc(lead.intent)} · Fit: {_esc(lead.product_fit)}\n"
        f"وضعیت / Status: {_esc(lead.status)}\n\n"
        f"<b>خلاصه AI</b>\n{_esc(lead.ai_summary)}\n\n"
        f"<b>اقدام بعدی</b>\n{_esc(lead.recommended_next_action)}\n\n"
        f"Pain points: {_esc(pain)}\n\n"
        "<i>پیام مشتری ارسال نشد — فقط نتیجه تحلیل برای تیم فروش.</i>"
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
    text = format_qualification_result_html(lead)
    logger.info("qualification_telegram_attempt lead_id=%s", lead.id)
    sent = telegram_provider.send_message(text)
    if sent:
        logger.info("qualification_telegram_sent lead_id=%s", lead.id)
        return "sent"
    logger.info("qualification_telegram_failed lead_id=%s", lead.id)
    return "failed"
