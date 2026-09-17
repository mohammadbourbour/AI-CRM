from __future__ import annotations

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_message(text: str, *, parse_mode: str | None = "HTML") -> bool:
    """Send a Telegram message to TELEGRAM_CHAT_ID (user, group, or channel).

    Returns False when disabled or when the API call fails. Never raises.
    The bot must be an administrator of the target channel.
    """
    settings = get_settings()
    if not settings.telegram_enabled:
        logger.info("Telegram disabled (missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)")
        return False
    url = TELEGRAM_API.format(token=settings.telegram_bot_token)
    payload: dict[str, object] = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        response = httpx.post(url, json=payload, timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Telegram send failed: %s", exc)
        return False
    logger.info("Telegram notification sent chat_id_configured=true")
    return True
