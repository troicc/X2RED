from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.domain.pool_memory import PoolMemorySnapshot
from app.domain.review_artifacts import ReviewArtifact, ReviewArtifactState

RhetoricalDuty = Literal[
    "opening",
    "title",
    "transition",
    "judgment",
    "ending",
    "sentence_rhythm",
    "paragraph_rhythm",
    "positive_phrase",
]


class StrictStyleExemplarModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class StyleExemplar(StrictStyleExemplarModel):
    memory_id: str = Field(min_length=1, max_length=64)
    source_kind: str = Field(min_length=1, max_length=60)
    text: str = Field(min_length=2, max_length=120)
    lesson: str = Field(min_length=2, max_length=240)
    rhetorical_duty: RhetoricalDuty
    rights_basis: Literal["human_approved_original_or_authorized"]
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class StyleExemplarBundle(StrictStyleExemplarModel):
    schema_version: Literal[1] = 1
    retrieval_version: Literal["style-exemplar-retrieval-v1"] = (
        "style-exemplar-retrieval-v1"
    )
    fact_guard_version: Literal["historical-fact-guard-v1"] = (
        "historical-fact-guard-v1"
    )
    memory_snapshot_id: str = Field(default="", max_length=64)
    memory_snapshot_hash: str = Field(default="", max_length=64)
    exemplars: list[StyleExemplar] = Field(default_factory=list, max_length=4)
    omitted_reasons: dict[str, int] = Field(default_factory=dict)
    prompt_text: str = Field(min_length=1, max_length=3000)

    @model_validator(mode="after")
    def enforce_short_diverse_bundle(self) -> StyleExemplarBundle:
        hashes = [item.content_sha256 for item in self.exemplars]
        if len(hashes) != len(set(hashes)):
            raise ValueError("style exemplar bundle contains duplicate text")
        if len(self.exemplars) > 4:
            raise ValueError("style exemplar bundle may contain at most four examples")
        return self


