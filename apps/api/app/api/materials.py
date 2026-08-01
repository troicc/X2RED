from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.domain.models import SourceItem
from app.domain.schemas import SourceListItem
from app.services.market_material_harvester import MarketMaterialHarvester
from app.services.material_harvester import MaterialHarvesterError
from app.services.mediacrawler_bridge import MediaCrawlerBridge, MediaCrawlerError

router = APIRouter(prefix="/api/materials", tags=["materials"])

MaterialCategory = Literal[
    "mature_life",
    "comfort",
    "seasonal",
    "photo_quote",
    "short_commentary",
]
MediaPlatform = Literal["xhs", "dy", "ks", "bili", "wb", "tieba", "zhihu"]
LoginType = Literal["qrcode", "phone", "cookie"]


class MaterialDiscoverRequest(BaseModel):
    category: MaterialCategory
    query: str = Field(default="", max_length=300)
    platform: MediaPlatform = "xhs"
    login_type: LoginType = "qrcode"
    max_records: int = Field(default=30, ge=1, le=100)


class MaterialImportRequest(BaseModel):
    url: str = Field(default="", max_length=2000)
    category: MaterialCategory
    editor_note: str = Field(default="", max_length=6000)
    candidate: dict[str, Any] | None = None


def _service() -> MarketMaterialHarvester:
    return MarketMaterialHarvester(get_settings())


def _crawler() -> MediaCrawlerBridge:
    return MediaCrawlerBridge(get_settings())


@router.get("/providers")
def material_providers() -> dict[str, Any]:
    settings = get_settings()
    crawler = _crawler()
    return {
        "default_search": "mediacrawler",
        "default_platform": settings.mediacrawler_platform,
        "default_login_type": settings.mediacrawler_login_type,
        "cdp_port": settings.mediacrawler_cdp_port,
        "installed": crawler.installed(),
        "cdp_ready": crawler.cdp_reachable(),
        "platforms": crawler.statuses(),
        "search_providers": crawler.statuses(),
        "extractors": [
            {
                "id": "local",
                "label": "本地 HTTP / Playwright",
                "configured": True,
                "description": "仅用于手工粘贴普通公开网页",
            }
        ],
    }


@router.post("/discover")
def discover_materials(body: MaterialDiscoverRequest) -> dict[str, Any]:
    service = _service()
    search_query = service.discovery_query(category=body.category, query=body.query)
    try:
        result = _crawler().search(
            platform=body.platform,
            query=search_query,
            max_results=body.max_records,
            login_type=body.login_type,
        )
    except MediaCrawlerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"MediaCrawler 运行失败：{str(exc)[:1000]}",
        ) from exc

    items: list[dict[str, Any]] = []
    for raw in result.get("items") or []:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        item["category"] = body.category
        item["fit_score"] = service.fit_score(
            category=body.category,
            text=f"{item.get('title', '')} {item.get('summary', '')}",
        )
        items.append(item)
    result["items"] = items
    result["count"] = len(items)
    result["category"] = body.category
    return result


@router.post(
    "/import",
    response_model=SourceListItem,
    status_code=status.HTTP_201_CREATED,
)
def import_material(
    body: MaterialImportRequest,
    db: Session = Depends(get_db),
) -> SourceItem:
    try:
        if body.candidate is not None:
            source = _crawler().import_candidate(
                db,
                candidate=body.candidate,
                category=body.category,
                editor_note=body.editor_note,
            )
        else:
            url = body.url.strip()
            if not url:
                raise MaterialHarvesterError("URL 不能为空")
            source = _service().import_url(
                db,
                url=url,
                category=body.category,
                editor_note=body.editor_note,
            )
        db.commit()
        db.refresh(source)
        return source
    except (MediaCrawlerError, MaterialHarvesterError) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail=f"原料收录失败：{str(exc)[:1000]}",
        ) from exc
