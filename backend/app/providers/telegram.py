from __future__ import annotations

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_message(text: str) -> bool:
    """Send a Telegram message. Returns False when disabled or when the API call fails."""
    settings = get_settings()
    if not settings.telegram_enabled:
        logger.info("Telegram disabled (missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)")
        return False
    url = TELEGRAM_API.format(token=settings.telegram_bot_token)
    try:
        response = httpx.post(
            url,
            json={"chat_id": settings.telegram_chat_id, "text": text},
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Telegram send failed: %s", exc)
        return False
    logger.info("Telegram notification sent")
    return True