class StyleExemplarRetrievalService:
    """Freeze a few approved rhetoric examples without importing historical facts."""

    version = "style-exemplar-retrieval-v1"
    fact_guard_version = "historical-fact-guard-v1"
    _ALLOWED_SOURCE_KINDS = {
        "authorized_sample",
        "approved_output",
        "writing_feedback",
        "manual_rule",
        "positive_example",
        "draft_revision",
        "platform_variant",
        "writing_artifact",
    }
    _INHERENTLY_AUTHORIZED_SOURCE_KINDS = {
        "authorized_sample",
        "writing_feedback",
        "manual_rule",
        "positive_example",
    }
    _SOURCE_PRIORITY = {
        "writing_feedback": 100,
        "manual_rule": 90,
        "authorized_sample": 85,
        "approved_output": 80,
        "positive_example": 75,
        "draft_revision": 70,
        "platform_variant": 65,
        "writing_artifact": 60,
    }
    _DUTY_ORDER: tuple[RhetoricalDuty, ...] = (
        "opening",
        "title",
        "transition",
        "judgment",
        "ending",
        "sentence_rhythm",
        "paragraph_rhythm",
        "positive_phrase",
    )
    _FACT_RISK = re.compile(
        r"https?://|www\.|@[A-Za-z0-9_]+|\b[A-Z][A-Za-z0-9_.-]{2,}\b|"
        r"\d+(?:\.\d+)?\s*(?:%|％|万|亿|元|美元|年|月|日|倍|项|次|名|个)|"
        r"(?:19|20)\d{2}年|第\s*\d+|[¥￥$€]",
        re.IGNORECASE,
    )

    @staticmethod
    def _object(value: object) -> dict:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _list(value: object) -> list:
        return value if isinstance(value, list) else []

    @staticmethod
    def _json(value: str, fallback: object) -> object:
        try:
            return json.loads(value or "")
        except (TypeError, json.JSONDecodeError):
            return fallback

    @classmethod
    def _duty(cls, example: dict, dimensions: list[str]) -> RhetoricalDuty:
        explicit = str(example.get("rhetorical_duty") or "")
        if explicit in cls._DUTY_ORDER:
            return explicit  # type: ignore[return-value]
        for duty in cls._DUTY_ORDER:
            if duty in dimensions:
                return duty
        return "positive_phrase"

    @classmethod
    def _fact_risk(cls, text: str) -> bool:
        compacted = " ".join(text.split())
        return bool(cls._FACT_RISK.search(compacted))

    def build(
        self,
        db: Session,
        snapshot: PoolMemorySnapshot | None,
        *,
        max_examples: int = 4,
    ) -> StyleExemplarBundle:
        limit = min(max(max_examples, 0), 4)
        if snapshot is None:
            return self._bundle(None, [], Counter({"NO_MEMORY_SNAPSHOT": 1}))
        if limit == 0:
            return self._bundle(snapshot, [], Counter({"MAX_EXAMPLES_ZERO": 1}))
        memory_ids = [
            str(item)
            for item in self._list(self._json(snapshot.memory_ids_json, []))
            if item
        ]
        candidates: list[tuple[int, int, StyleExemplar]] = []
        omitted: Counter[str] = Counter()
        for memory_order, memory_id in enumerate(memory_ids):
            artifact = db.get(ReviewArtifact, memory_id)
            if artifact is None or artifact.state != ReviewArtifactState.approved.value:
                omitted["NOT_APPROVED"] += 1
                continue
            if artifact.created_by != "human":
                omitted["NOT_HUMAN_APPROVED"] += 1
                continue
            payload = self._object(self._json(artifact.payload_json, {}))
            source = self._object(payload.get("source"))
            source_kind = str(source.get("kind") or "")
            if source_kind not in self._ALLOWED_SOURCE_KINDS:
                omitted["SOURCE_NOT_AUTHORIZED_FOR_EXEMPLARS"] += 1
                continue
            eligibility = self._object(payload.get("eligibility"))
            if eligibility and not bool(eligibility.get("eligible")):
                omitted["SOURCE_INELIGIBLE"] += 1
                continue
            if (
                source_kind not in self._INHERENTLY_AUTHORIZED_SOURCE_KINDS
                and not bool(eligibility.get("source_authorized_confirmed"))
            ):
                omitted["SOURCE_RIGHTS_NOT_CONFIRMED"] += 1
                continue
            if str(payload.get("usage_policy") or "") != "style_and_structure_only":
                omitted["ABSTRACT_OR_VISUAL_MEMORY"] += 1
                continue
            dimensions = [str(item) for item in self._list(payload.get("dimensions"))]
            memory = self._object(payload.get("memory"))
            for example in self._list(memory.get("positive_examples")):
                if not isinstance(example, dict):
                    omitted["INVALID_EXAMPLE"] += 1
                    continue
                text = " ".join(str(example.get("text") or "").split())[:120]
                lesson = " ".join(str(example.get("lesson") or "").split())[:240]
                if len(text) < 2 or len(lesson) < 2:
                    omitted["MISSING_TEXT_OR_LESSON"] += 1
                    continue
                if self._fact_risk(text):
                    omitted["HISTORICAL_FACT_RISK"] += 1
                    continue
                digest = hashlib.sha256(text.encode()).hexdigest()
                candidates.append(
                    (
                        self._SOURCE_PRIORITY[source_kind],
                        -memory_order,
                        StyleExemplar(
                            memory_id=artifact.id,
                            source_kind=source_kind,
                            text=text,
                            lesson=lesson,
                            rhetorical_duty=self._duty(example, dimensions),
                            rights_basis="human_approved_original_or_authorized",
                            content_sha256=digest,
                        ),
                    )
                )
        candidates.sort(key=lambda item: (-item[0], -item[1], item[2].content_sha256))
        selected: list[StyleExemplar] = []
        seen_hashes: set[str] = set()
        seen_duties: set[str] = set()
        for _priority, _order, exemplar in candidates:
            if exemplar.content_sha256 in seen_hashes or exemplar.rhetorical_duty in seen_duties:
                continue
            selected.append(exemplar)
            seen_hashes.add(exemplar.content_sha256)
            seen_duties.add(exemplar.rhetorical_duty)
            if len(selected) >= limit:
                break
        for _priority, _order, exemplar in candidates:
            if len(selected) >= limit:
                break
            if exemplar.content_sha256 in seen_hashes:
                continue
            selected.append(exemplar)
            seen_hashes.add(exemplar.content_sha256)
        return self._bundle(snapshot, selected, omitted)

    def _bundle(
        self,
        snapshot: PoolMemorySnapshot | None,
        exemplars: list[StyleExemplar],
        omitted: Counter[str],
    ) -> StyleExemplarBundle:
        if exemplars:
            lines = [
                "本任务冻结的授权短范例（只学习标注的修辞职责，禁止复制其中事实）："
            ]
            for index, exemplar in enumerate(exemplars, start=1):
                lines.append(
                    f"{index}. [{exemplar.rhetorical_duty}] “{exemplar.text}”"
                    f"（只学习：{exemplar.lesson}）"
                )
            lines.append("这些短例不是事实来源；当前事实只能来自本任务 evidence pack。")
            prompt_text = "\n".join(lines)
        else:
            prompt_text = (
                "本任务没有符合授权与历史事实防火墙的短范例。"
                "不要从原始风格样本或历史文章临时复制句子。"
            )
        return StyleExemplarBundle(
            memory_snapshot_id=snapshot.id if snapshot else "",
            memory_snapshot_hash=snapshot.snapshot_hash if snapshot else "",
            exemplars=exemplars,
            omitted_reasons=dict(sorted(omitted.items())),
            prompt_text=prompt_text,
        )
