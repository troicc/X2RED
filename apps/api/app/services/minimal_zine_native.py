from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import re
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any, Literal

import httpx
from PIL import Image, ImageDraw, ImageOps
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.platforms import PlatformVariant, PlatformVariantState
from app.services.light_visual_renderer import CJKFontError, LightVisualRenderer
from app.services.model_client import ModelClient, ModelClientError
from app.services.native_skill_manager import NativeSkillError, NativeSkillManager


RenderMode = Literal["render_missing", "recompose", "regenerate"]

STORYBOARD_LAYOUTS = (
    "center-fragment",
    "lower-left-float",
    "upper-right-block",
    "dual-panel",
    "irregular-cutout",
    "type-led",
    "dot-orbit",
    "single-specimen",
)
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


def _storyboard_controls(spec: dict[str, Any]) -> dict[str, Any]:
    """Return the one contract used by prompts, raw-cache validity and composing."""

    return {
        "visual_metaphor": _clean(spec.get("visual_metaphor"), 240)
        or "one isolated ordinary object",
        "layout": _allowed(spec.get("layout"), STORYBOARD_LAYOUTS, "center-fragment"),
        "anchor": _allowed(spec.get("anchor"), STORYBOARD_ANCHORS, "object-specimen"),
        "accent": _canonical_accent(spec.get("accent")),
        "texture": _allowed(spec.get("texture"), STORYBOARD_TEXTURES, "xerox-softness"),
        "mood": _clean(spec.get("mood"), 80) or "quiet",
    }


