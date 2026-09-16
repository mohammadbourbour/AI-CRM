from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.db import configure_engine, init_db
from app.routes.health import router as health_router
from app.routes.leads import router as leads_router
from app.routes.leads import webhook_router
from app.routes.exports import router as exports_router

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _configure_logging()
    settings = get_settings()
    configure_engine(settings.database_url)
    init_db()
    logger.info(
        "startup openai=%s telegram=%s google_sheets=%s",
        "enabled" if settings.openai_enabled else "mock",
        "enabled" if settings.telegram_enabled else "disabled",
        "enabled" if settings.google_sheets_enabled else "disabled",
    )
    if not settings.openai_enabled:
        logger.warning("OPENAI_API_KEY absent; qualification uses MockLLMProvider (not production).")
    if not settings.telegram_enabled:
        logger.info("Telegram credentials absent; hot-lead notify is disabled.")
    if not settings.google_sheets_enabled:
        logger.info("Google Sheets credentials absent; lead export is disabled.")
    yield


app = FastAPI(
    title="AI Sales & CRM Automation",
    description=(
        "Portfolio implementation demonstrating an AI-assisted sales and CRM automation workflow."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(health_router, tags=["health"])
app.include_router(leads_router, prefix="/api/leads", tags=["leads"])
app.include_router(exports_router, prefix="/api/exports", tags=["exports"])
app.include_router(webhook_router, prefix="/api/webhooks", tags=["webhooks"])


@app.exception_handler(SQLAlchemyError)
async def handle_db_error(_request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.exception("database_error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Database error"})
