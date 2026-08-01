from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_platform_service
from app.core.config import get_settings
from app.db.session import get_db
from app.domain.models import DraftRevision, SourceItem
from app.domain.platform_schemas import (
    LightContentApproval,
    LightContentCandidateSelect,
    LightContentIterateRequest,
    LightContentVariantCreate,
    LightCorpusCreate,
    PlatformCatalogOut,
    PlatformRenderRequest,
    PlatformVariantOut,
    PlatformVariantUpdate,
    WeChatRenderResult,
    WeChatVariantCreate,
)
from app.domain.platforms import PlatformVariant
from app.services.light_content import LightContentError
from app.services.light_content_lab import LightContentLabService
from app.services.light_visual_renderer import VISUAL_STYLE_LABELS
from app.services.platform_studio import PlatformStudioError, PlatformStudioService
from app.services.skill_packs import pack_payloads
from app.services.skills import ensure_bindings
from app.services.wechat_themes import list_theme_payloads

router = APIRouter(prefix="/api/platforms", tags=["platform-studio"])


def _light_lab(service: PlatformStudioService) -> LightContentLabService:
    return LightContentLabService(service.settings, service.editorial)


def _variant(db: Session, variant_id: str) -> PlatformVariant:
    value = db.get(PlatformVariant, variant_id)
    if value is None:
        raise HTTPException(status_code=404, detail="平台版本不存在")
    return value


@router.get("/catalog", response_model=PlatformCatalogOut)
def catalog(db: Session = Depends(get_db)) -> PlatformCatalogOut:
    settings = get_settings()
    ensure_bindings(db, settings.model_name)
    output = PlatformCatalogOut(
        skill_packs=pack_payloads(db, settings),
        wechat_themes=list_theme_payloads(),
        platform_capabilities={
            "xiaohongshu": {
                "formats": ["cards", "caption"],
                "ratios": ["3:4"],
                "skill_pack_ids": [
                    "xhs-editorial-growth",
                    "xhs-style-layout-matrix",
                    "material-first-social-design",
                ],
            },
            "wechat": {
                "formats": [
                    "article",
                    "light_series",
                    "cover_pair",
                    "publish_package",
                ],
                "ratios": ["21:9", "1:1"],
                "format_ratios": {
                    "article": ["21:9", "1:1"],
                    "light_series": ["3:5"],
                },
                "light_visual_styles": [
                    {"id": key, "label": value}
                    for key, value in VISUAL_STYLE_LABELS.items()
                ],
                "light_quality_modes": ["fast", "studio"],
                "skill_pack_ids": [
                    "wechat-editorial-adapter",
                    "wechat-inline-design-system",
                    "article-illustration-planner",
                    "wechat-light-zine",
                    "wechat-draft-publisher",
                ],
            },
        },
    )
    db.commit()
    return output


@router.get("/variants", response_model=list[PlatformVariantOut])
def list_variants(
    platform: str = Query(default="", max_length=30),
    source_id: str = Query(default="", max_length=64),
    limit: int = Query(default=100, ge=1, le=300),
    db: Session = Depends(get_db),
) -> list[PlatformVariant]:
    query = select(PlatformVariant)
    if platform:
        query = query.where(PlatformVariant.platform == platform)
    if source_id:
        query = query.where(PlatformVariant.source_id == source_id)
    return list(db.scalars(query.order_by(desc(PlatformVariant.updated_at)).limit(limit)).all())