def _model_input_fingerprint(spec: dict[str, Any]) -> str:
    encoded = json.dumps(_storyboard_controls(spec), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def storyboard_model_input_changed(
    previous: dict[str, Any],
    current: dict[str, Any],
) -> bool:
    """Public helper for immutable storyboard revisions.

    Phrase, note and crop controls deliberately do not invalidate a raw model anchor:
    they are composed locally.  Metaphor and visual recipe controls do.
    """

    return _model_input_fingerprint(previous) != _model_input_fingerprint(current)


class MinimalZineNativeService:
    skill_name = "gc-minimal-zine-poster-v0-1"
    compositor_version = "minimal-zine-local-type-v4"
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
        self.local_renderer = LightVisualRenderer(settings)

    @property
    def image_configured(self) -> bool:
        return bool(
            (self.settings.image_base_url or self.settings.model_base_url)
            and (self.settings.image_api_key or self.settings.model_api_key)
            and self.settings.image_model
        )

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
        if needs_generation:
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
                model_fingerprint = _model_input_fingerprint(spec)
                recipe = self._recipe_for(spec)
                composition: dict[str, Any] = {}

                if action == "regenerated":
                    compiled = self._compile_prompt(
                        skill_text=skill_text,
                        variant=variant,
                        spec=spec,
                        page=page,
                        total=total,
                        recent_recipes=recent_recipes,
                    )
                    recipe = compiled["recipe"]
                    image_bytes = self._generate_image(str(compiled["final_prompt"]))
                    self._write_raw_anchor(image_bytes, anchor_path)
                    spec.update(
                        {
                            "final_prompt": str(compiled["final_prompt"]),
                            "native_zine_recipe": recipe,
                            "native_zine_interpretation": str(
                                compiled.get("interpretation") or ""
                            ),
                            "model_input_fingerprint": model_fingerprint,
                            "raw_anchor_fingerprint": model_fingerprint,
                            "raw_anchor_source_variant_id": variant.id,
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
                    recipe = self._recipe_for(spec)
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
                    recipe = self._recipe_for(spec)
                    composition = self._compose_poster(
                        anchor_path.read_bytes(),
                        poster_path,
                        spec=spec,
                        recipe=recipe,
                        page=page,
                        total=total,
                        font_diagnostics=font_diagnostics,
                    )

                spec.update(
                    {
                        "native_zine_recipe": recipe,
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
                            "recipe": recipe,
                            "interpretation": str(
                                spec.get("native_zine_interpretation") or ""
                            ),
                            "diagnostics": composition,
                        }
                    )

            new_metadata = dict(metadata)
            new_metadata["poster_specs"] = new_specs
            new_metadata["render_engine"] = "gc-minimal-zine-local-compositor-v4"
            new_metadata["native_zine"] = {
                "repository": "https://github.com/LiamGvchi/gc-minimal-zine-poster",
                "commit": self.manager.definition(self.skill_name).commit,
                "license": "MIT",
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
                    "negative prompt, high-risk outer-edge crop, local clean text zone, "
                    "and required human visual review; no watermark-impossibility claim"
                ),
            }
            stage_paths = self._rebuild_artifacts(
                variant=variant,
                metadata=new_metadata,
                specs=new_specs,
                output_dir=staging_dir,
                output_paths=stage_paths,
                page_diagnostics=page_diagnostics,
            )
            self._assert_complete_artifact_set(stage_paths, total, staging_dir)

            final_paths = {
                key: str((target_dir / Path(value).name).resolve())
                for key, value in stage_paths.items()
            }
            backup_dir = self._promote_staging(staging_dir, target_dir)
            promoted = True
            variant.metadata_json = json.dumps(new_metadata, ensure_ascii=False)
            variant.output_paths_json = json.dumps(final_paths, ensure_ascii=False)
            variant.status = PlatformVariantState.packaged.value
            variant.error = ""
            db.flush()
        except Exception:
            if promoted:
                self._restore_promoted_directory(target_dir, backup_dir)
            variant.metadata_json = original_values["metadata_json"]
            variant.output_paths_json = original_values["output_paths_json"]
            variant.status = original_values["status"]
            variant.error = original_values["error"]
            raise
        else:
            if backup_dir is not None and backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)
            # Result paths must point at the promoted stable directory, never its
            # now-removed staging predecessor.
            for result in page_results:
                result["path"] = final_paths[result["poster_key"]]
                result["anchor_path"] = final_paths[result["anchor_key"]]
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
                expected_fingerprint=_model_input_fingerprint(spec),
            )
            current_final = self._final_candidate(
                variant=variant,
                specs=specs,
                paths=current_paths,
                page=page,
                target_spec=spec,
            )
            parent_final = (
                self._final_candidate(
                    variant=parent,
                    specs=parent_specs,
                    paths=parent_paths,
                    page=page,
                    target_spec=spec,
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
        if str(spec.get("raw_anchor_fingerprint") or "") != expected_fingerprint:
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
    ) -> dict[str, Any] | None:
        if variant is None or page > len(specs):
            return None
        source_spec = specs[page - 1]
        expected_model = _model_input_fingerprint(target_spec)
        raw = self._raw_from_variant(
            variant, specs, paths, page, expected_model
        )
        if raw is None:
            return None
        poster_path = self._artifact_path(variant, paths, f"poster_{page:02d}")
        if poster_path is None or not self._is_parseable_image(poster_path):
            return None
        expected_composition = self._composition_fingerprint(
            target_spec, self._recipe_for(target_spec)
        )
        if str(source_spec.get("final_composition_fingerprint") or "") != expected_composition:
            return None
        if str(source_spec.get("compositor_version") or "") != self.compositor_version:
            return None
        return {"raw": raw, "poster_path": poster_path, "variant_id": variant.id}

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
        *,
        controls: dict[str, Any],
        raw_prompt: str,
        safe_zone: dict[str, Any],
    ) -> str:
        accent = controls["accent"]
        accent_word = accent if not accent.startswith("#") else f"opaque {accent} ink"
        return "\n\n".join(
            [
                (
                    "Tall vertical 3:5 full-frame aged-paper editorial plate, no border and no mockup; "
                    "70%-90% perceived quiet paper, one sparse 8%-25% visual cluster positioned as "
                    f"{controls['layout']}, with {safe_zone['prompt']} and the bottom 30 percent blank "
                    "for local type."
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
        """Compose local type while retaining the model's full sparse art plate.

        The crop is intentionally constrained to high-risk outer margins.  It avoids
        the old destructive 4%-70% visual slice, avoids global grayscale/colorization,
        and only adds local accent ink if the raw plate is measurably color-starved.
        """

        try:
            with Image.open(io.BytesIO(image_bytes)) as source:
                source = ImageOps.exif_transpose(source).convert("RGB")
                width, height = source.size
                # Edge-only mitigation: 6% side, 4% top and 12% bottom at most.
                edges = {
                    "left": 0.06,
                    "top": 0.04,
                    "right": 0.06,
                    "bottom": 0.08,
                }
                cropped = source.crop(
                    (
                        int(width * edges["left"]),
                        int(height * edges["top"]),
                        int(width * (1 - edges["right"])),
                        int(height * (1 - edges["bottom"])),
                    )
                )
                focus_x = self._focus_value(spec.get("focus_x"), 0.5)
                focus_y = self._focus_value(spec.get("focus_y"), 0.5)
                zoom = self._zoom_value(spec.get("zoom"))
                cropped = self._focused_crop(cropped, focus_x, focus_y, zoom)
                # Preserve the complete post-edge-crop plate.  `contain` avoids a
                # second, hidden interior crop when a provider returns a ratio that
                # is not exactly 3:5; expected 3:5 anchors still fill the canvas.
                contained = ImageOps.contain(
                    cropped,
                    (self.local_renderer.width, self.local_renderer.height),
                    method=Image.Resampling.LANCZOS,
                )
                visual = self.local_renderer._paper("#e8ddc8", noise=8, blend=0.025)
                offset = (
                    (self.local_renderer.width - contained.width) // 2,
                    (self.local_renderer.height - contained.height) // 2,
                )
                visual.paste(contained, offset)
        except (OSError, ValueError) as exc:
            raise NativeSkillError("图片模型返回的 raw anchor 无法解析") from exc

        layout = str(recipe.get("layout") or "center-fragment")
        safe_zone = self._safe_zone(layout)
        color_signal = self._color_signal(visual)
        high_chroma_ratio = color_signal["high_chroma_ratio"]
        muted_chroma_ratio = color_signal["muted_chroma_ratio"]
        canvas = visual.copy()
        draw = ImageDraw.Draw(canvas)
        paper = "#e8ddc8"
        # This is a local text-safe field, not a repeated external frame.  The model
        # prompt reserves it; covering it protects local Chinese from edge badges and
        # keeps the artwork's full-plate color/geometry elsewhere intact.
        draw.rectangle(safe_zone["panel"], fill=paper)
        # Providers often place badges in the last few pixels even when prompted
        # otherwise.  Keep that high-risk outer bottom band locally clean rather
        # than taking a destructive interior crop from the sparse model plate.
        draw.rectangle(
            (0, self.local_renderer.height - 128, self.local_renderer.width, self.local_renderer.height),
            fill=paper,
        )
        draw.rectangle((0, 0, 72, self.local_renderer.height), fill=paper)
        draw.rectangle(
            (self.local_renderer.width - 72, 0, self.local_renderer.width, self.local_renderer.height),
            fill=paper,
        )

        accent_added = False
        accent_share = 0.0
        accent_diagnostics: dict[str, Any] = {
            "actual_share": 0.0,
            "shape": None,
            "placement": None,
            "bbox": None,
            "outside_text_safe_zone": True,
            "outside_principal_cluster": True,
        }
        if (
            high_chroma_ratio < self.high_chroma_threshold
            and muted_chroma_ratio < self.muted_chroma_threshold
        ):
            accent_share = self.local_accent_target_share
            accent_diagnostics = self._draw_local_accent(
                draw,
                layout=layout,
                anchor=str(recipe.get("anchor") or "object-specimen"),
                color=self._accent(str(recipe.get("accent") or spec.get("accent") or "")),
                share=accent_share,
                safe_zone=safe_zone,
            )
            accent_added = True
        elif high_chroma_ratio >= self.high_chroma_threshold:
            accent_reason = "upstream-high-chroma"
        else:
            accent_reason = "upstream-muted-accent"
        if accent_added:
            accent_reason = "color-starved"

        phrase = _clean(spec.get("phrase"), 80)
        note = _clean(spec.get("note"), 180)
        text_x, text_y, text_width = safe_zone["text"]
        title_size = int(safe_zone["title_size"])
        if len(phrase) > 20:
            title_size = max(44, title_size - 10)
        title_font = self.local_renderer._font(title_size, bold=True, serif=False)
        note_font = self.local_renderer._font(26, serif=True)
        lines = self.local_renderer._wrap(draw, phrase, title_font, text_width)[:4]
        line_height = int(title_size * 1.32)
        for offset, line in enumerate(lines):
            draw.text(
                (text_x, text_y + offset * line_height),
                line,
                font=title_font,
                fill="#171614",
            )
        note_y = text_y + len(lines) * line_height + 26
        for offset, line in enumerate(
            self.local_renderer._wrap(draw, note, note_font, text_width)[:3]
        ):
            draw.text(
                (text_x, note_y + offset * 40),
                line,
                font=note_font,
                fill="#625d54",
            )
        footer_font = self.local_renderer._font(18, serif=True)
        footer_y = min(self.local_renderer.height - 58, safe_zone["panel"][3] - 36)
        draw.text((safe_zone["panel"][0] + 18, footer_y), "X2RED · MINIMAL ZINE", font=footer_font, fill="#625d54")
        page_text = f"{page:02d} / {total:02d}"
        page_width = draw.textlength(page_text, font=footer_font)
        draw.text(
            (safe_zone["panel"][2] - 18 - page_width, footer_y),
            page_text,
            font=footer_font,
            fill="#625d54",
        )
        canvas.save(path, "PNG", optimize=True)
        return {
            "edge_crop": edges,
            "focus": {"x": focus_x, "y": focus_y, "zoom": zoom},
            "layout": layout,
            "safe_zone": safe_zone["id"],
            "preserved_model_color": True,
            "high_chroma_ratio": round(high_chroma_ratio, 5),
            "high_chroma_threshold": self.high_chroma_threshold,
            "muted_chroma_ratio": round(muted_chroma_ratio, 5),
            "muted_chroma_threshold": self.muted_chroma_threshold,
            "muted_chroma_saturation": self.muted_chroma_saturation,
            "local_accent_added": accent_added,
            "local_accent_target_share": accent_share,
            "local_accent_actual_share": round(
                float(accent_diagnostics["actual_share"]), 6
            ),
            "local_accent_max_share": self.local_accent_max_share,
            "local_accent_shape": accent_diagnostics["shape"],
            "local_accent_placement": accent_diagnostics["placement"],
            "local_accent_bbox": accent_diagnostics["bbox"],
            "local_accent_outside_text_safe_zone": accent_diagnostics[
                "outside_text_safe_zone"
            ],
            "local_accent_outside_principal_cluster": accent_diagnostics[
                "outside_principal_cluster"
            ],
            "local_accent_reason": accent_reason,
            "font": (font_diagnostics or self.local_renderer.cjk_font_diagnostics()).get("selected"),
        }

    def _safe_zone(self, layout: str) -> dict[str, Any]:
        layouts: dict[str, dict[str, Any]] = {
            "center-fragment": {
                "id": "bottom-wide",
                "panel": (72, 1260, 1128, 1872),
                "text": (112, 1320, 960),
                "title_size": 62,
                "prompt": "a clean lower paper zone spanning roughly the bottom 30 percent",
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
            "lower-left-float": ((1010, 1090), "right-lower-margin", (96, 620, 620, 1460)),
            "upper-right-block": ((96, 1080), "left-lower-margin", (620, 120, 1120, 1040)),
            "dual-panel": ((96, 1240), "left-lower-margin", (220, 320, 980, 1180)),
            "irregular-cutout": ((980, 1050), "right-upper-margin", (96, 220, 680, 1120)),
            "type-led": ((96, 60), "left-upper-margin", (180, 120, 1020, 520)),
            "dot-orbit": ((1010, 1240), "right-lower-margin", (180, 300, 1020, 1220)),
            "single-specimen": ((1010, 1000), "right-upper-margin", (120, 220, 660, 1120)),
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
            with Image.open(io.BytesIO(image_bytes)) as image:
                image.verify()
        except (OSError, ValueError) as exc:
            raise NativeSkillError("图片模型返回的 raw anchor 无法解析") from exc
        path.write_bytes(image_bytes)

    def _rebuild_artifacts(
        self,
        *,
        variant: PlatformVariant,
        metadata: dict[str, Any],
        specs: list[dict[str, Any]],
        output_dir: Path,
        output_paths: dict[str, Any],
        page_diagnostics: list[dict[str, Any]] | None = None,
    ) -> dict[str, str]:
        output_dir = output_dir.resolve()
        files: dict[str, str] = {}
        for prefix in ("anchor_", "poster_"):
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

        archive_path = output_dir / f"wechat-light-series-{variant.id}.zip"
        # Explicitly enumerate publishable finals.  Never add all files in the
        # directory: raw anchors, leftovers and unknown artifacts are excluded.
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
        base_url = (self.settings.image_base_url or self.settings.model_base_url).rstrip("/")
        endpoint = base_url + "/images/generations"
        api_key = self.settings.image_api_key or self.settings.model_api_key
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        bodies = [
            {
                "model": self.settings.image_model,
                "prompt": prompt,
                "size": self.settings.image_size,
                "n": 1,
            },
            {"model": self.settings.image_model, "prompt": prompt, "n": 1},
        ]
        last_error = ""
        with httpx.Client(timeout=300, follow_redirects=True) as client:
            for index, body in enumerate(bodies):
                try:
                    response = client.post(endpoint, headers=headers, json=body)
                    if response.status_code in {400, 404, 422} and index == 0:
                        last_error = response.text[:1000]
                        continue
                    response.raise_for_status()
                    data = response.json()
                    items = data.get("data") if isinstance(data, dict) else None
                    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
                        raise NativeSkillError("图片模型响应缺少 data")
                    item = items[0]
                    b64 = str(item.get("b64_json") or item.get("base64") or "")
                    if b64:
                        return base64.b64decode(b64)
                    url = str(item.get("url") or "")
                    if not url:
                        raise NativeSkillError("图片模型没有返回 URL 或 base64")
                    image_response = client.get(url)
                    image_response.raise_for_status()
                    return image_response.content
                except (
                    httpx.HTTPError,
                    ValueError,
                    KeyError,
                    base64.binascii.Error,
                ) as exc:
                    last_error = str(exc)
                    if index == len(bodies) - 1:
                        break
        raise NativeSkillError(f"图片生成失败：{last_error[:1000]}")
