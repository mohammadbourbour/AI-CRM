from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.exceptions import N8nUnavailableError

logger = logging.getLogger(__name__)


def _unwrap(data: Any) -> dict[str, Any]:
    if isinstance(data, list) and data:
        data = data[0]
    if isinstance(data, dict) and "json" in data and isinstance(data["json"], dict):
        data = data["json"]
    if not isinstance(data, dict):
        raise N8nUnavailableError("n8n webhook did not return a JSON object")
    return data


def post_lead_intake(payload: dict[str, Any]) -> dict[str, Any]:
    """POST the sample lead to n8n `/webhook/lead-intake`. Raises if n8n is down or unpublished."""
    settings = get_settings()
    url = settings.n8n_webhook_url.strip()
    if not url:
        raise N8nUnavailableError(
            "N8N_WEBHOOK_URL is empty. In .env set it to http://localhost:5678/webhook/lead-intake "
            "(Compose overrides this to http://n8n:5678/webhook/lead-intake)."
        )
    logger.info("n8n_intake_post url=%s", url)
    try:
        response = httpx.post(url, json=payload, timeout=90.0)
    except httpx.ConnectError as exc:
        raise N8nUnavailableError(
            "n8n is not running. From the repo root: docker compose up --build. "
            "Then open http://localhost:5678"
        ) from exc
    except httpx.TimeoutException as exc:
        raise N8nUnavailableError("n8n webhook timed out after 90s") from exc
    except httpx.HTTPError as exc:
        raise N8nUnavailableError(f"n8n request failed: {exc}") from exc

    if response.status_code == 404:
        raise N8nUnavailableError(
            "n8n webhook is not registered. Open Lead Qualification in n8n and click Publish "
            "(n8n 2.x). The workflow must be active."
        )
    if response.status_code >= 400:
        raise N8nUnavailableError(
            f"n8n returned HTTP {response.status_code}: {response.text[:400]}"
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise N8nUnavailableError("n8n did not return JSON — is the workflow using Respond to Webhook?") from exc
    return _unwrap(data)
