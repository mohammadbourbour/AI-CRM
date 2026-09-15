from __future__ import annotations

import logging

from app.models import Lead
from app.providers import telegram as telegram_provider

logger = logging.getLogger(__name__)


def format_hot_lead_message(lead: Lead) -> str:
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


def notify_hot_lead(lead: Lead) -> bool:
    """Best-effort notify. Never raises; Telegram outages must not fail qualification."""
    text = format_hot_lead_message(lead)
    logger.info("notification_attempt lead_id=%s channel=telegram", lead.id)
    sent = telegram_provider.send_message(text)
    if sent:
        logger.info("notification_success lead_id=%s channel=telegram", lead.id)
    else:
        logger.info("notification_skipped_or_failed lead_id=%s channel=telegram", lead.id)
    return sent
