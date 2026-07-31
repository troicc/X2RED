from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_intake_service
from app.db.session import get_db
from app.domain.schemas import IntakeRequest, IntakeResponse
from app.services.intake import IntakeService
from app.services.url_parser import extract_x_post_id

router = APIRouter(prefix="/api/intake", tags=["intake"])


@router.post("/x", response_model=IntakeResponse)
async def intake_x(
    body: IntakeRequest,
    db: Session = Depends(get_db),
    service: IntakeService = Depends(get_intake_service),
) -> IntakeResponse:
    try:
        post_id = extract_x_post_id(body.url)
        source_id, imported_count, asset_count, snapshot = await service.import_post(
            db,
            post_id=post_id,
            mode=body.mode,
            download_media=service.settings.download_media
            if body.download_media is None
            else body.download_media,
        )
        return IntakeResponse(
            source_id=source_id,
            external_id=post_id,
            imported_count=imported_count,
            asset_count=asset_count,
            snapshot_id=snapshot.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"X 数据导入失败：{exc}") from exc
