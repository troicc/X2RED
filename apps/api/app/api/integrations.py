from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.schemas import X2PDFImportRequest, X2PDFImportResponse
from app.services.x2pdf_import import X2PDFImportService

router = APIRouter(prefix="/api/integrations/x2pdf", tags=["integrations"])


@router.post("/documents", response_model=X2PDFImportResponse)
def import_x2pdf_document(
    body: X2PDFImportRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> X2PDFImportResponse:
    service: X2PDFImportService = request.app.state.x2pdf_import_service
    try:
        source, asset_count, updated = service.import_document(db, body.document)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(source)
    blocks = body.document.get("blocks")
    return X2PDFImportResponse(
        source_id=source.id,
        external_id=source.external_id,
        content_kind=source.content_kind,
        block_count=len(blocks) if isinstance(blocks, list) else 0,
        asset_count=asset_count,
        updated=updated,
    )
