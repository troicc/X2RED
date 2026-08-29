from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import DraftRevision, ReviewDecision, SourceItem, new_id, utcnow
from app.domain.platforms import PlatformVariant
from app.domain.pool_memory import PoolMemorySnapshot, PoolMemoryUsage
from app.domain.pool_memory_schemas import PoolMemoryContent
from app.domain.review_artifacts import ReviewArtifact, ReviewArtifactState
from app.domain.studio import PatternCard, WritingArtifact, WritingFeedback, WritingProject
from app.services.retrieval import bounded_json, keyword_digest, lexical_terms, term_similarity

if TYPE_CHECKING:
    from app.services.editorial import EditorialService


FACT_BOUNDARY = (
    "池子记忆不是事实来源。历史文章中的人名、数字、日期、结果和因果判断不得进入当前文章，"
    "除非它们同时存在于当前 evidence_pack 或当前来源。"
)

ROLE_DIMENSIONS: dict[str, set[str]] = {
    "editor_in_chief": {"identity", "reader_relationship", "judgment", "tone"},
    "outline_architect": {"opening", "structure", "transition", "ending"},
    "writer": {
        "identity",
        "tone",
        "sentence_rhythm",
        "paragraph_rhythm",
        "opening",
        "title",
        "structure",
        "transition",
        "judgment",
        "ending",
        "forbidden_expression",
        "positive_phrase",
    },
    "reader_reviewer": {"reader_relationship", "opening", "transition", "ending"},
    "style_reviewer": {
        "identity",
        "tone",
        "sentence_rhythm",
        "paragraph_rhythm",
        "forbidden_expression",
        "positive_phrase",
        "judgment",
    },
    "chief_editor": {
        "identity",
        "reader_relationship",
        "judgment",
        "forbidden_expression",
        "structure",
    },
    "final_reviser": {
        "identity",
        "tone",
        "sentence_rhythm",
        "paragraph_rhythm",
        "opening",
        "structure",
        "judgment",
        "ending",
        "forbidden_expression",
        "positive_phrase",
    },
    "visual_director": {"visual_direction", "layout_preference"},
    "visual": {"visual_direction", "layout_preference"},
    "transform": {
        "identity",
        "tone",
        "sentence_rhythm",
        "paragraph_rhythm",
        "opening",
        "title",
        "structure",
        "transition",
        "judgment",
        "ending",
        "forbidden_expression",
        "positive_phrase",
    },
}

FACT_ONLY_ROLES = {"evidence_researcher", "fact_reviewer", "culture_reviewer"}

SOURCE_WEIGHTS = {
    "writing_feedback": 3.0,
    "manual_rule": 2.8,
    "negative_example": 2.7,
    "positive_example": 2.4,
    "approved_output": 2.0,
    "authorized_sample": 1.8,
    "visual_reference": 1.7,
    "pattern_card": 1.0,
    "draft_revision": 2.0,
    "platform_variant": 2.0,
    "writing_artifact": 2.0,
    "review_artifact": 1.8,
}

_VALID_DIMENSIONS = set().union(*ROLE_DIMENSIONS.values())


class PoolMemoryError(ValueError):
    pass


