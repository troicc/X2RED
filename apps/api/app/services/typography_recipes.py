from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, cast

from PIL import Image, ImageChops, ImageDraw, ImageFont

from app.domain.typography_schemas import (
    TextRegion,
    TypographyMode,
    TypographyRecipe,
    TypographyRegionDiagnostic,
    TypographyRenderDiagnostic,
)

FontResolver = Callable[..., ImageFont.FreeTypeFont | ImageFont.ImageFont]

TYPOGRAPHY_MODE_LABELS: dict[str, str] = {
    "type_led_large": "大字主导",
    "edge_pressed_phrase": "边缘压字",
    "diagonal_fragments": "对角碎句",
    "ghost_text": "幽灵底字",
    "archive_microtype": "档案微排",
    "type_in_color_block": "色块承字",
    "margin_scatter": "边注散排",
    "safe_zone_caption": "安全区说明",
}

ALL_TYPOGRAPHY_MODES: tuple[TypographyMode, ...] = (
    "type_led_large",
    "edge_pressed_phrase",
    "diagonal_fragments",
    "ghost_text",
    "archive_microtype",
    "type_in_color_block",
    "margin_scatter",
    "safe_zone_caption",
)


def _region(
    region_id: str,
    role: str,
    source: str,
    box: tuple[float, float, float, float],
    **kwargs: Any,
) -> TextRegion:
    return TextRegion(
        region_id=region_id,
        role=role,
        source=source,
        x=box[0],
        y=box[1],
        width=box[2],
        height=box[3],
        **kwargs,
    )


