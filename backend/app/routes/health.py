from fastapi import APIRouter

from app.config import get_settings
from app.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        groq="enabled" if settings.groq_enabled else "mock",
        telegram="enabled" if settings.telegram_enabled else "disabled",
        google_sheets="enabled" if settings.google_sheets_enabled else "disabled",
    )