class PoolMemoryService:
    """Human-gated, append-only personal memory with deterministic retrieval."""

    def __init__(
        self,
        settings: Settings | None = None,
        editorial: EditorialService | None = None,
    ) -> None:
        self.settings = settings
        self.editorial = editorial

    @staticmethod
    def _json(value: str, fallback: Any) -> Any:
        try:
            parsed = json.loads(value or "")
        except (TypeError, json.JSONDecodeError):
            return fallback
        return parsed

    @staticmethod
    def _object(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _list(value: Any) -> list[Any]:
        return value if isinstance(value, list) else []

    @staticmethod
    def _compact(value: Any, limit: int) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"

    @staticmethod
    def _dedupe(values: list[Any], *, limit: int = 30, chars: int = 300) -> list[str]:
        output: list[str] = []
        for raw in values:
            value = re.sub(r"\s+", " ", str(raw or "")).strip()[:chars]
            if value and value not in output:
                output.append(value)
            if len(output) >= limit:
                break
        return output

    @staticmethod
    def _next_version(db: Session, artifact_type: str) -> int:
        current = db.scalar(
            select(func.max(ReviewArtifact.version)).where(
                ReviewArtifact.scope_type == "pool_memory",
                ReviewArtifact.scope_id == "default",
                ReviewArtifact.artifact_type == artifact_type,
            )
        )
        return int(current or 0) + 1

    def _normalize_memory(
        self,
        value: Any,
        *,
        usage_policy: str,
    ) -> dict[str, Any]:
        raw = self._object(value)
        examples: list[dict[str, str]] = []
        for item in self._list(raw.get("positive_examples"))[:12]:
            if isinstance(item, str):
                text = self._compact(item, 120)
                lesson = ""
            elif isinstance(item, dict):
                text = self._compact(item.get("text"), 120)
                lesson = self._compact(item.get("lesson"), 240)
            else:
                continue
            if text:
                examples.append({"text": text, "lesson": lesson})
        if usage_policy == "abstract_pattern_only":
            examples = []
        normalized = {
            "rules": self._dedupe(self._list(raw.get("rules"))),
            "avoid": self._dedupe(self._list(raw.get("avoid"))),
            "prefer": self._dedupe(self._list(raw.get("prefer"))),
            "positive_examples": examples,
            "structure": self._dedupe(self._list(raw.get("structure")), limit=20),
            "visual_directions": self._dedupe(self._list(raw.get("visual_directions")), limit=20),
        }
        try:
            return PoolMemoryContent.model_validate(normalized).model_dump()
        except ValueError as exc:
            raise PoolMemoryError(str(exc)) from exc

    def _normalize_card(self, payload: dict[str, Any]) -> dict[str, Any]:
        usage_policy = str(payload.get("usage_policy") or "style_and_structure_only")
        if usage_policy not in {
            "style_and_structure_only",
            "abstract_pattern_only",
            "visual_only",
        }:
            raise PoolMemoryError("未知的记忆使用策略")
        dimensions = self._dedupe(self._list(payload.get("dimensions")), limit=15, chars=60)
        dimensions = [item for item in dimensions if item in _VALID_DIMENSIONS]
        if not dimensions:
            raise PoolMemoryError("至少选择一个有效学习维度")
        if usage_policy == "visual_only":
            dimensions = [
                item for item in dimensions if item in {"visual_direction", "layout_preference"}
            ]
            if not dimensions:
                raise PoolMemoryError("视觉记忆必须选择视觉方向或版式偏好")
        scope_raw = self._object(payload.get("scope"))
        scope = {
            key: self._dedupe(self._list(scope_raw.get(key)), limit=30, chars=120)
            for key in (
                "platforms",
                "formats",
                "article_types",
                "style_profile_ids",
                "topics",
                "audiences",
                "recipes",
                "visual_routes",
            )
        }
        source = self._object(payload.get("source"))
        normalized = {
            "schema_version": 1,
            "title": self._compact(payload.get("title"), 160) or "未命名池子记忆",
            "source": {
                "kind": self._compact(source.get("kind"), 60) or "manual_rule",
                "id": self._compact(source.get("id"), 64),
                "label": self._compact(source.get("label"), 240),
            },
            "dimensions": dimensions,
            "scope": scope,
            "memory": self._normalize_memory(payload.get("memory"), usage_policy=usage_policy),
            "usage_policy": usage_policy,
            "note": self._compact(payload.get("note"), 3000),
            "extraction_mode": self._compact(payload.get("extraction_mode"), 60),
            "eligibility": self._object(payload.get("eligibility")),
            "supersedes_id": self._compact(payload.get("supersedes_id"), 64),
        }
        return normalized

    @staticmethod
    def _source_title(source: SourceItem | None) -> str:
        if source is None:
            return ""
        structured = PoolMemoryService._object(
            PoolMemoryService._json(source.structured_content_json, {})
        )
        title = str(structured.get("title") or "").strip()
        if title:
            return title[:160]
        first = re.split(r"[。！？!?\n]", source.text_original or "", maxsplit=1)[0].strip()
        return first[:160] or source.author_name or source.author_handle or "来源"

    def _material_from_source(
        self,
        db: Session,
        *,
        source_kind: str,
        source_id: str,
    ) -> dict[str, Any]:
        if source_kind == "draft_revision":
            draft = db.get(DraftRevision, source_id)
            if draft is None:
                raise PoolMemoryError("草稿版本不存在")
            source = db.get(SourceItem, draft.source_id)
            approved = bool(
                db.scalar(
                    select(ReviewDecision.id).where(
                        ReviewDecision.draft_id == draft.id,
                        ReviewDecision.decision == "approved",
                        ReviewDecision.facts_checked.is_(True),
                    )
                )
            )
            return {
                "title": draft.title or self._source_title(source),
                "text": draft.body,
                "source": {"kind": source_kind, "id": draft.id, "label": draft.title},
                "scope": {
                    "platforms": ["xhs"],
                    "formats": ["caption"],
                    "article_types": [draft.style] if draft.style else [],
                },
                "eligibility": {
                    "eligible": approved or draft.created_by == "human",
                    "reason": (
                        "草稿已有人工事实批准"
                        if approved
                        else "人工编辑版本"
                        if draft.created_by == "human"
                        else "草稿尚未完成事实与权利确认"
                    ),
                    "requires_confirmation": not approved,
                },
                "metadata": {"tags": draft.tags, "created_by": draft.created_by},
            }

        if source_kind == "platform_variant":
            variant = db.get(PlatformVariant, source_id)
            if variant is None:
                raise PoolMemoryError("平台版本不存在")
            metadata = self._object(self._json(variant.metadata_json, {}))
            approved = bool(metadata.get("human_approved"))
            scope = {
                "platforms": [variant.platform],
                "formats": [variant.format],
                "article_types": [],
                "recipes": [str(metadata.get("recipe"))] if metadata.get("recipe") else [],
                "audiences": [str(metadata.get("audience"))] if metadata.get("audience") else [],
                "visual_routes": (
                    [str(metadata.get("visual_style"))] if metadata.get("visual_style") else []
                ),
            }
            return {
                "title": variant.title,
                "text": variant.body_markdown,
                "source": {"kind": source_kind, "id": variant.id, "label": variant.title},
                "scope": scope,
                "eligibility": {
                    "eligible": approved,
                    "reason": "平台版本已人工批准" if approved else "平台版本尚未人工批准",
                    "requires_confirmation": not approved,
                },
                "metadata": metadata,
            }

        if source_kind == "writing_feedback":
            feedback = db.get(WritingFeedback, source_id)
            if feedback is None:
                raise PoolMemoryError("写作反馈不存在")
            project = db.get(WritingProject, feedback.project_id)
            before = (
                db.get(DraftRevision, feedback.draft_before_id)
                if feedback.draft_before_id
                else None
            )
            after = (
                db.get(DraftRevision, feedback.draft_after_id) if feedback.draft_after_id else None
            )
            diff = self._object(self._json(feedback.diff_json, {}))
            affected = self._list(self._json(feedback.affected_rules_json, []))
            text = "\n".join(
                item
                for item in (
                    f"反馈理由：{feedback.feedback_reason}" if feedback.feedback_reason else "",
                    f"受影响规则：{'；'.join(str(item) for item in affected)}" if affected else "",
                    f"修改前：{before.body[:4000]}" if before else "",
                    f"修改后：{after.body[:4000]}" if after else "",
                    f"差异：{bounded_json(diff, 5000)}" if diff else "",
                )
                if item
            )
            return {
                "title": feedback.feedback_reason[:120] or "真实改稿反馈",
                "text": text,
                "source": {
                    "kind": source_kind,
                    "id": feedback.id,
                    "label": feedback.feedback_reason or "真实改稿反馈",
                },
                "scope": {
                    "platforms": ["xhs"],
                    "formats": ["article"],
                    "article_types": [],
                    "style_profile_ids": (
                        [project.style_profile_id] if project and project.style_profile_id else []
                    ),
                },
                "eligibility": {
                    "eligible": True,
                    "reason": "用户主动保存的真实改稿反馈",
                    "requires_confirmation": False,
                },
                "metadata": {"affected_rules": affected, "diff": diff},
            }

        if source_kind == "pattern_card":
            pattern = db.get(PatternCard, source_id)
            if pattern is None:
                raise PoolMemoryError("模式卡不存在")
            text = "\n".join(
                item
                for item in (
                    f"开头模式：{pattern.hook_pattern}" if pattern.hook_pattern else "",
                    f"结构模式：{pattern.structure_pattern}" if pattern.structure_pattern else "",
                    f"读者触发：{pattern.audience_trigger}" if pattern.audience_trigger else "",
                    f"证据方式：{pattern.evidence_pattern}" if pattern.evidence_pattern else "",
                    f"可复用元素：{pattern.replicable_elements_json}",
                    f"不可复用语境：{pattern.non_replicable_context_json}",
                )
                if item
            )
            return {
                "title": pattern.name,
                "text": text,
                "source": {"kind": source_kind, "id": pattern.id, "label": pattern.name},
                "scope": {
                    "topics": self._list(self._json(pattern.suitable_topics_json, [])),
                    "article_types": [pattern.category] if pattern.category != "general" else [],
                },
                "eligibility": {
                    "eligible": True,
                    "reason": "模式卡只提取抽象结构",
                    "requires_confirmation": False,
                },
                "metadata": {},
            }

        if source_kind == "writing_artifact":
            artifact = db.get(WritingArtifact, source_id)
            if artifact is None:
                raise PoolMemoryError("写作产物不存在")
            if artifact.artifact_type not in {"draft", "final_draft"}:
                raise PoolMemoryError("只有初稿或终稿写作产物可以提炼记忆")
            project = db.get(WritingProject, artifact.project_id)
            content = self._object(self._json(artifact.content_json, {}))
            title = str(content.get("title") or "多 Agent 终稿")
            return {
                "title": title,
                "text": str(content.get("body") or ""),
                "source": {"kind": source_kind, "id": artifact.id, "label": title},
                "scope": {
                    "platforms": ["xhs"],
                    "formats": ["article"],
                    "style_profile_ids": (
                        [project.style_profile_id] if project and project.style_profile_id else []
                    ),
                },
                "eligibility": {
                    "eligible": bool(artifact.approved),
                    "reason": "写作产物已由作者确认"
                    if artifact.approved
                    else "写作产物尚未由作者确认",
                    "requires_confirmation": not artifact.approved,
                },
                "metadata": {},
            }

        if source_kind == "review_artifact":
            artifact = db.get(ReviewArtifact, source_id)
            if artifact is None:
                raise PoolMemoryError("审核产物不存在")
            if not (
                artifact.scope_type == "light_corpus"
                and artifact.artifact_type == "light_corpus_item"
                and artifact.state == ReviewArtifactState.approved.value
            ):
                raise PoolMemoryError("只有已批准的授权轻内容语料可以提炼")
            payload = self._object(self._json(artifact.payload_json, {}))
            return {
                "title": str(payload.get("title") or "已批准轻内容语料"),
                "text": str(payload.get("body_markdown") or ""),
                "source": {
                    "kind": str(payload.get("source_kind") or "authorized_sample"),
                    "id": artifact.id,
                    "label": str(payload.get("title") or "已批准轻内容语料"),
                },
                "scope": {
                    "platforms": ["wechat"],
                    "formats": ["light_series"],
                    "recipes": [artifact.scope_id],
                    "visual_routes": (
                        [str(payload.get("visual_style"))] if payload.get("visual_style") else []
                    ),
                },
                "eligibility": {
                    "eligible": True,
                    "reason": "已有私有语料的人类批准状态",
                    "requires_confirmation": False,
                },
                "metadata": payload,
            }

        raise PoolMemoryError("不支持的记忆来源类型")

    @staticmethod
    def _merge_scope(
        defaults: dict[str, Any],
        requested: dict[str, Any],
    ) -> dict[str, list[str]]:
        keys = (
            "platforms",
            "formats",
            "article_types",
            "style_profile_ids",
            "topics",
            "audiences",
            "recipes",
            "visual_routes",
        )
        output: dict[str, list[str]] = {}
        for key in keys:
            provided = requested.get(key)
            values = provided if isinstance(provided, list) and provided else defaults.get(key, [])
            output[key] = [str(item) for item in values if str(item).strip()]
        return output

    def _fallback_extraction(
        self,
        material: dict[str, Any],
        *,
        source_kind: str,
        dimensions: list[str],
    ) -> dict[str, Any]:
        text = str(material.get("text") or "")
        metadata = self._object(material.get("metadata"))
        sentences = [
            self._compact(item, 120)
            for item in re.split(r"(?<=[。！？!?])|\n+", text)
            if len(re.sub(r"\s+", "", item)) >= 4
        ]
        rules: list[str] = []
        avoid: list[str] = []
        prefer: list[str] = []
        structure: list[str] = []
        visual: list[str] = []
        examples: list[dict[str, str]] = []

        if source_kind == "writing_feedback":
            affected = self._dedupe(self._list(metadata.get("affected_rules")), limit=12)
            avoid.extend(affected)
            reason = re.sub(r"^反馈理由：", "", sentences[0]).strip() if sentences else ""
            if reason:
                rules.append(reason)
            if len(sentences) >= 2:
                prefer.append("以后遇到相同文章类型时，优先保留用户修改后的表达方向")
        else:
            if "opening" in dimensions and sentences:
                rules.append("开头直接进入具体变化、场景或读者问题，不先堆定义")
                examples.append({"text": sentences[0], "lesson": "仅学习开头动作，不继承其中事实"})
            if "title" in dimensions:
                rules.append("标题给出具体信息增量，不使用空泛承诺或模板悬念")
            if {"sentence_rhythm", "paragraph_rhythm"} & set(dimensions):
                rules.append("句子和段落保持长短变化，每段只承担一个认知任务")
            if "structure" in dimensions:
                headings = re.findall(r"(?m)^#{1,3}\s+(.+)$", text)
                structure = self._dedupe(headings, limit=10, chars=80)
                if not structure:
                    structure = ["先交代结果或场景", "解释问题与机制", "说明限制", "给出作者判断"]
            if "judgment" in dimensions and sentences:
                prefer.append("判断落到可验证效果、适用范围或下一项值得观察的问题")
                if len(sentences) > 1:
                    examples.append(
                        {"text": sentences[-1], "lesson": "仅学习收束方式，不继承结论事实"}
                    )
            if "forbidden_expression" in dimensions:
                avoid.extend(["值得注意的是", "总的来说", "不难发现"])

        if {"visual_direction", "layout_preference"} & set(dimensions):
            style = metadata.get("visual_style")
            if style:
                visual.append(f"视觉路线优先参考 {style}，但必须服从当前内容")
            posters = self._list(metadata.get("poster_specs"))
            for poster in posters[:4]:
                if not isinstance(poster, dict):
                    continue
                direction = "；".join(
                    str(poster.get(key) or "")
                    for key in ("layout", "visual_metaphor", "mood")
                    if poster.get(key)
                )
                if direction:
                    visual.append(direction)

        if not any((rules, avoid, prefer, examples, structure, visual)):
            rules.append("只保留这条来源中由用户确认的表达偏好，生成前必须再次人工检查")
        return {
            "rules": rules,
            "avoid": avoid,
            "prefer": prefer,
            "positive_examples": examples,
            "structure": structure,
            "visual_directions": visual,
        }

    async def _model_extraction(
        self,
        material: dict[str, Any],
        *,
        dimensions: list[str],
        usage_policy: str,
    ) -> dict[str, Any] | None:
        if not (
            self.settings
            and self.editorial
            and self.settings.model_base_url
            and self.settings.model_name
        ):
            return None
        prompt = f"""
把下面这份经过用户主动选择的内容提炼为个人写作记忆候选。只提炼表达、结构、节奏、判断方式、
禁止表达或视觉方向，绝不能把人名、数字、日期、测试结果、行业结论或因果判断变成跨文章事实。

学习维度：{json.dumps(dimensions, ensure_ascii=False)}
使用策略：{usage_policy}
内容：{str(material.get("text") or "")[:12000]}

正向例句只能保留不超过 120 字的短片段，并注明只学习什么；第三方抽象模式不得返回例句。
只输出 JSON：
{{"rules":["规则"],"avoid":["禁止"],"prefer":["偏好"],
"positive_examples":[{{"text":"短例句","lesson":"学习点"}}],
"structure":["结构步骤"],"visual_directions":["视觉方向"]}}
""".strip()
        try:
            return await self.editorial._chat_json(
                system_prompt="你是个人风格记忆提炼器，只生成待人类编辑批准的候选卡。",
                user_prompt=prompt,
                temperature=0.2,
                reasoning_effort="medium",
                model_name=self.settings.model_name,
            )
        except Exception:  # noqa: BLE001 - extraction failure must fall back to local rules
            return None

    async def create_candidate(
        self,
        db: Session,
        *,
        source_kind: str,
        source_id: str,
        title: str,
        dimensions: list[str],
        scope: dict[str, Any],
        usage_policy: str,
        note: str,
    ) -> ReviewArtifact:
        if source_kind == "pattern_card":
            usage_policy = "abstract_pattern_only"
        material = self._material_from_source(
            db,
            source_kind=source_kind,
            source_id=source_id,
        )
        extracted = await self._model_extraction(
            material,
            dimensions=dimensions,
            usage_policy=usage_policy,
        )
        extraction_mode = "model_candidate" if extracted is not None else "structured_fallback"
        if extracted is None:
            extracted = self._fallback_extraction(
                material,
                source_kind=source_kind,
                dimensions=dimensions,
            )
        payload = self._normalize_card(
            {
                "title": title or material.get("title"),
                "source": material.get("source"),
                "dimensions": dimensions,
                "scope": self._merge_scope(
                    self._object(material.get("scope")),
                    self._object(scope),
                ),
                "memory": extracted,
                "usage_policy": usage_policy,
                "note": note,
                "extraction_mode": extraction_mode,
                "eligibility": material.get("eligibility"),
            }
        )
        artifact = ReviewArtifact(
            scope_type="pool_memory",
            scope_id="default",
            artifact_type="memory_candidate",
            version=self._next_version(db, "memory_candidate"),
            payload_json=json.dumps(payload, ensure_ascii=False),
            state=ReviewArtifactState.draft.value,
            review_note=note.strip()[:3000],
            created_by="model" if extracted and extraction_mode == "model_candidate" else "system",
            applied_to_id=source_id,
        )
        db.add(artifact)
        db.flush()
        return artifact

    def update_candidate(
        self,
        db: Session,
        candidate: ReviewArtifact,
        *,
        title: str,
        dimensions: list[str],
        scope: dict[str, Any],
        memory: dict[str, Any],
        usage_policy: str,
        note: str,
    ) -> ReviewArtifact:
        if not self._is_candidate(candidate) or candidate.state != ReviewArtifactState.draft.value:
            raise PoolMemoryError("只有待批准候选可以编辑")
        previous = self._object(self._json(candidate.payload_json, {}))
        payload = self._normalize_card(
            {
                **previous,
                "title": title,
                "dimensions": dimensions,
                "scope": scope,
                "memory": memory,
                "usage_policy": usage_policy,
                "note": note,
                "extraction_mode": "human_edited_candidate",
            }
        )
        revised = ReviewArtifact(
            scope_type="pool_memory",
            scope_id="default",
            artifact_type="memory_candidate",
            version=self._next_version(db, "memory_candidate"),
            parent_id=candidate.id,
            payload_json=json.dumps(payload, ensure_ascii=False),
            state=ReviewArtifactState.draft.value,
            review_note=note.strip()[:3000],
            created_by="human",
            applied_to_id=candidate.applied_to_id,
        )
        candidate.state = ReviewArtifactState.superseded.value
        db.add(revised)
        db.flush()
        return revised

    def approve_candidate(
        self,
        db: Session,
        candidate: ReviewArtifact,
        *,
        review_note: str,
        confirm_source_authorized: bool,
    ) -> ReviewArtifact:
        if not self._is_candidate(candidate) or candidate.state != ReviewArtifactState.draft.value:
            raise PoolMemoryError("候选不存在、已失效或已经处理")
        payload = self._normalize_card(self._object(self._json(candidate.payload_json, {})))
        eligibility = self._object(payload.get("eligibility"))
        if eligibility.get("requires_confirmation") and not confirm_source_authorized:
            raise PoolMemoryError("该来源尚未完成授权或人工批准，请确认后再加入正式池子")
        card = ReviewArtifact(
            scope_type="pool_memory",
            scope_id="default",
            artifact_type="memory_card",
            version=self._next_version(db, "memory_card"),
            parent_id=candidate.id,
            payload_json=json.dumps(payload, ensure_ascii=False),
            state=ReviewArtifactState.approved.value,
            review_note=review_note.strip()[:3000],
            created_by="human",
            applied_to_id=candidate.applied_to_id,
            approved_at=utcnow(),
        )
        db.add(card)
        db.flush()
        candidate.state = ReviewArtifactState.applied.value
        candidate.applied_to_id = card.id
        db.flush()
        return card

    def add_manual_memory(
        self,
        db: Session,
        *,
        title: str,
        dimensions: list[str],
        scope: dict[str, Any],
        memory: dict[str, Any],
        usage_policy: str,
        note: str,
        confirm_original_or_authorized: bool,
    ) -> ReviewArtifact:
        if not confirm_original_or_authorized:
            raise PoolMemoryError("请确认这条手工记忆由你原创或已获授权")
        manual_id = new_id("manual_memory")
        payload = self._normalize_card(
            {
                "title": title,
                "source": {"kind": "manual_rule", "id": manual_id, "label": title},
                "dimensions": dimensions,
                "scope": scope,
                "memory": memory,
                "usage_policy": usage_policy,
                "note": note,
                "extraction_mode": "human_authored",
                "eligibility": {
                    "eligible": True,
                    "reason": "用户手工编写并确认授权",
                    "requires_confirmation": False,
                },
            }
        )
        artifact = ReviewArtifact(
            scope_type="pool_memory",
            scope_id="default",
            artifact_type="memory_card",
            version=self._next_version(db, "memory_card"),
            payload_json=json.dumps(payload, ensure_ascii=False),
            state=ReviewArtifactState.approved.value,
            review_note=note.strip()[:3000],
            created_by="human",
            applied_to_id=manual_id,
            approved_at=utcnow(),
        )
        db.add(artifact)
        db.flush()
        return artifact

    def supersede_memory(
        self,
        db: Session,
        current: ReviewArtifact,
        *,
        title: str,
        dimensions: list[str],
        scope: dict[str, Any],
        memory: dict[str, Any],
        usage_policy: str,
        note: str,
        reason: str,
    ) -> ReviewArtifact:
        self._require_approved_memory(current)
        payload = self._normalize_card(
            {
                "title": title,
                "source": {
                    "kind": "manual_rule",
                    "id": new_id("replacement_memory"),
                    "label": title,
                },
                "dimensions": dimensions,
                "scope": scope,
                "memory": memory,
                "usage_policy": usage_policy,
                "note": note,
                "extraction_mode": "human_superseding_rule",
                "eligibility": {
                    "eligible": True,
                    "reason": "用户明确替代旧记忆",
                    "requires_confirmation": False,
                },
                "supersedes_id": current.id,
            }
        )
        replacement = ReviewArtifact(
            scope_type="pool_memory",
            scope_id="default",
            artifact_type="memory_card",
            version=self._next_version(db, "memory_card"),
            parent_id=current.id,
            payload_json=json.dumps(payload, ensure_ascii=False),
            state=ReviewArtifactState.approved.value,
            review_note=reason.strip()[:3000],
            created_by="human",
            applied_to_id=current.id,
            approved_at=utcnow(),
        )
        db.add(replacement)
        db.flush()
        return replacement

    def revoke_memory(
        self,
        db: Session,
        current: ReviewArtifact,
        *,
        reason: str,
    ) -> ReviewArtifact:
        self._require_approved_memory(current)
        event = ReviewArtifact(
            scope_type="pool_memory",
            scope_id="default",
            artifact_type="memory_event",
            version=self._next_version(db, "memory_event"),
            parent_id=current.id,
            payload_json=json.dumps(
                {"event": "revoke", "target_id": current.id, "reason": reason.strip()},
                ensure_ascii=False,
            ),
            state=ReviewArtifactState.approved.value,
            review_note=reason.strip()[:3000],
            created_by="human",
            applied_to_id=current.id,
            approved_at=utcnow(),
        )
        db.add(event)
        db.flush()
        return event

    @staticmethod
    def _is_candidate(artifact: ReviewArtifact) -> bool:
        return artifact.scope_type == "pool_memory" and artifact.artifact_type == "memory_candidate"

    @staticmethod
    def _is_generic_card(artifact: ReviewArtifact) -> bool:
        return (
            artifact.scope_type == "pool_memory"
            and artifact.artifact_type == "memory_card"
            and artifact.state == ReviewArtifactState.approved.value
        )

    @staticmethod
    def _is_legacy_card(artifact: ReviewArtifact) -> bool:
        return (
            artifact.scope_type == "light_corpus"
            and artifact.artifact_type == "light_corpus_item"
            and artifact.state == ReviewArtifactState.approved.value
        )

    def _require_approved_memory(self, artifact: ReviewArtifact) -> None:
        if not (self._is_generic_card(artifact) or self._is_legacy_card(artifact)):
            raise PoolMemoryError("只有已批准记忆可以替代或撤销")

    def _legacy_payload(self, artifact: ReviewArtifact) -> dict[str, Any]:
        raw = self._object(self._json(artifact.payload_json, {}))
        source_kind = str(raw.get("source_kind") or "authorized_sample")
        dimensions = [
            "opening",
            "sentence_rhythm",
            "paragraph_rhythm",
            "structure",
            "judgment",
        ]
        visual = str(raw.get("visual_style") or "")
        if visual or raw.get("poster_specs"):
            dimensions.extend(["visual_direction", "layout_preference"])
        note = self._compact(raw.get("note"), 500)
        body = self._compact(raw.get("body_markdown"), 120)
        memory = {
            "rules": [note] if note else ["只学习这份已批准轻内容的结构、节奏和判断方式"],
            "avoid": [],
            "prefer": [],
            "positive_examples": (
                [{"text": body, "lesson": "只学习节奏，不继承历史事实"}] if body else []
            ),
            "structure": [],
            "visual_directions": [f"视觉路线：{visual}"] if visual else [],
        }
        return self._normalize_card(
            {
                "title": raw.get("title") or "已批准轻内容语料",
                "source": {
                    "kind": source_kind,
                    "id": str(raw.get("variant_id") or artifact.id),
                    "label": raw.get("title") or "已批准轻内容语料",
                },
                "dimensions": dimensions,
                "scope": {
                    "platforms": ["wechat"],
                    "formats": ["light_series"],
                    "recipes": [artifact.scope_id],
                    "visual_routes": [visual] if visual else [],
                },
                "memory": memory,
                "usage_policy": "style_and_structure_only",
                "note": note,
                "extraction_mode": "legacy_light_corpus_compat",
                "eligibility": {
                    "eligible": True,
                    "reason": "兼容已有轻内容私有语料的人类批准状态",
                    "requires_confirmation": False,
                },
            }
        )

    def _memory_records(self, db: Session) -> list[tuple[ReviewArtifact, dict[str, Any], bool]]:
        artifacts = list(
            db.scalars(
                select(ReviewArtifact).where(
                    ReviewArtifact.state == ReviewArtifactState.approved.value,
                    ReviewArtifact.artifact_type.in_(["memory_card", "light_corpus_item"]),
                )
            ).all()
        )
        output: list[tuple[ReviewArtifact, dict[str, Any], bool]] = []
        for artifact in artifacts:
            if self._is_generic_card(artifact):
                try:
                    payload = self._normalize_card(
                        self._object(self._json(artifact.payload_json, {}))
                    )
                except PoolMemoryError:
                    continue
                output.append((artifact, payload, False))
            elif self._is_legacy_card(artifact):
                try:
                    output.append((artifact, self._legacy_payload(artifact), True))
                except PoolMemoryError:
                    continue
        return output

    def _inactive_ids(
        self, db: Session, records: list[tuple[ReviewArtifact, dict[str, Any], bool]]
    ) -> tuple[set[str], set[str]]:
        superseded = {
            str(payload.get("supersedes_id"))
            for _, payload, _ in records
            if payload.get("supersedes_id")
        }
        revoked: set[str] = set()
        events = db.scalars(
            select(ReviewArtifact).where(
                ReviewArtifact.scope_type == "pool_memory",
                ReviewArtifact.artifact_type == "memory_event",
                ReviewArtifact.state == ReviewArtifactState.approved.value,
            )
        )
        for event in events:
            payload = self._object(self._json(event.payload_json, {}))
            if payload.get("event") == "revoke" and payload.get("target_id"):
                revoked.add(str(payload["target_id"]))
        return superseded, revoked

    def _usage_summary(self, db: Session, memory_id: str) -> tuple[int, list[dict[str, Any]]]:
        count = int(
            db.scalar(
                select(func.count(PoolMemoryUsage.id)).where(PoolMemoryUsage.memory_id == memory_id)
            )
            or 0
        )
        recent = list(
            db.scalars(
                select(PoolMemoryUsage)
                .where(PoolMemoryUsage.memory_id == memory_id)
                .order_by(desc(PoolMemoryUsage.created_at))
                .limit(5)
            ).all()
        )
        return count, [
            {
                "target_type": item.target_type,
                "target_id": item.target_id,
                "agent_role": item.agent_role,
                "stage": item.stage,
                "created_at": item.created_at.isoformat(),
            }
            for item in recent
        ]

    def _item_dict(
        self,
        db: Session,
        artifact: ReviewArtifact,
        payload: dict[str, Any],
        *,
        legacy: bool,
        superseded: bool = False,
        revoked: bool = False,
    ) -> dict[str, Any]:
        usage_count, recent_targets = self._usage_summary(db, artifact.id)
        return {
            "id": artifact.id,
            "state": artifact.state,
            "title": str(payload.get("title") or "未命名池子记忆"),
            "source": self._object(payload.get("source")),
            "dimensions": [str(item) for item in self._list(payload.get("dimensions"))],
            "scope": self._object(payload.get("scope")),
            "memory": self._object(payload.get("memory")),
            "usage_policy": str(payload.get("usage_policy") or "style_and_structure_only"),
            "created_by": artifact.created_by,
            "created_at": artifact.created_at,
            "approved_at": artifact.approved_at,
            "extraction_mode": str(payload.get("extraction_mode") or ""),
            "eligibility": self._object(payload.get("eligibility")),
            "legacy": legacy,
            "superseded": superseded,
            "revoked": revoked,
            "usage_count": usage_count,
            "recent_targets": recent_targets,
        }

    def list_items(
        self,
        db: Session,
        *,
        include_inactive: bool = False,
        platform: str = "",
        format: str = "",
        article_type: str = "",
        style_profile_id: str = "",
        topic: str = "",
        scope_id: str = "",
        state: str = "",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        records = self._memory_records(db)
        superseded_ids, revoked_ids = self._inactive_ids(db, records)
        output: list[dict[str, Any]] = []
        for artifact, payload, legacy in sorted(
            records,
            key=lambda row: row[0].created_at,
            reverse=True,
        ):
            inactive = artifact.id in superseded_ids or artifact.id in revoked_ids
            if scope_id and artifact.scope_id != scope_id:
                continue
            if inactive and not include_inactive:
                continue
            if state == "effective" and inactive:
                continue
            if state == "inactive" and not inactive:
                continue
            if state == "superseded" and artifact.id not in superseded_ids:
                continue
            if state == "revoked" and artifact.id not in revoked_ids:
                continue
            scope = self._object(payload.get("scope"))
            if (
                platform
                and self._list(scope.get("platforms"))
                and platform not in scope["platforms"]
            ):
                continue
            if format and self._list(scope.get("formats")) and format not in scope["formats"]:
                continue
            if (
                article_type
                and self._list(scope.get("article_types"))
                and article_type not in scope["article_types"]
            ):
                continue
            if (
                style_profile_id
                and self._list(scope.get("style_profile_ids"))
                and style_profile_id not in scope["style_profile_ids"]
            ):
                continue
            if (
                topic
                and self._list(scope.get("topics"))
                and not self._text_similarity(topic, " ".join(scope["topics"]))
            ):
                continue
            output.append(
                self._item_dict(
                    db,
                    artifact,
                    payload,
                    legacy=legacy,
                    superseded=artifact.id in superseded_ids,
                    revoked=artifact.id in revoked_ids,
                )
            )
            if len(output) >= limit:
                break
        return output

    def source_memory_status(
        self,
        db: Session,
        *,
        source_kind: str,
        source_id: str,
    ) -> dict[str, Any]:
        records = self._memory_records(db)
        superseded_ids, revoked_ids = self._inactive_ids(db, records)
        approved: list[str] = []
        inactive: list[str] = []
        for artifact, payload, _legacy in records:
            source = self._object(payload.get("source"))
            if source.get("kind") != source_kind or source.get("id") != source_id:
                continue
            if artifact.id in superseded_ids or artifact.id in revoked_ids:
                inactive.append(artifact.id)
            else:
                approved.append(artifact.id)

        candidates: list[str] = []
        for artifact in db.scalars(
            select(ReviewArtifact).where(
                ReviewArtifact.scope_type == "pool_memory",
                ReviewArtifact.artifact_type == "memory_candidate",
                ReviewArtifact.state == ReviewArtifactState.draft.value,
            )
        ):
            payload = self._object(self._json(artifact.payload_json, {}))
            source = self._object(payload.get("source"))
            if source.get("kind") == source_kind and source.get("id") == source_id:
                candidates.append(artifact.id)
        status = (
            "approved"
            if approved
            else "candidate"
            if candidates
            else "inactive"
            if inactive
            else "none"
        )
        return {
            "status": status,
            "approved_memory_ids": approved,
            "candidate_ids": candidates,
            "inactive_memory_ids": inactive,
        }

    def list_candidates(self, db: Session, *, limit: int = 100) -> list[dict[str, Any]]:
        artifacts = list(
            db.scalars(
                select(ReviewArtifact)
                .where(
                    ReviewArtifact.scope_type == "pool_memory",
                    ReviewArtifact.artifact_type == "memory_candidate",
                    ReviewArtifact.state == ReviewArtifactState.draft.value,
                )
                .order_by(desc(ReviewArtifact.created_at))
                .limit(limit)
            ).all()
        )
        output: list[dict[str, Any]] = []
        for artifact in artifacts:
            payload = self._object(self._json(artifact.payload_json, {}))
            item = self._item_dict(db, artifact, payload, legacy=False)
            item.update({"parent_id": artifact.parent_id, "note": artifact.review_note})
            output.append(item)
        return output

    @staticmethod
    def _terms(value: str) -> set[str]:
        return lexical_terms(value)

    @classmethod
    def _text_similarity(cls, left: str, right: str) -> float:
        return term_similarity(left, right)

    @staticmethod
    def _scope_matches(values: Any, requested: str) -> bool:
        scoped = [str(item).lower() for item in values] if isinstance(values, list) else []
        if not scoped or "global" in scoped or "*" in scoped:
            return True
        if not requested:
            return False
        return requested.lower() in scoped

    def retrieve(self, db: Session, query: dict[str, Any]) -> list[dict[str, Any]]:
        if query.get("legacy_none"):
            return []
        records = self._memory_records(db)
        superseded_ids, revoked_ids = self._inactive_ids(db, records)
        requested_dimensions = {str(item) for item in self._list(query.get("dimensions"))}
        platform = str(query.get("platform") or "")
        format_value = str(query.get("format") or "")
        article_type = str(query.get("article_type") or "")
        style_profile_id = str(query.get("style_profile_id") or "")
        recipe = str(query.get("recipe") or "")
        visual_route = str(query.get("visual_route") or "")
        audience = str(query.get("audience") or "")
        topic_text = " ".join(str(item) for item in self._list(query.get("topics")))
        source_text = keyword_digest(str(query.get("source_text") or ""), max_terms=512)
        relevance_text = f"{topic_text} {source_text}"
        scored: list[dict[str, Any]] = []

        for artifact, payload, legacy in records:
            if artifact.id in superseded_ids or artifact.id in revoked_ids:
                continue
            dimensions = {str(item) for item in self._list(payload.get("dimensions"))}
            if requested_dimensions and not (dimensions & requested_dimensions):
                continue
            scope = self._object(payload.get("scope"))
            if not self._scope_matches(scope.get("platforms"), platform):
                continue
            if not self._scope_matches(scope.get("formats"), format_value):
                continue
            if not self._scope_matches(scope.get("article_types"), article_type):
                continue
            if not self._scope_matches(scope.get("style_profile_ids"), style_profile_id):
                continue
            if not self._scope_matches(scope.get("recipes"), recipe):
                continue
            if not self._scope_matches(scope.get("visual_routes"), visual_route):
                continue
            scoped_audiences = self._list(scope.get("audiences"))
            audience_similarity = self._text_similarity(audience, " ".join(scoped_audiences))
            if scoped_audiences and audience_similarity <= 0:
                continue
            scoped_topics = self._list(scope.get("topics"))
            topic_similarity = self._text_similarity(relevance_text, " ".join(scoped_topics))
            if scoped_topics and topic_similarity <= 0:
                continue

            source_kind = str(self._object(payload.get("source")).get("kind") or "")
            score = SOURCE_WEIGHTS.get(source_kind, 1.2)
            reasons = [f"来源权重：{source_kind or 'memory'}"]
            if style_profile_id and style_profile_id in self._list(scope.get("style_profile_ids")):
                score += 2.5
                reasons.append("同一风格档案")
            if platform and platform in self._list(scope.get("platforms")):
                score += 2.0
                reasons.append("同平台")
            if format_value and format_value in self._list(scope.get("formats")):
                score += 2.0
                reasons.append("同内容格式")
            if article_type and article_type in self._list(scope.get("article_types")):
                score += 1.5
                reasons.append("同文章类型")
            if topic_similarity:
                score += 1.5 * min(topic_similarity * 4, 1)
                reasons.append("主题相关")
            if audience_similarity:
                score += min(audience_similarity * 4, 1)
                reasons.append("读者相关")
            usage_count = int(
                db.scalar(
                    select(func.count(PoolMemoryUsage.id)).where(
                        PoolMemoryUsage.memory_id == artifact.id
                    )
                )
                or 0
            )
            if usage_count:
                score += min(math.log1p(usage_count) * 0.1, 0.5)
                reasons.append(f"已有 {usage_count} 次真实使用")
            created_at = artifact.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            age_days = max((datetime.now(UTC) - created_at).total_seconds() / 86400, 0)
            score += 0.5 / (1 + age_days / 180)
            scored.append(
                {
                    "artifact": artifact,
                    "payload": payload,
                    "legacy": legacy,
                    "score": round(score, 4),
                    "reasons": reasons,
                }
            )

        scored.sort(key=lambda item: (item["score"], item["artifact"].created_at), reverse=True)
        deduped: list[dict[str, Any]] = []
        seen_sources: set[str] = set()
        limit = min(max(int(query.get("limit") or 6), 1), 8)
        for item in scored:
            source = self._object(item["payload"].get("source"))
            source_key = f"{source.get('kind')}:{source.get('id')}"
            if source_key in seen_sources:
                continue
            seen_sources.add(source_key)
            deduped.append(item)
            if len(deduped) >= limit:
                break
        return deduped

    def _prompt_text(self, items: list[dict[str, Any]], *, max_chars: int) -> str:
        if not items:
            return f"本任务没有命中已批准池子记忆。\n{FACT_BOUNDARY}"
        blocks = ["本任务检索到的池子记忆（只允许学习风格、结构、节奏与判断方式）："]
        for index, item in enumerate(items, start=1):
            payload = item["payload"]
            memory = self._object(payload.get("memory"))
            lines = [f"{index}. [{item['artifact'].id}] {payload.get('title', '记忆卡')}"]
            for key, label in (
                ("rules", "规则"),
                ("avoid", "避免"),
                ("prefer", "偏好"),
                ("structure", "结构"),
                ("visual_directions", "视觉"),
            ):
                values = self._list(memory.get(key))[:6]
                if values:
                    lines.append(
                        f"   {label}：" + "；".join(self._compact(value, 180) for value in values)
                    )
            examples = self._list(memory.get("positive_examples"))[:2]
            if examples:
                rendered = []
                for example in examples:
                    if isinstance(example, dict):
                        rendered.append(
                            f"“{self._compact(example.get('text'), 120)}”"
                            f"（{self._compact(example.get('lesson'), 120)}）"
                        )
                if rendered:
                    lines.append("   短例：" + "；".join(rendered))
            block = "\n".join(lines)
            candidate = "\n\n".join([*blocks, block, FACT_BOUNDARY])
            if len(candidate) > max_chars:
                break
            blocks.append(block)
        blocks.append(FACT_BOUNDARY)
        return "\n\n".join(blocks)[:max_chars]

    def retrieve_preview(self, db: Session, query: dict[str, Any]) -> dict[str, Any]:
        selected = self.retrieve(db, query)
        max_chars = min(max(int(query.get("max_chars") or 6000), 1000), 7000)
        return {
            "query": query,
            "items": [
                {
                    "item": self._item_dict(
                        db,
                        row["artifact"],
                        row["payload"],
                        legacy=row["legacy"],
                    ),
                    "score": row["score"],
                    "reasons": row["reasons"],
                }
                for row in selected
            ],
            "memory_ids": [row["artifact"].id for row in selected],
            "prompt_preview": self._prompt_text(selected, max_chars=max_chars),
            "fact_boundary": FACT_BOUNDARY,
        }

    def create_snapshot(
        self,
        db: Session,
        *,
        target_type: str,
        target_id: str,
        query: dict[str, Any],
        model_configured: bool,
        model_name: str = "",
    ) -> PoolMemorySnapshot:
        selected = self.retrieve(db, query)
        prompt_payload = {
            "schema_version": 1,
            "fact_boundary": FACT_BOUNDARY,
            "items": [
                {
                    "id": row["artifact"].id,
                    "title": row["payload"].get("title"),
                    "source": row["payload"].get("source"),
                    "dimensions": row["payload"].get("dimensions"),
                    "scope": row["payload"].get("scope"),
                    "memory": row["payload"].get("memory"),
                    "usage_policy": row["payload"].get("usage_policy"),
                    "score": row["score"],
                    "reasons": row["reasons"],
                }
                for row in selected
            ],
        }
        memory_ids = [row["artifact"].id for row in selected]
        canonical = json.dumps(
            {"query": query, "memory_ids": memory_ids, "prompt_payload": prompt_payload},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        snapshot = PoolMemorySnapshot(
            target_type=target_type,
            target_id=target_id,
            query_json=json.dumps(query, ensure_ascii=False, sort_keys=True),
            memory_ids_json=json.dumps(memory_ids, ensure_ascii=False),
            prompt_payload_json=json.dumps(prompt_payload, ensure_ascii=False, sort_keys=True),
            snapshot_hash=hashlib.sha256(canonical.encode()).hexdigest(),
            model_configured=model_configured,
            applied=False,
            model_name=model_name if model_configured else "",
        )
        db.add(snapshot)
        db.flush()
        return snapshot

    def clone_snapshot(
        self,
        db: Session,
        source: PoolMemorySnapshot,
        *,
        target_type: str,
        target_id: str,
        model_configured: bool | None = None,
        model_name: str = "",
    ) -> PoolMemorySnapshot:
        configured = source.model_configured if model_configured is None else model_configured
        clone = PoolMemorySnapshot(
            target_type=target_type,
            target_id=target_id,
            query_json=source.query_json,
            memory_ids_json=source.memory_ids_json,
            prompt_payload_json=source.prompt_payload_json,
            snapshot_hash=source.snapshot_hash,
            model_configured=configured,
            applied=False,
            model_name=(model_name or source.model_name) if configured else "",
        )
        db.add(clone)
        db.flush()
        return clone

    def snapshot(self, db: Session, snapshot_id: str) -> PoolMemorySnapshot | None:
        return db.get(PoolMemorySnapshot, snapshot_id)

    def snapshot_for_target(
        self,
        db: Session,
        *,
        target_type: str,
        target_id: str,
    ) -> PoolMemorySnapshot | None:
        return db.scalar(
            select(PoolMemorySnapshot)
            .where(
                PoolMemorySnapshot.target_type == target_type,
                PoolMemorySnapshot.target_id == target_id,
            )
            .order_by(desc(PoolMemorySnapshot.created_at))
            .limit(1)
        )

    def prompt_payload(
        self,
        snapshot: PoolMemorySnapshot | None,
        *,
        role: str,
        allow_pending: bool = False,
        max_chars: int = 6000,
    ) -> dict[str, Any]:
        if snapshot is None:
            return {
                "text": f"旧任务没有池子记忆快照；不得动态读取最新记忆。\n{FACT_BOUNDARY}",
                "memory_ids": [],
                "snapshot_hash": "legacy_none",
                "applied": False,
            }
        if role in FACT_ONLY_ROLES:
            return {
                "text": FACT_BOUNDARY,
                "memory_ids": [],
                "snapshot_hash": snapshot.snapshot_hash,
                "applied": False,
            }
        if not snapshot.model_configured:
            return {
                "text": f"当前未配置模型；池子记忆没有注入生成器。\n{FACT_BOUNDARY}",
                "memory_ids": [],
                "snapshot_hash": snapshot.snapshot_hash,
                "applied": False,
            }
        if not snapshot.applied and not allow_pending:
            return {
                "text": f"该记忆快照尚未被模型消费。\n{FACT_BOUNDARY}",
                "memory_ids": [],
                "snapshot_hash": snapshot.snapshot_hash,
                "applied": False,
            }
        payload = self._object(self._json(snapshot.prompt_payload_json, {}))
        allowed = ROLE_DIMENSIONS.get(role, ROLE_DIMENSIONS["writer"])
        selected: list[dict[str, Any]] = []
        for raw in self._list(payload.get("items")):
            if not isinstance(raw, dict):
                continue
            dimensions = {str(item) for item in self._list(raw.get("dimensions"))}
            if not dimensions & allowed:
                continue
            fake_artifact = type("FrozenMemory", (), {"id": str(raw.get("id") or "")})()
            selected.append(
                {
                    "artifact": fake_artifact,
                    "payload": raw,
                    "score": float(raw.get("score") or 0),
                    "reasons": self._list(raw.get("reasons")),
                }
            )
        return {
            "text": self._prompt_text(selected, max_chars=min(max_chars, 7000)),
            "memory_ids": [row["artifact"].id for row in selected],
            "snapshot_hash": snapshot.snapshot_hash,
            "applied": snapshot.applied or allow_pending,
        }

    def mark_snapshot_applied(
        self,
        db: Session,
        snapshot: PoolMemorySnapshot,
        *,
        roles: list[tuple[str, str]],
    ) -> None:
        if not snapshot.model_configured:
            return
        payload = self._object(self._json(snapshot.prompt_payload_json, {}))
        rows = {
            str(item.get("id")): item
            for item in self._list(payload.get("items"))
            if isinstance(item, dict) and item.get("id")
        }
        for role, stage in roles:
            role_payload = self.prompt_payload(
                snapshot,
                role=role,
                allow_pending=True,
            )
            if role_payload["memory_ids"]:
                snapshot.applied = True
            for memory_id in role_payload["memory_ids"]:
                exists = db.scalar(
                    select(PoolMemoryUsage.id).where(
                        PoolMemoryUsage.memory_id == memory_id,
                        PoolMemoryUsage.snapshot_id == snapshot.id,
                        PoolMemoryUsage.agent_role == role,
                        PoolMemoryUsage.stage == stage,
                    )
                )
                if exists:
                    continue
                raw = rows.get(memory_id, {})
                usage = PoolMemoryUsage(
                    memory_id=memory_id,
                    snapshot_id=snapshot.id,
                    target_type=snapshot.target_type,
                    target_id=snapshot.target_id,
                    agent_role=role,
                    stage=stage,
                    selected_reason="；".join(str(item) for item in self._list(raw.get("reasons"))),
                    score=float(raw.get("score") or 0),
                )
                db.add(usage)
        db.flush()

    def snapshot_summary(self, snapshot: PoolMemorySnapshot | None) -> dict[str, Any]:
        if snapshot is None:
            return {
                "snapshot_id": "",
                "snapshot_hash": "legacy_none",
                "memory_ids": [],
                "applied": False,
                "status": "legacy_none",
            }
        memory_ids = [str(item) for item in self._list(self._json(snapshot.memory_ids_json, []))]
        status = (
            "applied"
            if snapshot.applied
            else ("selected_not_applied" if snapshot.model_configured else "model_not_configured")
        )
        return {
            "snapshot_id": snapshot.id,
            "snapshot_hash": snapshot.snapshot_hash,
            "memory_ids": memory_ids,
            "applied": snapshot.applied,
            "status": status,
        }

    def source_options(self, db: Session, *, limit: int = 80) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        drafts = list(
            db.scalars(
                select(DraftRevision).order_by(desc(DraftRevision.created_at)).limit(limit)
            ).all()
        )
        for draft in drafts:
            source = db.get(SourceItem, draft.source_id)
            approved = bool(
                db.scalar(
                    select(ReviewDecision.id).where(
                        ReviewDecision.draft_id == draft.id,
                        ReviewDecision.decision == "approved",
                        ReviewDecision.facts_checked.is_(True),
                    )
                )
            )
            output.append(
                {
                    "kind": "draft_revision",
                    "id": draft.id,
                    "label": f"小红书 v{draft.version} · {draft.title or self._source_title(source)}",
                    "detail": self._compact(draft.body, 180),
                    "platform": "xhs",
                    "format": "caption",
                    "eligible": approved or draft.created_by == "human",
                    "eligibility_reason": "已批准/人工版本"
                    if approved or draft.created_by == "human"
                    else "批准记忆时需确认",
                    "created_at": draft.created_at,
                }
            )
        variants = list(
            db.scalars(
                select(PlatformVariant).order_by(desc(PlatformVariant.created_at)).limit(limit)
            ).all()
        )
        for variant in variants:
            metadata = self._object(self._json(variant.metadata_json, {}))
            approved = bool(metadata.get("human_approved"))
            output.append(
                {
                    "kind": "platform_variant",
                    "id": variant.id,
                    "label": f"{variant.platform}/{variant.format} v{variant.version} · {variant.title}",
                    "detail": self._compact(variant.body_markdown, 180),
                    "platform": variant.platform,
                    "format": variant.format,
                    "eligible": approved,
                    "eligibility_reason": "已人工批准" if approved else "批准记忆时需确认",
                    "created_at": variant.created_at,
                }
            )
        feedbacks = list(
            db.scalars(
                select(WritingFeedback).order_by(desc(WritingFeedback.created_at)).limit(limit)
            ).all()
        )
        for feedback in feedbacks:
            output.append(
                {
                    "kind": "writing_feedback",
                    "id": feedback.id,
                    "label": f"真实改稿反馈 · {feedback.feedback_reason or feedback.id}",
                    "detail": self._compact(feedback.feedback_reason, 180),
                    "platform": "xhs",
                    "format": "article",
                    "eligible": True,
                    "eligibility_reason": "用户主动保存的反馈",
                    "created_at": feedback.created_at,
                }
            )
        patterns = list(
            db.scalars(
                select(PatternCard).order_by(desc(PatternCard.created_at)).limit(limit)
            ).all()
        )
        for pattern in patterns:
            output.append(
                {
                    "kind": "pattern_card",
                    "id": pattern.id,
                    "label": f"模式卡 · {pattern.name}",
                    "detail": self._compact(pattern.structure_pattern or pattern.hook_pattern, 180),
                    "platform": "",
                    "format": "",
                    "eligible": True,
                    "eligibility_reason": "只提取抽象模式",
                    "created_at": pattern.created_at,
                }
            )
        artifacts = list(
            db.scalars(
                select(WritingArtifact)
                .where(WritingArtifact.artifact_type == "final_draft")
                .order_by(desc(WritingArtifact.created_at))
                .limit(limit)
            ).all()
        )
        for artifact in artifacts:
            content = self._object(self._json(artifact.content_json, {}))
            output.append(
                {
                    "kind": "writing_artifact",
                    "id": artifact.id,
                    "label": f"多 Agent 终稿 · {content.get('title') or artifact.id}",
                    "detail": self._compact(content.get("body"), 180),
                    "platform": "xhs",
                    "format": "article",
                    "eligible": artifact.approved,
                    "eligibility_reason": "已由作者确认"
                    if artifact.approved
                    else "批准记忆时需确认",
                    "created_at": artifact.created_at,
                }
            )
        output.sort(key=lambda item: item["created_at"], reverse=True)
        for item in output:
            item.pop("created_at", None)
        return output[:limit]

    def list_usages(
        self,
        db: Session,
        *,
        memory_id: str = "",
        target_type: str = "",
        target_id: str = "",
        limit: int = 200,
    ) -> list[PoolMemoryUsage]:
        query = select(PoolMemoryUsage)
        if memory_id:
            query = query.where(PoolMemoryUsage.memory_id == memory_id)
        if target_type:
            query = query.where(PoolMemoryUsage.target_type == target_type)
        if target_id:
            query = query.where(PoolMemoryUsage.target_id == target_id)
        return list(db.scalars(query.order_by(desc(PoolMemoryUsage.created_at)).limit(limit)).all())