def _templates() -> dict[TypographyMode, TypographyRecipe]:
    return {
        "type_led_large": TypographyRecipe(
            mode="type_led_large",
            text_regions=[
                _region("hero-title", "title", "phrase", (0.075, 0.25, 0.85, 0.37), max_lines=4),
                _region(
                    "support-note",
                    "caption",
                    "note",
                    (0.10, 0.69, 0.56, 0.14),
                    size_scale=0.30,
                    max_lines=3,
                    background_role="paper_veil",
                ),
                _region(
                    "folio",
                    "folio",
                    "folio",
                    (0.78, 0.88, 0.14, 0.055),
                    size_scale=0.20,
                    max_lines=1,
                    alignment="right",
                ),
            ],
            font_role="sans_display",
            weight=800,
            size_ratio=0.108,
            line_height=0.98,
            tracking=-0.025,
            rotation=0,
            alignment="left",
            opacity=1,
            blend_mode="multiply",
            collision_policy="avoid_subject",
        ),
        "edge_pressed_phrase": TypographyRecipe(
            mode="edge_pressed_phrase",
            text_regions=[
                _region("edge-title", "title", "phrase", (0.018, 0.12, 0.47, 0.58), max_lines=6),
                _region(
                    "edge-note",
                    "caption",
                    "note",
                    (0.58, 0.77, 0.36, 0.13),
                    size_scale=0.34,
                    max_lines=3,
                    background_role="paper_veil",
                ),
                _region(
                    "folio",
                    "folio",
                    "folio",
                    (0.02, 0.89, 0.16, 0.05),
                    size_scale=0.22,
                    max_lines=1,
                ),
            ],
            font_role="serif_editorial",
            weight=700,
            size_ratio=0.078,
            line_height=1.05,
            tracking=-0.01,
            rotation=0,
            alignment="left",
            opacity=1,
            blend_mode="multiply",
            collision_policy="avoid_subject",
        ),
        "diagonal_fragments": TypographyRecipe(
            mode="diagonal_fragments",
            text_regions=[
                _region(
                    "fragment-a",
                    "fragment",
                    "phrase_head",
                    (0.07, 0.15, 0.42, 0.24),
                    max_lines=3,
                    rotation=-8,
                ),
                _region(
                    "fragment-b",
                    "fragment",
                    "phrase_tail",
                    (0.50, 0.51, 0.43, 0.25),
                    max_lines=3,
                    rotation=7,
                    alignment="right",
                ),
                _region(
                    "diagonal-note",
                    "caption",
                    "note",
                    (0.08, 0.79, 0.47, 0.12),
                    size_scale=0.34,
                    max_lines=3,
                    background_role="paper_veil",
                ),
            ],
            font_role="sans_display",
            weight=750,
            size_ratio=0.073,
            line_height=1.02,
            tracking=0.005,
            rotation=0,
            alignment="left",
            opacity=1,
            blend_mode="multiply",
            collision_policy="avoid_subject",
        ),
        "ghost_text": TypographyRecipe(
            mode="ghost_text",
            text_regions=[
                _region(
                    "ghost",
                    "ghost",
                    "phrase",
                    (0.035, 0.09, 0.93, 0.50),
                    size_scale=1.28,
                    max_lines=3,
                    opacity=0.13,
                ),
                _region(
                    "ghost-title",
                    "title",
                    "phrase",
                    (0.11, 0.63, 0.68, 0.22),
                    size_scale=0.62,
                    max_lines=4,
                    background_role="paper_veil",
                ),
                _region(
                    "ghost-note",
                    "caption",
                    "note",
                    (0.12, 0.84, 0.58, 0.09),
                    size_scale=0.25,
                    max_lines=2,
                ),
            ],
            font_role="serif_editorial",
            weight=700,
            size_ratio=0.092,
            line_height=0.98,
            tracking=-0.03,
            rotation=0,
            alignment="left",
            opacity=1,
            blend_mode="multiply",
            collision_policy="soft_underlay",
        ),
        "archive_microtype": TypographyRecipe(
            mode="archive_microtype",
            text_regions=[
                _region(
                    "archive-label",
                    "microtype",
                    "label",
                    (0.07, 0.08, 0.48, 0.08),
                    size_scale=0.46,
                    max_lines=2,
                ),
                _region(
                    "archive-title",
                    "title",
                    "phrase",
                    (0.08, 0.55, 0.62, 0.25),
                    size_scale=1.55,
                    max_lines=4,
                ),
                _region(
                    "archive-note",
                    "microtype",
                    "note",
                    (0.72, 0.20, 0.22, 0.43),
                    size_scale=0.50,
                    max_lines=10,
                ),
                _region(
                    "archive-folio",
                    "folio",
                    "folio",
                    (0.74, 0.87, 0.18, 0.06),
                    size_scale=0.50,
                    max_lines=1,
                    alignment="right",
                ),
            ],
            font_role="mono_archive",
            weight=500,
            size_ratio=0.032,
            line_height=1.36,
            tracking=0.08,
            rotation=0,
            alignment="left",
            opacity=0.92,
            blend_mode="multiply",
            collision_policy="avoid_subject",
        ),
        "type_in_color_block": TypographyRecipe(
            mode="type_in_color_block",
            text_regions=[
                _region(
                    "block-title",
                    "title",
                    "phrase",
                    (0.07, 0.11, 0.58, 0.34),
                    max_lines=4,
                    background_role="ink_block",
                    inset_ratio=0.045,
                ),
                _region(
                    "block-note",
                    "caption",
                    "note",
                    (0.10, 0.51, 0.51, 0.14),
                    size_scale=0.31,
                    max_lines=3,
                    background_role="paper_veil",
                ),
                _region(
                    "block-folio",
                    "folio",
                    "folio",
                    (0.74, 0.87, 0.18, 0.06),
                    size_scale=0.22,
                    max_lines=1,
                    alignment="right",
                ),
            ],
            font_role="sans_display",
            weight=800,
            size_ratio=0.073,
            line_height=1.04,
            tracking=-0.015,
            rotation=0,
            alignment="left",
            opacity=1,
            blend_mode="normal",
            collision_policy="avoid_subject",
        ),
        "margin_scatter": TypographyRecipe(
            mode="margin_scatter",
            text_regions=[
                _region(
                    "margin-head",
                    "fragment",
                    "phrase_head",
                    (0.025, 0.16, 0.25, 0.35),
                    size_scale=0.78,
                    max_lines=5,
                    rotation=-4,
                ),
                _region(
                    "margin-tail",
                    "fragment",
                    "phrase_tail",
                    (0.69, 0.50, 0.28, 0.34),
                    size_scale=0.78,
                    max_lines=5,
                    rotation=4,
                    alignment="right",
                ),
                _region(
                    "margin-note",
                    "caption",
                    "note",
                    (0.24, 0.80, 0.49, 0.12),
                    size_scale=0.28,
                    max_lines=3,
                    alignment="center",
                    background_role="paper_veil",
                ),
            ],
            font_role="serif_editorial",
            weight=650,
            size_ratio=0.064,
            line_height=1.08,
            tracking=0.02,
            rotation=0,
            alignment="left",
            opacity=0.96,
            blend_mode="multiply",
            collision_policy="avoid_subject",
        ),
        "safe_zone_caption": TypographyRecipe(
            mode="safe_zone_caption",
            text_regions=[
                _region(
                    "safe-title",
                    "title",
                    "phrase",
                    (0.08, 0.66, 0.84, 0.20),
                    max_lines=4,
                    background_role="paper_veil",
                ),
                _region(
                    "safe-note",
                    "caption",
                    "note",
                    (0.09, 0.85, 0.66, 0.09),
                    size_scale=0.38,
                    max_lines=2,
                ),
                _region(
                    "safe-folio",
                    "folio",
                    "folio",
                    (0.78, 0.89, 0.14, 0.05),
                    size_scale=0.28,
                    max_lines=1,
                    alignment="right",
                ),
            ],
            font_role="serif_editorial",
            weight=700,
            size_ratio=0.062,
            line_height=1.16,
            tracking=0,
            rotation=0,
            alignment="left",
            opacity=1,
            blend_mode="multiply",
            collision_policy="safe_zone",
        ),
    }


