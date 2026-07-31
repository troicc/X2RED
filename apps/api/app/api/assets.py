from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.models import Asset

router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.get("/{asset_id}/file")
def asset_file(asset_id: str, db: Session = Depends(get_db)) -> FileResponse:
    asset = db.get(Asset, asset_id)
    if asset is None or not asset.local_path:
        raise HTTPException(status_code=404, detail="本地素材不存在")
    path = Path(asset.local_path).resolve()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="素材文件已丢失")
    return FileResponse(path, media_type=asset.mime_type or None, filename=path.name)
