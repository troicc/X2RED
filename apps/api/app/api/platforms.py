from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
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
from app.services.input_materials import InputMaterialError, resolve_input_materials
from app.services.light_content import LightContentError, poster_copy_issues
from app.services.light_content_fit import assess_source_fit
from app.services.light_content_lab import LightContentLabService
from app.services.light_visual_renderer import VISUAL_STYLE_LABELS
from app.services.minimal_zine_native import storyboard_model_input_changed
from app.services.platform_studio import PlatformStudioError, PlatformStudioService
from app.services.pool_memory import PoolMemoryError, PoolMemoryService
from app.services.skill_packs import pack_payloads
from app.services.skills import ensure_bindings
from app.services.visual_brief import VisualBriefError
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
    """Build a safe emergency storyboard only when a legacy variant has none.

    Normal article edits never call this data to overwrite an existing storyboard.
    Notes remain blank because adjacent body sentences are not page-level evidence and
    previously produced the exact N.note == N+1.phrase splice reported by users.
    """

    raw_candidates = [title, summary, *re.split(r"(?<=[。！？!?])|\n+", body)]
    phrases: list[str] = []
    keys: set[str] = set()
    for value in raw_candidates:
        candidate = re.sub(r"\s+", " ", str(value or "")).strip().rstrip("。！？!?")[:36]
        key = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", candidate).casefold()
        if not key or key in keys:
            continue
        phrases.append(candidate)
        keys.add(key)
        if len(phrases) >= count:
            break
    while len(phrases) < count:
        phrases.append(f"第 {len(phrases) + 1} 页短句待确认")
    return [(phrase, "") for phrase in phrases[:count]]