TEMPLATES = _templates()

LAYOUT_MODE_PREFERENCES: dict[str, tuple[TypographyMode, ...]] = {
    "type-led": ("type_led_large", "ghost_text"),
    "diagonal-notes": ("diagonal_fragments", "margin_scatter"),
    "edge-counterweight": ("edge_pressed_phrase", "margin_scatter"),
    "single-specimen": ("archive_microtype", "edge_pressed_phrase"),
    "dot-orbit": ("ghost_text", "diagonal_fragments"),
    "irregular-cutout": ("margin_scatter", "archive_microtype"),
    "dual-panel": ("type_in_color_block", "ghost_text"),
    "lower-left-float": ("edge_pressed_phrase", "archive_microtype"),
    "upper-right-block": ("margin_scatter", "type_in_color_block"),
    "lower-fragment": ("type_led_large", "diagonal_fragments"),
    "center-fragment": ("ghost_text", "type_led_large"),
}

ROLE_MODE_PREFERENCES: dict[str, tuple[TypographyMode, ...]] = {
    "cover": ("type_led_large", "type_in_color_block"),
    "evidence": ("archive_microtype", "edge_pressed_phrase"),
    "comparison": ("diagonal_fragments", "type_in_color_block"),
    "process": ("diagonal_fragments", "margin_scatter"),
    "limitation": ("edge_pressed_phrase", "archive_microtype"),
    "conclusion": ("type_in_color_block", "type_led_large"),
    "scene": ("ghost_text", "margin_scatter"),
    "transition": ("margin_scatter", "ghost_text"),
    "explanation": ("archive_microtype", "type_led_large"),
}


@dataclass(frozen=True)
class TypographySelection:
    recipe: TypographyRecipe
    protected_regions: tuple[tuple[int, int, int, int], ...]


