from __future__ import annotations

import difflib
import hashlib
import html
import io
import json
import math
import re
import shutil
import uuid
import zipfile
from functools import cache
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.image_candidate_schemas import ImageCandidateLifecycle
from app.domain.platforms import PlatformVariant, PlatformVariantState
from app.domain.visual_brief_schemas import PageVisualBrief
from app.domain.visual_prompt_schemas import (
    VisualPromptContext,
    VisualPromptFeatureMode,
    VisualPromptRecipe,
    VisualPromptSpec,
)
from app.services.image_candidate_service import (
    CandidateBatchResult,
    ImageCandidateError,
    ImageCandidateService,
)
from app.services.light_visual_renderer import CJKFontError, LightVisualRenderer
from app.services.model_client import ModelClient, ModelClientError
from app.services.native_skill_manager import NativeSkillError, NativeSkillManager
from app.services.visual_prompt_compiler import (
    COMPILER_VERSION,
    DEGRADED_FALLBACK,
    V03_SKILL_NAME,
    VisualPromptCompiler,
)

RenderMode = Literal["render_missing", "recompose", "regenerate"]

STORYBOARD_LAYOUTS = (
    "center-fragment",
    "lower-fragment",
    "lower-left-float",
    "upper-right-block",
    "dual-panel",
    "irregular-cutout",
    "type-led",
    "dot-orbit",
    "single-specimen",
    "diagonal-notes",
    "edge-counterweight",
)
_LEGACY_LAYOUT_ALIASES = {
    "三分法构图，文字在画面上方": "lower-fragment",
    "三分法构图,文字在画面上方": "lower-fragment",
    "极简留白，文字在左下角": "upper-right-block",
    "极简留白,文字在左下角": "upper-right-block",
    "中心对称，文字在底部居中": "dual-panel",
    "中心对称,文字在底部居中": "dual-panel",
    "对角线构图，文字随窗帘飘动方向排列": "irregular-cutout",
    "对角线构图,文字随窗帘飘动方向排列": "irregular-cutout",
}
STORYBOARD_ANCHORS = (
    "tiny-faded-photo",
    "torn-paper-clipping",
    "flat-silhouette",
    "solid-color-block",
    "old-printed-illustration",
    "object-specimen",
    "translucent-geometric-overlay",
    "abstract-texture-window",
)
STORYBOARD_TEXTURES = (
    "xerox-softness",
    "risograph-grain",
    "letterpress-ink-bleed",
    "halftone-degradation",
    "film-grain-photo",
    "scan-noise-paper-fibers",
    "aged-paper-mottling",
    "soft-motion-blur",
)
_ACCENT_ALIASES = {
    "blue": "cobalt",
    "cobalt": "cobalt",
    "ultramarine": "ultramarine",
    "cyan": "cyan",
    "violet": "violet",
    "magenta": "magenta-pink",
    "magenta-pink": "magenta-pink",
    "yellow": "lemon-yellow",
    "lemon-yellow": "lemon-yellow",
    "green": "pear-green",
    "pear-green": "pear-green",
    "orange": "orange",
    "red": "tomato-red",
    "tomato-red": "tomato-red",
    "vermilion": "vermilion",
}
_ACCENT_COLORS = {
    "cobalt": "#1646d8",
    "ultramarine": "#263fca",
    "cyan": "#00a7c6",
    "violet": "#6f3cc3",
    "magenta-pink": "#cb247d",
    "lemon-yellow": "#d5aa00",
    "pear-green": "#4d9b4a",
    "orange": "#d46f1b",
    "tomato-red": "#c93a2b",
    "vermilion": "#c91f2c",
}


def _clean(value: Any, limit: int) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _allowed(value: Any, allowed: tuple[str, ...], fallback: str) -> str:
    candidate = _clean(value, 100).lower().replace("_", "-").replace(" ", "-")
    return candidate if candidate in allowed else fallback


def _canonical_accent(value: Any) -> str:
    candidate = _clean(value, 32).lower().replace("_", "-").replace(" ", "-")
    if re.fullmatch(r"#[0-9a-f]{6}", candidate):
        return candidate
    return _ACCENT_ALIASES.get(candidate, "cobalt")


def _canonical_layout(value: Any) -> str:
    raw = _clean(value, 100)
    candidate = raw.lower().replace("_", "-").replace(" ", "-")
    if candidate in STORYBOARD_LAYOUTS:
        return candidate
    if raw in _LEGACY_LAYOUT_ALIASES:
        return _LEGACY_LAYOUT_ALIASES[raw]
    compact = re.sub(r"[\s，,。；;：:]", "", raw)
    if "文字" in compact and any(word in compact for word in ("画面上方", "顶部", "上方")):
        return "lower-fragment"
    if "文字" in compact and "左下" in compact:
        return "upper-right-block"
    if "文字" in compact and any(word in compact for word in ("底部居中", "下方居中")):
        return "dual-panel"
    if any(word in compact for word in ("对角线", "斜向", "飘动方向")):
        return "irregular-cutout"
    return "center-fragment"


def _storyboard_controls(spec: dict[str, Any]) -> dict[str, Any]:
    """Return the one contract used by prompts, raw-cache validity and composing."""

    return {
        "visual_metaphor": _clean(spec.get("visual_metaphor"), 240)
        or "one isolated ordinary object",
        "layout": _canonical_layout(spec.get("layout")),
        "anchor": _allowed(spec.get("anchor"), STORYBOARD_ANCHORS, "object-specimen"),
        "accent": _canonical_accent(spec.get("accent")),
        "texture": _allowed(spec.get("texture"), STORYBOARD_TEXTURES, "xerox-softness"),
        "mood": _clean(spec.get("mood"), 80) or "quiet",
    }


