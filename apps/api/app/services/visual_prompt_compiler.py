from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from app.core.config import Settings
from app.domain.visual_prompt_schemas import (
    VisualPromptContext,
    VisualPromptFeatureMode,
    VisualPromptMode,
    VisualPromptRecipe,
    VisualPromptSpec,
)
from app.services.model_client import ModelClient, ModelClientError
from app.services.native_skill_manager import NativeSkillError, NativeSkillManager

DEGRADED_FALLBACK = "DEGRADED_FALLBACK"
V03_SKILL_NAME = "gc-minimal-zine-poster-v0-3"
LEGACY_SKILL_NAME = "gc-minimal-zine-poster-v0-1"
V03_SKILL_VERSION = "v0.3.0"
LEGACY_SKILL_VERSION = "v0.1-pinned"
COMPILER_VERSION = "x2red-visual-prompt-compiler-v1"


class VisualPromptCompileError(RuntimeError):
    pass


def canonical_fingerprint(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class VisualPromptCompiler:
    """Compile one page through the pinned Minimal Zine Skill contract.

    This service never calls an image provider. Both the manual web handoff and
    the API image route consume its same ``VisualPromptSpec`` result.
    """

    reference_paths = (
        "references/style-system.md",
        "references/prompt-compiler.md",
        "references/variation-engine.md",
        "references/quality-gate.md",
        "references/reference-analysis.md",
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.manager = NativeSkillManager(settings)
        self.model = ModelClient(settings)

    @property
    def feature_mode(self) -> VisualPromptFeatureMode:
        return self.settings.minimal_zine_prompt_mode

    @staticmethod
    def schema_mode(feature_mode: VisualPromptFeatureMode) -> VisualPromptMode:
        return {
            "legacy": "legacy",
            "skill_v03": "faithful_skill",
            "production": "production_text_safe",
        }[feature_mode]

    def source_fingerprint(
        self,
        context: VisualPromptContext,
        *,
        feature_mode: VisualPromptFeatureMode | None = None,
    ) -> str:
        selected = feature_mode or self.feature_mode
        skill_name = LEGACY_SKILL_NAME if selected == "legacy" else V03_SKILL_NAME
        definition = self.manager.definition(skill_name)
        return canonical_fingerprint(
            {
                "context": context.model_dump(mode="json"),
                "skill_name": skill_name,
                "skill_sha": definition.commit,
                "compiler_version": COMPILER_VERSION,
                "feature_mode": selected,
            }
        )

    def compile(
        self,
        context: VisualPromptContext,
        *,
        feature_mode: VisualPromptFeatureMode | None = None,
        fallback_recipe_factory: Callable[[], VisualPromptRecipe | dict[str, Any]],
        legacy_positive_prompt: str = "",
    ) -> VisualPromptSpec:
        selected = feature_mode or self.feature_mode
        if selected == "legacy":
            recipe = self._coerce_recipe(fallback_recipe_factory(), context)
            positive = legacy_positive_prompt.strip() or self._fallback_positive_prompt(
                context,
                recipe,
            )
            return self._build_spec(
                context=context,
                feature_mode=selected,
                positive_prompt=positive,
                recipe=recipe,
                invariants=["Legacy compiler behavior is active."],
                exclusions=[],
                warnings=["LEGACY_COMPILER_ACTIVE"],
            )

        try:
            bundle = self._skill_bundle()
            response = self.model.chat_json(
                system_prompt=(
                    "You are the pinned gc-minimal-zine-poster v0.3 prompt compiler. "
                    "Return a concrete four-paragraph image prompt and the exact recipe "
                    "you selected. The image is a text-free visual anchor; X2RED performs "
                    "final Chinese typography locally."
                ),
                user_prompt=self._compiler_request(
                    bundle=bundle,
                    context=context,
                    feature_mode=selected,
                ),
                temperature=0.34,
                reasoning_effort="high",
                max_tokens=6000,
            )
            positive_prompt = self._positive_prompt(response)
            recipe = self._coerce_recipe(response.get("recipe"), context)
            invariants = self._string_list(response.get("invariants"))
            exclusions = self._string_list(response.get("exclusions"))
            warnings = self._string_list(response.get("warnings"))
            invariants = self._merge_unique(
                invariants,
                [
                    "Preserve a tall 3:5 aged-paper plate with 70%-90% perceived open paper.",
                    "Keep one imageable visual event and one clearly visible high-chroma hue.",
                    "Final Chinese typography is composed locally by X2RED, never by the image model.",
                ],
            )
            exclusions = self._merge_unique(
                exclusions,
                [
                    "readable Chinese, Latin letters, numbers, logos, signatures, watermarks or UI",
                    "full-bleed commercial advertising, glossy mockups or dense scrapbook clutter",
                ],
            )
            return self._build_spec(
                context=context,
                feature_mode=selected,
                positive_prompt=positive_prompt,
                recipe=recipe,
                invariants=invariants,
                exclusions=exclusions,
                warnings=warnings,
            )
        except (
            ModelClientError,
            NativeSkillError,
            VisualPromptCompileError,
            ValidationError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            recipe = self._coerce_recipe(fallback_recipe_factory(), context)
            detail = re.sub(r"\s+", " ", str(exc)).strip()[:260]
            return self._build_spec(
                context=context,
                feature_mode=selected,
                positive_prompt=self._fallback_positive_prompt(context, recipe),
                recipe=recipe,
                invariants=[
                    "Preserve a tall 3:5 aged-paper plate with 70%-90% perceived open paper.",
                    "Use one text-free visual event; X2RED composes all Chinese locally.",
                ],
                exclusions=[
                    "readable text, logos, signatures, watermarks or UI",
                    "commercial advertising, glossy mockups or dense collage clutter",
                ],
                warnings=[
                    f"{DEGRADED_FALLBACK}: {detail or 'text compiler unavailable'}"
                ],
            )

    def eval_requests(self) -> list[dict[str, Any]]:
        raw = self.manager.read_text(V03_SKILL_NAME, "evals/evals.json")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise VisualPromptCompileError("v0.3 evals/evals.json 无法解析") from exc
        values = payload.get("evals") if isinstance(payload, dict) else None
        if not isinstance(values, list):
            raise VisualPromptCompileError("v0.3 eval 请求缺失")
        return [dict(item) for item in values if isinstance(item, dict)]

    def route_eval_request(self, eval_id: int) -> dict[str, Any]:
        routes = {
            1: "generate",
            2: "generate",
            3: "reference_analysis",
            4: "prompt_only",
            5: "photo_input_identity",
            6: "photo_input_product",
            7: "reference_style_only",
        }
        request = next(
            (item for item in self.eval_requests() if int(item.get("id") or 0) == eval_id),
            None,
        )
        if request is None or eval_id not in routes:
            raise VisualPromptCompileError(f"未知 v0.3 eval 请求：{eval_id}")
        return {
            "skill_name": V03_SKILL_NAME,
            "skill_commit": self.manager.definition(V03_SKILL_NAME).commit,
            "eval_id": eval_id,
            "route": routes[eval_id],
            "request": request,
        }

    def _skill_bundle(self) -> str:
        sections = [
            "# SKILL.md\n" + self.manager.read_text(V03_SKILL_NAME, "SKILL.md")
        ]
        for path in self.reference_paths:
            sections.append(f"# {path}\n" + self.manager.read_text(V03_SKILL_NAME, path))
        sections.append(
            "# evals/evals.json\n"
            + self.manager.read_text(V03_SKILL_NAME, "evals/evals.json")
        )
        return "\n\n".join(sections)

    def _compiler_request(
        self,
        *,
        bundle: str,
        context: VisualPromptContext,
        feature_mode: VisualPromptFeatureMode,
    ) -> str:
        safety = (
            "Preserve the upstream recipe exactly, then make only a text-safe production "
            "adaptation: the image model must render no readable text."
            if feature_mode == "production"
            else "Follow the upstream v0.3 prompt compiler faithfully while keeping final Chinese local."
        )
        model_context = self._model_context_payload(context)
        return f"""
Execute the complete pinned Skill compiler below for exactly one page. {safety}
Use the article and neighboring-page context to choose a distinct, imageable relation.
Do not replace the chosen recipe with defaults after selecting it.
When page_visual_brief is present, it is the sole page-level visual authority. Treat phrase
and note only as local-typography/cache inputs; do not infer a second subject, action, layout,
palette or mood from them. Never override the frozen Visual Bible or PageVisualBrief.

PAGE CONTEXT (only the fields below may influence the image):
{json.dumps(model_context, ensure_ascii=False, indent=2)}

PINNED SKILL AND REFERENCES:
{bundle}

Return JSON only:
{{
  "positive_prompt": "four concrete English paragraphs with substantially more positive pixel information than prohibitions",
  "recipe": {{
    "layout_family": "",
    "anchor_form": "",
    "typography_mode": "local-cjk",
    "texture_mode": "",
    "decorative_system": [""],
    "main_hue": "",
    "mood": ""
  }},
  "invariants": [""],
  "exclusions": ["compact, relevant exclusion"],
  "warnings": []
}}
""".strip()

    @staticmethod
    def _model_context_payload(context: VisualPromptContext) -> dict[str, Any]:
        """Exclude copy-only fields once V2 has frozen the visual authority."""

        brief = context.page_visual_brief
        if brief is None:
            return context.model_dump(mode="json")
        return {
            "variant_id": context.variant_id,
            "page": context.page,
            "total_pages": context.total_pages,
            "visual_bible": context.visual_bible,
            "page_visual_brief": brief.model_dump(mode="json"),
            "previous_page_concept": context.previous_page_concept,
            "next_page_concept": context.next_page_concept,
            "content_recipe": context.content_recipe,
            "source_fit": context.source_fit,
        }

    @staticmethod
    def _positive_prompt(response: dict[str, Any]) -> str:
        value = str(response.get("positive_prompt") or response.get("final_prompt") or "").strip()
        if len(value) < 80:
            raise VisualPromptCompileError("Minimal Zine v0.3 返回的正向 Prompt 过短")
        paragraphs = [item.strip() for item in re.split(r"\n\s*\n", value) if item.strip()]
        if len(paragraphs) != 4:
            raise VisualPromptCompileError("Minimal Zine v0.3 必须返回四段正向 Prompt")
        return "\n\n".join(paragraphs)

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        output: list[str] = []
        for item in value:
            cleaned = re.sub(r"\s+", " ", str(item)).strip()[:500]
            if cleaned and cleaned not in output:
                output.append(cleaned)
        return output[:24]

    @staticmethod
    def _merge_unique(first: list[str], second: list[str]) -> list[str]:
        output: list[str] = []
        for value in [*first, *second]:
            if value and value not in output:
                output.append(value)
        return output[:24]

    def _coerce_recipe(
        self,
        value: VisualPromptRecipe | dict[str, Any] | Any,
        context: VisualPromptContext,
    ) -> VisualPromptRecipe:
        if isinstance(value, VisualPromptRecipe):
            return value
        raw = value if isinstance(value, dict) else {}
        decorative = raw.get("decorative_system")
        if not isinstance(decorative, list):
            decorative = []
        brief = context.page_visual_brief
        return VisualPromptRecipe(
            layout_family=str(
                (brief.layout_family if brief is not None else "")
                or raw.get("layout_family")
                or raw.get("layout")
                or context.layout_hint
                or "center-fragment"
            ),
            anchor_form=str(
                raw.get("anchor_form")
                or raw.get("anchor")
                or context.anchor_hint
                or "object-specimen"
            ),
            typography_mode=str(
                (brief.typography_mode if brief is not None else "")
                or raw.get("typography_mode")
                or raw.get("typography")
                or "local-cjk"
            ),
            texture_mode=str(
                raw.get("texture_mode")
                or raw.get("texture")
                or context.texture_hint
                or "xerox-softness"
            ),
            decorative_system=[str(item) for item in decorative],
            main_hue=str(
                (brief.palette_delta[0] if brief is not None and brief.palette_delta else "")
                or raw.get("main_hue")
                or raw.get("accent")
                or context.main_hue_hint
                or "cobalt"
            ),
            mood=str(
                (brief.reader_emotion if brief is not None else "")
                or raw.get("mood")
                or context.mood_hint
                or context.emotion
                or "quiet"
            ),
        )

    def _build_spec(
        self,
        *,
        context: VisualPromptContext,
        feature_mode: VisualPromptFeatureMode,
        positive_prompt: str,
        recipe: VisualPromptRecipe,
        invariants: list[str],
        exclusions: list[str],
        warnings: list[str],
    ) -> VisualPromptSpec:
        skill_name = LEGACY_SKILL_NAME if feature_mode == "legacy" else V03_SKILL_NAME
        skill_version = (
            LEGACY_SKILL_VERSION if feature_mode == "legacy" else V03_SKILL_VERSION
        )
        source_fingerprint = self.source_fingerprint(
            context,
            feature_mode=feature_mode,
        )
        payload = {
            "schema_version": 1,
            "skill_name": skill_name,
            "skill_version": skill_version,
            "compiler_version": COMPILER_VERSION,
            "mode": self.schema_mode(feature_mode),
            "positive_prompt": positive_prompt.strip(),
            "invariants": invariants,
            "exclusions": exclusions,
            "recipe": recipe.model_dump(mode="json"),
            "source_fingerprint": source_fingerprint,
            "warnings": warnings,
        }
        fingerprint_payload = {
            **payload,
            "skill_sha": self.manager.definition(skill_name).commit,
        }
        return VisualPromptSpec(
            **payload,
            prompt_fingerprint=canonical_fingerprint(fingerprint_payload),
        )

    @staticmethod
    def _fallback_positive_prompt(
        context: VisualPromptContext,
        recipe: VisualPromptRecipe,
    ) -> str:
        brief = context.page_visual_brief
        previous = (
            f"The preceding page uses {context.previous_page_concept}; avoid repeating its silhouette."
            if context.previous_page_concept
            else "Open the series with a singular, immediately legible visual relation."
        )
        following = (
            f"Leave a rhythmic contrast for the next page concept, {context.next_page_concept}."
            if context.next_page_concept
            else "Resolve the series without introducing a second subject."
        )
        evidence = (
            " / ".join(brief.evidence_refs)
            if brief is not None
            else context.evidence_summary
        ) or "the supplied page evidence"
        current_concept = (
            ", ".join(
                value
                for value in (
                    brief.concrete_subject,
                    brief.action_or_relation,
                    brief.setting,
                )
                if value
            )
            if brief is not None
            else context.current_page_concept
        )
        thesis = brief.claim if brief is not None else context.article_thesis
        return "\n\n".join(
            [
                (
                    "Tall vertical 3:5 full-frame aged-paper editorial plate with 70%-90% "
                    f"perceived open paper. Use the {recipe.layout_family} layout as a quiet "
                    "asymmetrical field with one visual event occupying roughly 8%-25% of the canvas."
                ),
                (
                    f"Build one concrete {recipe.anchor_form} from this page concept: "
                    f"{current_concept}. Let it embody the thesis ‘{thesis}’ "
                    f"through visible material evidence from {evidence}, not through a literal caption."
                ),
                (
                    f"Render the anchor with {recipe.texture_mode}; use {recipe.main_hue} as the one "
                    f"clear high-chroma signal against subdued paper and grayscale support. {previous}"
                ),
                (
                    f"Keep a {recipe.mood} editorial atmosphere with diffuse light, matte absorbent "
                    f"paper, scan grain and tactile printed edges. {following} Reserve continuous clean "
                    "paper for X2RED's local typography."
                ),
            ]
        )