class TypographyRecipeEngine:
    version = "x2red-typography-recipes-v2"

    def select(
        self,
        *,
        size: tuple[int, int],
        phrase: str,
        note: str,
        page: int,
        total: int,
        layout: str,
        visual_role: str = "",
        requested_mode: str = "",
        protected_regions: Iterable[tuple[int, int, int, int]] = (),
        stored_recipe: dict[str, Any] | None = None,
    ) -> TypographySelection:
        protected = tuple(self._bounded_rect(item, size) for item in protected_regions)
        fingerprint = self.source_fingerprint(
            size=size,
            phrase=phrase,
            note=note,
            page=page,
            total=total,
            layout=layout,
            visual_role=visual_role,
            requested_mode=requested_mode,
            protected_regions=protected,
        )
        if stored_recipe:
            try:
                stored = TypographyRecipe.model_validate(stored_recipe)
            except ValueError:
                stored = None
            if stored is not None and stored.source_fingerprint == fingerprint:
                return TypographySelection(recipe=stored, protected_regions=protected)

        candidates = self._candidate_modes(
            requested_mode=requested_mode,
            layout=layout,
            visual_role=visual_role,
            page=page,
            phrase=phrase,
        )
        requested_specific = requested_mode if requested_mode in ALL_TYPOGRAPHY_MODES else ""
        for mode in candidates:
            template = TEMPLATES[mode]
            for transform in ("identity", "mirror_x", "mirror_y", "mirror_xy"):
                recipe = self._transformed(template, transform)
                if self._recipe_subject_safe(recipe, size=size, protected_regions=protected):
                    reason = self._selection_reason(
                        mode=mode,
                        requested_specific=requested_specific,
                        layout=layout,
                        visual_role=visual_role,
                        transform=transform,
                    )
                    return TypographySelection(
                        recipe=recipe.model_copy(
                            update={
                                "source_fingerprint": fingerprint,
                                "selection_reason": reason,
                                "transform": transform,
                            }
                        ),
                        protected_regions=protected,
                    )

        fallback = self._fit_safe_caption(
            size=size,
            protected_regions=protected,
        ).model_copy(
            update={
                "source_fingerprint": fingerprint,
                "selection_reason": "其他排版模式均与关键主体碰撞，降级到安全区说明",
                "fallback_from": candidates[0] if candidates else requested_specific,
            }
        )
        return TypographySelection(recipe=fallback, protected_regions=protected)

    @staticmethod
    def source_fingerprint(
        *,
        size: tuple[int, int],
        phrase: str,
        note: str,
        page: int,
        total: int,
        layout: str,
        visual_role: str,
        requested_mode: str,
        protected_regions: Iterable[tuple[int, int, int, int]],
    ) -> str:
        payload = {
            "version": TypographyRecipeEngine.version,
            "size": list(size),
            "phrase": phrase,
            "note": note,
            "page": page,
            "total": total,
            "layout": layout,
            "visual_role": visual_role,
            "requested_mode": requested_mode,
            "protected_regions": [list(item) for item in protected_regions],
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def render(
        self,
        canvas: Image.Image,
        *,
        selection: TypographySelection,
        phrase: str,
        note: str,
        folio: str,
        label: str,
        font_resolver: FontResolver,
        ink: str = "#171614",
        muted: str = "#514c45",
        paper: str = "#eee5d5",
        accent: str = "#8c3f2d",
    ) -> tuple[Image.Image, TypographyRenderDiagnostic]:
        recipe = selection.recipe
        result = canvas.convert("RGB")
        diagnostics: list[TypographyRegionDiagnostic] = []
        text_values = self.region_text_values(
            recipe,
            phrase=phrase,
            note=note,
            folio=folio,
            label=label,
        )
        for region in recipe.text_regions:
            value = text_values.get(region.region_id, "")
            box = self.region_box(region, result.size)
            rotation = region.rotation if region.rotation is not None else recipe.rotation
            opacity = region.opacity if region.opacity is not None else recipe.opacity
            overlaps = any(self._overlap(box, protected) for protected in selection.protected_regions)
            if not value:
                diagnostics.append(
                    TypographyRegionDiagnostic(
                        region_id=region.region_id,
                        role=region.role,
                        source=region.source,
                        box=box,
                        font_size=0,
                        rotation=rotation,
                        opacity=opacity,
                        overlaps_subject=overlaps,
                    )
                )
                continue
            result, diagnostic = self._render_region(
                result,
                recipe=recipe,
                region=region,
                value=value,
                box=box,
                rotation=rotation,
                opacity=opacity,
                overlaps_subject=overlaps,
                font_resolver=font_resolver,
                ink=ink,
                muted=muted,
                paper=paper,
                accent=accent,
            )
            diagnostics.append(diagnostic)

        visible = [item for item in diagnostics if item.lines and item.opacity >= 0.2]
        no_overflow = all(not item.clipped for item in diagnostics)
        subject_clear = all(
            not item.overlaps_subject or item.opacity <= 0.18
            for item in diagnostics
            if item.role not in {"folio", "microtype"}
        )
        if not no_overflow:
            raise ValueError("本地中文排版发生溢出")
        if not subject_clear:
            raise ValueError("本地中文排版覆盖关键主体")
        diagnostic = TypographyRenderDiagnostic(
            mode=recipe.mode,
            font_role=recipe.font_role,
            canvas_ratio=self.ratio_label(result.size),
            transform=recipe.transform,
            selection_reason=recipe.selection_reason,
            fallback_from=recipe.fallback_from,
            collision_policy=recipe.collision_policy,
            protected_regions=list(selection.protected_regions),
            regions=diagnostics,
            no_overflow=no_overflow,
            subject_clear=subject_clear,
            visible_text_region_count=len(visible),
            source_fingerprint=recipe.source_fingerprint,
        )
        return result, diagnostic

    @staticmethod
    def ratio_label(size: tuple[int, int]) -> str:
        width, height = size
        ratio = width / max(1, height)
        known_ratios = (
            (21 / 9, "21:9"),
            (1.0, "1:1"),
            (3 / 4, "3:4"),
            (3 / 5, "3:5"),
        )
        for expected, label in known_ratios:
            if abs(ratio - expected) <= 0.005:
                return label
        divisor = math.gcd(max(1, width), max(1, height))
        return f"{width // divisor}:{height // divisor}"

    @staticmethod
    def region_box(region: TextRegion, size: tuple[int, int]) -> tuple[int, int, int, int]:
        width, height = size
        return (
            round(region.x * width),
            round(region.y * height),
            round((region.x + region.width) * width),
            round((region.y + region.height) * height),
        )

    @staticmethod
    def region_text_values(
        recipe: TypographyRecipe,
        *,
        phrase: str,
        note: str,
        folio: str,
        label: str,
    ) -> dict[str, str]:
        head, tail = TypographyRecipeEngine._split_phrase(phrase)
        sources = {
            "phrase": phrase,
            "phrase_head": head,
            "phrase_tail": tail,
            "note": note,
            "folio": folio,
            "label": label,
        }
        return {region.region_id: sources.get(region.source, "") for region in recipe.text_regions}

    def _candidate_modes(
        self,
        *,
        requested_mode: str,
        layout: str,
        visual_role: str,
        page: int,
        phrase: str,
    ) -> list[TypographyMode]:
        candidates: list[TypographyMode] = []
        if requested_mode in ALL_TYPOGRAPHY_MODES:
            candidates.append(cast(TypographyMode, requested_mode))
        elif requested_mode in {"local-cjk-caption", "caption"}:
            candidates.append("safe_zone_caption")
        candidates.extend(ROLE_MODE_PREFERENCES.get(visual_role, ()))
        candidates.extend(LAYOUT_MODE_PREFERENCES.get(layout, ()))
        rotation = [
            "type_led_large",
            "edge_pressed_phrase",
            "diagonal_fragments",
            "ghost_text",
            "archive_microtype",
            "type_in_color_block",
            "margin_scatter",
        ]
        offset = int(hashlib.sha256(f"{page}:{phrase}".encode()).hexdigest()[:4], 16)
        candidates.extend(rotation[(offset + page - 1) % len(rotation) :] + rotation[: (offset + page - 1) % len(rotation)])
        candidates.append("safe_zone_caption")
        unique: list[TypographyMode] = []
        for mode in candidates:
            if mode not in unique:
                unique.append(mode)
        return unique

    @staticmethod
    def _selection_reason(
        *,
        mode: TypographyMode,
        requested_specific: str,
        layout: str,
        visual_role: str,
        transform: str,
    ) -> str:
        if requested_specific == mode:
            base = "沿用冻结的明确排版模式"
        elif mode in ROLE_MODE_PREFERENCES.get(visual_role, ()):
            base = f"按页面职责 {visual_role or '未标注'} 选择"
        else:
            base = f"按视觉版式 {layout or '默认'} 选择"
        return base if transform == "identity" else f"{base}；为避让关键主体采用 {transform}"

    def _recipe_subject_safe(
        self,
        recipe: TypographyRecipe,
        *,
        size: tuple[int, int],
        protected_regions: tuple[tuple[int, int, int, int], ...],
    ) -> bool:
        if not protected_regions:
            return True
        for region in recipe.text_regions:
            if region.role in {"folio", "microtype"}:
                continue
            if recipe.collision_policy == "soft_underlay" and (region.opacity or recipe.opacity) <= 0.18:
                continue
            box = self.region_box(region, size)
            if any(self._overlap(box, protected) for protected in protected_regions):
                return False
        return True

    def _fit_safe_caption(
        self,
        *,
        size: tuple[int, int],
        protected_regions: tuple[tuple[int, int, int, int], ...],
    ) -> TypographyRecipe:
        template = TEMPLATES["safe_zone_caption"]
        transforms = ("identity", "mirror_y", "mirror_x", "mirror_xy")
        for transform in transforms:
            candidate = self._transformed(template, transform)
            if self._recipe_subject_safe(candidate, size=size, protected_regions=protected_regions):
                return candidate.model_copy(update={"transform": transform})
        # A final caption lane must remain bounded even if the provider supplied
        # an overly broad subject estimate. Keep it at the bottom and fail visibly
        # during render if a caller claims that area is also the key subject.
        return template

    @staticmethod
    def _transformed(recipe: TypographyRecipe, transform: str) -> TypographyRecipe:
        regions: list[TextRegion] = []
        for region in recipe.text_regions:
            updates: dict[str, Any] = {}
            if transform in {"mirror_x", "mirror_xy"}:
                updates["x"] = round(1.0 - region.x - region.width, 6)
                if region.alignment == "left":
                    updates["alignment"] = "right"
                elif region.alignment == "right":
                    updates["alignment"] = "left"
            if transform in {"mirror_y", "mirror_xy"}:
                updates["y"] = round(1.0 - region.y - region.height, 6)
            rotation = region.rotation if region.rotation is not None else recipe.rotation
            if rotation and transform in {"mirror_x", "mirror_y"}:
                updates["rotation"] = -rotation
            regions.append(region.model_copy(update=updates))
        return recipe.model_copy(update={"text_regions": regions, "transform": transform})

    def _render_region(
        self,
        canvas: Image.Image,
        *,
        recipe: TypographyRecipe,
        region: TextRegion,
        value: str,
        box: tuple[int, int, int, int],
        rotation: float,
        opacity: float,
        overlaps_subject: bool,
        font_resolver: FontResolver,
        ink: str,
        muted: str,
        paper: str,
        accent: str,
    ) -> tuple[Image.Image, TypographyRegionDiagnostic]:
        width = max(1, box[2] - box[0])
        height = max(1, box[3] - box[1])
        # Region-relative inset keeps microtype and folio lanes usable on both
        # panorama and square outputs. Canvas-relative inset can consume the
        # full height of a deliberately shallow region.
        inset = max(2, int(min(width, height) * region.inset_ratio))
        inner_width = max(1, width - inset * 2)
        inner_height = max(1, height - inset * 2)
        min_dimension = min(canvas.size)
        initial_size = max(12, int(min_dimension * recipe.size_ratio * region.size_scale))
        # Microtype intentionally starts below the general body-text floor.
        # Never let that floor make the descending fit range empty.
        min_size = min(initial_size, max(12, int(min_dimension * 0.015)))
        serif = recipe.font_role == "serif_editorial"
        bold = recipe.weight >= 650
        fitted_font: ImageFont.FreeTypeFont | ImageFont.ImageFont | None = None
        fitted_lines: list[str] = []
        fitted_height = 0
        tracking_px = 0.0
        for font_size in range(initial_size, min_size - 1, -2):
            font = font_resolver(font_size, bold=bold, serif=serif)
            tracking_px = font_size * recipe.tracking
            lines = self._wrap(
                value,
                font=font,
                max_width=inner_width,
                max_lines=region.max_lines,
                tracking=tracking_px,
            )
            if not lines:
                continue
            line_height = max(1, int(font_size * recipe.line_height))
            rendered_height = line_height * len(lines)
            rendered_width = max(self._tracked_text_width(line, font, tracking_px) for line in lines)
            radians = math.radians(abs(rotation))
            rotated_width = rendered_width * math.cos(radians) + rendered_height * math.sin(radians)
            rotated_height = rendered_height * math.cos(radians) + rendered_width * math.sin(radians)
            if rotated_width <= inner_width and rotated_height <= inner_height:
                fitted_font = font
                fitted_lines = lines
                fitted_height = rendered_height
                break
        if fitted_font is None:
            raise ValueError(f"文字区域 {region.region_id} 无法容纳中文内容")

        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        layer_draw = ImageDraw.Draw(layer)
        if region.background_role != "none":
            self._draw_region_background(
                layer_draw,
                role=region.background_role,
                box=(2, 2, max(2, width - 3), max(2, height - 3)),
                paper=paper,
                ink=ink,
                accent=accent,
                opacity=opacity,
            )
        alignment = region.alignment or recipe.alignment
        if region.background_role in {"ink_block", "accent_block"}:
            fill = paper
        elif region.role in {"caption", "microtype", "folio"}:
            fill = muted
        else:
            fill = ink
        fill_rgba = self._rgba(fill, opacity)
        line_height = max(1, int(getattr(fitted_font, "size", initial_size) * recipe.line_height))
        centered_y = (
            (height - fitted_height) // 2
            if region.role in {"title", "fragment", "ghost"}
            else inset
        )
        text_y = max(inset, centered_y)
        for index, line in enumerate(fitted_lines):
            line_width = self._tracked_text_width(line, fitted_font, tracking_px)
            if alignment == "center":
                text_x = (width - line_width) / 2
            elif alignment == "right":
                text_x = width - inset - line_width
            else:
                text_x = inset
            y = text_y + index * line_height
            self._draw_tracked_text(
                layer_draw,
                (text_x, y),
                line,
                font=fitted_font,
                fill=fill_rgba,
                tracking=tracking_px,
            )
        if rotation:
            layer = layer.rotate(rotation, resample=Image.Resampling.BICUBIC, expand=False)

        alpha_bbox = layer.getchannel("A").getbbox()
        clipped = False
        rendered_box: tuple[int, int, int, int] | None = None
        if alpha_bbox:
            rendered_box = (
                box[0] + alpha_bbox[0],
                box[1] + alpha_bbox[1],
                box[0] + alpha_bbox[2],
                box[1] + alpha_bbox[3],
            )
            clipped = (
                alpha_bbox[0] <= 0
                or alpha_bbox[1] <= 0
                or alpha_bbox[2] >= width
                or alpha_bbox[3] >= height
            )
        composed = self._blend(canvas, layer, (box[0], box[1]), recipe.blend_mode)
        diagnostic = TypographyRegionDiagnostic(
            region_id=region.region_id,
            role=region.role,
            source=region.source,
            box=box,
            rendered_box=rendered_box,
            font_size=int(getattr(fitted_font, "size", initial_size)),
            lines=fitted_lines,
            rotation=rotation,
            opacity=opacity,
            overlaps_subject=overlaps_subject,
            clipped=clipped,
        )
        return composed, diagnostic

    @staticmethod
    def _draw_region_background(
        draw: ImageDraw.ImageDraw,
        *,
        role: str,
        box: tuple[int, int, int, int],
        paper: str,
        ink: str,
        accent: str,
        opacity: float,
    ) -> None:
        if role == "paper_veil":
            fill = TypographyRecipeEngine._rgba(paper, min(0.78, max(0.35, opacity * 0.68)))
        elif role == "accent_block":
            fill = TypographyRecipeEngine._rgba(accent, max(0.88, opacity))
        else:
            fill = TypographyRecipeEngine._rgba(ink, max(0.90, opacity))
        radius = max(4, int(min(box[2] - box[0], box[3] - box[1]) * 0.035))
        draw.rounded_rectangle(box, radius=radius, fill=fill)

    @staticmethod
    def _blend(canvas: Image.Image, layer: Image.Image, offset: tuple[int, int], mode: str) -> Image.Image:
        base = canvas.convert("RGBA")
        full = Image.new("RGBA", base.size, (0, 0, 0, 0))
        full.alpha_composite(layer, dest=offset)
        if mode == "normal":
            return Image.alpha_composite(base, full).convert("RGB")
        alpha = full.getchannel("A")
        color = Image.new("RGBA", base.size, (255, 255, 255, 255))
        color.alpha_composite(full)
        if mode == "screen":
            blended = ImageChops.screen(base.convert("RGB"), color.convert("RGB"))
        else:
            blended = ImageChops.multiply(base.convert("RGB"), color.convert("RGB"))
        return Image.composite(blended, base.convert("RGB"), alpha)

    @staticmethod
    def _draw_tracked_text(
        draw: ImageDraw.ImageDraw,
        position: tuple[float, float],
        text: str,
        *,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        fill: tuple[int, int, int, int],
        tracking: float,
    ) -> None:
        x, y = position
        for character in text:
            draw.text((x, y), character, font=font, fill=fill)
            x += draw.textlength(character, font=font) + tracking

    @staticmethod
    def _tracked_text_width(
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        tracking: float,
    ) -> float:
        if not text:
            return 0.0
        return sum(font.getlength(character) for character in text) + tracking * max(
            0,
            len(text) - 1,
        )

    def _wrap(
        self,
        text: str,
        *,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        max_width: int,
        max_lines: int,
        tracking: float,
    ) -> list[str]:
        content = re.sub(r"\s+", " ", str(text or "")).strip()
        if not content:
            return []
        lines: list[str] = []
        current = ""
        for character in content:
            candidate = current + character
            if current and self._tracked_text_width(candidate, font, tracking) > max_width:
                lines.append(current.rstrip())
                current = character.lstrip()
            else:
                current = candidate
        if current:
            lines.append(current.rstrip())
        if len(lines) > max_lines:
            return []
        return self._rebalance_last_line(lines, font=font, max_width=max_width, tracking=tracking)

    def _rebalance_last_line(
        self,
        lines: list[str],
        *,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        max_width: int,
        tracking: float,
    ) -> list[str]:
        if len(lines) < 2:
            return lines

        def visible(value: str) -> int:
            return len(re.sub(r"[\s，。！？、；：,.!?;:（）【】《》「」『』…]", "", value))

        while visible(lines[-1]) < 3 and visible(lines[-2]) > 5:
            moved = lines[-2][-1]
            proposal = moved + lines[-1]
            if self._tracked_text_width(proposal, font, tracking) > max_width:
                break
            lines[-2] = lines[-2][:-1]
            lines[-1] = proposal
        return lines

    @staticmethod
    def _split_phrase(value: str) -> tuple[str, str]:
        text = str(value or "").strip()
        if len(text) <= 4:
            return text, ""
        punctuation = "，。！？；：、,!?;:"
        middle = len(text) // 2
        candidates = [index + 1 for index, character in enumerate(text) if character in punctuation]
        split = min(candidates, key=lambda item: abs(item - middle)) if candidates else middle
        return text[:split].strip(), text[split:].strip()

    @staticmethod
    def _bounded_rect(
        rect: tuple[int, int, int, int],
        size: tuple[int, int],
    ) -> tuple[int, int, int, int]:
        width, height = size
        left, top, right, bottom = rect
        return (
            max(0, min(width, int(left))),
            max(0, min(height, int(top))),
            max(0, min(width, int(right))),
            max(0, min(height, int(bottom))),
        )

    @staticmethod
    def _overlap(
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
    def _rgba(value: str, opacity: float) -> tuple[int, int, int, int]:
        cleaned = str(value or "#000000").lstrip("#")
        if len(cleaned) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", cleaned):
            cleaned = "000000"
        return (
            int(cleaned[0:2], 16),
            int(cleaned[2:4], 16),
            int(cleaned[4:6], 16),
            int(max(0.0, min(1.0, opacity)) * 255),
        )
