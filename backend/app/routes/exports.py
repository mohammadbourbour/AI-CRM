from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.exceptions import SheetsExportError
from app.schemas import SheetsExportResponse
from app.services import export_service

router = APIRouter()


@router.post("/google-sheets", response_model=SheetsExportResponse)
def export_qualified_leads_to_sheets(db: Session = Depends(get_db)) -> SheetsExportResponse:
    """Replace the configured worksheet with the current qualified-lead snapshot."""
    try:
        return export_service.export_qualified_leads(db)
    except SheetsExportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.message,
        ) from exc