def _legacy_model_input_fingerprint(spec: dict[str, Any]) -> str:
    """Fingerprint produced by compositor v5 before legacy layout normalization."""

    controls = {
        "visual_metaphor": _clean(spec.get("visual_metaphor"), 240)
        or "one isolated ordinary object",
        "layout": _allowed(spec.get("layout"), STORYBOARD_LAYOUTS, "center-fragment"),
        "anchor": _allowed(spec.get("anchor"), STORYBOARD_ANCHORS, "object-specimen"),
        "accent": _canonical_accent(spec.get("accent")),
        "texture": _allowed(spec.get("texture"), STORYBOARD_TEXTURES, "xerox-softness"),
        "mood": _clean(spec.get("mood"), 80) or "quiet",
    }
    encoded = json.dumps(controls, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _model_input_fingerprint(spec: dict[str, Any]) -> str:
    encoded = json.dumps(_storyboard_controls(spec), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _semantic_model_input_fingerprint(
    spec: dict[str, Any],
    *,
    semantic_context: dict[str, Any] | None = None,
) -> str:
    """Fingerprint the production compiler inputs while preserving C0 replay helpers."""

    payload = {
        "storyboard": _storyboard_controls(spec),
        "phrase": _clean(spec.get("phrase"), 160),
        "note": _clean(spec.get("note"), 500),
        "evidence_summary": _clean(
            spec.get("evidence_summary") or spec.get("evidence_basis"),
            1600,
        ),
        "source_refs": [
            _clean(value, 160)
            for value in spec.get("source_refs", [])
            if _clean(value, 160)
        ]
        if isinstance(spec.get("source_refs"), list)
        else [],
        "page_visual_role": _clean(spec.get("page_visual_role"), 100),
        "article_thesis": _clean(spec.get("article_thesis"), 1200),
        "visual_bible": spec.get("visual_bible")
        if isinstance(spec.get("visual_bible"), dict)
        else {},
        "page_visual_brief": spec.get("page_visual_brief")
        if isinstance(spec.get("page_visual_brief"), dict)
        else {},
        "visual_brief_source_fingerprint": _clean(
            spec.get("visual_brief_source_fingerprint"),
            128,
        ),
        "semantic_context": semantic_context or {},
        "skill_sha": NativeSkillManager.definition(V03_SKILL_NAME).commit,
        "compiler_version": COMPILER_VERSION,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def storyboard_model_input_changed(
    previous: dict[str, Any],
    current: dict[str, Any],
    *,
    feature_mode: VisualPromptFeatureMode = "production",
    semantic_context: dict[str, Any] | None = None,
) -> bool:
    """Public helper for immutable storyboard revisions.

    Production Prompt inputs include copy, evidence and page role. Legacy mode keeps
    the historical raw-anchor behavior for explicit rollback and C0 replay.
    """

    if feature_mode == "legacy":
        return _model_input_fingerprint(previous) != _model_input_fingerprint(current)
    return _semantic_model_input_fingerprint(
        previous,
        semantic_context=semantic_context,
    ) != _semantic_model_input_fingerprint(
        current,
        semantic_context=semantic_context,
    )


class MinimalZineNativeService:
    skill_name = "gc-minimal-zine-poster-v0-1"
    compositor_version = "minimal-zine-local-type-v7-typography-recipes"
    high_chroma_threshold = 0.004
    # A sparse plate can have a deliberately faded, but still meaningful, color
    # cluster.  Keep this separate from the stronger prompt-compliance signal so
    # the local repair is reserved for genuinely color-starved anchors.
    muted_chroma_saturation = 55
    muted_chroma_threshold = 0.0015
    # The fallback is a tiny printer's registration mark, not a second visual
    # subject.  Its actual painted area is lower than this budget.
    local_accent_target_share = 0.0025
    local_accent_max_share = 0.003

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.manager = NativeSkillManager(settings)
        self.model = ModelClient(settings)
        self.image_candidates = ImageCandidateService(
            settings,
            model_client=self.model,
        )
        self.prompt_compiler = VisualPromptCompiler(settings)
        self.local_renderer = LightVisualRenderer(settings)

    @property
    def image_configured(self) -> bool:
        return bool(
            (self.settings.image_base_url or self.settings.model_base_url)
            and (self.settings.image_api_key or self.settings.model_api_key)
            and self.settings.image_model
        )

    def prepare_web_handoff(
        self,
        variant: PlatformVariant,
        *,
        pages: list[int] | None = None,
        force_recompile: bool = False,
    ) -> dict[str, Any]:
        """Build ChatGPT Images prompts without ever calling an image API.

        ChatGPT's consumer web UI is intentionally treated as a human handoff:
        X2RED runs the same text compiler used by API rendering, then the user
        generates and saves the image in ChatGPT and uploads it back. We never
        automate the signed-in web session or pretend it is an API.
        """

        self._require_light_variant(variant)
        metadata = self._object(variant.metadata_json)
        specs = self._poster_specs(metadata)
        total = len(specs)
        if not 3 <= total <= 6:
            raise NativeSkillError("Minimal Zine 故事板必须包含 3 到 6 页")
        selected = self._selected_pages(pages, total)
        new_specs = [dict(item) for item in specs]
        feature_mode = self._compiler_feature_mode(metadata, new_specs)
        results: list[dict[str, Any]] = []
        for page in selected:
            spec = new_specs[page - 1]
            previous_prompt = str(spec.get("final_prompt") or "")
            visual_spec = self._compile_visual_prompt_spec(
                variant=variant,
                metadata=metadata,
                specs=new_specs,
                page=page,
                feature_mode=feature_mode,
                force_recompile=force_recompile,
            )
            prompt = self._four_paragraph_prompt(visual_spec)
            model_fingerprint = (
                _model_input_fingerprint(spec)
                if feature_mode == "legacy"
                else visual_spec.source_fingerprint
            )
            spec.update(
                {
                    "final_prompt": prompt,
                    "visual_prompt_spec": visual_spec.model_dump(mode="json"),
                    "native_zine_recipe": visual_spec.recipe.model_dump(mode="json"),
                    "model_input_fingerprint": model_fingerprint,
                }
            )
            results.append(
                {
                    "page": page,
                    "prompt": prompt,
                    "recipe": visual_spec.recipe.model_dump(mode="json"),
                    "visual_prompt_spec": visual_spec.model_dump(mode="json"),
                    "compiler_mode": visual_spec.mode,
                    "skill_version": visual_spec.skill_version,
                    "source_fingerprint": visual_spec.source_fingerprint,
                    "prompt_fingerprint": visual_spec.prompt_fingerprint,
                    "warnings": visual_spec.warnings,
                    "model_input_fingerprint": model_fingerprint,
                    "prompt_diff": self._prompt_diff(previous_prompt, prompt),
                    "aspect_ratio": "3:5",
                    "text_policy": "no-model-text; x2red-local-cjk",
                }
            )
        metadata["poster_specs"] = new_specs
        metadata["visual_prompt_mode"] = feature_mode
        variant.metadata_json = json.dumps(metadata, ensure_ascii=False)
        return {
            "variant_id": variant.id,
            "provider": "chatgpt-web",
            "chatgpt_url": "https://chatgpt.com/images",
            "api_used": False,
            "text_compiler": feature_mode != "legacy",
            "compiler_mode": self.prompt_compiler.schema_mode(feature_mode),
            "automation": "manual-copy-save-upload",
            "pages": results,
        }

    def import_external_anchor(
        self,
        db: Session,
        variant: PlatformVariant,
        *,
        page: int,
        image_bytes: bytes | None = None,
        image_candidates: list[bytes] | None = None,
        provider: str = "chatgpt-web",
    ) -> tuple[PlatformVariant, dict[str, Any], bool]:
        """Import one human-generated web image and rebuild every available final.

        Partial imports are allowed so a fresh 3–6 page set can be handed through
        ChatGPT one page at a time.  A publish ZIP is exposed only after all pages
        have both a raw anchor and a locally composed final poster.
        """

        self._require_light_variant(variant)
        uploaded_images = list(image_candidates or ([] if image_bytes is None else [image_bytes]))
        if not 1 <= len(uploaded_images) <= 4:
            raise NativeSkillError("手工网页路径每页必须上传 1 到 4 张图片")
        if any(not value for value in uploaded_images):
            raise NativeSkillError("上传图片为空")
        if any(len(value) > 12 * 1024 * 1024 for value in uploaded_images):
            raise NativeSkillError("单张图片不能超过 12 MB")

        metadata = self._object(variant.metadata_json)
        specs = self._poster_specs(metadata)
        total = len(specs)
        if not 3 <= total <= 6:
            raise NativeSkillError("Minimal Zine 故事板必须包含 3 到 6 页")
        self._selected_pages([page], total)
        try:
            font_diagnostics = self.local_renderer.require_cjk_font()
        except CJKFontError as exc:
            raise NativeSkillError(str(exc)) from exc

        current_paths = self._object(variant.output_paths_json)
        parent = self._parent_variant(db, metadata, variant)
        parent_metadata = self._object(parent.metadata_json) if parent else {}
        parent_specs = self._poster_specs(parent_metadata) if parent else []
        parent_paths = self._object(parent.output_paths_json) if parent else {}
        handoff = self.prepare_web_handoff(variant, pages=[page])["pages"][0]
        handoff_visual_spec = VisualPromptSpec.model_validate(
            handoff["visual_prompt_spec"]
        )
        feature_mode = self._compiler_feature_mode(metadata, specs)
        candidate_mode = self._candidate_feature_mode(metadata)
        candidate_lifecycle = (
            self._candidate_lifecycle(metadata)
            if candidate_mode == "production"
            else ImageCandidateLifecycle()
        )

        wechat_root = (self.settings.export_dir / "wechat").resolve()
        wechat_root.mkdir(parents=True, exist_ok=True)
        target_dir = self._variant_directory(wechat_root, variant.id)
        staging_dir = wechat_root / f".{variant.id}.staging-{uuid.uuid4().hex}"
        staging_dir.mkdir(parents=False, exist_ok=False)
        new_specs = [dict(item) for item in specs]
        stage_paths: dict[str, str] = {}
        selected_uploaded_candidate = None
        if candidate_mode == "production":
            self._copy_candidate_artifacts(current_paths, staging_dir, stage_paths)
            self._copy_candidate_artifacts(parent_paths, staging_dir, stage_paths)
            try:
                batch = self.image_candidates.add_manual_candidates(
                    lifecycle=candidate_lifecycle,
                    page=page,
                    prompt=str(handoff["prompt"]),
                    images=uploaded_images,
                    output_dir=staging_dir,
                    artifact_paths=stage_paths,
                    page_visual_brief=(
                        new_specs[page - 1].get("page_visual_brief")
                        if isinstance(new_specs[page - 1].get("page_visual_brief"), dict)
                        else None
                    ),
                    invariants=self._candidate_invariants(metadata, new_specs[page - 1]),
                    provider=provider,
                    model="manual-web-image",
                    series_reference_bytes=self._candidate_reference_bytes(
                        candidate_lifecycle,
                        page,
                        stage_paths,
                    ),
                )
                candidate_lifecycle = batch.lifecycle
                stage_paths = batch.artifact_paths
                selected_uploaded_candidate = (
                    batch.selected_candidate
                    if batch.selected_candidate is not None
                    and batch.selected_candidate.candidate_id in batch.created_candidate_ids
                    else None
                )
            except ImageCandidateError as exc:
                raise NativeSkillError(str(exc)) from exc
        selected_uploaded_bytes: bytes | None
        if candidate_mode == "production" and selected_uploaded_candidate is not None:
            try:
                selected_uploaded_bytes = self.image_candidates.selected_bytes(
                    candidate_lifecycle,
                    page,
                    stage_paths,
                )
            except ImageCandidateError as exc:
                raise NativeSkillError(str(exc)) from exc
        elif candidate_mode == "legacy":
            selected_uploaded_bytes = uploaded_images[0]
        else:
            selected_uploaded_bytes = None
        page_diagnostics: list[dict[str, Any]] = []
        backup_dir: Path | None = None
        promoted = False
        original_values = {
            "metadata_json": variant.metadata_json,
            "output_paths_json": variant.output_paths_json,
            "status": variant.status,
            "error": variant.error,
        }

        try:
            for current_page, spec in enumerate(new_specs, start=1):
                anchor_key = f"anchor_{current_page:02d}"
                poster_key = f"poster_{current_page:02d}"
                anchor_path = staging_dir / f"anchor-{current_page:02d}.png"
                poster_path = staging_dir / f"poster-{current_page:02d}.png"
                model_fingerprint = self._expected_model_fingerprint(
                    variant=variant,
                    metadata=metadata,
                    specs=new_specs,
                    page=current_page,
                    feature_mode=feature_mode,
                )
                stored_recipe = self._stored_visual_recipe(spec)
                recipe = self._persisted_recipe(spec)
                action = ""
                raw_source_variant_id = variant.id

                if current_page == page and selected_uploaded_bytes is not None:
                    model_fingerprint = (
                        _model_input_fingerprint(spec)
                        if feature_mode == "legacy"
                        else handoff_visual_spec.source_fingerprint
                    )
                    stored_recipe = handoff_visual_spec.recipe.model_dump(mode="json")
                    recipe = self._composer_recipe(handoff_visual_spec.recipe)
                    self._write_raw_anchor(selected_uploaded_bytes, anchor_path)
                    spec.update(
                        {
                            "final_prompt": str(handoff["prompt"]),
                            "visual_prompt_spec": handoff_visual_spec.model_dump(mode="json"),
                            "native_zine_recipe": stored_recipe,
                            "native_zine_interpretation": "由人工在 ChatGPT Images 网页生成并回传的无字视觉锚点。",
                            "model_input_fingerprint": model_fingerprint,
                            "raw_anchor_fingerprint": model_fingerprint,
                            "raw_anchor_source_variant_id": variant.id,
                            "raw_anchor_provider": provider,
                            "raw_anchor_handoff": "manual-web-save-upload",
                        }
                    )
                    if selected_uploaded_candidate is not None:
                        spec.update(
                            {
                                "selected_image_candidate_id": selected_uploaded_candidate.candidate_id,
                                "image_candidate_review": selected_uploaded_candidate.review.model_dump(
                                    mode="json"
                                ),
                            }
                        )
                    action = "external_import"
                else:
                    final_source = self._final_candidate(
                        variant=variant,
                        specs=specs,
                        paths=current_paths,
                        page=current_page,
                        target_spec=spec,
                        expected_model_fingerprint=model_fingerprint,
                    )
                    if final_source is None and parent is not None:
                        final_source = self._final_candidate(
                            variant=parent,
                            specs=parent_specs,
                            paths=parent_paths,
                            page=current_page,
                            target_spec=spec,
                            expected_model_fingerprint=model_fingerprint,
                        )
                    if final_source is not None:
                        raw = final_source.get("raw")
                        final_path = final_source.get("poster_path")
                        if not isinstance(raw, dict) or not isinstance(final_path, Path):
                            raise NativeSkillError(f"第 {current_page} 页缓存文件记录损坏")
                        self._copy_raw_anchor(raw, anchor_path)
                        shutil.copy2(final_path, poster_path)
                        self._hydrate_trace(spec, raw.get("spec"), model_fingerprint)
                        stored_recipe = self._stored_visual_recipe(spec)
                        recipe = self._persisted_recipe(spec)
                        raw_source_variant_id = str(raw.get("variant_id") or variant.id)
                        action = "cached"
                    else:
                        raw = self._raw_candidate(
                            variant=variant,
                            specs=specs,
                            paths=current_paths,
                            parent=parent,
                            parent_specs=parent_specs,
                            parent_paths=parent_paths,
                            page=current_page,
                            expected_fingerprint=model_fingerprint,
                        )
                        if raw is None:
                            continue
                        self._copy_raw_anchor(raw, anchor_path)
                        self._hydrate_trace(spec, raw.get("spec"), model_fingerprint)
                        stored_recipe = self._stored_visual_recipe(spec)
                        recipe = self._persisted_recipe(spec)
                        raw_source_variant_id = str(raw.get("variant_id") or variant.id)
                        action = "recomposed"

                if action != "cached":
                    composition = self._compose_poster(
                        anchor_path.read_bytes(),
                        poster_path,
                        spec=spec,
                        recipe=recipe,
                        page=current_page,
                        total=total,
                        font_diagnostics=font_diagnostics,
                    )
                else:
                    composition = self._object_value(spec.get("composition_diagnostics"))
                    composition = {**composition, "cached_final": True}

                if candidate_mode == "production":
                    selected_candidate = self.image_candidates.selected_candidate(
                        candidate_lifecycle,
                        current_page,
                    )
                    if selected_candidate is None:
                        adopted = self._adopt_existing_candidate(
                            lifecycle=candidate_lifecycle,
                            metadata=metadata,
                            spec=spec,
                            page=current_page,
                            anchor_path=anchor_path,
                            output_dir=staging_dir,
                            artifact_paths=stage_paths,
                        )
                        candidate_lifecycle = adopted.lifecycle
                        stage_paths = adopted.artifact_paths
                        selected_candidate = adopted.selected_candidate
                    if selected_candidate is not None:
                        spec.update(
                            {
                                "selected_image_candidate_id": selected_candidate.candidate_id,
                                "image_candidate_review": selected_candidate.review.model_dump(
                                    mode="json"
                                ),
                            }
                        )

                spec.update(
                    {
                        "native_zine_recipe": stored_recipe or recipe,
                        "model_input_fingerprint": model_fingerprint,
                        "raw_anchor_fingerprint": model_fingerprint,
                        "final_composition_fingerprint": self._composition_fingerprint(spec, recipe),
                        "compositor_version": self.compositor_version,
                        "composition_diagnostics": composition,
                        "visual_style": "minimal_zine_native",
                        "text_rendering": "x2red-local-cjk",
                        "model_text_forbidden": True,
                    }
                )
                stage_paths[anchor_key] = str(anchor_path.resolve())
                stage_paths[poster_key] = str(poster_path.resolve())
                page_diagnostics.append(
                    {
                        "page": current_page,
                        "anchor_key": anchor_key,
                        "poster_key": poster_key,
                        "action": action,
                        "raw_source_variant_id": raw_source_variant_id,
                        "provider": provider if current_page == page else str(spec.get("raw_anchor_provider") or "existing"),
                        "diagnostics": composition,
                    }
                )

            imported_pages = [
                index
                for index, spec in enumerate(new_specs, start=1)
                if str(spec.get("raw_anchor_provider") or "") == provider
            ]
            complete = all(
                f"anchor_{index:02d}" in stage_paths and f"poster_{index:02d}" in stage_paths
                for index in range(1, total + 1)
            )
            pending_pages = [
                index
                for index in range(1, total + 1)
                if f"poster_{index:02d}" not in stage_paths
            ]
            previous_native = self._object_value(metadata.get("native_zine"))
            new_metadata = dict(metadata)
            new_metadata["poster_specs"] = new_specs
            new_metadata["render_engine"] = "gc-minimal-zine-local-compositor-v7"
            new_metadata["visual_prompt_mode"] = feature_mode
            new_metadata["image_candidate_mode"] = candidate_mode
            if candidate_mode == "production":
                new_metadata["image_candidate_lifecycle"] = candidate_lifecycle.model_dump(
                    mode="json"
                )
            new_metadata["native_zine"] = {
                **previous_native,
                "repository": "https://github.com/LiamGvchi/gc-minimal-zine-poster",
                "commit": self.manager.definition(
                    self.skill_name if feature_mode == "legacy" else V03_SKILL_NAME
                ).commit,
                "license": "MIT",
                "prompt_compiler": COMPILER_VERSION,
                "prompt_compiler_mode": self.prompt_compiler.schema_mode(feature_mode),
                "compositor_version": self.compositor_version,
                "model_role": "visual-anchor-only",
                "local_typography": True,
                "font": font_diagnostics,
                "external_web_handoff": {
                    "provider": provider,
                    "api_used": False,
                    "automation": "manual-copy-save-upload",
                    "imported_pages": imported_pages,
                    "pending_pages": pending_pages,
                    "complete": complete,
                },
                "artifact_contract": "anchors-and-finals-separate; zip-excludes-anchors",
                "image_candidates": {
                    "mode": candidate_mode,
                    "manual_upload_count": len(uploaded_images),
                    "auto_repair_limit": 1,
                    "publish_requires_review_pass": candidate_mode == "production",
                },
                "watermark_policy": (
                    "negative prompt, feathered high-risk outer-edge masking, local Chinese type, "
                    "and required human visual review; no watermark-impossibility claim"
                ),
            }
            candidate_publish_allowed = (
                candidate_mode != "production"
                or self.image_candidates.publish_allowed(
                    candidate_lifecycle,
                    total_pages=total,
                    artifact_paths=stage_paths,
                )
            )
            allow_package = complete and candidate_publish_allowed
            stage_paths = self._rebuild_artifacts(
                variant=variant,
                metadata=new_metadata,
                specs=new_specs,
                output_dir=staging_dir,
                output_paths=stage_paths,
                page_diagnostics=page_diagnostics,
                allow_package=allow_package,
            )
            if f"poster_{page:02d}" in stage_paths:
                self._assert_import_artifacts(stage_paths, staging_dir, page)
            else:
                required = {"markdown", "manifest", "preview", f"contact_sheet_{page:02d}"}
                missing = sorted(key for key in required if key not in stage_paths)
                if missing:
                    raise NativeSkillError(
                        f"候选审稿产物不完整：缺少 {', '.join(missing)}"
                    )
            if not allow_package and "package" in stage_paths:
                raise NativeSkillError("未通过视觉审稿的候选不得进入发布包")

            final_paths = {
                key: str((target_dir / Path(value).name).resolve())
                for key, value in stage_paths.items()
            }
            backup_dir = self._promote_staging(staging_dir, target_dir)
            promoted = True
            variant.metadata_json = json.dumps(new_metadata, ensure_ascii=False)
            variant.output_paths_json = json.dumps(final_paths, ensure_ascii=False)
            variant.status = (
                PlatformVariantState.packaged.value
                if "package" in final_paths
                else PlatformVariantState.rendered.value
            )
            variant.error = ""
            db.flush()
        except Exception as exc:
            if promoted:
                self._restore_promoted_directory(target_dir, backup_dir)
            variant.metadata_json = original_values["metadata_json"]
            variant.output_paths_json = original_values["output_paths_json"]
            variant.status = original_values["status"]
            variant.error = original_values["error"]
            if isinstance(exc, NativeSkillError):
                raise
            detail = _clean(str(exc), 240) or exc.__class__.__name__
            raise NativeSkillError(
                f"网页生图回传失败，已保留上一版成品：{detail}"
            ) from exc
        else:
            if backup_dir is not None and backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)
            poster_key = f"poster_{page:02d}"
            anchor_key = f"anchor_{page:02d}"
            result = {
                "page": page,
                "path": final_paths.get(poster_key, ""),
                "anchor_path": final_paths.get(anchor_key, ""),
                "anchor_key": anchor_key if anchor_key in final_paths else "",
                "poster_key": poster_key if poster_key in final_paths else "",
                "action": (
                    "external_import"
                    if poster_key in final_paths
                    else "candidate_review_required"
                ),
                "provider": provider,
                "api_used": False,
                "final_prompt": str(handoff["prompt"]),
                "recipe": handoff["recipe"],
                "candidate_page": (
                    candidate_lifecycle.pages.get(str(page)).model_dump(mode="json")
                    if candidate_mode == "production"
                    and candidate_lifecycle.pages.get(str(page)) is not None
                    else {}
                ),
            }
            return variant, result, "package" in final_paths
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)

    def review_image_candidate(
        self,
        db: Session,
        variant: PlatformVariant,
        *,
        page: int,
        candidate_id: str,
        action: Literal["keep", "reject", "approve"],
        reason: str = "",
    ) -> dict[str, Any]:
        self._require_light_variant(variant)
        metadata = self._object(variant.metadata_json)
        specs = self._poster_specs(metadata)
        self._selected_pages([page], len(specs))
        if self._candidate_feature_mode(metadata) != "production":
            raise NativeSkillError("当前版本处于 legacy 图片候选模式")
        lifecycle = self._candidate_lifecycle(metadata)
        page_state = lifecycle.pages.get(str(page))
        was_selected = bool(
            page_state and page_state.selected_candidate_id == candidate_id
        )
        try:
            lifecycle = self.image_candidates.review_candidate(
                lifecycle=lifecycle,
                page=page,
                candidate_id=candidate_id,
                action=action,
                reason=reason,
            )
        except ImageCandidateError as exc:
            raise NativeSkillError(str(exc)) from exc
        metadata["image_candidate_lifecycle"] = lifecycle.model_dump(mode="json")
        metadata["image_candidate_mode"] = "production"
        output_paths = self._object(variant.output_paths_json)
        if action == "reject" and was_selected:
            for key in (
                f"anchor_{page:02d}",
                f"poster_{page:02d}",
                "package",
            ):
                output_paths.pop(key, None)
            spec = specs[page - 1]
            for key in (
                "selected_image_candidate_id",
                "image_candidate_review",
                "raw_anchor_fingerprint",
                "raw_anchor_source_variant_id",
                "final_composition_fingerprint",
                "composition_diagnostics",
            ):
                spec.pop(key, None)
            metadata["poster_specs"] = specs
            variant.status = PlatformVariantState.rendered.value
        variant.metadata_json = json.dumps(metadata, ensure_ascii=False)
        variant.output_paths_json = json.dumps(output_paths, ensure_ascii=False)
        variant.error = ""
        db.flush()
        return self._candidate_response(
            variant=variant,
            lifecycle=lifecycle,
            page=page,
            output_paths=output_paths,
            total_pages=len(specs),
        )

    def select_image_candidate(
        self,
        db: Session,
        variant: PlatformVariant,
        *,
        page: int,
        candidate_id: str,
    ) -> tuple[PlatformVariant, dict[str, Any]]:
        self._require_light_variant(variant)
        metadata = self._object(variant.metadata_json)
        specs = self._poster_specs(metadata)
        total = len(specs)
        self._selected_pages([page], total)
        if self._candidate_feature_mode(metadata) != "production":
            raise NativeSkillError("当前版本处于 legacy 图片候选模式")
        lifecycle = self._candidate_lifecycle(metadata)
        output_paths = self._object(variant.output_paths_json)
        target_dir = self._variant_directory(
            (self.settings.export_dir / "wechat").resolve(),
            variant.id,
        )
        try:
            lifecycle = self.image_candidates.select_candidate(
                lifecycle=lifecycle,
                page=page,
                candidate_id=candidate_id,
                output_dir=target_dir,
                artifact_paths=output_paths,
            )
            selected = self.image_candidates.selected_candidate(lifecycle, page)
            if selected is None:
                raise ImageCandidateError("候选选择没有生效")
            # This verifies both the file hash and the selected review state before
            # exposing the candidate as a raw anchor to the compositor.
            self.image_candidates.selected_bytes(lifecycle, page, output_paths)
        except ImageCandidateError as exc:
            raise NativeSkillError(str(exc)) from exc

        feature_mode = self._compiler_feature_mode(metadata, specs)
        spec = specs[page - 1]
        model_fingerprint = self._expected_model_fingerprint(
            variant=variant,
            metadata=metadata,
            specs=specs,
            page=page,
            feature_mode=feature_mode,
        )
        spec.update(
            {
                "selected_image_candidate_id": selected.candidate_id,
                "image_candidate_review": selected.review.model_dump(mode="json"),
                "raw_anchor_fingerprint": model_fingerprint,
                "raw_anchor_source_variant_id": variant.id,
                "raw_anchor_provider": selected.provider,
            }
        )
        spec.pop("final_composition_fingerprint", None)
        spec.pop("composition_diagnostics", None)
        metadata["poster_specs"] = specs
        metadata["image_candidate_mode"] = "production"
        metadata["image_candidate_lifecycle"] = lifecycle.model_dump(mode="json")
        output_paths[f"anchor_{page:02d}"] = output_paths[selected.artifact_key]
        output_paths.pop(f"poster_{page:02d}", None)
        output_paths.pop("package", None)
        variant.metadata_json = json.dumps(metadata, ensure_ascii=False)
        variant.output_paths_json = json.dumps(output_paths, ensure_ascii=False)
        variant.status = PlatformVariantState.rendered.value
        variant.error = ""
        db.flush()

        pages: list[dict[str, Any]] = []
        deferred = False
        try:
            variant, pages = self.render_variant(
                db,
                variant,
                mode="recompose",
                pages=[page],
            )
        except NativeSkillError as exc:
            if "部分渲染无法组成完整图组" not in str(exc):
                raise
            deferred = True
        fresh_metadata = self._object(variant.metadata_json)
        fresh_lifecycle = self._candidate_lifecycle(fresh_metadata)
        fresh_paths = self._object(variant.output_paths_json)
        response = self._candidate_response(
            variant=variant,
            lifecycle=fresh_lifecycle,
            page=page,
            output_paths=fresh_paths,
            total_pages=total,
        )
        response.update(
            {
                "deferred_composition": deferred,
                "pages": pages,
            }
        )
        return variant, response

    def repair_image_candidate(
        self,
        db: Session,
        variant: PlatformVariant,
        *,
        page: int,
        candidate_id: str,
    ) -> tuple[PlatformVariant, dict[str, Any]]:
        self._require_light_variant(variant)
        metadata = self._object(variant.metadata_json)
        specs = self._poster_specs(metadata)
        total = len(specs)
        self._selected_pages([page], total)
        if self._candidate_feature_mode(metadata) != "production":
            raise NativeSkillError("当前版本处于 legacy 图片候选模式")
        lifecycle = self._candidate_lifecycle(metadata)
        output_paths = self._object(variant.output_paths_json)
        output_dir = self._variant_directory(
            (self.settings.export_dir / "wechat").resolve(),
            variant.id,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        spec = specs[page - 1]
        try:
            result = self.image_candidates.repair_once(
                lifecycle=lifecycle,
                page=page,
                candidate_id=candidate_id,
                output_dir=output_dir,
                artifact_paths=output_paths,
                page_visual_brief=(
                    spec.get("page_visual_brief")
                    if isinstance(spec.get("page_visual_brief"), dict)
                    else None
                ),
                invariants=self._candidate_invariants(metadata, spec),
                series_reference_bytes=self._candidate_reference_bytes(
                    lifecycle,
                    page,
                    output_paths,
                ),
            )
        except ImageCandidateError as exc:
            raise NativeSkillError(str(exc)) from exc
        lifecycle = result.lifecycle
        output_paths = result.artifact_paths
        metadata["image_candidate_mode"] = "production"
        metadata["image_candidate_lifecycle"] = lifecycle.model_dump(mode="json")
        variant.metadata_json = json.dumps(metadata, ensure_ascii=False)
        variant.output_paths_json = json.dumps(output_paths, ensure_ascii=False)
        variant.error = ""
        db.flush()
        repaired = result.page_state.candidates[-1]
        if repaired.review.passed and result.page_state.selected_candidate_id == repaired.candidate_id:
            return self.select_image_candidate(
                db,
                variant,
                page=page,
                candidate_id=repaired.candidate_id,
            )
        return variant, self._candidate_response(
            variant=variant,
            lifecycle=lifecycle,
            page=page,
            output_paths=output_paths,
            total_pages=total,
        )

    def _candidate_response(
        self,
        *,
        variant: PlatformVariant,
        lifecycle: ImageCandidateLifecycle,
        page: int,
        output_paths: dict[str, Any],
        total_pages: int,
    ) -> dict[str, Any]:
        page_state = lifecycle.pages.get(str(page))
        return {
            "variant_id": variant.id,
            "status": variant.status,
            "page": page,
            "candidate_page": page_state.model_dump(mode="json") if page_state else {},
            "publish_allowed": self.image_candidates.publish_allowed(
                lifecycle,
                total_pages=total_pages,
                artifact_paths={key: str(value) for key, value in output_paths.items()},
            ),
            "package_available": bool(output_paths.get("package")),
            "output_paths_json": variant.output_paths_json,
            "metadata_json": variant.metadata_json,
        }

    @staticmethod
    def _require_light_variant(variant: PlatformVariant) -> None:
        if variant.platform != "wechat" or variant.format != "light_series":
            raise NativeSkillError("Minimal Zine 原生生图只支持公众号轻内容图组")

    def render_variant(
        self,
        db: Session,
        variant: PlatformVariant,
        *,
        mode: RenderMode | None = None,
        pages: list[int] | None = None,
        regenerate: bool = False,
    ) -> tuple[PlatformVariant, list[dict[str, Any]]]:
        """Render a complete, atomically-promoted Minimal Zine artifact set.

        Raw anchors are the only model outputs accepted by recompose.  Final posters
        are never used as a raw fallback, even for legacy variants that only recorded
        poster paths.  This keeps a local recomposition diagnosable and prevents
        repeated post-processing of a previously composed final.
        """

        if mode is not None and regenerate:
            raise NativeSkillError("显式 mode 与 regenerate=true 不能同时使用")
        selected_mode: RenderMode = mode or (
            "regenerate" if regenerate else "render_missing"
        )
        if variant.platform != "wechat" or variant.format != "light_series":
            raise NativeSkillError("Minimal Zine 原生生图只支持公众号轻内容图组")

        metadata = self._object(variant.metadata_json)
        specs = self._poster_specs(metadata)
        total = len(specs)
        if not 3 <= total <= 6:
            raise NativeSkillError("Minimal Zine 故事板必须包含 3 到 6 页")
        feature_mode = self._compiler_feature_mode(metadata, specs)
        candidate_mode = self._candidate_feature_mode(metadata)
        candidate_lifecycle = (
            self._candidate_lifecycle(metadata)
            if candidate_mode == "production"
            else ImageCandidateLifecycle()
        )
        expected_fingerprints = {
            page: self._expected_model_fingerprint(
                variant=variant,
                metadata=metadata,
                specs=specs,
                page=page,
                feature_mode=feature_mode,
            )
            for page in range(1, total + 1)
        }
        selected_pages = self._selected_pages(pages, total)
        selected_set = set(selected_pages)

        try:
            font_diagnostics = self.local_renderer.require_cjk_font()
        except CJKFontError as exc:
            raise NativeSkillError(str(exc)) from exc

        current_paths = self._object(variant.output_paths_json)
        parent = self._parent_variant(db, metadata, variant)
        parent_metadata = self._object(parent.metadata_json) if parent else {}
        parent_specs = self._poster_specs(parent_metadata) if parent else []
        parent_paths = self._object(parent.output_paths_json) if parent else {}

        plans = self._plan_pages(
            variant=variant,
            specs=specs,
            current_paths=current_paths,
            parent=parent,
            parent_specs=parent_specs,
            parent_paths=parent_paths,
            selected_pages=selected_set,
            mode=selected_mode,
            expected_fingerprints=expected_fingerprints,
            allow_pending_pages=candidate_mode == "production",
        )
        needs_generation = any(
            page_plan["action"] == "regenerated" and page_plan["selected"]
            for page_plan in plans
        )
        if needs_generation and not self.image_configured:
            raise NativeSkillError(
                "尚未配置图片模型。请设置 X2RED_IMAGE_MODEL，以及图片接口的 BASE_URL/API_KEY；"
                "智谱兼容接口可填写 glm-image。"
            )

        skill_text = ""
        if needs_generation and feature_mode == "legacy":
            skill_dir = self.manager.ensure_installed(self.skill_name, install_runtime=False)
            # Deliberately read the full upstream instruction file; the compiler uses
            # its four-paragraph, variation and color engines as hard constraints.
            skill_text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")

        wechat_root = (self.settings.export_dir / "wechat").resolve()
        wechat_root.mkdir(parents=True, exist_ok=True)
        target_dir = self._variant_directory(wechat_root, variant.id)
        staging_dir = wechat_root / f".{variant.id}.staging-{uuid.uuid4().hex}"
        staging_dir.mkdir(parents=False, exist_ok=False)

        new_specs = [dict(item) for item in specs]
        stage_paths: dict[str, str] = {}
        if candidate_mode == "production":
            self._copy_candidate_artifacts(current_paths, staging_dir, stage_paths)
            self._copy_candidate_artifacts(parent_paths, staging_dir, stage_paths)
        page_results: list[dict[str, Any]] = []
        page_diagnostics: list[dict[str, Any]] = []
        recent_recipes: list[str] = []
        backup_dir: Path | None = None
        promoted = False
        original_values = {
            "metadata_json": variant.metadata_json,
            "output_paths_json": variant.output_paths_json,
            "status": variant.status,
            "error": variant.error,
        }

        try:
            for page_plan in plans:
                page = int(page_plan["page"])
                spec = new_specs[page - 1]
                anchor_key = f"anchor_{page:02d}"
                poster_key = f"poster_{page:02d}"
                anchor_path = staging_dir / f"anchor-{page:02d}.png"
                poster_path = staging_dir / f"poster-{page:02d}.png"
                action = str(page_plan["action"])
                model_fingerprint = expected_fingerprints[page]
                stored_recipe = self._stored_visual_recipe(spec)
                recipe = self._persisted_recipe(spec)
                composition: dict[str, Any] = {}

                if action == "pending":
                    page_diagnostics.append(
                        {
                            "page": page,
                            "action": "pending",
                            "review_required": True,
                            "diagnostics": {},
                        }
                    )
                    continue

                if action == "regenerated":
                    if feature_mode == "legacy":
                        compiled = self._compile_prompt(
                            skill_text=skill_text,
                            variant=variant,
                            spec=spec,
                            page=page,
                            total=total,
                            recent_recipes=recent_recipes,
                        )
                        final_prompt = str(compiled["final_prompt"])
                        recipe = compiled["recipe"]
                        stored_recipe = recipe
                        interpretation = str(compiled.get("interpretation") or "")
                    else:
                        visual_spec = self._compile_visual_prompt_spec(
                            variant=variant,
                            metadata=metadata,
                            specs=new_specs,
                            page=page,
                            feature_mode=feature_mode,
                            force_recompile=selected_mode == "regenerate",
                        )
                        final_prompt = self._four_paragraph_prompt(visual_spec)
                        stored_recipe = visual_spec.recipe.model_dump(mode="json")
                        recipe = self._composer_recipe(visual_spec.recipe)
                        model_fingerprint = visual_spec.source_fingerprint
                        interpretation = self._visual_interpretation(visual_spec, spec)
                        spec["visual_prompt_spec"] = visual_spec.model_dump(mode="json")
                    selected_image_candidate = None
                    if candidate_mode == "production":
                        try:
                            batch = self.image_candidates.generate_candidates(
                                lifecycle=candidate_lifecycle,
                                page=page,
                                prompt=final_prompt,
                                output_dir=staging_dir,
                                artifact_paths=stage_paths,
                                page_visual_brief=(
                                    spec.get("page_visual_brief")
                                    if isinstance(spec.get("page_visual_brief"), dict)
                                    else None
                                ),
                                invariants=self._candidate_invariants(metadata, spec),
                                count=self.settings.image_candidate_count,
                                series_reference_bytes=self._candidate_reference_bytes(
                                    candidate_lifecycle,
                                    page,
                                    stage_paths,
                                ),
                                auto_repair=True,
                            )
                            candidate_lifecycle = batch.lifecycle
                            stage_paths = batch.artifact_paths
                            selected_image_candidate = (
                                batch.selected_candidate
                                if batch.selected_candidate is not None
                                and batch.selected_candidate.candidate_id
                                in batch.created_candidate_ids
                                else None
                            )
                            if selected_image_candidate is None:
                                spec.update(
                                    {
                                        "final_prompt": final_prompt,
                                        "native_zine_recipe": stored_recipe,
                                        "native_zine_interpretation": interpretation,
                                        "model_input_fingerprint": model_fingerprint,
                                        "candidate_review_required": True,
                                    }
                                )
                                for trace_key in (
                                    "selected_image_candidate_id",
                                    "image_candidate_review",
                                    "raw_anchor_fingerprint",
                                    "raw_anchor_source_variant_id",
                                    "raw_anchor_provider",
                                    "final_composition_fingerprint",
                                    "composition_diagnostics",
                                ):
                                    spec.pop(trace_key, None)
                                recent_recipes.append(
                                    json.dumps(recipe, ensure_ascii=False, sort_keys=True)
                                )
                                review_state = candidate_lifecycle.pages.get(str(page))
                                diagnostic = {
                                    "page": page,
                                    "action": "candidate_review_required",
                                    "review_required": True,
                                    "diagnostics": {},
                                }
                                page_diagnostics.append(diagnostic)
                                if page in selected_set:
                                    page_results.append(
                                        {
                                            "page": page,
                                            "action": "candidate_review_required",
                                            "review_required": True,
                                            "candidate_page": (
                                                review_state.model_dump(mode="json")
                                                if review_state is not None
                                                else {}
                                            ),
                                        }
                                    )
                                continue
                            image_bytes = self.image_candidates.selected_bytes(
                                candidate_lifecycle,
                                page,
                                stage_paths,
                            )
                        except ImageCandidateError as exc:
                            raise NativeSkillError(f"第 {page} 页候选生成未通过：{exc}") from exc
                    else:
                        image_bytes = self._generate_image(final_prompt)
                    self._write_raw_anchor(image_bytes, anchor_path)
                    spec.update(
                        {
                            "final_prompt": final_prompt,
                            "native_zine_recipe": stored_recipe,
                            "native_zine_interpretation": interpretation,
                            "model_input_fingerprint": model_fingerprint,
                            "raw_anchor_fingerprint": model_fingerprint,
                            "raw_anchor_source_variant_id": variant.id,
                        }
                    )
                    if selected_image_candidate is not None:
                        spec.update(
                            {
                                "selected_image_candidate_id": selected_image_candidate.candidate_id,
                                "raw_anchor_provider": selected_image_candidate.provider,
                                "image_candidate_review": selected_image_candidate.review.model_dump(
                                    mode="json"
                                ),
                            }
                        )
                    composition = self._compose_poster(
                        anchor_path.read_bytes(),
                        poster_path,
                        spec=spec,
                        recipe=recipe,
                        page=page,
                        total=total,
                        font_diagnostics=font_diagnostics,
                    )

                elif action == "cached":
                    source = page_plan.get("final_source")
                    if not isinstance(source, dict):
                        raise NativeSkillError(f"第 {page} 页没有可缓存的完整成品")
                    raw = source.get("raw")
                    final_path = source.get("poster_path")
                    if not isinstance(raw, dict) or not isinstance(final_path, Path):
                        raise NativeSkillError(f"第 {page} 页缓存文件记录损坏")
                    self._copy_raw_anchor(raw, anchor_path)
                    shutil.copy2(final_path, poster_path)
                    self._hydrate_trace(spec, raw.get("spec"), model_fingerprint)
                    stored_recipe = self._stored_visual_recipe(spec)
                    recipe = self._persisted_recipe(spec)
                    composition = self._object_value(spec.get("composition_diagnostics"))
                    composition = {
                        **composition,
                        "cached_final": True,
                        "raw_source_variant_id": raw.get("variant_id"),
                    }
                else:  # recomposed; the preflight guarantees a raw anchor exists.
                    raw = page_plan.get("raw")
                    if not isinstance(raw, dict):
                        raise NativeSkillError(
                            f"第 {page} 页缺少可重合成的原始视觉锚点；最终海报不能代替 raw anchor。"
                        )
                    self._copy_raw_anchor(raw, anchor_path)
                    self._hydrate_trace(spec, raw.get("spec"), model_fingerprint)
                    stored_recipe = self._stored_visual_recipe(spec)
                    recipe = self._persisted_recipe(spec)
                    composition = self._compose_poster(
                        anchor_path.read_bytes(),
                        poster_path,
                        spec=spec,
                        recipe=recipe,
                        page=page,
                        total=total,
                        font_diagnostics=font_diagnostics,
                    )

                if candidate_mode == "production":
                    selected_image_candidate = self.image_candidates.selected_candidate(
                        candidate_lifecycle,
                        page,
                    )
                    if selected_image_candidate is None:
                        adopted = self._adopt_existing_candidate(
                            lifecycle=candidate_lifecycle,
                            metadata=metadata,
                            spec=spec,
                            page=page,
                            anchor_path=anchor_path,
                            output_dir=staging_dir,
                            artifact_paths=stage_paths,
                        )
                        candidate_lifecycle = adopted.lifecycle
                        stage_paths = adopted.artifact_paths
                        selected_image_candidate = adopted.selected_candidate
                    if selected_image_candidate is None or not selected_image_candidate.review.passed:
                        raise NativeSkillError(
                            f"第 {page} 页没有通过视觉审稿的候选，不能进入最终图组"
                        )
                    spec.pop("candidate_review_required", None)
                    spec.update(
                        {
                            "selected_image_candidate_id": selected_image_candidate.candidate_id,
                            "image_candidate_review": selected_image_candidate.review.model_dump(
                                mode="json"
                            ),
                        }
                    )

                spec.update(
                    {
                        "native_zine_recipe": stored_recipe or recipe,
                        "model_input_fingerprint": model_fingerprint,
                        "raw_anchor_fingerprint": model_fingerprint,
                        "final_composition_fingerprint": self._composition_fingerprint(
                            spec, recipe
                        ),
                        "compositor_version": self.compositor_version,
                        "composition_diagnostics": composition,
                        "visual_style": "minimal_zine_native",
                        "text_rendering": "x2red-local-cjk",
                        "model_text_forbidden": True,
                    }
                )
                stage_paths[anchor_key] = str(anchor_path.resolve())
                stage_paths[poster_key] = str(poster_path.resolve())
                recent_recipes.append(json.dumps(recipe, ensure_ascii=False, sort_keys=True))
                diagnostic = {
                    "page": page,
                    "anchor_key": anchor_key,
                    "poster_key": poster_key,
                    "action": action,
                    "raw_source_variant_id": (
                        page_plan.get("raw", {}).get("variant_id")
                        if isinstance(page_plan.get("raw"), dict)
                        else page_plan.get("final_source", {})
                        .get("raw", {})
                        .get("variant_id")
                        if isinstance(page_plan.get("final_source"), dict)
                        else variant.id
                    ),
                    "diagnostics": composition,
                }
                page_diagnostics.append(diagnostic)
                if page in selected_set:
                    page_results.append(
                        {
                            "page": page,
                            "path": str(poster_path.resolve()),
                            "anchor_path": str(anchor_path.resolve()),
                            "anchor_key": anchor_key,
                            "poster_key": poster_key,
                            "action": action,
                            "cached": action == "cached",
                            "recomposed": action == "recomposed",
                            "regenerated": action == "regenerated",
                            "final_prompt": str(spec.get("final_prompt") or ""),
                            "recipe": stored_recipe or recipe,
                            "visual_prompt_spec": spec.get("visual_prompt_spec"),
                            "interpretation": str(
                                spec.get("native_zine_interpretation") or ""
                            ),
                            "diagnostics": composition,
                            "candidate_page": (
                                candidate_lifecycle.pages[str(page)].model_dump(mode="json")
                                if candidate_mode == "production"
                                and str(page) in candidate_lifecycle.pages
                                else {}
                            ),
                        }
                    )

            new_metadata = dict(metadata)
            new_metadata["poster_specs"] = new_specs
            new_metadata["render_engine"] = "gc-minimal-zine-local-compositor-v7"
            new_metadata["visual_prompt_mode"] = feature_mode
            new_metadata["image_candidate_mode"] = candidate_mode
            if candidate_mode == "production":
                new_metadata["image_candidate_lifecycle"] = candidate_lifecycle.model_dump(
                    mode="json"
                )
            new_metadata["native_zine"] = {
                "repository": "https://github.com/LiamGvchi/gc-minimal-zine-poster",
                "commit": self.manager.definition(
                    self.skill_name if feature_mode == "legacy" else V03_SKILL_NAME
                ).commit,
                "license": "MIT",
                "prompt_compiler": COMPILER_VERSION,
                "prompt_compiler_mode": self.prompt_compiler.schema_mode(feature_mode),
                "image_model": self.settings.image_model,
                "image_size_requested": self.settings.image_size,
                "generated_pages": sum(
                    1 for plan in plans if plan["action"] == "regenerated"
                ),
                "compositor_version": self.compositor_version,
                "model_role": "visual-anchor-only",
                "local_typography": True,
                "font": font_diagnostics,
                "artifact_contract": "anchors-and-finals-separate; zip-excludes-anchors",
                "watermark_policy": (
                    "negative prompt, feathered high-risk outer-edge masking, local Chinese type, "
                    "and required human visual review; no watermark-impossibility claim"
                ),
                "image_candidates": {
                    "mode": candidate_mode,
                    "default_count": self.settings.image_candidate_count,
                    "auto_repair_limit": 1,
                    "publish_requires_review_pass": candidate_mode == "production",
                },
            }
            candidate_publish_allowed = (
                candidate_mode != "production"
                or self.image_candidates.publish_allowed(
                    candidate_lifecycle,
                    total_pages=total,
                    artifact_paths=stage_paths,
                )
            )
            stage_paths = self._rebuild_artifacts(
                variant=variant,
                metadata=new_metadata,
                specs=new_specs,
                output_dir=staging_dir,
                output_paths=stage_paths,
                page_diagnostics=page_diagnostics,
                allow_package=candidate_publish_allowed,
            )
            if candidate_publish_allowed:
                self._assert_complete_artifact_set(stage_paths, total, staging_dir)
            else:
                self._assert_rendered_artifact_set(stage_paths, total, staging_dir)

            final_paths = {
                key: str((target_dir / Path(value).name).resolve())
                for key, value in stage_paths.items()
            }
            backup_dir = self._promote_staging(staging_dir, target_dir)
            promoted = True
            variant.metadata_json = json.dumps(new_metadata, ensure_ascii=False)
            variant.output_paths_json = json.dumps(final_paths, ensure_ascii=False)
            variant.status = (
                PlatformVariantState.packaged.value
                if "package" in final_paths
                else PlatformVariantState.rendered.value
            )
            variant.error = ""
            db.flush()
        except Exception as exc:
            if promoted:
                self._restore_promoted_directory(target_dir, backup_dir)
            variant.metadata_json = original_values["metadata_json"]
            variant.output_paths_json = original_values["output_paths_json"]
            variant.status = original_values["status"]
            variant.error = original_values["error"]
            if isinstance(exc, NativeSkillError):
                raise
            detail = _clean(str(exc), 240) or exc.__class__.__name__
            raise NativeSkillError(
                f"轻内容渲染失败，已保留上一版完整成品：{detail}"
            ) from exc
        else:
            if backup_dir is not None and backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)
            # Result paths must point at the promoted stable directory, never its
            # now-removed staging predecessor.
            for result in page_results:
                poster_key = str(result.get("poster_key") or "")
                anchor_key = str(result.get("anchor_key") or "")
                if poster_key and poster_key in final_paths:
                    result["path"] = final_paths[poster_key]
                if anchor_key and anchor_key in final_paths:
                    result["anchor_path"] = final_paths[anchor_key]
            return variant, page_results
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)

    def _plan_pages(
        self,
        *,
        variant: PlatformVariant,
        specs: list[dict[str, Any]],
        current_paths: dict[str, Any],
        parent: PlatformVariant | None,
        parent_specs: list[dict[str, Any]],
        parent_paths: dict[str, Any],
        selected_pages: set[int],
        mode: RenderMode,
        expected_fingerprints: dict[int, str],
        allow_pending_pages: bool = False,
    ) -> list[dict[str, Any]]:
        plans: list[dict[str, Any]] = []
        for page, spec in enumerate(specs, start=1):
            raw = self._raw_candidate(
                variant=variant,
                specs=specs,
                paths=current_paths,
                parent=parent,
                parent_specs=parent_specs,
                parent_paths=parent_paths,
                page=page,
                expected_fingerprint=expected_fingerprints[page],
            )
            current_final = self._final_candidate(
                variant=variant,
                specs=specs,
                paths=current_paths,
                page=page,
                target_spec=spec,
                expected_model_fingerprint=expected_fingerprints[page],
            )
            parent_final = (
                self._final_candidate(
                    variant=parent,
                    specs=parent_specs,
                    paths=parent_paths,
                    page=page,
                    target_spec=spec,
                    expected_model_fingerprint=expected_fingerprints[page],
                )
                if parent is not None
                else None
            )
            selected = page in selected_pages
            if selected and mode == "regenerate":
                plans.append(
                    {"page": page, "selected": True, "action": "regenerated"}
                )
                continue
            if selected and mode == "recompose":
                if raw is None:
                    raise NativeSkillError(
                        f"第 {page} 页缺少原始视觉锚点，无法重合成；最终海报不能作为 raw anchor 使用。"
                    )
                plans.append(
                    {
                        "page": page,
                        "selected": True,
                        "action": "recomposed",
                        "raw": raw,
                    }
                )
                continue
            if selected:  # render_missing
                if current_final is not None:
                    plans.append(
                        {
                            "page": page,
                            "selected": True,
                            "action": "cached",
                            "final_source": current_final,
                        }
                    )
                elif parent_final is not None:
                    plans.append(
                        {
                            "page": page,
                            "selected": True,
                            "action": "cached",
                            "final_source": parent_final,
                        }
                    )
                elif raw is not None:
                    plans.append(
                        {
                            "page": page,
                            "selected": True,
                            "action": "recomposed",
                            "raw": raw,
                        }
                    )
                else:
                    plans.append(
                        {"page": page, "selected": True, "action": "regenerated"}
                    )
                continue

            # Partial operations must carry every unselected page into the new full
            # artifact directory.  Recomposition from an existing raw anchor is
            # allowed; an image-model generation for an unselected page is not.
            if current_final is not None:
                plans.append(
                    {
                        "page": page,
                        "selected": False,
                        "action": "cached",
                        "final_source": current_final,
                    }
                )
            elif parent_final is not None:
                plans.append(
                    {
                        "page": page,
                        "selected": False,
                        "action": "cached",
                        "final_source": parent_final,
                    }
                )
            elif raw is not None:
                plans.append(
                    {
                        "page": page,
                        "selected": False,
                        "action": "recomposed",
                        "raw": raw,
                    }
                )
            else:
                if allow_pending_pages:
                    plans.append(
                        {"page": page, "selected": False, "action": "pending"}
                    )
                else:
                    raise NativeSkillError(
                        f"部分渲染无法组成完整图组：未选中的第 {page} 页没有可保留的 raw anchor 或最终海报。"
                    )
        return plans

    def _raw_candidate(
        self,
        *,
        variant: PlatformVariant,
        specs: list[dict[str, Any]],
        paths: dict[str, Any],
        parent: PlatformVariant | None,
        parent_specs: list[dict[str, Any]],
        parent_paths: dict[str, Any],
        page: int,
        expected_fingerprint: str,
    ) -> dict[str, Any] | None:
        current = self._raw_from_variant(
            variant, specs, paths, page, expected_fingerprint
        )
        if current is not None:
            return current
        if parent is None:
            return None
        return self._raw_from_variant(
            parent, parent_specs, parent_paths, page, expected_fingerprint
        )

    def _raw_from_variant(
        self,
        variant: PlatformVariant,
        specs: list[dict[str, Any]],
        paths: dict[str, Any],
        page: int,
        expected_fingerprint: str,
    ) -> dict[str, Any] | None:
        if page > len(specs):
            return None
        spec = specs[page - 1]
        stored_fingerprint = str(spec.get("raw_anchor_fingerprint") or "")
        current_fingerprint = _model_input_fingerprint(spec)
        legacy_fingerprint = _legacy_model_input_fingerprint(spec)
        fingerprint_matches = stored_fingerprint == expected_fingerprint
        legacy_matches_same_visual = (
            stored_fingerprint == legacy_fingerprint
            and current_fingerprint == expected_fingerprint
        )
        if not fingerprint_matches and not legacy_matches_same_visual:
            return None
        path = self._artifact_path(variant, paths, f"anchor_{page:02d}")
        if path is None or not self._is_parseable_image(path):
            return None
        return {"path": path, "spec": spec, "variant_id": variant.id}

    def _final_candidate(
        self,
        *,
        variant: PlatformVariant | None,
        specs: list[dict[str, Any]],
        paths: dict[str, Any],
        page: int,
        target_spec: dict[str, Any],
        expected_model_fingerprint: str | None = None,
    ) -> dict[str, Any] | None:
        if variant is None or page > len(specs):
            return None
        source_spec = specs[page - 1]
        expected_model = expected_model_fingerprint or _model_input_fingerprint(
            target_spec
        )
        raw = self._raw_from_variant(
            variant, specs, paths, page, expected_model
        )
        if raw is None:
            return None
        poster_path = self._artifact_path(variant, paths, f"poster_{page:02d}")
        if poster_path is None or not self._is_parseable_image(poster_path):
            return None
        expected_composition = self._composition_fingerprint(
            target_spec, self._persisted_recipe(target_spec)
        )
        if str(source_spec.get("final_composition_fingerprint") or "") != expected_composition:
            return None
        if str(source_spec.get("compositor_version") or "") != self.compositor_version:
            return None
        return {"raw": raw, "poster_path": poster_path, "variant_id": variant.id}

    def _compiler_feature_mode(
        self,
        metadata: dict[str, Any],
        specs: list[dict[str, Any]],
    ) -> VisualPromptFeatureMode:
        explicit = str(metadata.get("visual_prompt_mode") or "")
        if explicit in {"legacy", "skill_v03", "production"}:
            return explicit  # type: ignore[return-value]
        if self.settings.minimal_zine_prompt_mode == "legacy":
            return "legacy"
        # Historical packages have raw anchors but no structured compiler trace.
        # Treat those pages as legacy so a rollout cannot invalidate reviewed art.
        if any(
            spec.get("raw_anchor_fingerprint") and not spec.get("visual_prompt_spec")
            for spec in specs
        ):
            return "legacy"
        return self.settings.minimal_zine_prompt_mode

    def _visual_prompt_context(
        self,
        *,
        variant: PlatformVariant,
        metadata: dict[str, Any],
        specs: list[dict[str, Any]],
        page: int,
    ) -> VisualPromptContext:
        spec = specs[page - 1]
        strategy = self._object_value(metadata.get("strategy"))
        controls = _storyboard_controls(spec)
        frozen_brief: PageVisualBrief | None = None
        raw_brief = spec.get("page_visual_brief")
        if isinstance(raw_brief, dict):
            try:
                frozen_brief = PageVisualBrief.model_validate(raw_brief)
            except ValidationError as exc:
                if str(metadata.get("visual_brief_mode") or "") == "production":
                    raise NativeSkillError(
                        f"第 {page} 页冻结视觉简报损坏，拒绝绕过简报编译 Prompt"
                    ) from exc
        if (
            str(metadata.get("visual_brief_mode") or "") == "production"
            and frozen_brief is None
        ):
            raise NativeSkillError(
                f"第 {page} 页缺少冻结 PageVisualBrief，production 不允许回退到自由隐喻"
            )
        article_thesis = _clean(
            spec.get("article_thesis")
            or strategy.get("content_thesis")
            or variant.summary
            or variant.title,
            1200,
        ) or "让当前页面以一个具体视觉关系承接文章判断"
        section_title = _clean(
            spec.get("section_title") or spec.get("phrase") or variant.title,
            300,
        ) or f"第 {page} 页"
        role = _clean(
            frozen_brief.visual_role if frozen_brief else spec.get("page_visual_role"),
            100,
        )
        if not role:
            role = "cover" if page == 1 else "conclusion" if page == len(specs) else "scene"
        evidence = _clean(
            spec.get("evidence_summary") or spec.get("evidence_basis"),
            1200,
        )
        refs = (
            frozen_brief.evidence_refs
            if frozen_brief is not None
            else spec.get("source_refs")
        )
        if isinstance(refs, list) and refs:
            ref_text = "、".join(_clean(value, 120) for value in refs if _clean(value, 120))
            evidence = _clean(f"{evidence}；来源：{ref_text}" if evidence else f"来源：{ref_text}", 1600)
        visual_bible = metadata.get("visual_bible")
        if not isinstance(visual_bible, dict):
            visual_bible = {
                "status": "pre-v2-page-context",
                "content_recipe": str(metadata.get("recipe") or ""),
                "series_style": str(metadata.get("visual_style") or "minimal_zine"),
                "rule": "one visual event per page; local Chinese typography",
            }

        def concept(index: int) -> str:
            if index < 0 or index >= len(specs):
                return ""
            value = specs[index]
            candidate_brief = value.get("page_visual_brief")
            if isinstance(candidate_brief, dict):
                try:
                    parsed = PageVisualBrief.model_validate(candidate_brief)
                except ValidationError:
                    parsed = None
                if parsed is not None:
                    return _clean(
                        "，".join(
                            item
                            for item in (
                                parsed.concrete_subject,
                                parsed.action_or_relation,
                                parsed.setting,
                            )
                            if item
                        ),
                        800,
                    )
            return _clean(
                value.get("current_page_concept")
                or value.get("visual_metaphor")
                or value.get("photo_direction"),
                800,
            )

        current_concept = (
            _clean(
                "，".join(
                    item
                    for item in (
                        frozen_brief.concrete_subject,
                        frozen_brief.action_or_relation,
                        frozen_brief.setting,
                    )
                    if item
                ),
                800,
            )
            if frozen_brief is not None
            else concept(page - 1) or controls["visual_metaphor"]
        )
        main_hue = (
            frozen_brief.palette_delta[0]
            if frozen_brief is not None and frozen_brief.palette_delta
            else controls["accent"]
        )

        return VisualPromptContext(
            variant_id=variant.id,
            page=page,
            total_pages=len(specs),
            article_thesis=article_thesis,
            section_title=section_title,
            page_visual_role=role,
            phrase=_clean(spec.get("phrase"), 160),
            note=_clean(spec.get("note"), 500),
            evidence_summary=evidence,
            audience=_clean(metadata.get("audience"), 500),
            emotion=_clean(
                frozen_brief.reader_emotion
                if frozen_brief is not None
                else spec.get("emotion")
                or strategy.get("emotional_job")
                or controls["mood"],
                300,
            ),
            current_page_concept=current_concept,
            visual_bible=visual_bible,
            page_visual_brief=frozen_brief,
            previous_page_concept=concept(page - 2),
            next_page_concept=concept(page),
            content_recipe=_clean(metadata.get("recipe"), 100),
            source_fit=_clean(strategy.get("source_fit"), 800),
            layout_hint=(
                frozen_brief.layout_family
                if frozen_brief is not None
                else controls["layout"]
            ),
            anchor_hint=controls["anchor"],
            texture_hint=controls["texture"],
            main_hue_hint=main_hue,
            mood_hint=(
                frozen_brief.reader_emotion
                if frozen_brief is not None
                else controls["mood"]
            ),
        )

    def _expected_model_fingerprint(
        self,
        *,
        variant: PlatformVariant,
        metadata: dict[str, Any],
        specs: list[dict[str, Any]],
        page: int,
        feature_mode: VisualPromptFeatureMode,
    ) -> str:
        if feature_mode == "legacy":
            return _model_input_fingerprint(specs[page - 1])
        context = self._visual_prompt_context(
            variant=variant,
            metadata=metadata,
            specs=specs,
            page=page,
        )
        return self.prompt_compiler.source_fingerprint(
            context,
            feature_mode=feature_mode,
        )

    def _compile_visual_prompt_spec(
        self,
        *,
        variant: PlatformVariant,
        metadata: dict[str, Any],
        specs: list[dict[str, Any]],
        page: int,
        feature_mode: VisualPromptFeatureMode,
        force_recompile: bool,
    ) -> VisualPromptSpec:
        spec = specs[page - 1]
        context = self._visual_prompt_context(
            variant=variant,
            metadata=metadata,
            specs=specs,
            page=page,
        )
        expected = self.prompt_compiler.source_fingerprint(
            context,
            feature_mode=feature_mode,
        )
        stored = spec.get("visual_prompt_spec")
        if not force_recompile and isinstance(stored, dict):
            try:
                cached = VisualPromptSpec.model_validate(stored)
            except ValidationError:
                cached = None
            if (
                cached is not None
                and cached.source_fingerprint == expected
                and cached.mode == self.prompt_compiler.schema_mode(feature_mode)
            ):
                return cached

        controls = _storyboard_controls(spec)
        raw_prompt = (
            "Create one sparse, non-literal editorial visual symbol for this idea: "
            f"{controls['visual_metaphor']}. Express it as one {controls['anchor']} "
            f"with a {controls['texture']} material treatment and a {controls['mood']} mood. "
            "Render only the visual object and paper texture; do not render the idea as words."
        )
        legacy_prompt = self._four_paragraph_prompt(
            controls=controls,
            raw_prompt=raw_prompt,
            safe_zone=self._safe_zone(controls["layout"]),
        )
        return self.prompt_compiler.compile(
            context,
            feature_mode=feature_mode,
            fallback_recipe_factory=lambda: self._fallback_visual_recipe(spec),
            legacy_positive_prompt=legacy_prompt,
        )

    def _fallback_visual_recipe(self, spec: dict[str, Any]) -> VisualPromptRecipe:
        fallback = self._recipe_for(spec)
        return VisualPromptRecipe(
            layout_family=fallback["layout"],
            anchor_form=fallback["anchor"],
            typography_mode=fallback["typography"],
            texture_mode=fallback["texture"],
            decorative_system=[],
            main_hue=fallback["accent"],
            mood=fallback["mood"],
        )

    @staticmethod
    def _stored_visual_recipe(spec: dict[str, Any]) -> dict[str, Any]:
        visual_spec = spec.get("visual_prompt_spec")
        if isinstance(visual_spec, dict) and isinstance(visual_spec.get("recipe"), dict):
            return dict(visual_spec["recipe"])
        value = spec.get("native_zine_recipe")
        return dict(value) if isinstance(value, dict) else {}

    def _persisted_recipe(self, spec: dict[str, Any]) -> dict[str, Any]:
        stored = self._stored_visual_recipe(spec)
        if stored:
            return self._composer_recipe(stored)
        # The deterministic page controls are the documented degraded/legacy fallback.
        return self._recipe_for(spec)

    @staticmethod
    def _composer_recipe(
        recipe: VisualPromptRecipe | dict[str, Any],
    ) -> dict[str, Any]:
        value = recipe.model_dump(mode="json") if isinstance(recipe, VisualPromptRecipe) else recipe
        return {
            "layout": str(value.get("layout_family") or value.get("layout") or "center-fragment"),
            "anchor": str(value.get("anchor_form") or value.get("anchor") or "object-specimen"),
            "typography": str(
                value.get("typography_mode") or value.get("typography") or "local-cjk"
            ),
            "accent": str(value.get("main_hue") or value.get("accent") or "cobalt"),
            "texture": str(
                value.get("texture_mode") or value.get("texture") or "xerox-softness"
            ),
            "mood": str(value.get("mood") or "quiet"),
            "decorative_system": list(value.get("decorative_system") or []),
        }

    @staticmethod
    def _visual_interpretation(
        visual_spec: VisualPromptSpec,
        spec: dict[str, Any],
    ) -> str:
        warning = next(
            (value for value in visual_spec.warnings if value.startswith(DEGRADED_FALLBACK)),
            "",
        )
        base = _clean(spec.get("visual_metaphor"), 220)
        return _clean(f"{base}。{warning}" if warning else base, 320)

    @staticmethod
    def _prompt_diff(previous: str, current: str) -> dict[str, Any]:
        if not previous:
            return {"changed": False, "before": "", "after": current, "unified": ""}
        changed = previous != current
        unified = "\n".join(
            difflib.unified_diff(
                previous.splitlines(),
                current.splitlines(),
                fromfile="previous-prompt",
                tofile="compiled-prompt",
                lineterm="",
            )
        )
        return {
            "changed": changed,
            "before": previous,
            "after": current,
            "unified": unified[:12_000],
        }

    def _compile_prompt(
        self,
        *,
        skill_text: str,
        variant: PlatformVariant,
        spec: dict[str, Any],
        page: int,
        total: int,
        recent_recipes: list[str],
    ) -> dict[str, Any]:
        controls = _storyboard_controls(spec)
        safe_zone = self._safe_zone(controls["layout"])
        prompt = f"""
按照下面完整的上游 SKILL.md，以 Standard Mode Prompt Compiler 为基础，为一张 Minimal Zine 的“无字视觉锚点”编译配方。
不要省略其四段 Prompt 结构、Variation Engine 或 Standard Color Engine；但图片模型绝不负责任何文字，中文将由 X2RED 本地合成。

上游 SKILL.md（完整内容）：
{skill_text}

本页已由人工冻结的视觉合同：
- 页码：{page}/{total}
- 单一视觉隐喻：{controls['visual_metaphor']}
- layout：{controls['layout']}
- anchor：{controls['anchor']}
- accent：{controls['accent']}
- texture：{controls['texture']}
- mood：{controls['mood']}
- 需要留给本地中文的安全区：{safe_zone['prompt']}
- 最近页面已使用配方：{json.dumps(recent_recipes[-3:], ensure_ascii=False)}

严格规则：
1. 视觉必须保留完整 3:5 旧纸海报、70%-90% 感知纸张、8%-25% 小视觉簇；不要全幅场景、边缘贴靠或厚框。
2. 只生成一个有可见缩略图辨识度的高饱和强调色，约占全画布 0.8%-2.5%，其余纸张和灰阶照片可低对比，但不得全局低饱和或抹掉强调色。
3. 图像中禁止任何中文、英文、数字、字母、Logo、水印、签名、角标、徽章、UI、按钮、标签和可读文字。不要生成字体或微文本；本地合成器会处理中文。
4. 不要商业广告、产品海报、3D、霓虹、电影光、可爱卡通、密集拼贴、通用图库感或干净 UI 背景。
5. recipe 必须复述上面的冻结合同；不得替换 layout、anchor、accent、texture、mood。typography 只能为 local-cjk。

只输出 JSON：
{{
  "final_prompt":"英文视觉描述，可包含物件处理细节，但不得要求模型绘制文字",
  "recipe":{{"layout":"","anchor":"","typography":"local-cjk","accent":"","texture":"","mood":""}},
  "interpretation":"一句说明这个视觉隐喻"
}}
""".strip()
        try:
            result = self.model.chat_json(
                system_prompt=(
                    "你执行 gc-minimal-zine-poster-v0-1 的视觉配方编译。"
                    "模型只生成无字视觉锚点；最终中文由本地 CJK 排版器完成。"
                ),
                user_prompt=prompt,
                temperature=0.36,
                reasoning_effort="high",
                max_tokens=5000,
            )
        except ModelClientError as exc:
            raise NativeSkillError(str(exc)) from exc
        raw_prompt = _clean(result.get("final_prompt"), 2400)
        if len(raw_prompt) < 40:
            raise NativeSkillError("Minimal Zine 视觉 Prompt 编译结果过短")
        recipe = self._recipe_for(spec)
        interpretation = _clean(result.get("interpretation"), 320)
        final_prompt = self._four_paragraph_prompt(
            controls=controls,
            raw_prompt=raw_prompt,
            safe_zone=safe_zone,
        )
        return {
            "final_prompt": final_prompt,
            "recipe": recipe,
            "interpretation": interpretation,
        }

    def _four_paragraph_prompt(
        self,
        visual_spec: VisualPromptSpec | None = None,
        *,
        controls: dict[str, Any] | None = None,
        raw_prompt: str = "",
        safe_zone: dict[str, Any] | None = None,
    ) -> str:
        if visual_spec is not None:
            positive = visual_spec.positive_prompt.strip()
            if visual_spec.mode != "production_text_safe":
                return positive
            text_exclusions = [
                value
                for value in visual_spec.exclusions
                if any(
                    token in value.lower()
                    for token in (
                        "text",
                        "chinese",
                        "latin",
                        "letter",
                        "number",
                        "logo",
                        "watermark",
                        "signature",
                        "ui",
                    )
                )
            ][:4]
            suffix = (
                "Production text-safety invariant — NO TEXT: render no readable Chinese, Latin letters, "
                "numbers, logos, signatures, watermarks, badges or UI; keep the selected visual "
                "theme, layout, anchor, texture and hue unchanged because X2RED composes final "
                "Chinese locally. X2RED adds Chinese locally after generation."
            )
            if text_exclusions:
                suffix += " Compact text exclusions: " + "; ".join(text_exclusions) + "."
            return positive.rstrip() + "\n" + suffix

        if controls is None or safe_zone is None:
            raise NativeSkillError("Legacy Prompt 编译参数不完整")
        accent = controls["accent"]
        accent_word = accent if not accent.startswith("#") else f"opaque {accent} ink"
        return "\n\n".join(
            [
                (
                    "Tall vertical 3:5 full-frame aged-paper editorial plate, no border and no mockup; "
                    "70%-90% perceived quiet paper, one sparse 8%-25% visual cluster positioned as "
                    f"{controls['layout']}, with {safe_zone['prompt']} for local type. Keep that zone as the same "
                    "continuous paper surface: no panel, frame, card, cream box, caption plate or hard-edged overlay."
                ),
                (
                    f"One {controls['anchor']} interprets {controls['visual_metaphor']}; "
                    f"treat it with {controls['texture']} and restrained old-print material process. "
                    f"Use this imageable detail only as visual guidance: {raw_prompt}."
                ),
                (
                    "No model typography: X2RED adds Chinese locally after generation. "
                    f"Use one fully saturated {accent_word} as the clear high-chroma anchor, about "
                    "0.8%-2.5% of the full canvas, never washed out; paper and grayscale support remain subdued. "
                    "NO TEXT, NO CHINESE CHARACTERS, NO LATIN LETTERS, NO NUMBERS, NO LOGO, "
                    "NO WATERMARK, NO SIGNATURE, NO BADGE, NO UI, NO LABEL."
                ),
                (
                    f"Flat orthographic scanned-paper mood: {controls['mood']}, diffuse light, matte absorbent paper, "
                    "low-to-medium contrast and no 3D depth. Avoid full-bleed scenes, commercial hierarchy, product ads, "
                    "CTA, glossy mockups, cinematic lighting, neon, cute cartoon, fashion drama, dense scrapbook, "
                    "many colors and readable generated text."
                ),
            ]
        )

    def _compose_poster(
        self,
        image_bytes: bytes,
        path: Path,
        *,
        spec: dict[str, Any],
        recipe: dict[str, Any],
        page: int,
        total: int,
        font_diagnostics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Compose local Chinese without redesigning the supplied visual anchor."""

        try:
            with Image.open(io.BytesIO(image_bytes)) as source:
                source = ImageOps.exif_transpose(source).convert("RGB")
                focus_x = self._focus_value(spec.get("focus_x"), 0.5)
                focus_y = self._focus_value(spec.get("focus_y"), 0.5)
                zoom = self._zoom_value(spec.get("zoom"))
                focused = self._focused_crop(source, focus_x, focus_y, zoom)
                target_size = (
                    self.local_renderer.width,
                    self.local_renderer.height,
                )
                if zoom < 1.0:
                    target_size = (
                        max(1, int(target_size[0] * zoom)),
                        max(1, int(target_size[1] * zoom)),
                    )
                contained = ImageOps.contain(
                    focused,
                    target_size,
                    method=Image.Resampling.LANCZOS,
                )
                paper_rgb = self._sample_paper_color(source)
                paper_hex = "#{:02x}{:02x}{:02x}".format(*paper_rgb)
                visual = self.local_renderer._paper(paper_hex, noise=7, blend=0.018)
                offset = (
                    (self.local_renderer.width - contained.width) // 2,
                    (self.local_renderer.height - contained.height) // 2,
                )
                visual.paste(contained, offset)
        except (OSError, ValueError) as exc:
            raise NativeSkillError("图片模型返回的 raw anchor 无法解析") from exc

        layout = _canonical_layout(recipe.get("layout") or spec.get("layout"))
        safe_zone = self._safe_zone(layout)
        color_signal = self._color_signal(visual)
        high_chroma_ratio = color_signal["high_chroma_ratio"]
        muted_chroma_ratio = color_signal["muted_chroma_ratio"]
        paper_layer = self.local_renderer._paper(paper_hex, noise=7, blend=0.018)
        edge_bands = {"left": 36, "top": 48, "right": 36, "bottom": 72}
        edge_mask = self._edge_cleanup_mask(
            visual.size,
            bands=edge_bands,
            feather=26,
        )
        plate_box = (
            offset[0],
            offset[1],
            offset[0] + contained.width,
            offset[1] + contained.height,
        )
        badge_mask, badge_regions = self._suspicious_edge_badge_mask(
            visual,
            plate_box=plate_box,
        )
        edge_mask = ImageChops.lighter(edge_mask, badge_mask)
        canvas = Image.composite(paper_layer, visual, edge_mask)

        if high_chroma_ratio >= self.high_chroma_threshold:
            accent_reason = "upstream-high-chroma"
        elif muted_chroma_ratio >= self.muted_chroma_threshold:
            accent_reason = "upstream-muted-accent"
        else:
            accent_reason = "disabled-no-fabricated-mark"

        phrase = _clean(spec.get("phrase"), 80)
        note = _clean(spec.get("note"), 180)
        typography_diagnostics: dict[str, Any] = {}
        typography_recipe: dict[str, Any] = {}
        if self.settings.typography_recipe_mode == "legacy":
            veil_mask = self._soft_panel_mask(
                canvas.size,
                tuple(safe_zone["panel"]),
                opacity=92,
                feather=52,
            )
            canvas = Image.composite(paper_layer, canvas, veil_mask)
            draw = ImageDraw.Draw(canvas)
            text_x, text_y, text_width = safe_zone["text"]
            note_font = self.local_renderer._font(30, serif=True)
            note_lines = self._balanced_wrap(
                draw,
                note,
                note_font,
                text_width,
                max_lines=3,
                min_last_chars=3,
            )
            title_size = int(safe_zone["title_size"])
            title_font = self.local_renderer._font(title_size, bold=True, serif=False)
            title_lines: list[str] = []
            max_title_lines = 4 if text_width >= 520 else 5
            available_height = max(180, safe_zone["panel"][3] - text_y - 92)
            for candidate_size in range(title_size, 39, -2):
                candidate_font = self.local_renderer._font(
                    candidate_size,
                    bold=True,
                    serif=False,
                )
                candidate_lines = self._balanced_wrap(
                    draw,
                    phrase,
                    candidate_font,
                    text_width,
                    max_lines=max_title_lines,
                    min_last_chars=4,
                )
                candidate_height = len(candidate_lines) * int(candidate_size * 1.28)
                if note_lines:
                    candidate_height += 30 + len(note_lines) * 44
                if candidate_lines and candidate_height <= available_height:
                    title_size = candidate_size
                    title_font = candidate_font
                    title_lines = candidate_lines
                    break
            if phrase and not title_lines:
                title_lines = self.local_renderer._wrap(
                    draw,
                    phrase,
                    title_font,
                    text_width,
                )[:max_title_lines]
            line_height = int(title_size * 1.32)
            for line_index, line in enumerate(title_lines):
                draw.text(
                    (text_x, text_y + line_index * line_height),
                    line,
                    font=title_font,
                    fill="#171614",
                )
            note_y = text_y + len(title_lines) * line_height + 30
            for line_index, line in enumerate(note_lines):
                draw.text(
                    (text_x, note_y + line_index * 44),
                    line,
                    font=note_font,
                    fill="#514c45",
                )
            footer_font = self.local_renderer._font(20, serif=True)
            footer_y = self.local_renderer.height - 76
            page_text = f"{page:02d} / {total:02d}"
            page_width = draw.textlength(page_text, font=footer_font)
            draw.text(
                (self.local_renderer.width - 84 - page_width, footer_y),
                page_text,
                font=footer_font,
                fill="#625d54",
            )
            text_safe_treatment = "feathered-paper-veil"
        else:
            brief = spec.get("page_visual_brief")
            brief = brief if isinstance(brief, dict) else {}
            requested_typography = str(
                brief.get("typography_mode")
                or recipe.get("typography")
                or "local-cjk-editorial"
            )
            protected_regions = [self._principal_subject_region(layout)]
            selection = self.local_renderer.typography_recipes.select(
                size=canvas.size,
                phrase=phrase,
                note=note,
                page=page,
                total=total,
                layout=layout,
                visual_role=str(brief.get("visual_role") or spec.get("visual_role") or ""),
                requested_mode=requested_typography,
                protected_regions=protected_regions,
                stored_recipe=(
                    spec.get("typography_recipe_v2")
                    if isinstance(spec.get("typography_recipe_v2"), dict)
                    else None
                ),
            )
            try:
                canvas, rendered_typography = self.local_renderer.render_typography(
                    canvas,
                    selection=selection,
                    phrase=phrase,
                    note=note,
                    folio=f"{page:02d} / {total:02d}",
                    label=f"PAGE {page:02d} · LOCAL CJK",
                    paper=paper_hex,
                    accent=self._accent(str(recipe.get("accent") or "cobalt")),
                )
            except ValueError as exc:
                raise NativeSkillError(f"本地中文排版失败：{exc}") from exc
            typography_recipe = selection.recipe.model_dump(mode="json")
            typography_diagnostics = rendered_typography.model_dump(mode="json")
            spec["typography_recipe_v2"] = typography_recipe
            title_regions = [
                item
                for item in rendered_typography.regions
                if item.role in {"title", "fragment"} and item.lines
            ]
            title_lines = [line for item in title_regions for line in item.lines]
            title_size = max((item.font_size for item in title_regions), default=0)
            text_safe_treatment = "typography-recipe-regions"
        canvas.save(path, "PNG", optimize=True)
        return {
            "edge_crop": {"left": 0.0, "top": 0.0, "right": 0.0, "bottom": 0.0},
            "edge_cleanup": {
                "mode": "feathered-paper-mask",
                "bands_px": edge_bands,
                "feather_px": 26,
                "badge_regions": badge_regions,
            },
            "focus": {"x": focus_x, "y": focus_y, "zoom": zoom},
            "layout": layout,
            "safe_zone": safe_zone["id"],
            "source_plate_size": {"width": contained.width, "height": contained.height},
            "source_plate_offset": {"x": offset[0], "y": offset[1]},
            "source_aspect_preserved": True,
            "sampled_paper_color": paper_hex,
            "text_safe_zone_treatment": text_safe_treatment,
            "title_lines": title_lines,
            "title_size": title_size,
            "title_last_line_chars": len(re.sub(r"\W", "", title_lines[-1])) if title_lines else 0,
            "typography_recipe_mode": self.settings.typography_recipe_mode,
            "typography_recipe": typography_recipe,
            "typography": typography_diagnostics,
            "preserved_model_color": True,
            "model_text_mitigation": "feather-high-risk-outer-edge-and-local-type",
            "high_chroma_ratio": round(high_chroma_ratio, 5),
            "high_chroma_threshold": self.high_chroma_threshold,
            "muted_chroma_ratio": round(muted_chroma_ratio, 5),
            "muted_chroma_threshold": self.muted_chroma_threshold,
            "muted_chroma_saturation": self.muted_chroma_saturation,
            "local_accent_added": False,
            "local_accent_target_share": 0.0,
            "local_accent_actual_share": 0.0,
            "local_accent_max_share": self.local_accent_max_share,
            "local_accent_shape": None,
            "local_accent_placement": None,
            "local_accent_bbox": None,
            "local_accent_outside_text_safe_zone": True,
            "local_accent_outside_principal_cluster": True,
            "local_accent_reason": accent_reason,
            "font": (font_diagnostics or self.local_renderer.cjk_font_diagnostics()).get("selected"),
        }

    @staticmethod
    def _sample_paper_color(image: Image.Image) -> tuple[int, int, int]:
        sampled = ImageOps.contain(image.convert("RGB"), (64, 96))
        width, height = sampled.size
        band_x = max(2, width // 8)
        band_y = max(2, height // 12)
        pixels: list[tuple[int, int, int]] = []
        for y in range(height):
            for x in range(width):
                if x < band_x or x >= width - band_x or y < band_y or y >= height - band_y:
                    pixels.append(sampled.getpixel((x, y)))
        if not pixels:
            return (232, 221, 200)

        def median(channel: int) -> int:
            values = sorted(pixel[channel] for pixel in pixels)
            return int(values[len(values) // 2])

        return median(0), median(1), median(2)

    @staticmethod
    def _edge_cleanup_mask(
        size: tuple[int, int],
        *,
        bands: dict[str, int],
        feather: int,
    ) -> Image.Image:
        width, height = size
        mask = Image.new("L", size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rectangle((0, 0, bands["left"], height), fill=255)
        draw.rectangle((width - bands["right"], 0, width, height), fill=255)
        draw.rectangle((0, 0, width, bands["top"]), fill=255)
        draw.rectangle((0, height - bands["bottom"], width, height), fill=255)
        return mask.filter(ImageFilter.GaussianBlur(radius=max(1, feather)))

    @staticmethod
    def _suspicious_edge_badge_mask(
        image: Image.Image,
        *,
        plate_box: tuple[int, int, int, int],
    ) -> tuple[Image.Image, list[dict[str, Any]]]:
        """Mask large saturated corner components without cropping the source plate."""

        width, height = image.size
        hsv = image.convert("HSV")
        saturation = hsv.getchannel("S").point([0] * 150 + [255] * 106)
        value = hsv.getchannel("V").point([0] * 90 + [255] * 166)
        high_chroma = ImageChops.multiply(saturation, value)
        plate_left, plate_top, plate_right, plate_bottom = plate_box
        corner_width = int(width * 0.42)
        corner_height = int(height * 0.32)
        proximity = max(72, int(min(width, height) * 0.06))
        minimum_pixels = max(1200, int(width * height * 0.002))
        corners = (
            ("top-left", (0, 0, corner_width, corner_height), "left", "top"),
            ("top-right", (width - corner_width, 0, width, corner_height), "right", "top"),
            ("bottom-left", (0, height - corner_height, corner_width, height), "left", "bottom"),
            (
                "bottom-right",
                (width - corner_width, height - corner_height, width, height),
                "right",
                "bottom",
            ),
        )
        cleanup = Image.new("L", image.size, 0)
        regions: list[dict[str, Any]] = []
        for corner, risk_box, horizontal_edge, vertical_edge in corners:
            risk = Image.new("L", image.size, 0)
            ImageDraw.Draw(risk).rectangle(risk_box, fill=255)
            candidate = ImageChops.multiply(high_chroma, risk)
            bbox = candidate.getbbox()
            if bbox is None or candidate.histogram()[255] < minimum_pixels:
                continue
            near_horizontal = (
                bbox[0] - plate_left <= proximity
                if horizontal_edge == "left"
                else plate_right - bbox[2] <= proximity
            )
            near_vertical = (
                bbox[1] - plate_top <= proximity
                if vertical_edge == "top"
                else plate_bottom - bbox[3] <= proximity
            )
            if not (near_horizontal and near_vertical):
                continue
            padding = 20
            expanded = (
                max(0, bbox[0] - padding),
                max(0, bbox[1] - padding),
                min(width, bbox[2] + padding),
                min(height, bbox[3] + padding),
            )
            hard = Image.new("L", image.size, 0)
            ImageDraw.Draw(hard).rounded_rectangle(expanded, radius=24, fill=255)
            cleanup = ImageChops.lighter(
                cleanup,
                ImageChops.lighter(hard, hard.filter(ImageFilter.GaussianBlur(radius=18))),
            )
            regions.append(
                {
                    "corner": corner,
                    "left": expanded[0],
                    "top": expanded[1],
                    "right": expanded[2],
                    "bottom": expanded[3],
                }
            )
        return cleanup, regions

    @staticmethod
    def _soft_panel_mask(
        size: tuple[int, int],
        panel: tuple[int, int, int, int],
        *,
        opacity: int,
        feather: int,
    ) -> Image.Image:
        mask = Image.new("L", size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle(panel, radius=30, fill=min(255, max(0, opacity)))
        return mask.filter(ImageFilter.GaussianBlur(radius=max(1, feather)))

    def _balanced_wrap(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: Any,
        max_width: int,
        *,
        max_lines: int,
        min_last_chars: int,
    ) -> list[str]:
        content = _clean(text, 240)
        if not content:
            return []
        closing = "，。！？、；：）】》」』…,.!?;:)]}"
        opening = "（【《「『([{"
        weak_starters = "的了得着过后前时里上下来也而且与和或"

        def visible_length(value: str) -> int:
            return len(re.sub(r"[\s，。！？、；：,.!?;:（）【】《》「」『』…]", "", value))

        minimum_last = min(min_last_chars, max(1, visible_length(content)))
        total_visible = visible_length(content)
        length = len(content)
        for line_count in range(1, max_lines + 1):
            balanced_last = max(
                minimum_last,
                math.ceil((total_visible / line_count) * 0.75),
            )

            @cache
            def solve(
                start: int,
                remaining: int,
                last_line_minimum: int = balanced_last,
            ) -> tuple[float, tuple[str, ...]] | None:
                if remaining == 1:
                    segment = content[start:].strip()
                    if not segment or draw.textlength(segment, font=font) > max_width:
                        return None
                    if (
                        segment[0] in closing
                        or segment[0] in weak_starters
                        or visible_length(segment) < last_line_minimum
                    ):
                        return None
                    return 0.0, (segment,)
                best: tuple[float, tuple[str, ...]] | None = None
                max_end = length - (remaining - 1)
                for end in range(start + 1, max_end + 1):
                    segment = content[start:end].strip()
                    if not segment:
                        continue
                    width = float(draw.textlength(segment, font=font))
                    if width > max_width:
                        break
                    if (
                        segment[0] in closing
                        or segment[0] in weak_starters
                        or segment[-1] in opening
                    ):
                        continue
                    tail = solve(end, remaining - 1)
                    if tail is None:
                        continue
                    fill = width / max(max_width, 1)
                    score = (1.0 - fill) ** 2 + tail[0]
                    if segment[-1] in "，。！？；：,.!?;:":
                        score -= 0.08
                    candidate = (score, (segment, *tail[1]))
                    if best is None or candidate[0] < best[0]:
                        best = candidate
                return best

            result = solve(0, line_count)
            if result is not None:
                return list(result[1])
        return self.local_renderer._wrap(draw, content, font, max_width)[:max_lines]

    def _principal_subject_region(self, layout: str) -> tuple[int, int, int, int]:
        """Conservative key-subject estimate used only by local type collision checks."""

        regions = {
            "center-fragment": (220, 250, 980, 1050),
            "lower-fragment": (200, 1050, 1000, 1750),
            "lower-left-float": (90, 720, 650, 1580),
            "upper-right-block": (610, 120, 1130, 1050),
            "dual-panel": (800, 300, 1130, 1350),
            "irregular-cutout": (100, 260, 690, 1160),
            "type-led": (180, 100, 1040, 560),
            "dot-orbit": (250, 300, 950, 1180),
            "single-specimen": (120, 250, 650, 1100),
            "diagonal-notes": (420, 800, 780, 1000),
            "edge-counterweight": (100, 350, 560, 1300),
        }
        return regions.get(layout, regions["center-fragment"])

    def _safe_zone(self, layout: str) -> dict[str, Any]:
        layouts: dict[str, dict[str, Any]] = {
            "center-fragment": {
                "id": "bottom-wide",
                "panel": (72, 1260, 1128, 1872),
                "text": (112, 1320, 960),
                "title_size": 62,
                "prompt": "the bottom 30 percent blank as one clean continuous paper zone",
            },
            "lower-fragment": {
                "id": "top-wide",
                "panel": (72, 100, 1128, 650),
                "text": (112, 170, 960),
                "title_size": 62,
                "prompt": "a quiet upper paper zone spanning roughly the top 28 percent",
            },
            "lower-left-float": {
                "id": "upper-right-column",
                "panel": (650, 180, 1130, 1020),
                "text": (704, 270, 360),
                "title_size": 54,
                "prompt": "a quiet upper-right vertical paper zone for local Chinese",
            },
            "upper-right-block": {
                "id": "lower-left-block",
                "panel": (70, 1220, 860, 1850),
                "text": (112, 1300, 680),
                "title_size": 60,
                "prompt": "a clean lower-left paper block for local Chinese",
            },
            "dual-panel": {
                "id": "bottom-centered",
                "panel": (140, 1370, 1060, 1850),
                "text": (190, 1430, 810),
                "title_size": 56,
                "prompt": "a clean lower-center paper band for local Chinese",
            },
            "irregular-cutout": {
                "id": "lower-right-column",
                "panel": (550, 1160, 1130, 1840),
                "text": (604, 1230, 460),
                "title_size": 54,
                "prompt": "a clean lower-right paper column for local Chinese",
            },
            "type-led": {
                "id": "central-type-field",
                "panel": (80, 560, 1120, 1500),
                "text": (130, 660, 940),
                "title_size": 72,
                "prompt": "a large central clean paper field where local Chinese is the type-led anchor",
            },
            "dot-orbit": {
                "id": "lower-orbit-caption",
                "panel": (125, 1290, 1075, 1835),
                "text": (180, 1360, 840),
                "title_size": 58,
                "prompt": "a quiet lower paper caption field outside the dot orbit",
            },
            "single-specimen": {
                "id": "lower-right-specimen-label",
                "panel": (620, 1100, 1130, 1840),
                "text": (670, 1180, 400),
                "title_size": 52,
                "prompt": "a clean lower-right specimen-label paper zone for local Chinese",
            },
            "diagonal-notes": {
                "id": "upper-right-diagonal-counterfield",
                "panel": (620, 150, 1130, 1080),
                "text": (670, 250, 400),
                "title_size": 52,
                "prompt": "a continuous upper-right paper counterfield beside the diagonal visual rhythm",
            },
            "edge-counterweight": {
                "id": "lower-right-edge-counterfield",
                "panel": (520, 1120, 1130, 1840),
                "text": (580, 1200, 490),
                "title_size": 54,
                "prompt": "a clean lower-right paper field counterbalancing the edge visual event",
            },
        }
        return dict(layouts.get(layout, layouts["center-fragment"]))

    def _draw_local_accent(
        self,
        draw: ImageDraw.ImageDraw,
        *,
        layout: str,
        anchor: str,
        color: str,
        share: float,
        safe_zone: dict[str, Any],
    ) -> dict[str, Any]:
        """Draw a bounded local registration mark outside art and type fields.

        It deliberately avoids an ellipse/circle in the model's focal cluster.  The
        layout map gives every recipe a quiet margin slot; the defensive overlap
        checks make a later slot edit fail closed instead of covering local Chinese
        or the recipe's principal visual region.
        """

        canvas_area = self.local_renderer.width * self.local_renderer.height
        budget = min(max(float(share), 0.0), self.local_accent_max_share)
        unit = max(18, min(44, int((canvas_area * budget * 0.28) ** 0.5)))
        origin, placement, principal_cluster = self._local_accent_slot(layout)
        x, y = origin
        rule_length = max(32, int(unit * 1.45))
        rule_height = max(4, unit // 7)
        stamp = max(14, unit // 2)
        if anchor == "solid-color-block":
            parts = [(x, y, unit, unit), (x + unit + 9, y + unit - rule_height, rule_length, rule_height)]
            shape = "registration-block"
        elif anchor in {"flat-silhouette", "torn-paper-clipping"}:
            parts = [
                (x, y, rule_length, rule_height),
                (x + 9, y + unit // 3, rule_length - 10, rule_height),
                (x + 18, y + (unit * 2) // 3, rule_length - 20, rule_height),
            ]
            shape = "registration-stair"
        else:
            parts = [(x, y, stamp, stamp), (x + stamp + 9, y + stamp - rule_height, rule_length, rule_height)]
            shape = "registration-stamp"

        bbox = self._parts_bbox(parts)
        outside_text_safe_zone = not self._rectangles_overlap(
            bbox, tuple(safe_zone["panel"])
        )
        outside_principal_cluster = not self._rectangles_overlap(
            bbox, principal_cluster
        )
        if not outside_text_safe_zone or not outside_principal_cluster:
            raise NativeSkillError("本地强调色标记位置不能覆盖文字安全区或主视觉簇")
        if bbox[0] < 72 or bbox[2] > self.local_renderer.width - 72:
            raise NativeSkillError("本地强调色标记必须留在清理后的外侧边界内")

        actual_area = 0
        for part_x, part_y, width, height in parts:
            draw.rectangle(
                (part_x, part_y, part_x + width - 1, part_y + height - 1),
                fill=color,
            )
            actual_area += width * height
        return {
            "actual_share": actual_area / canvas_area,
            "shape": shape,
            "placement": placement,
            "bbox": {
                "x": bbox[0],
                "y": bbox[1],
                "width": bbox[2] - bbox[0],
                "height": bbox[3] - bbox[1],
            },
            "outside_text_safe_zone": outside_text_safe_zone,
            "outside_principal_cluster": outside_principal_cluster,
        }

    @staticmethod
    def _local_accent_slot(
        layout: str,
    ) -> tuple[tuple[int, int], str, tuple[int, int, int, int]]:
        slots = {
            "center-fragment": ((96, 1120), "left-lower-margin", (160, 240, 1040, 1080)),
            "lower-fragment": ((1010, 760), "right-upper-margin", (150, 720, 1050, 1500)),
            "lower-left-float": ((1010, 1090), "right-lower-margin", (96, 620, 620, 1460)),
            "upper-right-block": ((96, 1080), "left-lower-margin", (620, 120, 1120, 1040)),
            "dual-panel": ((96, 1240), "left-lower-margin", (220, 320, 980, 1180)),
            "irregular-cutout": ((980, 1050), "right-upper-margin", (96, 220, 680, 1120)),
            "type-led": ((96, 60), "left-upper-margin", (180, 120, 1020, 520)),
            "dot-orbit": ((1010, 1240), "right-lower-margin", (180, 300, 1020, 1220)),
            "single-specimen": ((1010, 1000), "right-upper-margin", (120, 220, 660, 1120)),
            "diagonal-notes": ((96, 1120), "left-lower-margin", (120, 220, 720, 1120)),
            "edge-counterweight": ((1010, 900), "right-edge-margin", (80, 180, 500, 1300)),
        }
        return slots.get(layout, slots["center-fragment"])

    @staticmethod
    def _parts_bbox(parts: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
        return (
            min(x for x, _, _, _ in parts),
            min(y for _, y, _, _ in parts),
            max(x + width for x, _, width, _ in parts),
            max(y + height for _, y, _, height in parts),
        )

    @staticmethod
    def _rectangles_overlap(
        first: tuple[int, int, int, int],
        second: tuple[int, int, int, int],
    ) -> bool:
        return not (
            first[2] <= second[0]
            or second[2] <= first[0]
            or first[3] <= second[1]
            or second[3] <= first[1]
        )

    @staticmethod
    def _high_chroma_ratio(image: Image.Image) -> float:
        return MinimalZineNativeService._color_signal(image)["high_chroma_ratio"]

    @classmethod
    def _color_signal(cls, image: Image.Image) -> dict[str, float]:
        # The previous 120×200 resample could erase a small, intentional faded
        # accent at its edges.  A larger area-preserving sample retains such marks
        # without mistaking warm paper grain for color.
        sampled = image.resize((240, 400), Image.Resampling.BOX).convert("HSV")
        total = sampled.width * sampled.height
        high_chroma = 0
        muted_chroma = 0
        for _, saturation, value in sampled.get_flattened_data():
            if saturation >= 150 and value >= 90:
                high_chroma += 1
            if saturation >= cls.muted_chroma_saturation and value >= 70:
                muted_chroma += 1
        return {
            "high_chroma_ratio": high_chroma / max(total, 1),
            "muted_chroma_ratio": muted_chroma / max(total, 1),
        }

    @staticmethod
    def _focused_crop(
        image: Image.Image,
        focus_x: float,
        focus_y: float,
        zoom: float,
    ) -> Image.Image:
        if zoom <= 1.0:
            return image
        width, height = image.size
        crop_width = max(1, int(width / zoom))
        crop_height = max(1, int(height / zoom))
        center_x = int(width * focus_x)
        center_y = int(height * focus_y)
        left = min(max(0, center_x - crop_width // 2), width - crop_width)
        top = min(max(0, center_y - crop_height // 2), height - crop_height)
        return image.crop((left, top, left + crop_width, top + crop_height))

    @staticmethod
    def _focus_value(value: Any, fallback: float) -> float:
        try:
            return min(1.0, max(0.0, float(value)))
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _zoom_value(value: Any) -> float:
        try:
            return min(2.0, max(0.65, float(value)))
        except (TypeError, ValueError):
            return 1.0

    def _recipe_for(self, spec: dict[str, Any]) -> dict[str, str]:
        controls = _storyboard_controls(spec)
        return {
            "layout": controls["layout"],
            "anchor": controls["anchor"],
            "typography": "local-cjk",
            "accent": controls["accent"],
            "texture": controls["texture"],
            "mood": controls["mood"],
        }

    def _composition_fingerprint(
        self,
        spec: dict[str, Any],
        recipe: dict[str, Any],
    ) -> str:
        payload = {
            "model": _storyboard_controls(spec),
            "phrase": _clean(spec.get("phrase"), 80),
            "note": _clean(spec.get("note"), 180),
            "focus_x": self._focus_value(spec.get("focus_x"), 0.5),
            "focus_y": self._focus_value(spec.get("focus_y"), 0.5),
            "zoom": self._zoom_value(spec.get("zoom")),
            "recipe": recipe,
            "typography_recipe_v2": (
                spec.get("typography_recipe_v2")
                if isinstance(spec.get("typography_recipe_v2"), dict)
                else {}
            ),
            "compositor_version": self.compositor_version,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _hydrate_trace(
        self,
        target: dict[str, Any],
        source: Any,
        model_fingerprint: str,
    ) -> None:
        if isinstance(source, dict):
            for key in (
                "final_prompt",
                "visual_prompt_spec",
                "native_zine_recipe",
                "native_zine_interpretation",
            ):
                if not target.get(key) and source.get(key):
                    target[key] = source[key]
        target["model_input_fingerprint"] = model_fingerprint
        target["raw_anchor_fingerprint"] = model_fingerprint

    def _copy_raw_anchor(self, raw: dict[str, Any], target: Path) -> None:
        source = raw.get("path")
        if not isinstance(source, Path) or not self._is_parseable_image(source):
            raise NativeSkillError("记录的 raw anchor 不存在或无法解析")
        shutil.copy2(source, target)

    @staticmethod
    def _write_raw_anchor(image_bytes: bytes, path: Path) -> None:
        try:
            with Image.open(io.BytesIO(image_bytes)) as opened:
                image = ImageOps.exif_transpose(opened)
                image.load()
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise NativeSkillError("只能回传可读取的 PNG、JPEG 或 WebP 图片") from exc
        if image.width < 240 or image.height < 240:
            raise NativeSkillError("图片尺寸过小，宽高都至少需要 240 像素")
        if image.width * image.height > 50_000_000:
            raise NativeSkillError("图片像素过大，请先缩小到 5000 万像素以内")
        if max(image.size) > 2560:
            image.thumbnail((2560, 2560), Image.Resampling.LANCZOS)
        image.convert("RGB").save(path, format="PNG", optimize=True)

    def _rebuild_artifacts(
        self,
        *,
        variant: PlatformVariant,
        metadata: dict[str, Any],
        specs: list[dict[str, Any]],
        output_dir: Path,
        output_paths: dict[str, Any],
        page_diagnostics: list[dict[str, Any]] | None = None,
        allow_package: bool = True,
    ) -> dict[str, str]:
        output_dir = output_dir.resolve()
        files: dict[str, str] = {}
        for prefix in ("anchor_", "poster_", "candidate_", "contact_sheet_"):
            for key, value in output_paths.items():
                if not key.startswith(prefix):
                    continue
                path = Path(str(value)).resolve()
                if path.is_file() and output_dir in path.parents:
                    files[key] = str(path)

        article = output_dir / "article.md"
        article.write_text(variant.body_markdown, encoding="utf-8")
        files["markdown"] = str(article.resolve())

        poster_names = [
            Path(value).name
            for key, value in sorted(files.items())
            if key.startswith("poster_")
        ]
        anchor_names = [
            Path(value).name
            for key, value in sorted(files.items())
            if key.startswith("anchor_")
        ]
        manifest = output_dir / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "variant_id": variant.id,
                    "platform": variant.platform,
                    "format": variant.format,
                    "title": variant.title,
                    "summary": variant.summary,
                    "render_engine": metadata.get("render_engine"),
                    "native_zine": metadata.get("native_zine"),
                    "image_candidate_mode": metadata.get("image_candidate_mode") or "legacy",
                    "image_candidate_lifecycle": metadata.get("image_candidate_lifecycle") or {},
                    "candidate_publish_gate": {
                        "allowed": allow_package,
                        "rule": "every page requires a selected candidate that passed visual review",
                    },
                    "raw_anchors": anchor_names,
                    "posters": poster_names,
                    "pages": page_diagnostics or self._manifest_pages(files, specs),
                    "poster_specs": specs,
                    "package_allowlist": [
                        *poster_names,
                        "article.md",
                        "manifest.json",
                        "preview.html",
                    ],
                    "human_review_required": True,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        files["manifest"] = str(manifest.resolve())

        preview = output_dir / "preview.html"
        cards = []
        for index, spec in enumerate(specs, start=1):
            key = f"poster_{index:02d}"
            value = files.get(key)
            if not value:
                continue
            cards.append(
                "<figure><img src='{}' alt='{}'><figcaption>{}</figcaption></figure>".format(
                    html.escape(Path(value).name),
                    html.escape(str(spec.get("phrase") or f"第 {index} 页")),
                    html.escape(str(spec.get("phrase") or f"第 {index} 页")),
                )
            )
        preview.write_text(
            """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{title}</title><style>
body{{margin:0;background:#181818;color:#eee;font-family:system-ui,-apple-system,sans-serif}}
main{{max-width:1120px;margin:auto;padding:32px}}h1{{font-size:24px}}p{{color:#aaa}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:20px}}
figure{{margin:0;background:#242424;padding:10px;border-radius:14px}}img{{display:block;width:100%;border-radius:8px}}
figcaption{{padding:10px 4px 2px;font-size:13px;color:#bbb}}
</style></head><body><main><h1>{title}</h1><p>{summary}</p><section class='grid'>{cards}</section></main></body></html>""".format(
                title=html.escape(variant.title),
                summary=html.escape(variant.summary),
                cards="".join(cards),
            ),
            encoding="utf-8",
        )
        files["preview"] = str(preview.resolve())

        if allow_package:
            archive_path = output_dir / f"wechat-light-series-{variant.id}.zip"
            # Explicitly enumerate publishable finals.  Never add all files in the
            # directory: raw anchors, candidates, contact sheets, leftovers and
            # unknown artifacts are excluded.
            allowlist = [
                *(Path(files[key]) for key in sorted(files) if key.startswith("poster_")),
                article,
                manifest,
                preview,
            ]
            with zipfile.ZipFile(
                archive_path,
                "w",
                compression=zipfile.ZIP_DEFLATED,
            ) as archive:
                for file_path in allowlist:
                    if file_path.is_file():
                        archive.write(file_path, arcname=file_path.name)
            files["package"] = str(archive_path.resolve())
        return files

    @staticmethod
    def _manifest_pages(
        files: dict[str, str], specs: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        return [
            {
                "page": page,
                "anchor_key": f"anchor_{page:02d}",
                "poster_key": f"poster_{page:02d}",
                "anchor": Path(files[f"anchor_{page:02d}"]).name
                if f"anchor_{page:02d}" in files
                else "",
                "poster": Path(files[f"poster_{page:02d}"]).name
                if f"poster_{page:02d}" in files
                else "",
                "diagnostics": spec.get("composition_diagnostics") or {},
            }
            for page, spec in enumerate(specs, start=1)
        ]

    def _assert_complete_artifact_set(
        self,
        files: dict[str, str],
        total: int,
        output_dir: Path,
    ) -> None:
        required = {"markdown", "manifest", "preview", "package"}
        for page in range(1, total + 1):
            required.add(f"anchor_{page:02d}")
            required.add(f"poster_{page:02d}")
        missing = sorted(key for key in required if key not in files)
        if missing:
            raise NativeSkillError(f"Minimal Zine 产物不完整：缺少 {', '.join(missing)}")
        root = output_dir.resolve()
        invalid = [
            key
            for key, value in files.items()
            if root not in Path(value).resolve().parents or not Path(value).is_file()
        ]
        if invalid:
            raise NativeSkillError(f"Minimal Zine 产物路径无效：{', '.join(invalid)}")

    def _assert_rendered_artifact_set(
        self,
        files: dict[str, str],
        total: int,
        output_dir: Path,
    ) -> None:
        required = {"markdown", "manifest", "preview"}
        missing = sorted(key for key in required if key not in files)
        if missing:
            raise NativeSkillError(
                f"Minimal Zine 候选审稿产物不完整：缺少 {', '.join(missing)}"
            )
        if "package" in files:
            raise NativeSkillError("视觉审稿未通过时不得生成发布包")
        root = output_dir.resolve()
        invalid = [
            key
            for key, value in files.items()
            if root not in Path(value).resolve().parents or not Path(value).is_file()
        ]
        if invalid:
            raise NativeSkillError(f"Minimal Zine 产物路径无效：{', '.join(invalid)}")

    def _assert_import_artifacts(
        self,
        files: dict[str, str],
        output_dir: Path,
        page: int,
    ) -> None:
        required = {
            f"anchor_{page:02d}",
            f"poster_{page:02d}",
            "markdown",
            "manifest",
            "preview",
        }
        missing = sorted(key for key in required if key not in files)
        if missing:
            raise NativeSkillError(f"网页回传产物不完整：缺少 {', '.join(missing)}")
        root = output_dir.resolve()
        invalid = [
            key
            for key, value in files.items()
            if root not in Path(value).resolve().parents or not Path(value).is_file()
        ]
        if invalid:
            raise NativeSkillError(f"网页回传产物路径无效：{', '.join(invalid)}")

    def _promote_staging(self, staging_dir: Path, target_dir: Path) -> Path | None:
        backup_dir: Path | None = None
        if target_dir.exists():
            if not target_dir.is_dir():
                raise NativeSkillError("Minimal Zine 目标导出路径不是目录")
            backup_dir = target_dir.parent / f".{target_dir.name}.previous-{uuid.uuid4().hex}"
            target_dir.rename(backup_dir)
        try:
            staging_dir.rename(target_dir)
        except Exception:
            if backup_dir is not None and backup_dir.exists() and not target_dir.exists():
                backup_dir.rename(target_dir)
            raise
        return backup_dir

    @staticmethod
    def _restore_promoted_directory(target_dir: Path, backup_dir: Path | None) -> None:
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        if backup_dir is not None and backup_dir.exists():
            backup_dir.rename(target_dir)

    def _artifact_path(
        self,
        variant: PlatformVariant,
        paths: dict[str, Any],
        key: str,
    ) -> Path | None:
        value = paths.get(key)
        if not value:
            return None
        path = Path(str(value)).resolve()
        expected_dir = self._variant_directory(
            (self.settings.export_dir / "wechat").resolve(), variant.id
        )
        if expected_dir not in path.parents or not path.is_file():
            return None
        return path

    @staticmethod
    def _is_parseable_image(path: Path) -> bool:
        try:
            with Image.open(path) as image:
                image.verify()
            return True
        except (OSError, ValueError):
            return False

    def _parent_variant(
        self,
        db: Session,
        metadata: dict[str, Any],
        variant: PlatformVariant,
    ) -> PlatformVariant | None:
        parent_id = str(metadata.get("parent_variant_id") or "")
        if not parent_id or parent_id == variant.id:
            return None
        parent = db.get(PlatformVariant, parent_id)
        if (
            parent is None
            or parent.source_id != variant.source_id
            or parent.platform != "wechat"
            or parent.format != "light_series"
        ):
            return None
        return parent

    @staticmethod
    def _poster_specs(metadata: dict[str, Any]) -> list[dict[str, Any]]:
        raw = metadata.get("poster_specs")
        return [dict(item) for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []

    def _candidate_feature_mode(self, metadata: dict[str, Any]) -> str:
        stored = str(metadata.get("image_candidate_mode") or "").strip().lower()
        if stored in {"legacy", "production"}:
            return stored
        return self.settings.image_candidate_mode

    def _candidate_lifecycle(
        self,
        metadata: dict[str, Any],
    ) -> ImageCandidateLifecycle:
        try:
            return self.image_candidates.load(metadata.get("image_candidate_lifecycle"))
        except ImageCandidateError as exc:
            raise NativeSkillError(str(exc)) from exc

    @staticmethod
    def _candidate_invariants(
        metadata: dict[str, Any],
        spec: dict[str, Any],
    ) -> list[str]:
        values: list[str] = []
        bible = metadata.get("visual_bible")
        if isinstance(bible, dict):
            raw = bible.get("invariants")
            if isinstance(raw, list):
                values.extend(str(item).strip() for item in raw if str(item).strip())
        brief = spec.get("page_visual_brief")
        if isinstance(brief, dict):
            frozen = (
                ("concrete subject", brief.get("concrete_subject")),
                ("action or relation", brief.get("action_or_relation")),
                ("setting", brief.get("setting")),
                ("viewpoint", brief.get("viewpoint")),
                ("crop", brief.get("crop")),
                ("lighting", brief.get("lighting")),
            )
            values.extend(
                f"{label}: {_clean(value, 240)}"
                for label, value in frozen
                if _clean(value, 240)
            )
        deduplicated: list[str] = []
        for value in values:
            if value not in deduplicated:
                deduplicated.append(value)
        return deduplicated[:12]

    @staticmethod
    def _copy_candidate_artifacts(
        current_paths: dict[str, Any],
        output_dir: Path,
        stage_paths: dict[str, str],
    ) -> None:
        for key, value in current_paths.items():
            if not key.startswith(("candidate_", "contact_sheet_")):
                continue
            source = Path(str(value)).resolve()
            if not source.is_file():
                continue
            target = output_dir / source.name
            shutil.copy2(source, target)
            stage_paths[key] = str(target.resolve())

    def _adopt_existing_candidate(
        self,
        *,
        lifecycle: ImageCandidateLifecycle,
        metadata: dict[str, Any],
        spec: dict[str, Any],
        page: int,
        anchor_path: Path,
        output_dir: Path,
        artifact_paths: dict[str, str],
    ) -> CandidateBatchResult:
        selected = self.image_candidates.selected_candidate(lifecycle, page)
        if selected is not None:
            return CandidateBatchResult(
                lifecycle=lifecycle,
                page_state=lifecycle.pages[str(page)],
                artifact_paths=dict(artifact_paths),
                selected_candidate=selected,
            )
        prompt = str(spec.get("final_prompt") or "").strip()
        if not prompt:
            prompt = (
                "NO TEXT. Preserve this previously reviewed raw visual anchor as an auditable "
                "candidate; X2RED adds Chinese typography locally."
            )
        try:
            return self.image_candidates.add_manual_candidates(
                lifecycle=lifecycle,
                page=page,
                prompt=prompt,
                images=[anchor_path.read_bytes()],
                output_dir=output_dir,
                artifact_paths=artifact_paths,
                page_visual_brief=(
                    spec.get("page_visual_brief")
                    if isinstance(spec.get("page_visual_brief"), dict)
                    else None
                ),
                invariants=self._candidate_invariants(metadata, spec),
                provider=str(spec.get("raw_anchor_provider") or "x2red-existing-anchor"),
                model="frozen-raw-anchor",
                series_reference_bytes=self._candidate_reference_bytes(
                    lifecycle,
                    page,
                    artifact_paths,
                ),
            )
        except (ImageCandidateError, OSError) as exc:
            raise NativeSkillError(f"第 {page} 页旧锚点无法纳入候选审计：{exc}") from exc

    def _candidate_reference_bytes(
        self,
        lifecycle: ImageCandidateLifecycle,
        page: int,
        artifact_paths: dict[str, str],
    ) -> list[bytes]:
        references: list[bytes] = []
        for key in sorted(lifecycle.pages, key=lambda value: int(value)):
            other_page = int(key)
            if other_page == page:
                continue
            try:
                references.append(
                    self.image_candidates.selected_bytes(
                        lifecycle,
                        other_page,
                        artifact_paths,
                    )
                )
            except ImageCandidateError:
                continue
        return references[-4:]

    @staticmethod
    def _object(value: str) -> dict[str, Any]:
        try:
            parsed = json.loads(value or "{}")
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _object_value(value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _selected_pages(pages: list[int] | None, total: int) -> list[int]:
        selected = list(pages or range(1, total + 1))
        if len(set(selected)) != len(selected):
            raise NativeSkillError("pages 不能包含重复页码")
        invalid = [page for page in selected if not isinstance(page, int) or page < 1 or page > total]
        if invalid:
            raise NativeSkillError(
                f"pages 必须是 1 到 {total} 之间的页码：{', '.join(str(value) for value in invalid)}"
            )
        return selected

    @staticmethod
    def _variant_directory(wechat_root: Path, variant_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", variant_id):
            raise NativeSkillError("平台版本 ID 无法安全用于导出路径")
        return wechat_root / variant_id

    @staticmethod
    def _accent(value: str) -> str:
        canonical = _canonical_accent(value)
        return canonical if canonical.startswith("#") else _ACCENT_COLORS[canonical]

    def _generate_image(self, prompt: str) -> bytes:
        try:
            result = self.model.generate_images(prompt=prompt, count=1)
        except ModelClientError as exc:
            raise NativeSkillError(str(exc)) from exc
        return result.images[0].image_bytes
