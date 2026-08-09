from __future__ import annotations

import itertools
import re
from collections import Counter
from difflib import SequenceMatcher

from app.domain.visual_brief_schemas import (
    PageVisualConceptCandidate,
    VisualDistinctnessIssue,
    VisualDistinctnessReport,
)


class VisualDistinctnessError(RuntimeError):
    pass


class VisualDistinctnessService:
    """Select and audit a page series as one visual system."""

    cliches = (
        "通往未来的门",
        "人生迷宫",
        "希望灯塔",
        "时间沙漏",
        "破茧成蝶",
        "拼图最后一块",
        "站在十字路口",
        "黑暗中的一束光",
        "大脑与齿轮",
        "火箭起飞",
        "handshake",
        "lightbulb moment",
        "road to success",
    )
    abstract_terms = (
        "焦虑",
        "压力",
        "成长",
        "希望",
        "自由",
        "未来",
        "效率",
        "情绪",
        "关系",
        "价值",
        "意义",
        "困境",
        "anxiety",
        "growth",
        "hope",
        "freedom",
        "future",
        "meaning",
    )

    def select(
        self,
        candidate_sets: list[list[PageVisualConceptCandidate]],
    ) -> tuple[list[PageVisualConceptCandidate], VisualDistinctnessReport]:
        if not candidate_sets or any(len(values) != 3 for values in candidate_sets):
            raise VisualDistinctnessError("每页必须恰好提供 3 个视觉候选")
        best: tuple[
            int,
            float,
            tuple[str, ...],
            list[PageVisualConceptCandidate],
            VisualDistinctnessReport,
        ] | None = None
        for combination in itertools.product(*candidate_sets):
            selected = list(combination)
            report = self.evaluate(selected)
            editor_score = sum(item.editor_score for item in selected) / len(selected)
            ranking = report.score + editor_score * 0.25
            identifiers = tuple(item.candidate_id for item in selected)
            candidate = (
                int(report.passed),
                ranking,
                identifiers,
                selected,
                report,
            )
            if best is None or candidate[:2] > best[:2] or (
                candidate[:2] == best[:2] and candidate[2] < best[2]
            ):
                best = candidate
        if best is None:
            raise VisualDistinctnessError("没有可选择的视觉候选组合")
        return best[3], best[4]

    def evaluate(
        self,
        selected: list[PageVisualConceptCandidate],
    ) -> VisualDistinctnessReport:
        issues: list[VisualDistinctnessIssue] = []
        subjects = [item.brief.concrete_subject for item in selected]
        anchors = [item.anchor_family for item in selected]
        layouts = [item.brief.layout_family for item in selected]

        for left_index, left in enumerate(subjects):
            for right_index in range(left_index + 1, len(subjects)):
                right = subjects[right_index]
                similarity = self._similarity(left, right)
                if similarity >= 0.78:
                    issues.append(
                        VisualDistinctnessIssue(
                            code="duplicate_subject",
                            pages=[left_index + 1, right_index + 1],
                            detail=(
                                f"具体主体过于相似：‘{left}’ / ‘{right}’"
                            ),
                            blocking=True,
                        )
                    )

        anchor_counts = Counter(self._key(value) for value in anchors)
        for anchor, count in anchor_counts.items():
            if anchor and count > 2:
                pages = [
                    index + 1
                    for index, value in enumerate(anchors)
                    if self._key(value) == anchor
                ]
                issues.append(
                    VisualDistinctnessIssue(
                        code="repeated_anchor",
                        pages=pages,
                        detail=f"同一 anchor family 连续占用 {count} 页",
                        blocking=count == len(selected),
                    )
                )

        required_layouts = min(3, len(selected))
        unique_layouts = list(dict.fromkeys(layouts))
        if len(unique_layouts) < required_layouts:
            issues.append(
                VisualDistinctnessIssue(
                    code="layout_monotony",
                    pages=list(range(1, len(selected) + 1)),
                    detail=(
                        f"{len(selected)} 页仅使用 {len(unique_layouts)} 个 layout family；"
                        f"至少需要 {required_layouts} 个"
                    ),
                    blocking=True,
                )
            )
        for index in range(1, len(layouts)):
            if layouts[index] == layouts[index - 1]:
                issues.append(
                    VisualDistinctnessIssue(
                        code="adjacent_layout_repeat",
                        pages=[index, index + 1],
                        detail=f"相邻页面重复 layout family：{layouts[index]}",
                    )
                )

        for index, candidate in enumerate(selected, start=1):
            brief = candidate.brief
            combined = " ".join(
                [
                    brief.concrete_subject,
                    brief.secondary_subject,
                    brief.action_or_relation,
                ]
            ).casefold()
            matched = [value for value in self.cliches if value.casefold() in combined]
            if matched:
                issues.append(
                    VisualDistinctnessIssue(
                        code="visual_cliche",
                        pages=[index],
                        detail=f"命中视觉陈词滥调：{matched[0]}",
                        blocking=True,
                    )
                )
            abstract_count = sum(
                1 for value in self.abstract_terms if value.casefold() in combined
            )
            if abstract_count >= 3:
                issues.append(
                    VisualDistinctnessIssue(
                        code="compound_abstraction",
                        pages=[index],
                        detail="主体同时承载过多抽象概念，无法形成单一可画事件",
                        blocking=True,
                    )
                )
            if not brief.evidence_refs:
                issues.append(
                    VisualDistinctnessIssue(
                        code="missing_evidence_ref",
                        pages=[index],
                        detail="页面视觉简报缺少 evidence ref",
                        blocking=True,
                    )
                )

        blocking = sum(1 for item in issues if item.blocking)
        soft = len(issues) - blocking
        score = max(0.0, min(100.0, 100.0 - blocking * 28.0 - soft * 5.0))
        return VisualDistinctnessReport(
            passed=blocking == 0,
            score=score,
            layout_families=unique_layouts,
            concrete_subjects=subjects,
            anchor_families=list(dict.fromkeys(anchors)),
            issues=issues,
        )

    @staticmethod
    def _key(value: str) -> str:
        return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())

    @classmethod
    def _similarity(cls, left: str, right: str) -> float:
        left_key = cls._key(left)
        right_key = cls._key(right)
        if not left_key or not right_key:
            return 0.0
        if left_key == right_key:
            return 1.0
        if left_key in right_key or right_key in left_key:
            shorter = min(len(left_key), len(right_key))
            longer = max(len(left_key), len(right_key))
            if shorter >= 4:
                return max(0.8, shorter / longer)
        return SequenceMatcher(None, left_key, right_key).ratio()
