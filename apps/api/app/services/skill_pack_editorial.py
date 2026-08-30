from __future__ import annotations

import json
import re
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.domain.models import DraftRevision, SourceItem
from app.services.pool_memory import PoolMemoryService
from app.services.reader_editorial import ReaderFirstEditorialService
from app.services.skills import binding_for

_ALLOWED_CARD_KINDS = {
    "hero_cover",
    "key_result",
    "concept_diagram",
    "before_after",
    "workflow_flow",
    "key_takeaways",
    "opinion_close",
}


class SkillPackEditorialService(ReaderFirstEditorialService):
    """Reader-first editorial service with platform copy and visual planning."""

    async def generate(self, db: Session, source: SourceItem, style: str) -> DraftRevision:
        draft = await super().generate(db, source, style)
        bindings = {
            name: binding_for(db, name, self.settings.model_name)
            for name in (
                "xhs.selling_points",
                "xhs.title_formulas",
                "xhs.caption_hashtags",
                "xhs.viral_structure",
                "visual.storyboard",
                "visual.art_direction",
                "visual.material_intake",
            )
        }
        if not (
            self.settings.model_base_url
            and self.settings.model_name
            and any(binding.enabled for binding in bindings.values())
        ):
            return draft

        provenance = self._parse_object(draft.provenance_json)
        analysis = provenance.get("editorial_analysis") if isinstance(provenance, dict) else {}
        memory_service = PoolMemoryService(self.settings, self)
        memory_snapshot = memory_service.snapshot(
            db,
            str(provenance.get("memory_snapshot_id") or ""),
        )
        copy_memory = memory_service.prompt_payload(
            memory_snapshot,
            role="writer",
            allow_pending=True,
        )["text"]
        visual_memory = memory_service.prompt_payload(
            memory_snapshot,
            role="visual_director",
            allow_pending=True,
        )["text"]
        active = [name for name, binding in bindings.items() if binding.enabled]
        selling_point_rule = (
            "先按稀缺性、实用性和可感知性给信息排序，只让一到两个核心卖点主导标题和开头。"
            if bindings["xhs.selling_points"].enabled
            else "保持现有卖点顺序。"
        )
        title_rule = (
            "分别尝试痛点、提问、发现、热点和身份共鸣五类标题，再选择最具体且不过度承诺的一条。"
            if bindings["xhs.title_formulas"].enabled
            else "保留现有标题。"
        )
        caption_rule = (
            "生成一段独立发布配文和 4-8 个高相关标签；正文不能变成 hashtag 堆积。"
            if bindings["xhs.caption_hashtags"].enabled
            else "保留现有标签。"
        )
        structure_rule = (
            "开头必须有可感知的反差或问题，随后迅速兑现信息，不复制任何对标文案。"
            if bindings["xhs.viral_structure"].enabled
            else "保持现有结构。"
        )
        storyboard_rule = (
            "为制图输出 4-7 页故事板。每页只能解决一个问题，禁止按字符长度切正文。"
            if bindings["visual.storyboard"].enabled
            else "card_storyboard 输出空数组。"
        )
        material_rule = (
            "有来源图片时只在确实能解释内容的页面标记 asset_role=source；否则使用 diagram 或 none。"
            if bindings["visual.material_intake"].enabled
            else "所有页面 asset_role=none。"
        )
        prompt = f"""
对下面已经完成事实核查和读者化编辑的小红书草稿，执行最后一轮平台适配与制图策划。
这一步只能改善卖点优先级、标题、开头节奏、发布配文、标签和视觉故事板，不能改变事实、数字、来源归属或结论范围。

启用的 Skill：{", ".join(active)}
- {selling_point_rule}
- {title_rule}
- {caption_rule}
- {structure_rule}
- {storyboard_rule}
- {material_rule}

硬性要求：
1. 不使用“震惊、炸裂、封神、必须收藏”等廉价夸张词。
2. 不用 emoji 堆叠，不写“点赞收藏关注”。
3. 技术内容先讲人能感知的结果，再解释术语。
4. 保留读者稿，不把正文改回审计报告、风险清单或逐句翻译。
5. 标题 14-26 个汉字；正文长度不超过当前正文的 1.15 倍。
6. 故事板必须面向公开发布，禁止出现 X2RED、X2PDF、X SOURCE、WECHAT、工作台、来源恢复、审核状态等内部词。
7. 故事板可用页型只有 hero_cover、key_result、concept_diagram、before_after、workflow_flow、key_takeaways、opinion_close。
8. 封面只表达一个核心判断；正文页每页最多 4 个短要点；最后一页给出清晰判断，不放免责声明或来源说明。
9. 技术长文优先使用：封面 → 新变化 → 机制图解 → 前后对比/工作流 → 关键要点 → 判断。
10. card_storyboard 中每页 title 不超过 22 字，subtitle 不超过 70 字，单个 item 不超过 42 字。

编辑分析：{json.dumps(analysis or {}, ensure_ascii=False)[:10000]}
当前标题：{draft.title}
当前正文：{draft.body}
当前标签：{draft.tags}

当前任务冻结的文案记忆：
{copy_memory}

仅供视觉故事板使用的视觉记忆：
{visual_memory}

只输出 JSON：
{{
  "title":"最终标题",
  "body":"最终正文",
  "tags":["标签"],
  "selling_points":[{{"text":"卖点","score":0.0,"reason":"为什么"}}],
  "title_candidates":[{{"formula":"pain|question|discovery|hotspot|identity","title":"标题"}}],
  "caption":"发布时使用的短配文",
  "content_type":"technology|design|tutorial|opinion|news|explainer",
  "visual_direction":{{"style":"editorial|swiss|knowledge|minimal|poster","layout":"sparse|balanced|comparison|flow|quadrant","palette":"neutral|warm|macaron|neon|monochrome","reason":"选择原因"}},
  "card_storyboard":[
    {{"kind":"hero_cover","label":"技术趋势","title":"封面标题","subtitle":"一句话副标题","items":[],"visual_brief":"画面说明","asset_role":"source|diagram|none"}},
    {{"kind":"key_result","label":"先看变化","title":"这一页的中心","subtitle":"可选说明","items":["短要点"],"visual_brief":"画面说明","asset_role":"source|diagram|none"}}
  ]
}}
""".strip()
        strongest = max(
            (binding for binding in bindings.values() if binding.enabled),
            key=lambda item: {"low": 1, "medium": 2, "high": 3}.get(
                item.reasoning_effort,
                2,
            ),
        )
        try:
            result = await self._chat_json(
                system_prompt=(
                    "你是克制的小红书科技与知识内容主编，也是信息设计总监。"
                    "你理解平台阅读节奏，但不以标题党、夸张词、模板排字和伪生活感换取点击。"
                ),
                user_prompt=prompt,
                temperature=0.44,
                reasoning_effort=strongest.reasoning_effort,
                model_name=strongest.model_name,
            )
        except (
            httpx.HTTPError,
            KeyError,
            TypeError,
            ValueError,
            RuntimeError,
            json.JSONDecodeError,
        ):
            return draft

        generated = self._sanitize_generated(
            {
                "title": str(result.get("title") or draft.title),
                "body": str(result.get("body") or draft.body),
                "tags": self._tags_value(result.get("tags")) or draft.tags,
                "claims": self._parse_list(draft.claims_json),
            },
            self._context(db, source),
            style,
        )
        draft.title = generated["title"][:80]
        draft.body = generated["body"][:4000]
        draft.tags = generated["tags"][:500]
        if memory_snapshot is not None:
            roles = [("writer", "xhs_platform_adaptation")]
            if bindings["visual.storyboard"].enabled or bindings["visual.art_direction"].enabled:
                roles.append(("visual_director", "xhs_storyboard"))
            memory_service.mark_snapshot_applied(db, memory_snapshot, roles=roles)
        memory_summary = memory_service.snapshot_summary(memory_snapshot)
        next_provenance = {
            **(provenance if isinstance(provenance, dict) else {}),
            "xhs_skill_pack": {
                "active_skills": active,
                "selling_points": result.get("selling_points") or [],
                "title_candidates": result.get("title_candidates") or [],
                "caption": str(result.get("caption") or ""),
                "content_type": self._content_type(result.get("content_type")),
                "visual_direction": self._visual_direction(result.get("visual_direction")),
                "card_storyboard": self._normalize_storyboard(result.get("card_storyboard")),
            },
            "quality_passes": [
                *(provenance.get("quality_passes") or []),
                *active,
            ][-24:],
            "memory_snapshot_id": memory_summary["snapshot_id"],
            "memory_snapshot_hash": memory_summary["snapshot_hash"],
            "memory_ids": memory_summary["memory_ids"],
            "memory_applied": memory_summary["applied"],
            "memory_status": memory_summary["status"],
        }
        draft.provenance_json = json.dumps(next_provenance, ensure_ascii=False)
        return draft

    @staticmethod
    def _content_type(value: object) -> str:
        text = str(value or "").strip()
        return (
            text
            if text in {"technology", "design", "tutorial", "opinion", "news", "explainer"}
            else "explainer"
        )

    @staticmethod
    def _visual_direction(value: object) -> dict[str, str]:
        raw = value if isinstance(value, dict) else {}
        allowed = {
            "style": {"editorial", "swiss", "knowledge", "minimal", "poster"},
            "layout": {"sparse", "balanced", "comparison", "flow", "quadrant"},
            "palette": {"neutral", "warm", "macaron", "neon", "monochrome"},
        }
        output: dict[str, str] = {}
        for key, values in allowed.items():
            item = str(raw.get(key) or "").strip()
            if item in values:
                output[key] = item
        reason = re.sub(r"\s+", " ", str(raw.get("reason") or "")).strip()
        if reason:
            output["reason"] = reason[:180]
        return output

    @classmethod
    def _normalize_storyboard(cls, value: object) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        output: list[dict[str, Any]] = []
        for raw in value[:7]:
            if not isinstance(raw, dict):
                continue
            kind = str(raw.get("kind") or "").strip()
            if kind not in _ALLOWED_CARD_KINDS:
                continue
            title = cls._trim(raw.get("title"), 42)
            if not title:
                continue
            items = []
            raw_items = raw.get("items")
            if isinstance(raw_items, list):
                for item in raw_items[:4]:
                    text = cls._trim(item, 84)
                    if text and text not in items:
                        items.append(text)
            asset_role = str(raw.get("asset_role") or "none").strip()
            if asset_role not in {"source", "diagram", "none"}:
                asset_role = "none"
            output.append(
                {
                    "kind": kind,
                    "label": cls._trim(raw.get("label"), 14),
                    "title": title,
                    "subtitle": cls._trim(raw.get("subtitle"), 140),
                    "items": items,
                    "visual_brief": cls._trim(raw.get("visual_brief"), 180),
                    "asset_role": asset_role,
                }
            )
        if output and output[0]["kind"] != "hero_cover":
            output.insert(
                0,
                {
                    "kind": "hero_cover",
                    "label": "主题",
                    "title": output[0]["title"],
                    "subtitle": "",
                    "items": [],
                    "visual_brief": "只表达一个核心判断",
                    "asset_role": "source",
                },
            )
        return output[:7]

    @staticmethod
    def _trim(value: object, limit: int) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        return text if len(text) <= limit else text[: limit - 1].rstrip("，。； ") + "…"