@router.post(
    "/wechat/variants",
    response_model=PlatformVariantOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_wechat_variant(
    body: WeChatVariantCreate,
    db: Session = Depends(get_db),
    service: PlatformStudioService = Depends(get_platform_service),
) -> PlatformVariant:
    source = db.get(SourceItem, body.source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="来源不存在")
    draft: DraftRevision | None = None
    if body.draft_id:
        draft = db.get(DraftRevision, body.draft_id)
        if draft is None or draft.source_id != source.id:
            raise HTTPException(status_code=404, detail="所选草稿不存在或不属于当前来源")
    else:
        draft = db.scalar(
            select(DraftRevision)
            .where(DraftRevision.source_id == source.id)
            .order_by(DraftRevision.version.desc())
        )
    try:
        variant = await service.create_wechat_variant(
            db,
            source=source,
            draft=draft,
            theme=body.theme,
            mode=body.mode,
            include_citations=body.include_citations,
            include_illustration_plan=body.include_illustration_plan,
            author=body.author,
        )
    except PlatformStudioError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(variant)
    return variant


@router.post(
    "/wechat/light/variants",
    response_model=PlatformVariantOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_wechat_light_variant(
    body: LightContentVariantCreate,
    db: Session = Depends(get_db),
    service: PlatformStudioService = Depends(get_platform_service),
) -> PlatformVariant:
    source = db.get(SourceItem, body.source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="来源不存在")
    draft: DraftRevision | None = None
    if body.draft_id:
        draft = db.get(DraftRevision, body.draft_id)
        if draft is None or draft.source_id != source.id:
            raise HTTPException(status_code=404, detail="所选草稿不存在或不属于当前来源")
    else:
        draft = db.scalar(
            select(DraftRevision)
            .where(DraftRevision.source_id == source.id)
            .order_by(DraftRevision.version.desc())
        )
    try:
        variant = await _light_lab(service).create_variant(
            db,
            source=source,
            draft=draft,
            recipe=body.recipe,
            image_count=body.image_count,
            seasonal_topic=body.seasonal_topic,
            audience=body.audience,
            tone=body.tone,
            theme=body.theme,
            author=body.author,
            visual_style=body.visual_style,
            quality_mode=body.quality_mode,
            feedback=body.feedback,
        )
    except LightContentError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(variant)
    return variant


@router.post(
    "/wechat/light/variants/{variant_id}/iterate",
    response_model=PlatformVariantOut,
    status_code=status.HTTP_201_CREATED,
)
async def iterate_wechat_light_variant(
    variant_id: str,
    body: LightContentIterateRequest,
    db: Session = Depends(get_db),
    service: PlatformStudioService = Depends(get_platform_service),
) -> PlatformVariant:
    current = _variant(db, variant_id)
    try:
        revised = await _light_lab(service).iterate_variant(
            db,
            current,
            feedback=body.feedback,
            quality_mode=body.quality_mode,
        )
    except LightContentError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(revised)
    return revised


@router.post(
    "/wechat/light/variants/{variant_id}/select-candidate",
    response_model=PlatformVariantOut,
    status_code=status.HTTP_201_CREATED,
)
def select_wechat_light_candidate(
    variant_id: str,
    body: LightContentCandidateSelect,
    db: Session = Depends(get_db),
    service: PlatformStudioService = Depends(get_platform_service),
) -> PlatformVariant:
    current = _variant(db, variant_id)
    try:
        revised = _light_lab(service).select_candidate(
            db,
            current,
            candidate_index=body.candidate_index,
        )
    except LightContentError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(revised)
    return revised


@router.post("/wechat/light/variants/{variant_id}/approve")
def approve_wechat_light_variant(
    variant_id: str,
    body: LightContentApproval,
    db: Session = Depends(get_db),
    service: PlatformStudioService = Depends(get_platform_service),
) -> dict:
    current = _variant(db, variant_id)
    try:
        corpus_item = _light_lab(service).approve_to_corpus(db, current, note=body.note)
    except LightContentError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(current)
    return {
        "variant_id": current.id,
        "corpus_item_id": corpus_item.id,
        "approved": True,
    }


@router.get("/wechat/light/corpus")
def list_wechat_light_corpus(
    recipe: str = Query(default="", max_length=40),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    service: PlatformStudioService = Depends(get_platform_service),
) -> list[dict]:
    return _light_lab(service).list_corpus(db, recipe=recipe, limit=limit)


@router.post("/wechat/light/corpus", status_code=status.HTTP_201_CREATED)
def create_wechat_light_corpus(
    body: LightCorpusCreate,
    db: Session = Depends(get_db),
    service: PlatformStudioService = Depends(get_platform_service),
) -> dict:
    try:
        artifact = _light_lab(service).add_corpus_item(
            db,
            recipe=body.recipe,
            title=body.title,
            body_markdown=body.body_markdown,
            visual_style=body.visual_style,
            note=body.note,
        )
    except LightContentError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return {
        "id": artifact.id,
        "recipe": artifact.scope_id,
        "version": artifact.version,
        "approved": True,
    }


@router.get("/variants/{variant_id}", response_model=PlatformVariantOut)
def get_variant(variant_id: str, db: Session = Depends(get_db)) -> PlatformVariant:
    return _variant(db, variant_id)


@router.put("/variants/{variant_id}", response_model=PlatformVariantOut)
def update_variant(
    variant_id: str,
    body: PlatformVariantUpdate,
    db: Session = Depends(get_db),
    service: PlatformStudioService = Depends(get_platform_service),
) -> PlatformVariant:
    variant = _variant(db, variant_id)
    revised = service.revise_variant(
        db,
        variant,
        title=body.title,
        subtitle=body.subtitle,
        summary=body.summary,
        body_markdown=body.body_markdown,
        tags=body.tags,
        theme=body.theme,
    )
    db.commit()
    db.refresh(revised)
    return revised


@router.post("/variants/{variant_id}/render", response_model=WeChatRenderResult)
def render_variant(
    variant_id: str,
    body: PlatformRenderRequest,
    db: Session = Depends(get_db),
    service: PlatformStudioService = Depends(get_platform_service),
) -> dict:
    variant = _variant(db, variant_id)
    try:
        if variant.format == "light_series":
            variant, validation, files = _light_lab(service).render_variant(
                db,
                variant,
                package=body.package,
            )
        else:
            variant, validation, files = service.render_wechat_variant(
                db,
                variant,
                package=body.package,
            )
        db.commit()
        db.refresh(variant)
    except (PlatformStudioError, LightContentError) as exc:
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "variant": variant,
        "validation": {
            "errors": validation.errors,
            "warnings": validation.warnings,
        },
        "files": files,
        "preview_url": f"/api/platforms/variants/{variant.id}/preview",
        "download_urls": {
            key: f"/api/platforms/variants/{variant.id}/files/{key}"
            for key in files
        },
    }


@router.get("/variants/{variant_id}/preview")
def preview_variant(variant_id: str, db: Session = Depends(get_db)) -> FileResponse:
    path = _variant_file(db, variant_id, "preview")
    return FileResponse(path, media_type="text/html; charset=utf-8")


@router.get("/variants/{variant_id}/files/{file_key}")
def download_variant_file(
    variant_id: str,
    file_key: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    path = _variant_file(db, variant_id, file_key)
    media_type = {
        ".html": "text/html; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
        ".json": "application/json",
        ".png": "image/png",
        ".zip": "application/zip",
    }.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type, filename=path.name)


def _variant_file(db: Session, variant_id: str, file_key: str) -> Path:
    variant = _variant(db, variant_id)
    try:
        files = json.loads(variant.output_paths_json or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="平台版本文件记录损坏") from exc
    value = files.get(file_key) if isinstance(files, dict) else None
    if not value:
        raise HTTPException(status_code=404, detail="文件尚未生成")
    path = Path(str(value)).resolve()
    export_root = get_settings().export_dir.resolve()
    if export_root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在或路径无效")
    return path
