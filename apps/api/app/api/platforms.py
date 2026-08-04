from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_platform_service, get_pool_memory_service
from app.core.config import get_settings
from app.db.session import get_db
from app.domain.models import DraftRevision, SourceItem
from app.domain.platform_schemas import (
    LightContentApproval,
    LightContentCandidateSelect,
    LightContentIterateRequest,
    LightContentVariantCreate,
    LightCorpusCreate,
    MinimalZineStoryboardRevisionRequest,
    PlatformCatalogOut,
    PlatformRenderRequest,
    PlatformVariantOut,
    PlatformVariantUpdate,
    WeChatRenderResult,
    WeChatVariantCreate,
)
from app.domain.platforms import PlatformVariant
from app.domain.pool_memory_schemas import PoolMemoryTargetCandidateRequest
from app.services.light_content import LightContentError
from app.services.light_content_fit import assess_source_fit
from app.services.light_content_lab import LightContentLabService
from app.services.light_visual_renderer import VISUAL_STYLE_LABELS
from app.services.minimal_zine_native import storyboard_model_input_changed
from app.services.platform_studio import PlatformStudioError, PlatformStudioService
from app.services.pool_memory import PoolMemoryError, PoolMemoryService
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


def _json_object(value: str) -> dict:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _light_copy_segments(title: str, summary: str, body: str, count: int) -> list[tuple[str, str]]:
    cleaned_title = re.sub(r"\s+", " ", title).strip()[:36]
    sentences = [
        re.sub(r"\s+", " ", item).strip()
        for item in re.split(r"(?<=[。！？!?])|\n+", body)
        if re.sub(r"\s+", " ", item).strip()
    ]
    summary_text = re.sub(r"\s+", " ", summary).strip()
    phrases = [cleaned_title] if cleaned_title else []
    for sentence in sentences:
        candidate = sentence.rstrip("。！？!?")[:36]
        if candidate and candidate not in phrases:
            phrases.append(candidate)
        if len(phrases) >= count:
            break
    if summary_text and len(phrases) < count:
        phrases.append(summary_text.rstrip("。！？!?")[:36])
    while len(phrases) < count:
        phrases.append(phrases[-1] if phrases else "把这一页说清楚")

    segments: list[tuple[str, str]] = []
    for index, phrase in enumerate(phrases[:count]):
        note_source = sentences[index] if index < len(sentences) else summary_text
        note = note_source.rstrip("。！？!?")[:48]
        if note == phrase:
            note = ""
        segments.append((phrase, note))
    return segments


def _sync_light_storyboard(
    current: PlatformVariant,
    revised: PlatformVariant,
) -> None:
    metadata = _json_object(revised.metadata_json)
    specs_raw = metadata.get("poster_specs")
    specs = [dict(item) for item in specs_raw if isinstance(item, dict)] if isinstance(specs_raw, list) else []
    count = min(max(len(specs), 3), 6)
    segments = _light_copy_segments(revised.title, revised.summary, revised.body_markdown, count)
    if not specs:
        specs = [
            {
                "visual_metaphor": "真实生活中的单一物件或场景",
                "photo_direction": "画面必须与文字中的具体场景一致",
                "layout": "editorial",
                "accent": "#1646d8",
                "mood": "quiet",
                "visual_style": metadata.get("visual_style") or "minimal_zine",
            }
            for _ in range(count)
        ]
    for index in range(count):
        spec = specs[index] if index < len(specs) else dict(specs[-1])
        phrase, note = segments[index]
        spec["phrase"] = phrase
        spec["note"] = note
        # Editing title/body persists a new immutable textual revision.  It does not
        # make an unchanged visual metaphor/raw anchor stale; only its local final
        # composition needs rebuilding in the child directory.
        spec.pop("final_composition_fingerprint", None)
        spec.pop("compositor_version", None)
        spec.pop("composition_diagnostics", None)
        if index < len(specs):
            specs[index] = spec
        else:
            specs.append(spec)
    metadata.update(
        {
            "parent_variant_id": current.id,
            "poster_specs": specs[:count],
            "human_edited": True,
            "human_approved": False,
            "render_engine": "",
            "validation": {},
        }
    )
    revised.metadata_json = json.dumps(metadata, ensure_ascii=False)
    revised.output_paths_json = "{}"
    revised.body_html = ""


def _storyboard_page_changed(previous: dict, current: dict) -> bool:
    fields = ("phrase", "note", "focus_x", "focus_y", "zoom")
    return any(previous.get(field) != current.get(field) for field in fields)


def _carry_storyboard_trace(
    previous: dict,
    current: dict,
) -> None:
    for key in (
        "final_prompt",
        "native_zine_recipe",
        "native_zine_interpretation",
        "model_input_fingerprint",
        "raw_anchor_fingerprint",
        "raw_anchor_source_variant_id",
        "text_rendering",
        "model_text_forbidden",
    ):
        if key in previous:
            current[key] = previous[key]


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
    source_text = draft.body if draft and draft.body.strip() else source.text_original
    fit = assess_source_fit(
        source_text=source_text,
        recipe=body.recipe,
        seasonal_topic=body.seasonal_topic,
        audience=body.audience,
        feedback=body.feedback,
    )
    if not fit.allowed:
        raise HTTPException(status_code=409, detail=fit.reason)
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
        metadata = _json_object(variant.metadata_json)
        metadata["source_fit"] = {
            "allowed": fit.allowed,
            "score": fit.score,
            "source_kind": fit.source_kind,
            "reason": fit.reason,
            "suggested_recipes": list(fit.suggested_recipes),
        }
        variant.metadata_json = json.dumps(metadata, ensure_ascii=False)
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