def _sync_light_storyboard(
    current: PlatformVariant,
    revised: PlatformVariant,
) -> None:
    metadata = _json_object(revised.metadata_json)
    specs_raw = metadata.get("poster_specs")
    specs = [dict(item) for item in specs_raw if isinstance(item, dict)] if isinstance(specs_raw, list) else []
    count = min(max(len(specs) or int(metadata.get("image_count") or 4), 3), 6)
    if not specs:
        segments = _light_copy_segments(revised.title, revised.summary, revised.body_markdown, count)
        specs = [
            {
                "phrase": phrase,
                "note": note,
                "visual_metaphor": "真实生活中的单一物件或场景",
                "photo_direction": "画面必须与文字中的具体场景一致",
                "layout": "editorial",
                "accent": "#1646d8",
                "mood": "quiet",
                "visual_style": metadata.get("visual_style") or "minimal_zine",
            }
            for phrase, note in segments
        ]
    specs = specs[:count]
    quality_issues = poster_copy_issues(specs)
    metadata.update(
        {
            "parent_variant_id": current.id,
            "poster_specs": specs,
            "storyboard_copy_sync": {
                "mode": "preserved-after-article-edit",
                "status": "review_required" if quality_issues else "preserved",
                "copy_changed": False,
                "quality_issues": quality_issues,
                "message": (
                    "正文保存不会静默改写逐页短句与说明；请在视觉分镜中单独确认。"
                ),
            },
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
        "visual_prompt_spec",
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


def _drop_storyboard_trace(current: dict) -> None:
    for key in (
        "final_prompt",
        "visual_prompt_spec",
        "native_zine_recipe",
        "native_zine_interpretation",
        "model_input_fingerprint",
        "raw_anchor_fingerprint",
        "raw_anchor_source_variant_id",
        "text_rendering",
        "model_text_forbidden",
    ):
        current.pop(key, None)


def _carry_storyboard_copy_provenance(previous: dict, current: dict) -> None:
    for key in ("evidence_basis", "source_refs"):
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
    try:
        resolved = resolve_input_materials(
            db,
            [
                *body.material_refs,
                *(f"source:{source_id}" for source_id in body.supporting_source_ids),
            ],
            preferred_source_id=body.source_id,
        )
    except InputMaterialError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    source = resolved.primary_source
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
            supporting_sources=resolved.sources[1:],
            input_materials=resolved.materials,
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
    visual_brief_mode = str(current_metadata.get("visual_brief_mode") or "legacy")
    configured_mode = str(
        current_metadata.get("visual_prompt_mode")
        or get_settings().minimal_zine_prompt_mode
    )
    if any(
        item.get("raw_anchor_fingerprint") and not item.get("visual_prompt_spec")
        for item in current_specs
    ):
        configured_mode = "legacy"
    semantic_context = {
        "article_thesis": current_metadata.get("strategy", {}).get("content_thesis")
        if isinstance(current_metadata.get("strategy"), dict)
        else "",
        "visual_bible": current_metadata.get("visual_bible") or {},
        "audience": current_metadata.get("audience") or "",
    }
    for submitted in sorted(body.pages, key=lambda page: page.page):
        page = submitted.page
        previous = current_specs[page - 1]
        replacement = submitted.model_dump()
        replacement["visual_style"] = str(
            previous.get("visual_style")
            or current_metadata.get("visual_style")
            or "minimal_zine"
        )
        _carry_storyboard_copy_provenance(previous, replacement)
        if visual_brief_mode == "production":
            raw_brief = replacement.get("page_visual_brief")
            if not isinstance(raw_brief, dict):
                raise HTTPException(
                    status_code=400,
                    detail=f"第 {page} 页缺少冻结 PageVisualBrief",
                )
            previous_brief = previous.get("page_visual_brief")
            if isinstance(previous_brief, dict):
                raw_brief["evidence_refs"] = previous_brief.get("evidence_refs") or previous.get(
                    "source_refs"
                ) or ["当前来源"]
            replacement["page_visual_brief"] = raw_brief
            replacement["visual_bible"] = current_metadata.get("visual_bible") or {}
        replacement_specs.append(replacement)

    copy_issues = poster_copy_issues(replacement_specs)
    if copy_issues:
        raise HTTPException(
            status_code=400,
            detail=(
                "分镜文案存在跨页重复：上一页说明不能复用为下一页短句，"
                "各页短句与说明也不能彼此近似重复。请逐页写成独立观点。"
            ),
        )

    if visual_brief_mode == "production":
        strategy = current_metadata.get("strategy")
        strategy = strategy if isinstance(strategy, dict) else {}
        try:
            frozen_bundle, replacement_specs = service.visual_briefs.refreeze_after_human_edit(
                previous_bundle=current_metadata.get("visual_brief") or {},
                posters=replacement_specs,
                article_thesis=str(
                    strategy.get("content_thesis") or current.summary or current.title
                ),
            )
        except VisualBriefError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        metadata["visual_bible"] = frozen_bundle.visual_bible.model_dump(mode="json")
        metadata["visual_brief"] = frozen_bundle.model_dump(mode="json")
        metadata["visual_distinctness"] = frozen_bundle.distinctness.model_dump(
            mode="json"
        )

    for page, (previous, replacement) in enumerate(
        zip(current_specs, replacement_specs, strict=True),
        start=1,
    ):
        model_changed = storyboard_model_input_changed(
            previous,
            replacement,
            feature_mode=configured_mode,  # type: ignore[arg-type]
            semantic_context=semantic_context,
        )
        local_changed = _storyboard_page_changed(previous, replacement)
        if model_changed:
            model_changed_pages.append(page)
            _drop_storyboard_trace(replacement)
        else:
            # Copy-only or crop-only revisions can keep the exact image prompt.
            _carry_storyboard_trace(previous, replacement)
        if local_changed or model_changed:
            local_changed_pages.append(page)
            replacement.pop("final_composition_fingerprint", None)
            replacement.pop("compositor_version", None)
            replacement.pop("composition_diagnostics", None)

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


@router.post("/variants/{variant_id}/repair-incomplete", response_model=PlatformVariantOut)
async def repair_incomplete_variant(
    variant_id: str,
    db: Session = Depends(get_db),
    service: PlatformStudioService = Depends(get_platform_service),
) -> PlatformVariant:
    variant = _variant(db, variant_id)
    try:
        repaired = await service.repair_incomplete_variant(db, variant)
    except PlatformStudioError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(repaired)
    return repaired


@router.post(
    "/variants/{variant_id}/visuals/{slot_id}",
    response_model=PlatformVariantOut,
)
async def upload_variant_visual(
    variant_id: str,
    slot_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    service: PlatformStudioService = Depends(get_platform_service),
) -> PlatformVariant:
    variant = _variant(db, variant_id)
    try:
        payload = await file.read(12 * 1024 * 1024 + 1)
        service.attach_visual_asset(
            db,
            variant,
            slot_id=slot_id,
            payload=payload,
        )
        db.commit()
        db.refresh(variant)
        return variant
    except PlatformStudioError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()


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
    return FileResponse(
        path,
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


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
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".zip": "application/zip",
    }.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(
        path,
        media_type=media_type,
        filename=path.name,
        headers={"Cache-Control": "no-store, max-age=0"},
    )


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
