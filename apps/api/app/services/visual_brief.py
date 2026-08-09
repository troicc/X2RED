from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.domain.visual_brief_schemas import (
    FrozenVisualBriefBundle,
    PageVisualBrief,
    PageVisualConceptCandidate,
    PageVisualConceptSet,
    VisualBible,
)
from app.services.editorial import EditorialService
from app.services.visual_distinctness import (
    VisualDistinctnessError,
    VisualDistinctnessService,
)

VISUAL_BRIEF_COMPILER_VERSION = "x2red-visual-brief-v2"
VISUAL_BRIEF_DEGRADED = "DEGRADED_VISUAL_BRIEF"

LAYOUT_FAMILIES = (
    "center-fragment",
    "upper-right-block",
    "dual-panel",
    "lower-left-float",
    "diagonal-notes",
    "edge-counterweight",
    "irregular-cutout",
    "single-specimen",
    "type-led",
    "dot-orbit",
    "lower-fragment",
)
ANCHOR_FAMILIES = (
    "tiny-faded-photo",
    "torn-paper-clipping",
    "old-printed-illustration",
    "flat-silhouette",
    "translucent-geometric-overlay",
    "object-specimen",
)
VISUAL_ROLES = (
    "cover",
    "scene",
    "explanation",
    "evidence",
    "comparison",
    "process",
    "limitation",
    "transition",
    "conclusion",
)

_ROLE_FLOW: dict[int, tuple[str, ...]] = {
    1: ("cover",),
    2: ("cover", "conclusion"),
    3: ("cover", "explanation", "conclusion"),
    4: ("cover", "scene", "evidence", "conclusion"),
    5: ("cover", "scene", "evidence", "process", "conclusion"),
    6: (
        "cover",
        "scene",
        "evidence",
        "comparison",
        "limitation",
        "conclusion",
    ),
}

_PRIMARY_SUBJECTS = (
    "钉在纸面的首张证据照片",
    "并排放置的两条时间刻度带",
    "拆开的三层透明结构片",
    "被朱砂线截断的流程记录带",
    "正反两面的参数标签",
    "收进档案夹的最终核对单",
)
_SECONDARY_SUBJECTS = (
    "俯视工作台上的一组输入部件",
    "两份边缘磨损程度不同的记录页",
    "沿因果顺序展开的四枚结构节点",
    "在边界处停下的测量纸带",
    "显露限制条件的折页说明片",
    "只保留已核对项目的归档封套",
)
_RELATIONS = (
    "让核心证据在系列开头形成单一视觉入口",
    "把前后差异排成可直接比较的空间关系",
    "按由外到内的顺序揭示本页解释机制",
    "让动线在证据所限定的位置明确停止",
    "把适用范围与限制条件放在同一可见关系中",
    "将结论收束回已经出现并可核对的材料",
)


class VisualBriefError(RuntimeError):
    pass


