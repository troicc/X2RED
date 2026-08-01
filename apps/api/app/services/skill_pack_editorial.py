from __future__ import annotations

import json

import httpx
from sqlalchemy.orm import Session

from app.domain.models import DraftRevision, SourceItem
from app.services.reader_editorial import ReaderFirstEditorialService
from app.services.skills import binding_for


class SkillPackEditorialService(ReaderFirstEditorialService):
    """Reader-first editorial service with optional platform skill packs."""

    async def generate(self, db: Session, source: SourceItem, style: str) -> DraftRevision:
        draft = await super().generate(db, source, style)
        bindings = {
            name: binding_for(db, name, self.settings.model_name)
            for name in (
                "xhs.selling_points",
                "xhs.title_formulas",
                "xhs.caption_hashtags",
                "xhs.viral_structure",
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
        prompt = f"""
对下面已经完成事实核查和读者化编辑的小红书草稿，执行最后一轮平台适配。
这一步只能改善卖点优先级、标题、开头节奏、发布配文和标签，不能改变事实、数字、来源归属或结论范围。

启用的 Skill：{', '.join(active)}
- {selling_point_rule}
- {title_rule}
- {caption_rule}
- {structure_rule}

硬性要求：
1. 不使用“震惊、炸裂、封神、必须收藏”等廉价夸张词。
2. 不用 emoji 堆叠，不写“点赞收藏关注”。
3. 技术内容先讲人能感知的结果，再解释术语。
4. 保留读者稿，不把正文改回审计报告、风险清单或逐句翻译。
5. 标题 14-26 个汉字；正文长度不超过当前正文的 1.15 倍。

编辑分析：{json.dumps(analysis or {}, ensure_ascii=False)[:10000]}
当前标题：{draft.title}
当前正文：{draft.body}
当前标签：{draft.tags}

只输出 JSON：
{{
  "title":"最终标题",
  "body":"最终正文",
  "tags":["标签"],
  "selling_points":[{{"text":"卖点","score":0.0,"reason":"为什么"}}],
  "title_candidates":[{{"formula":"pain|question|discovery|hotspot|identity","title":"标题"}}],
  "caption":"发布时使用的短配文"
}}
""".strip()
        strongest = max(
            (binding for binding in bindings.values() if binding.enabled),
            key=lambda item: {"low": 1, "medium": 2, "high": 3}.get(item.reasoning_effort, 2),
        )
        try:
            result = await self._chat_json(
                system_prompt=(
                    "你是克制的小红书科技与知识内容主编。你理解平台阅读节奏，"
                    "但不以标题党、夸张词和伪生活感换取点击。"
                ),
                user_prompt=prompt,
                temperature=0.48,
                reasoning_effort=strongest.reasoning_effort,
                model_name=strongest.model_name,
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
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
        next_provenance = {
            **(provenance if isinstance(provenance, dict) else {}),
            "xhs_skill_pack": {
                "active_skills": active,
                "selling_points": result.get("selling_points") or [],
                "title_candidates": result.get("title_candidates") or [],
                "caption": str(result.get("caption") or ""),
            },
            "quality_passes": [
                *(provenance.get("quality_passes") or []),
                *active,
            ][-20:],
        }
        draft.provenance_json = json.dumps(next_provenance, ensure_ascii=False)
        return draft
