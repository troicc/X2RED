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
from app.services.material_search_providers import MaterialSearchError
from app.services.resilient_material_search import ResilientMaterialSearchEngine

router = APIRouter(prefix="/api/materials", tags=["materials"])

MaterialCategory = Literal[
    "mature_life",
    "comfort",
    "seasonal",
    "photo_quote",
    "short_commentary",
]
MaterialProvider = Literal[
    "auto",
    "serpapi_baidu",
    "dataforseo_baidu",
    "firecrawl",
    "brave",
    "jina",
    "tavily",
    "gdelt",
]
MaterialExtractor = Literal[
    "auto",
    "firecrawl",
    "jina",
    "direct",
    "playwright",
]


class MaterialDiscoverRequest(BaseModel):
    category: MaterialCategory
    query: str = Field(default="", max_length=300)
    provider: MaterialProvider = "auto"
    max_records: int = Field(default=30, ge=1, le=100)
    timespan: str = Field(default="7d", max_length=20)


class MaterialFeedRequest(BaseModel):
    url: str = Field(max_length=2000)
    category: MaterialCategory
    max_records: int = Field(default=50, ge=1, le=100)


class MaterialImportRequest(BaseModel):
    url: str = Field(max_length=2000)
    category: MaterialCategory
    extractor: MaterialExtractor = "auto"
    editor_note: str = Field(default="", max_length=6000)


def _service() -> MarketMaterialHarvester:
    return MarketMaterialHarvester(get_settings())


def _engine() -> ResilientMaterialSearchEngine:
    return ResilientMaterialSearchEngine(get_settings())


@router.get("/providers")
def material_providers() -> dict[str, Any]:
    settings = get_settings()
    search_providers = _engine().statuses()
    extractors = _service().extractor_statuses()
    return {
        "default_search": settings.material_search_provider,
        "default_extractor": settings.material_extract_provider,
        "search_providers": search_providers,
        "extractors": extractors,
        "providers": search_providers,
    }


@router.post("/discover")
def discover_materials(body: MaterialDiscoverRequest) -> dict[str, Any]:
    service = _service()
    search_query = service.discovery_query(category=body.category, query=body.query)
    try:
        result = _engine().search(
            provider=body.provider,
            query=search_query,
            max_results=body.max_records,
            timespan=body.timespan,
        )
    except MaterialSearchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"搜索供应商请求失败：{str(exc)[:500]}",
        ) from exc

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in result.get("items") or []:
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("url") or "").strip()
        if not url:
            continue
        try:
            url = service.validate_public_url(url, resolve_dns=False)
        except MaterialHarvesterError:
            continue
        key = url.split("#", 1)[0].rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        title = str(raw.get("title") or "")
        summary = str(raw.get("summary") or "")
        item = dict(raw)
        item["url"] = url
        item["category"] = body.category
        item["fit_score"] = service.fit_score(
            category=body.category,
            text=f"{title} {summary}",
        )
        items.append(item)
        if len(items) >= body.max_records:
            break
    return {
        "category": body.category,
        "query": search_query,
        "provider": result.get("provider"),
        "attempts": result.get("attempts") or [],
        "count": len(items),
        "items": items,
    }


@router.post("/discover-feed", deprecated=True)
def discover_feed(body: MaterialFeedRequest) -> dict[str, Any]:
    """Compatibility endpoint; feeds are no longer part of the primary material UI."""
    try:
        items = _service().discover_feed(
            url=body.url,
            category=body.category,
            max_records=body.max_records,
        )
    except MaterialHarvesterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Feed 查询失败：{str(exc)[:500]}",
        ) from exc
    return {
        "category": body.category,
        "count": len(items),
        "items": items,
        "deprecated": True,
    }


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
        source = _service().import_url(
            db,
            url=body.url,
            category=body.category,
            extractor=body.extractor,
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
        raise HTTPException(
            status_code=502,
            detail=f"公开网页收录失败：{str(exc)[:500]}",
        ) from exc