class VisualBriefService:
    """Build a Visual Bible, three concepts per page and one frozen series."""

    def __init__(self, settings: Settings, editorial: EditorialService) -> None:
        self.settings = settings
        self.editorial = editorial
        self.distinctness = VisualDistinctnessService()

    async def build(
        self,
        *,
        article_thesis: str,
        posters: list[dict[str, Any]],
        audience: str,
        visual_style: str,
        content_recipe: str,
        model_name: str,
        reasoning_effort: str,
        use_model: bool,
        visual_memory: str = "",
    ) -> FrozenVisualBriefBundle:
        warnings: list[str] = []
        mode = "deterministic"
        bible = self.default_bible(
            visual_style=visual_style,
            content_recipe=content_recipe,
        )
        if use_model:
            try:
                bible = await self._model_bible(
                    article_thesis=article_thesis,
                    audience=audience,
                    visual_style=visual_style,
                    content_recipe=content_recipe,
                    visual_memory=visual_memory,
                    model_name=model_name,
                    reasoning_effort=reasoning_effort,
                )
                if self._bible_leaks_page_subjects(bible, posters):
                    raise VisualBriefError(
                        "Visual Bible 包含页面级具体对象，不能作为项目不变量"
                    )
                mode = "production"
            except (
                httpx.HTTPError,
                ValidationError,
                VisualBriefError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                warnings.append(
                    f"{VISUAL_BRIEF_DEGRADED}: Visual Bible：{self._detail(exc)}"
                )

        candidate_sets = self._fallback_candidate_sets(
            article_thesis=article_thesis,
            posters=posters,
            bible=bible,
        )
        if use_model and mode == "production":
            try:
                candidate_sets = await self._model_candidate_sets(
                    article_thesis=article_thesis,
                    posters=posters,
                    bible=bible,
                    audience=audience,
                    model_name=model_name,
                    reasoning_effort=reasoning_effort,
                )
            except (
                httpx.HTTPError,
                ValidationError,
                VisualBriefError,
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                warnings.append(
                    f"{VISUAL_BRIEF_DEGRADED}: 三候选：{self._detail(exc)}"
                )
                mode = "deterministic"

        selected, report = self.distinctness.select(candidate_sets)
        if not report.passed:
            candidate_sets = self._fallback_candidate_sets(
                article_thesis=article_thesis,
                posters=posters,
                bible=bible,
                prefer_structured=True,
            )
            selected, report = self.distinctness.select(candidate_sets)
            warnings.append(
                f"{VISUAL_BRIEF_DEGRADED}: 模型候选未通过 distinctness，已使用结构化主编修复"
            )
            mode = "deterministic"
        if not report.passed:
            raise VisualBriefError("结构化视觉候选仍未通过 distinctness 门禁")
        if self._bible_contains_selected_subject(bible, selected):
            bible = self.default_bible(
                visual_style=visual_style,
                content_recipe=content_recipe,
            )
            candidate_sets = self._fallback_candidate_sets(
                article_thesis=article_thesis,
                posters=posters,
                bible=bible,
                prefer_structured=True,
            )
            selected, report = self.distinctness.select(candidate_sets)
            warnings.append(
                f"{VISUAL_BRIEF_DEGRADED}: 项目 Bible 泄漏逐页主体，已重新冻结"
            )
            mode = "deterministic"

        pages = [
            PageVisualConceptSet(
                page=index,
                candidates=values,
                selected_candidate_id=selected[index - 1].candidate_id,
            )
            for index, values in enumerate(candidate_sets, start=1)
        ]
        fingerprint = self.source_fingerprint(
            article_thesis=article_thesis,
            posters=posters,
            bible=bible,
            pages=pages,
            mode=mode,
        )
        return FrozenVisualBriefBundle(
            compiler_version=VISUAL_BRIEF_COMPILER_VERSION,
            mode=mode,
            visual_bible=bible,
            pages=pages,
            distinctness=report,
            source_fingerprint=fingerprint,
            warnings=warnings,
        )

    def build_deterministic(
        self,
        *,
        article_thesis: str,
        posters: list[dict[str, Any]],
        visual_style: str,
        content_recipe: str,
    ) -> FrozenVisualBriefBundle:
        bible = self.default_bible(
            visual_style=visual_style,
            content_recipe=content_recipe,
        )
        candidate_sets = self._fallback_candidate_sets(
            article_thesis=article_thesis,
            posters=posters,
            bible=bible,
            prefer_structured=True,
        )
        try:
            selected, report = self.distinctness.select(candidate_sets)
        except VisualDistinctnessError as exc:
            raise VisualBriefError(str(exc)) from exc
        if not report.passed:
            raise VisualBriefError("确定性视觉简报未通过 distinctness 门禁")
        pages = [
            PageVisualConceptSet(
                page=index,
                candidates=values,
                selected_candidate_id=selected[index - 1].candidate_id,
            )
            for index, values in enumerate(candidate_sets, start=1)
        ]
        return FrozenVisualBriefBundle(
            compiler_version=VISUAL_BRIEF_COMPILER_VERSION,
            mode="deterministic",
            visual_bible=bible,
            pages=pages,
            distinctness=report,
            source_fingerprint=self.source_fingerprint(
                article_thesis=article_thesis,
                posters=posters,
                bible=bible,
                pages=pages,
                mode="deterministic",
            ),
            warnings=[
                f"{VISUAL_BRIEF_DEGRADED}: 未调用视觉简报模型，使用可审计的确定性三候选"
            ],
        )

    def apply_bundle(
        self,
        posters: list[dict[str, Any]],
        bundle: FrozenVisualBriefBundle,
    ) -> list[dict[str, Any]]:
        selected = bundle.selected_candidates()
        if len(selected) != len(posters):
            raise VisualBriefError("冻结视觉简报页数与故事板页数不一致")
        bible = bundle.visual_bible.model_dump(mode="json")
        output: list[dict[str, Any]] = []
        for index, (raw, candidate) in enumerate(zip(posters, selected, strict=True)):
            brief = candidate.brief
            concept_set = bundle.pages[index]
            accent = next(
                (
                    value
                    for value in brief.palette_delta
                    if re.fullmatch(r"#[0-9a-fA-F]{6}", value)
                ),
                "#b65d3c",
            )
            texture = self._texture_for(bundle.visual_bible.print_process)
            concept = "，".join(
                value
                for value in (
                    brief.concrete_subject,
                    brief.action_or_relation,
                    brief.setting,
                )
                if value
            )[:240]
            merged = {
                **raw,
                "article_thesis": brief.claim,
                "section_title": str(raw.get("phrase") or brief.claim)[:300],
                "page_visual_role": brief.visual_role,
                "emotion": brief.reader_emotion,
                "current_page_concept": concept,
                "visual_bible": bible,
                "visual_metaphor": concept,
                "photo_direction": (
                    f"{brief.viewpoint}；{brief.crop}；{brief.lighting}"
                )[:240],
                "layout": brief.layout_family,
                "anchor": candidate.anchor_family,
                "accent": accent,
                "texture": texture,
                "mood": brief.reader_emotion[:80],
                "evidence_summary": str(
                    raw.get("evidence_basis") or brief.claim
                )[:1600],
                "source_refs": brief.evidence_refs,
                "page_visual_brief": brief.model_dump(mode="json"),
                "visual_concept_candidates": [
                    item.model_dump(mode="json") for item in concept_set.candidates
                ],
                "selected_visual_candidate_id": candidate.candidate_id,
                "visual_brief_frozen": True,
                "visual_brief_source_fingerprint": bundle.source_fingerprint,
            }
            merged.pop("series_motif", None)
            output.append(merged)
        return output

    def refreeze_after_human_edit(
        self,
        *,
        previous_bundle: dict[str, Any],
        posters: list[dict[str, Any]],
        article_thesis: str,
    ) -> tuple[FrozenVisualBriefBundle, list[dict[str, Any]]]:
        try:
            previous = FrozenVisualBriefBundle.model_validate(previous_bundle)
        except ValidationError as exc:
            raise VisualBriefError("现有冻结视觉简报损坏，不能在其上静默编辑") from exc
        if len(previous.pages) != len(posters):
            raise VisualBriefError("现有冻结视觉简报页数与故事板不一致")

        page_sets: list[PageVisualConceptSet] = []
        normalized_specs: list[dict[str, Any]] = []
        selected: list[PageVisualConceptCandidate] = []
        for page, (raw, old_page) in enumerate(
            zip(posters, previous.pages, strict=True),
            start=1,
        ):
            raw_brief = raw.get("page_visual_brief")
            if not isinstance(raw_brief, dict):
                raise VisualBriefError(f"第 {page} 页缺少 PageVisualBrief")
            brief = self._freeze_brief(
                raw_brief,
                page=page,
                total=len(posters),
                poster=raw,
                article_thesis=article_thesis,
                bible=previous.visual_bible,
            )
            candidates: list[PageVisualConceptCandidate] = []
            for candidate in old_page.candidates:
                if candidate.candidate_id == old_page.selected_candidate_id:
                    candidate = candidate.model_copy(
                        update={
                            "brief": brief,
                            "anchor_family": str(
                                raw.get("anchor") or candidate.anchor_family
                            ),
                            "rationale": (
                                "人工编辑后重新冻结；Visual Bible 与 evidence refs 保持不变量"
                            ),
                        }
                    )
                    selected.append(candidate)
                candidates.append(candidate)
            page_sets.append(
                PageVisualConceptSet(
                    page=page,
                    candidates=candidates,
                    selected_candidate_id=old_page.selected_candidate_id,
                )
            )
            concept = "，".join(
                value
                for value in (
                    brief.concrete_subject,
                    brief.action_or_relation,
                    brief.setting,
                )
                if value
            )[:240]
            accent = next(
                (
                    value
                    for value in brief.palette_delta
                    if re.fullmatch(r"#[0-9a-fA-F]{6}", value)
                ),
                str(raw.get("accent") or "#b65d3c"),
            )
            normalized = {
                **raw,
                "page_visual_brief": brief.model_dump(mode="json"),
                "page_visual_role": brief.visual_role,
                "current_page_concept": concept,
                "visual_metaphor": concept,
                "layout": brief.layout_family,
                "accent": accent,
                "mood": brief.reader_emotion[:80],
                "visual_bible": previous.visual_bible.model_dump(mode="json"),
                "source_refs": brief.evidence_refs,
                "visual_concept_candidates": [
                    item.model_dump(mode="json") for item in candidates
                ],
                "visual_brief_frozen": True,
            }
            normalized.pop("series_motif", None)
            normalized_specs.append(normalized)

        if len(selected) != len(posters):
            raise VisualBriefError("现有视觉简报缺少选中候选")
        report = self.distinctness.evaluate(selected)
        if not report.passed:
            details = "；".join(
                issue.detail for issue in report.issues if issue.blocking
            )
            raise VisualBriefError(f"编辑后的分镜未通过 distinctness：{details}")
        if self._bible_contains_selected_subject(previous.visual_bible, selected):
            raise VisualBriefError("页面具体主体泄漏进 Visual Bible，拒绝冻结")
        fingerprint = self.source_fingerprint(
            article_thesis=article_thesis,
            posters=normalized_specs,
            bible=previous.visual_bible,
            pages=page_sets,
            mode=previous.mode,
        )
        bundle = FrozenVisualBriefBundle(
            compiler_version=VISUAL_BRIEF_COMPILER_VERSION,
            mode=previous.mode,
            visual_bible=previous.visual_bible,
            pages=page_sets,
            distinctness=report,
            source_fingerprint=fingerprint,
            warnings=[*previous.warnings, "HUMAN_EDITED_VISUAL_BRIEF"],
        )
        for spec in normalized_specs:
            spec["visual_brief_source_fingerprint"] = fingerprint
        return bundle, normalized_specs

    @staticmethod
    def default_bible(*, visual_style: str, content_recipe: str) -> VisualBible:
        identity = (
            f"{visual_style or 'editorial'} · {content_recipe or 'light-series'} 的"
            "克制纸本编辑系统"
        )
        return VisualBible(
            identity=identity,
            paper_system="统一暖白吸墨纸底，保留扫描纤维与轻微旧印刷磨损",
            palette=["#2b2926", "#f2ede3", "#b65d3c", "#365d73"],
            accent_policy="每页只让一个高饱和强调色承担视线锚点，整组不改变色彩角色",
            print_process=["xerox softness", "risograph grain", "letterpress ink bleed"],
            typography_modes=["local-cjk-editorial", "local-cjk-caption"],
            photographic_treatment="低对比纪实片段，保留真实材质，不使用商业棚拍光泽",
            illustration_treatment="单一可辨认主体，以旧印刷、剪贴或平面结构表达可见关系",
            layout_distribution=list(LAYOUT_FAMILIES),
            recurring_motif_policy=(
                "只重复纸张、网点、印刷磨损与强调色规则；不得重复具体主体、轮廓或同一物件"
            ),
            prohibited_cliches=list(VisualDistinctnessService.cliches[:10]),
            invariants=[
                "3:5 竖版纸本编辑画布",
                "每页只有一个具体可画视觉事件",
                "中文与最终版式始终由 X2RED 本地合成",
                "证据决定能画什么，风格记忆只决定怎么画",
            ],
        )

    @staticmethod
    def source_fingerprint(
        *,
        article_thesis: str,
        posters: list[dict[str, Any]],
        bible: VisualBible,
        pages: list[PageVisualConceptSet],
        mode: str,
    ) -> str:
        compact_posters = [
            {
                key: item.get(key)
                for key in (
                    "phrase",
                    "note",
                    "visual_metaphor",
                    "photo_direction",
                    "evidence_basis",
                    "source_refs",
                )
            }
            for item in posters
        ]
        payload = {
            "compiler_version": VISUAL_BRIEF_COMPILER_VERSION,
            "mode": mode,
            "article_thesis": article_thesis,
            "posters": compact_posters,
            "visual_bible": bible.model_dump(mode="json"),
            "pages": [item.model_dump(mode="json") for item in pages],
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    async def _model_bible(
        self,
        *,
        article_thesis: str,
        audience: str,
        visual_style: str,
        content_recipe: str,
        visual_memory: str,
        model_name: str,
        reasoning_effort: str,
    ) -> VisualBible:
        result = await self.editorial._chat_json(
            system_prompt=(
                "你是文章级视觉系统总监。只定义整组的不变量，不得写任何页面级具体物件、人物、场景、"
                "动作或单页构图。Visual Bible 只能决定怎么画，不能替代证据决定画什么。"
            ),
            user_prompt=f"""
文章主张：{article_thesis}
读者：{audience or '普通中文读者'}
内容配方：{content_recipe}
视觉路线：{visual_style}
仅限视觉表达的已批准记忆：{visual_memory or '无'}

先定义一套可供 3—6 页共享、但不含任何页面具体对象的 Visual Bible。
只输出 JSON：{{"visual_bible":{{"identity":"","paper_system":"","palette":["#RRGGBB"],
"accent_policy":"","print_process":[""],"typography_modes":["local-cjk-editorial"],
"photographic_treatment":"","illustration_treatment":"","layout_distribution":["center-fragment","dual-panel","upper-right-block"],
"recurring_motif_policy":"只能重复风格规则，禁止重复具体主体","prohibited_cliches":[""],"invariants":[""]}}}}
""".strip(),
            temperature=0.24,
            reasoning_effort=reasoning_effort,
            model_name=model_name,
        )
        raw = result.get("visual_bible") if isinstance(result, dict) else None
        if not isinstance(raw, dict):
            raise VisualBriefError("模型没有返回 Visual Bible")
        return VisualBible.model_validate(raw)

    async def _model_candidate_sets(
        self,
        *,
        article_thesis: str,
        posters: list[dict[str, Any]],
        bible: VisualBible,
        audience: str,
        model_name: str,
        reasoning_effort: str,
    ) -> list[list[PageVisualConceptCandidate]]:
        page_inputs = [
            {
                "page": index,
                "required_visual_role": self._role_for(index, len(posters)),
                "claim": self._claim(item, article_thesis),
                "phrase": str(item.get("phrase") or ""),
                "note": str(item.get("note") or ""),
                "evidence": str(item.get("evidence_basis") or ""),
                "evidence_refs": self._evidence_refs(item),
                "existing_concept": self._base_subject(item),
            }
            for index, item in enumerate(posters, start=1)
        ]
        result = await self.editorial._chat_json(
            system_prompt=(
                "你是逐页视觉主编。Visual Bible 是不可变项目规则；每页必须给出三个真正不同、"
                "具体可画、能回溯证据的概念。禁止共享同一具体主体，禁止复合抽象隐喻，禁止把技术内容"
                "改成泛鸡汤物件。第一、末页职责不可更改。"
            ),
            user_prompt=f"""
文章主张：{article_thesis}
目标读者：{audience or '普通中文读者'}
冻结 Visual Bible：{json.dumps(bible.model_dump(mode='json'), ensure_ascii=False)}
页面输入：{json.dumps(page_inputs, ensure_ascii=False)}

每页恰好生成 3 个候选。每个候选必须包含 concrete_subject、action_or_relation、visual_role、evidence_refs，
并服从 Visual Bible 的 palette、typography、layout 与 invariants。不能只写“本页变化”。
只输出 JSON：{{"pages":[{{"page":1,"candidates":[{{"candidate_id":"p1-c1","anchor_family":"tiny-faded-photo","rationale":"",
"brief":{{"page":1,"section_id":"page-01","visual_role":"cover","claim":"","reader_emotion":"",
"concrete_subject":"","secondary_subject":"","action_or_relation":"","setting":"","viewpoint":"","crop":"","lighting":"",
"materials":[""],"layout_family":"center-fragment","typography_mode":"local-cjk-editorial","palette_delta":["#RRGGBB"],
"must_preserve":[""],"must_avoid":[""],"evidence_refs":[""]}}}}]}}]}}
""".strip(),
            temperature=0.58,
            reasoning_effort=reasoning_effort,
            model_name=model_name,
        )
        raw_pages = result.get("pages") if isinstance(result, dict) else None
        if not isinstance(raw_pages, list):
            raise VisualBriefError("模型没有返回逐页视觉候选")
        by_page = {
            int(item.get("page") or 0): item
            for item in raw_pages
            if isinstance(item, dict)
        }
        output: list[list[PageVisualConceptCandidate]] = []
        for index, poster in enumerate(posters, start=1):
            page = by_page.get(index)
            values = page.get("candidates") if isinstance(page, dict) else None
            if not isinstance(values, list) or len(values) != 3:
                raise VisualBriefError(f"第 {index} 页没有恰好三个视觉候选")
            output.append(
                [
                    self._coerce_model_candidate(
                        raw,
                        page=index,
                        total=len(posters),
                        candidate_index=candidate_index,
                        poster=poster,
                        article_thesis=article_thesis,
                        bible=bible,
                    )
                    for candidate_index, raw in enumerate(values, start=1)
                ]
            )
        return output

    def _fallback_candidate_sets(
        self,
        *,
        article_thesis: str,
        posters: list[dict[str, Any]],
        bible: VisualBible,
        prefer_structured: bool = False,
    ) -> list[list[PageVisualConceptCandidate]]:
        total = len(posters)
        output: list[list[PageVisualConceptCandidate]] = []
        for page, poster in enumerate(posters, start=1):
            base = self._base_subject(poster)
            primary = _PRIMARY_SUBJECTS[(page - 1) % len(_PRIMARY_SUBJECTS)]
            secondary = _SECONDARY_SUBJECTS[(page - 1) % len(_SECONDARY_SUBJECTS)]
            subjects = [primary, secondary, base] if prefer_structured else [base, primary, secondary]
            page_values: list[PageVisualConceptCandidate] = []
            for candidate_index, subject in enumerate(subjects, start=1):
                layout = LAYOUT_FAMILIES[
                    (page - 1 + (candidate_index - 1) * 3) % len(LAYOUT_FAMILIES)
                ]
                anchor = ANCHOR_FAMILIES[
                    (page - 1 + candidate_index - 1) % len(ANCHOR_FAMILIES)
                ]
                brief = self._freeze_brief(
                    {
                        "page": page,
                        "section_id": f"page-{page:02d}",
                        "visual_role": self._role_for(page, total),
                        "claim": self._claim(poster, article_thesis),
                        "reader_emotion": str(
                            poster.get("mood") or poster.get("emotion") or "克制、清晰"
                        ),
                        "concrete_subject": subject,
                        "secondary_subject": "" if candidate_index == 1 else self._secondary_subject(poster),
                        "action_or_relation": _RELATIONS[(page - 1) % len(_RELATIONS)],
                        "setting": self._setting(poster),
                        "viewpoint": "正俯视或轻微斜俯视，关系一眼可读",
                        "crop": "保留完整主体轮廓与连续中文安全区",
                        "lighting": "低对比漫射光，材质边缘清楚",
                        "materials": [bible.paper_system, bible.print_process[0]],
                        "layout_family": layout,
                        "typography_mode": bible.typography_modes[0],
                        "palette_delta": [
                            self._accent_palette(bible)[
                                (page + candidate_index) % len(self._accent_palette(bible))
                            ]
                        ],
                        "must_preserve": bible.invariants,
                        "must_avoid": [
                            *bible.prohibited_cliches,
                            "模型生成可读文字、Logo、水印或 UI",
                        ],
                        "evidence_refs": self._evidence_refs(poster),
                    },
                    page=page,
                    total=total,
                    poster=poster,
                    article_thesis=article_thesis,
                    bible=bible,
                )
                page_values.append(
                    PageVisualConceptCandidate(
                        candidate_id=f"p{page}-c{candidate_index}",
                        brief=brief,
                        anchor_family=anchor,
                        rationale=(
                            "把当前 evidence ref 转译为一个可见关系；不复用系列中其他页的具体主体"
                        ),
                        editor_score=8.0 - (candidate_index - 1) * 0.2,
                    )
                )
            output.append(page_values)
        return output

    def _coerce_model_candidate(
        self,
        raw: Any,
        *,
        page: int,
        total: int,
        candidate_index: int,
        poster: dict[str, Any],
        article_thesis: str,
        bible: VisualBible,
    ) -> PageVisualConceptCandidate:
        if not isinstance(raw, dict):
            raise VisualBriefError(f"第 {page} 页视觉候选不是对象")
        brief_raw = raw.get("brief")
        if not isinstance(brief_raw, dict):
            raise VisualBriefError(f"第 {page} 页视觉候选缺少 brief")
        brief = self._freeze_brief(
            brief_raw,
            page=page,
            total=total,
            poster=poster,
            article_thesis=article_thesis,
            bible=bible,
        )
        anchor = str(raw.get("anchor_family") or "").strip()
        if anchor not in ANCHOR_FAMILIES:
            anchor = ANCHOR_FAMILIES[(page + candidate_index - 2) % len(ANCHOR_FAMILIES)]
        return PageVisualConceptCandidate(
            candidate_id=str(raw.get("candidate_id") or f"p{page}-c{candidate_index}")[:120],
            brief=brief,
            anchor_family=anchor,
            rationale=str(raw.get("rationale") or "依据页面证据形成独立可画概念")[:400],
            editor_score=float(raw.get("editor_score") or 7.5),
        )

    def _freeze_brief(
        self,
        raw: dict[str, Any],
        *,
        page: int,
        total: int,
        poster: dict[str, Any],
        article_thesis: str,
        bible: VisualBible,
    ) -> PageVisualBrief:
        value = dict(raw)
        value["page"] = page
        value["section_id"] = str(value.get("section_id") or f"page-{page:02d}")
        expected_role = self._role_for(page, total)
        if page in {1, total} or str(value.get("visual_role") or "") not in VISUAL_ROLES:
            value["visual_role"] = expected_role
        value["claim"] = str(value.get("claim") or self._claim(poster, article_thesis))
        value["reader_emotion"] = str(
            value.get("reader_emotion") or poster.get("mood") or "克制、清晰"
        )
        subject = self._strip_variation(str(value.get("concrete_subject") or ""))
        value["concrete_subject"] = subject or self._base_subject(poster)
        value["secondary_subject"] = self._strip_variation(
            str(value.get("secondary_subject") or "")
        )
        value["action_or_relation"] = str(
            value.get("action_or_relation") or _RELATIONS[(page - 1) % len(_RELATIONS)]
        )
        value["setting"] = str(value.get("setting") or self._setting(poster))
        value["viewpoint"] = str(value.get("viewpoint") or "正俯视，空间关系清楚")
        value["crop"] = str(value.get("crop") or "完整保留主体轮廓与中文安全区")
        value["lighting"] = str(value.get("lighting") or "低对比漫射光")
        materials = value.get("materials")
        value["materials"] = (
            [str(item) for item in materials if str(item).strip()]
            if isinstance(materials, list) and materials
            else [bible.paper_system, bible.print_process[0]]
        )
        layout = str(value.get("layout_family") or "")
        value["layout_family"] = (
            layout
            if layout in bible.layout_distribution and layout in LAYOUT_FAMILIES
            else LAYOUT_FAMILIES[(page - 1) % len(LAYOUT_FAMILIES)]
        )
        typography = str(value.get("typography_mode") or "")
        value["typography_mode"] = (
            typography
            if typography in bible.typography_modes
            else bible.typography_modes[0]
        )
        raw_palette = value.get("palette_delta")
        allowed_accents = self._accent_palette(bible)
        palette = [
            str(item)
            for item in raw_palette
            if str(item) in allowed_accents
        ] if isinstance(raw_palette, list) else []
        value["palette_delta"] = palette or [allowed_accents[page % len(allowed_accents)]]
        value["must_preserve"] = self._merge_lists(
            value.get("must_preserve"),
            bible.invariants,
        )
        value["must_avoid"] = self._merge_lists(
            value.get("must_avoid"),
            bible.prohibited_cliches,
        )
        refs = self._merge_lists(value.get("evidence_refs"), self._evidence_refs(poster))
        value["evidence_refs"] = refs or ["当前来源"]
        return PageVisualBrief.model_validate(value)

    @staticmethod
    def _role_for(page: int, total: int) -> str:
        flow = _ROLE_FLOW.get(total) or _ROLE_FLOW[6]
        return flow[min(max(page - 1, 0), len(flow) - 1)]

    @staticmethod
    def _claim(poster: dict[str, Any], article_thesis: str) -> str:
        values = [
            str(poster.get("phrase") or "").strip(),
            str(poster.get("note") or "").strip(),
            str(poster.get("evidence_basis") or "").strip(),
            article_thesis.strip(),
        ]
        return "；".join(value for value in values if value)[:600] or "承接当前文章判断"

    @classmethod
    def _base_subject(cls, poster: dict[str, Any]) -> str:
        value = str(
            poster.get("visual_metaphor")
            or poster.get("photo_direction")
            or "一组可核对的纸本证据片"
        )
        value = cls._strip_variation(value)
        return value[:240] or "一组可核对的纸本证据片"

    @staticmethod
    def _secondary_subject(poster: dict[str, Any]) -> str:
        value = str(poster.get("photo_direction") or "").strip()
        return value[:240]

    @staticmethod
    def _setting(poster: dict[str, Any]) -> str:
        direction = str(poster.get("photo_direction") or "").strip()
        return direction[:240] or "与证据一致的真实工作或生活现场"

    @staticmethod
    def _evidence_refs(poster: dict[str, Any]) -> list[str]:
        raw = poster.get("source_refs")
        refs = [str(item).strip()[:240] for item in raw if str(item).strip()] if isinstance(raw, list) else []
        if refs:
            return list(dict.fromkeys(refs))[:12]
        evidence = str(poster.get("evidence_basis") or "").strip()
        return [evidence[:120]] if evidence else ["当前来源"]

    @staticmethod
    def _merge_lists(first: Any, second: list[str]) -> list[str]:
        values = first if isinstance(first, list) else []
        output: list[str] = []
        for raw in [*values, *second]:
            value = " ".join(str(raw).split())[:240]
            if value and value not in output:
                output.append(value)
        return output[:24]

    @staticmethod
    def _strip_variation(value: str) -> str:
        cleaned = re.sub(r"^.*?；\s*本页变化[：:]\s*", "", value.strip())
        cleaned = re.sub(r"^本页变化[：:]\s*", "", cleaned)
        return " ".join(cleaned.split())

    @staticmethod
    def _texture_for(processes: list[str]) -> str:
        combined = " ".join(processes).casefold()
        if "riso" in combined or "孔版" in combined:
            return "risograph-grain"
        if "letterpress" in combined or "活版" in combined:
            return "letterpress-ink-bleed"
        if "halftone" in combined or "半色调" in combined:
            return "halftone-degradation"
        return "xerox-softness"

    @staticmethod
    def _accent_palette(bible: VisualBible) -> list[str]:
        return bible.palette[2:] if len(bible.palette) > 2 else bible.palette

    @classmethod
    def _bible_leaks_page_subjects(
        cls,
        bible: VisualBible,
        posters: list[dict[str, Any]],
    ) -> bool:
        bible_key = cls._semantic_key(
            json.dumps(bible.model_dump(mode="json"), ensure_ascii=False)
        )
        for poster in posters:
            subject = cls._semantic_key(cls._base_subject(poster))
            if len(subject) >= 6 and subject in bible_key:
                return True
        return False

    @classmethod
    def _bible_contains_selected_subject(
        cls,
        bible: VisualBible,
        selected: list[PageVisualConceptCandidate],
    ) -> bool:
        bible_key = cls._semantic_key(
            json.dumps(bible.model_dump(mode="json"), ensure_ascii=False)
        )
        return any(
            len(subject) >= 6 and subject in bible_key
            for subject in (
                cls._semantic_key(item.brief.concrete_subject) for item in selected
            )
        )

    @staticmethod
    def _semantic_key(value: str) -> str:
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())

    @staticmethod
    def _detail(exc: Exception) -> str:
        return " ".join(str(exc).split())[:260] or exc.__class__.__name__
