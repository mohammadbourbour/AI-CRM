from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.schemas import DemoMetaResponse, DemoRunRequest, DemoRunResponse, PipelineStage
from app.services import demo_service

router = APIRouter()


@router.get("/meta", response_model=DemoMetaResponse)
def demo_meta() -> DemoMetaResponse:
    settings = get_settings()
    return DemoMetaResponse(
        stages=[
            PipelineStage(
                id=item["id"],
                label_fa=item["label_fa"],
                label_en=item["label_en"],
                n8n_node=item["n8n_node"],
                status="pending",
            )
            for item in demo_service.STAGE_DEFS
        ],
        samples=list(demo_service.SAMPLES),
        n8n_webhook_configured=bool(settings.n8n_webhook_url.strip()),
        telegram="enabled" if settings.telegram_enabled else "disabled",
        openai="enabled" if settings.openai_enabled else "mock",
        google_sheets="enabled" if settings.google_sheets_enabled else "disabled",
    )


@router.post("/runs", response_model=DemoRunResponse)
def create_demo_run(payload: DemoRunRequest, db: Session = Depends(get_db)) -> DemoRunResponse:
    sample = (payload.sample or "hot").strip().lower()
    try:
        run, enrichment = demo_service.run_demo(db, sample=sample, lead_in=payload.lead)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    body = demo_service.serialize_run(db, run, enrichment)
    return DemoRunResponse.model_validate(body)


@router.get("/runs/latest", response_model=DemoRunResponse | None)
def get_latest_demo_run(db: Session = Depends(get_db)) -> DemoRunResponse | None:
    run = demo_service.latest_run(db)
    if run is None:
        return None
    return DemoRunResponse.model_validate(demo_service.serialize_run(db, run))
