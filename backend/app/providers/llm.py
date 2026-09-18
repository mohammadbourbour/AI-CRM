from __future__ import annotations

import json
import logging
from typing import Protocol

from pydantic import ValidationError

from app.config import Settings, get_settings
from app.exceptions import QualificationFailedError
from app.models import IntentLevel, Lead, Priority, ProductFit
from app.schemas import AIQualificationResult

logger = logging.getLogger(__name__)

QUALIFICATION_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "industry": {"type": "string"},
        "intent": {"type": "string", "enum": ["low", "medium", "high"]},
        "product_fit": {"type": "string", "enum": ["unknown", "low", "medium", "high"]},
        "priority": {"type": "string", "enum": ["cold", "warm", "hot"]},
        "pain_points": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
        "recommended_next_action": {"type": "string"},
    },
    "required": [
        "industry",
        "intent",
        "product_fit",
        "priority",
        "pain_points",
        "summary",
        "recommended_next_action",
    ],
    "additionalProperties": False,
}

_JSON_SCHEMA_PREFIXES = (
    "gpt-4o",
    "gpt-4.1",
    "gpt-5",
    "o1",
    "o3",
    "o4-mini",
)

SYSTEM_PROMPT = (
    "You are a B2B sales qualification assistant. "
    "Return JSON that matches the lead qualification schema. "
    "Do not invent contact details. Do not propose URLs or tool calls. "
    "priority is a hint only; the backend recomputes it."
)


def model_supports_json_schema(model: str) -> bool:
    name = model.lower().strip()
    return any(name.startswith(prefix) for prefix in _JSON_SCHEMA_PREFIXES)


def parse_qualification(raw: str) -> AIQualificationResult:
    data = json.loads(raw)
    return AIQualificationResult.model_validate(data)


class LLMProvider(Protocol):
    def qualify_lead(self, lead: Lead) -> AIQualificationResult: ...

    def generate_followup_draft(self, lead: Lead) -> str: ...


class MockLLMProvider:
    """Keyword heuristic stand-in. Not production inference."""

    def qualify_lead(self, lead: Lead) -> AIQualificationResult:
        logger.info(
            "MockLLMProvider.qualify_lead used for lead_id=%s; not production inference",
            lead.id,
        )
        text = f"{lead.message} {lead.company}".lower()
        if any(
            token in text
            for token in (
                "predictive maintenance",
                "manufacturing",
                "multi-site",
                "facilities",
                "industrial",
            )
        ):
            return AIQualificationResult(
                industry="manufacturing",
                intent=IntentLevel.HIGH,
                product_fit=ProductFit.HIGH,
                priority=Priority.HOT,
                pain_points=["predictive maintenance", "multi-site monitoring"],
                summary=(
                    "The prospect is actively evaluating an industrial analytics solution."
                ),
                recommended_next_action="Schedule a discovery call",
            )
        if any(
            token in text
            for token in ("saas", "onboarding", "seat", "scaling", "subscription")
        ):
            return AIQualificationResult(
                industry="saas",
                intent=IntentLevel.MEDIUM,
                product_fit=ProductFit.MEDIUM,
                priority=Priority.WARM,
                pain_points=["onboarding friction", "scaling customer success"],
                summary="The prospect is exploring automation to support SaaS growth.",
                recommended_next_action="Send a short product walkthrough",
            )
        return AIQualificationResult(
            industry="unknown",
            intent=IntentLevel.LOW,
            product_fit=ProductFit.LOW,
            priority=Priority.COLD,
            pain_points=["unspecified need"],
            summary="Generic inquiry with little buying signal.",
            recommended_next_action="Send a light-touch resource and wait",
        )

    def generate_followup_draft(self, lead: Lead) -> str:
        logger.info(
            "MockLLMProvider.generate_followup_draft used for lead_id=%s; not production inference",
            lead.id,
        )
        next_action = lead.recommended_next_action or "a brief intro call"
        summary = (lead.ai_summary or lead.message).rstrip(".")
        return (
            f"Hi {lead.name},\n\n"
            f"Thanks for reaching out from {lead.company}. {summary}. "
            f"Suggested next step: {next_action}.\n\n"
            "Would you like to schedule 20 minutes this week?\n\n"
            "Best regards"
        )


class GroqProvider:
    """Groq Chat Completions via the OpenAI-compatible SDK."""

    def __init__(self, settings: Settings) -> None:
        from openai import OpenAI

        self._model = settings.groq_model.strip() or "llama-3.1-8b-instant"
        self._client = OpenAI(
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url.strip() or "https://api.groq.com/openai/v1",
            timeout=30.0,
        )

    def _complete(self, messages: list[dict], *, json_object: bool) -> str:
        from openai import APIError, APITimeoutError

        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": 0 if json_object else 0.3,
        }
        if json_object:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = self._client.chat.completions.create(**kwargs)
        except APITimeoutError as exc:
            raise QualificationFailedError("LLM request timed out") from exc
        except APIError as exc:
            raise QualificationFailedError(f"LLM provider error: {exc}") from exc
        content = response.choices[0].message.content
        if not content:
            raise QualificationFailedError("LLM returned an empty response")
        return content

    def qualify_lead(self, lead: Lead) -> AIQualificationResult:
        user_prompt = (
            f"Qualify this sales lead.\n"
            f"Name: {lead.name}\n"
            f"Company: {lead.company}\n"
            f"Company size: {lead.company_size or 'unknown'}\n"
            f"Source: {lead.source}\n"
            f"Message: {lead.message}\n"
        )
        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        raw = self._complete(messages, json_object=True)
        try:
            return parse_qualification(raw)
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning(
                "LLM qualification JSON failed validation for lead_id=%s; retrying once",
                lead.id,
            )
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your previous JSON failed validation with this error: "
                        f"{exc}. Return corrected JSON only that matches the schema."
                    ),
                }
            )
            retry_raw = self._complete(messages, json_object=True)
            try:
                return parse_qualification(retry_raw)
            except (json.JSONDecodeError, ValidationError) as retry_exc:
                raise QualificationFailedError(
                    f"LLM returned invalid qualification JSON: {retry_exc}"
                ) from retry_exc

    def generate_followup_draft(self, lead: Lead) -> str:
        prompt = (
            "Write a short, professional follow-up email body for this B2B lead. "
            "Do not include URLs. Do not claim a meeting is booked.\n"
            f"Name: {lead.name}\n"
            f"Company: {lead.company}\n"
            f"Summary: {lead.ai_summary or lead.message}\n"
            f"Recommended next action: {lead.recommended_next_action or 'discovery call'}\n"
        )
        content = self._complete(
            [
                {
                    "role": "system",
                    "content": "You write concise sales follow-up drafts. Plain text only.",
                },
                {"role": "user", "content": prompt},
            ],
            json_object=False,
        )
        if not content.strip():
            raise QualificationFailedError("LLM returned an empty follow-up draft")
        return content.strip()


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    if settings.groq_enabled:
        logger.info("Using GroqProvider model=%s", settings.groq_model)
        return GroqProvider(settings)
    logger.warning(
        "GROQ_API_KEY absent; using MockLLMProvider. Not production inference."
    )
    return MockLLMProvider()
