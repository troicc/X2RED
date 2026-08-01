from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.domain.models import SourceItem
from app.domain.schemas import SourceListItem
from app.services.material_harvester import MaterialHarvesterError
from app.services.safe_material_harvester import SafeMaterialHarvester

router = APIRouter(prefix="/api/materials", tags=["materials"])

MaterialCategory = Literal[
    "mature_life",
    "comfort",
    "seasonal",
    "photo_quote",
    "short_commentary",
]


class MaterialDiscoverRequest(BaseModel):
    category: MaterialCategory
    query: str = Field(default="", max_length=300)
    max_records: int = Field(default=30, ge=1, le=100)
    timespan: str = Field(default="7d", max_length=20)


class MaterialFeedRequest(BaseModel):
    url: str = Field(max_length=2000)
    category: MaterialCategory
    max_records: int = Field(default=50, ge=1, le=100)


class MaterialImportRequest(BaseModel):
    url: str = Field(max_length=2000)
    category: MaterialCategory
    editor_note: str = Field(default="", max_length=6000)


def _service() -> SafeMaterialHarvester:
    return SafeMaterialHarvester(get_settings())


@router.post("/discover")
def discover_materials(body: MaterialDiscoverRequest) -> dict:
    try:
        items = _service().discover_gdelt(
            category=body.category,
            query=body.query,
            max_records=body.max_records,
            timespan=body.timespan,
        )
    except (MaterialHarvesterError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"公开索引查询失败：{str(exc)[:500]}") from exc
    return {"category": body.category, "count": len(items), "items": items}


@router.post("/discover-feed")
def discover_feed(body: MaterialFeedRequest) -> dict:
    try:
        items = _service().discover_feed(
            url=body.url,
            category=body.category,
            max_records=body.max_records,
        )
    except MaterialHarvesterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Feed 查询失败：{str(exc)[:500]}") from exc
    return {"category": body.category, "count": len(items), "items": items}


@router.post("/import", response_model=SourceListItem, status_code=status.HTTP_201_CREATED)
def import_material(
    body: MaterialImportRequest,
    db: Session = Depends(get_db),
) -> SourceItem:
    try:
        source = _service().import_url(
            db,
            url=body.url,
            category=body.category,
            editor_note=body.editor_note,
        )
        db.commit()
        db.refresh(source)
        return source
    except MaterialHarvesterError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=f"公开网页收录失败：{str(exc)[:500]}") from exc