@router.post(
    "/wechat/light/variants/{variant_id}/storyboard",
    response_model=PlatformVariantOut,
    status_code=status.HTTP_201_CREATED,
)
def revise_wechat_light_storyboard(
    variant_id: str,
    body: MinimalZineStoryboardRevisionRequest,
    db: Session = Depends(get_db),
    service: PlatformStudioService = Depends(get_platform_service),
) -> PlatformVariant:
    """Freeze a page-level storyboard as a new PlatformVariant revision.

    The source variant remains untouched.  Parent artifact linkage is retained only
    for render-time, read-only inheritance; the new child starts with no output refs.
    """

    current = _variant(db, variant_id)
    if current.platform != "wechat" or current.format != "light_series":
        raise HTTPException(status_code=400, detail="当前版本不是公众号轻内容图组")
    current_metadata = _json_object(current.metadata_json)
    current_specs_raw = current_metadata.get("poster_specs")
    current_specs = (
        [dict(item) for item in current_specs_raw if isinstance(item, dict)]
        if isinstance(current_specs_raw, list)
        else []
    )
    page_count = len(current_specs)
    if not 3 <= page_count <= 6:
        raise HTTPException(status_code=400, detail="当前轻内容故事板必须包含 3 到 6 页")
    submitted_numbers = [page.page for page in body.pages]
    expected_numbers = list(range(1, page_count + 1))
    if sorted(submitted_numbers) != expected_numbers:
        raise HTTPException(
            status_code=400,
            detail=f"故事板页码必须唯一并完整覆盖 1 到 {page_count} 页",
        )

    revised = service.revise_variant(
        db,
        current,
        title=current.title,
        subtitle=current.subtitle,
        summary=current.summary,
        body_markdown=current.body_markdown,
        tags=current.tags,
        theme=current.theme,
    )
    metadata = _json_object(revised.metadata_json)
    replacement_specs: list[dict] = []
    model_changed_pages: list[int] = []
    local_changed_pages: list[int] = []
    for submitted in sorted(body.pages, key=lambda page: page.page):
        page = submitted.page
        previous = current_specs[page - 1]
        replacement = submitted.model_dump()
        replacement["visual_style"] = str(
            previous.get("visual_style")
            or current_metadata.get("visual_style")
            or "minimal_zine"
        )
        model_changed = storyboard_model_input_changed(previous, replacement)
        local_changed = _storyboard_page_changed(previous, replacement)
        if model_changed:
            model_changed_pages.append(page)
        else:
            # A phrase/note/crop-only revision keeps the exact prompt and recipe so
            # the renderer can copy the parent raw anchor into the child staging set.
            _carry_storyboard_trace(previous, replacement)
        if local_changed or model_changed:
            local_changed_pages.append(page)
            replacement.pop("final_composition_fingerprint", None)
            replacement.pop("compositor_version", None)
            replacement.pop("composition_diagnostics", None)
        replacement_specs.append(replacement)

    metadata.update(
        {
            "parent_variant_id": current.id,
            "poster_specs": replacement_specs,
            "storyboard_revision": {
                "parent_variant_id": current.id,
                "model_input_changed_pages": model_changed_pages,
                "local_composition_changed_pages": local_changed_pages,
            },
            "human_edited": True,
            "human_approved": False,
            "render_engine": "",
            "validation": {},
        }
    )
    revised.metadata_json = json.dumps(metadata, ensure_ascii=False)
    revised.output_paths_json = "{}"
    revised.status = "draft"
    revised.error = ""
    revised.body_html = ""
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


@router.post(
    "/variants/{variant_id}/memory-candidate",
    status_code=status.HTTP_201_CREATED,
)
async def variant_memory_candidate(
    variant_id: str,
    body: PoolMemoryTargetCandidateRequest,
    db: Session = Depends(get_db),
    service: PoolMemoryService = Depends(get_pool_memory_service),
) -> dict:
    variant = _variant(db, variant_id)
    try:
        candidate = await service.create_candidate(
            db,
            source_kind="platform_variant",
            source_id=variant.id,
            title=body.title,
            dimensions=[str(item) for item in body.dimensions],
            scope=body.scope.model_dump(),
            usage_policy=body.usage_policy,
            note=body.note,
        )
        db.commit()
        db.refresh(candidate)
        return {"candidate_id": candidate.id, "state": candidate.state}
    except PoolMemoryError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/variants/{variant_id}/memory-usages")
def variant_memory_usages(
    variant_id: str,
    db: Session = Depends(get_db),
    service: PoolMemoryService = Depends(get_pool_memory_service),
) -> dict:
    variant = _variant(db, variant_id)
    metadata = _json_object(variant.metadata_json)
    snapshot = service.snapshot(db, str(metadata.get("memory_snapshot_id") or ""))
    if snapshot is None:
        return {
            "variant_id": variant.id,
            "snapshot": service.snapshot_summary(None),
            "usages": [],
        }
    return {
        "variant_id": variant.id,
        "snapshot": service.snapshot_summary(snapshot),
        "usages": service.list_usages(db, target_id=snapshot.target_id, limit=200),
    }


@router.put("/variants/{variant_id}", response_model=PlatformVariantOut)
def update_variant(
    variant_id: str,
    body: PlatformVariantUpdate,
    db: Session = Depends(get_db),
    service: PlatformStudioService = Depends(get_platform_service),
) -> PlatformVariant:
    current = _variant(db, variant_id)
    revised = service.revise_variant(
        db,
        current,
        title=body.title,
        subtitle=body.subtitle,
        summary=body.summary,
        body_markdown=body.body_markdown,
        tags=body.tags,
        theme=body.theme,
    )
    if current.format == "light_series":
        _sync_light_storyboard(current, revised)
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
