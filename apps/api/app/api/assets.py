from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.paths import UnsafePathError, resolved_file_within
from app.db.session import get_db
from app.domain.models import Asset

router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.get("/{asset_id}/file")
def asset_file(asset_id: str, db: Session = Depends(get_db)) -> FileResponse:
    asset = db.get(Asset, asset_id)
    if asset is None or not asset.local_path:
        raise HTTPException(status_code=404, detail="本地素材不存在")
    try:
        path = resolved_file_within(asset.local_path, [get_settings().media_dir])
    except UnsafePathError:
        raise HTTPException(status_code=404, detail="素材文件已丢失") from None
    return FileResponse(path, media_type=asset.mime_type or None, filename=path.name)
