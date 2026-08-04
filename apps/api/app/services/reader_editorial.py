from __future__ import annotations

import json
import re

import httpx

from app.domain.models import SkillBinding, SourceItem
from app.services.editorial import EditorialService

_STYLE_LABELS = {
    "news": "资讯速览",
    "explain": "解释拆解",
    "opinion": "编辑观察",
}

_READER_STYLE_GUIDES = {
    "news": (
        "写成一篇读者能快速看懂的技术资讯。先说结果，再解释它为什么重要，"
        "最后交代实现方法。不要写成公告摘要或风险清单。"
    ),
    "explain": (
        "写成一篇带读者走进技术现场的解释文章。先给直观结论，再用通俗语言拆解"
        "关键机制、数字意味着什么，以及它可能改变什么。"
    ),
    "opinion": (
        "写成有明确观点的技术观察。观点必须建立在来源中的具体做法和数字上，"
        "不要用审计式免责声明代替判断。"
    ),
}

_INTERNAL_HEADINGS = (
    "阅读提醒",
    "阅读时注意",
    "阅读时需注意",
    "注意以下边界",
    "适用边界",
    "信息边界",
    "事实边界",
    "风险提示",
    "仍需确认",
    "仍待确认",
    "需要警惕",
    "事实核查",
    "核查提醒",
    "判断边界",
    "评估此方案",
    "适用性判断",
    "局限性",
)

_GENERIC_DISCLAIMER_MARKERS = (
    "本文基于已归档",
    "本文仅基于",
    "仍需结合公开资料核查",
    "仍需进一步验证",
    "实际效果仍需验证",
    "不能直接当作普遍效果",
    "不代表所有场景",
    "不构成完整结论",
    "需要更多数据验证",
    "需结合具体硬件配置",
)

_TEMPLATE_HEADINGS = (
    "先说结论",
    "发生了什么",
    "核心信息",
    "值得关注的 3 个点",
    "值得关注的3个点",
    "这对读者有什么用",
    "我的判断",
    "判断依据",
    "给读者的判断框架",
)


class ReaderFirstEditorialService(EditorialService):
    """Editorial pipeline that separates internal review from reader-facing copy."""

    async def _model_generate(
        self,
        context: list[SourceItem],
        style: str,
        bindings: dict[str, SkillBinding] | None = None,
        memory_prompts: dict[str, str] | None = None,
    ) -> dict | None:
        if not (self.settings.model_base_url and self.settings.model_name):
            return None

        active = bindings or {
            name: self._binding_defaults(name, self.settings)
            for name in ("editorial.analysis", "writing.draft", "writing.de_translate")
        }
        analysis_binding = active["editorial.analysis"]
        draft_binding = active["writing.draft"]
        polish_binding = active["writing.de_translate"]
        if not analysis_binding.enabled or not draft_binding.enabled:
            return None

        source_json = json.dumps(self._source_blocks(context), ensure_ascii=False)[:30000]
        memory = memory_prompts or {}
        style_label = _STYLE_LABELS.get(style, style)
        analysis_prompt = f"""
先分析下面的 X 原帖、Thread 或 X Article，不要直接写成稿。
写作类型：{style_label}

你的任务不是做审计报告，而是找到一个普通技术读者愿意继续看的叙事：
1. 用一句人话说明作者到底做成了什么，避免从模型名、缩写或免责声明开场。
2. 找出最反直觉、最有画面或最有信息增量的一点，作为 reader hook。
3. 把技术内容拆成：结果、关键方法、数字意味着什么、为什么值得关注。
4. 每个首次出现的术语都准备一句通俗解释或类比。
5. 区分来源事实、作者自测结果和作者判断；不确定项只用于内部编辑分析。
6. 推荐一个单一叙事角度。它应让读者看懂技术进展，而不是教读者如何规避误读。
7. 给出 5 个具体标题和自然的文章提纲。

只输出 JSON，字段仍为：topic、one_sentence_summary、verified_facts、author_claims、
uncertainties、audience_value、angles、recommended_angle、title_candidates、outline、avoid。
其中 recommended_angle 必须包含 name、reason、reader_hook、plain_language_thesis；
outline 每一项包含 heading、purpose、source_indices，并按读者理解顺序组织。
来源：{source_json}

当前任务相关个人记忆：
{memory.get("editor", "")}
""".strip()

        try:
            analysis = await self._chat_json(
                system_prompt=(
                    "你是优秀的中文科技编辑。内部分析要严谨，但最终目标是让读者先看懂、"
                    "再产生兴趣；不要把事实核查流程写成面向读者的内容。"
                ),
                user_prompt=analysis_prompt,
                temperature=0.2,
                reasoning_effort=analysis_binding.reasoning_effort,
                model_name=analysis_binding.model_name,
            )

            writing_prompt = f"""
根据编辑分析和原始来源，写一篇真正面向读者的小红书技术长文。
类型：{style_label}。{_READER_STYLE_GUIDES.get(style, _READER_STYLE_GUIDES["explain"])}
编辑分析：{json.dumps(analysis, ensure_ascii=False)[:15000]}
原始来源：{source_json}

当前任务相关个人记忆：
{memory.get("writer", "")}

读者稿必须遵守：
- 开头两三句直接讲清“做成了什么”和“为什么这很厉害或很有意思”。
- 先用普通人能理解的语言建立画面，再引入 VSA、TMA、TMEM、Triton 等术语。
- 术语第一次出现时，紧跟一句中文解释；可以用类比，但不能编造事实。
- 围绕一个主线写，不逐段翻译原文，不罗列所有信息，不堆缩写。
- 数字必须解释意义。例如延迟从多少降到多少，意味着优化发生在哪一层。
- 作者自测用自然来源归属表达，例如“据作者在 Blackwell GPU 上的测试”。
- 真正会改变结论的限制，最多用一句自然的限定语嵌入相关段落。
- 不要出现独立的免责声明、核查清单或教学式边界提醒。
- 禁止使用以下标题或句式：阅读提醒、阅读时注意以下边界、适用边界、仍需确认、
  需要警惕、事实核查、本文基于已归档来源整理、评估此方案的适用性。
- 禁止用“先说结论 / 值得关注的3个点 / 这对读者有什么用”组成模板化骨架。
- 正文 650-1200 个中文字符，短段落，最多一个三项列表；结尾留下一个清晰判断，
  不要以免责声明收尾。
- 标题 14-26 个汉字，必须具体说明技术结果或关键反差。
- 标签 4-7 个。

只输出 JSON：
{{"title":"标题","body":"正文","tags":["标签"],"claims":[{{"statement":"陈述","source_index":1,"verification":"source_only"}}]}}
""".strip()

            initial = await self._chat_json(
                system_prompt=(
                    "你是会讲故事的中文科技主编。把复杂技术写清楚、写得有吸引力，"
                    "但绝不把内部核查备注、风险清单或免责声明塞进读者稿。"
                ),
                user_prompt=writing_prompt,
                temperature=0.55,
                reasoning_effort=draft_binding.reasoning_effort,
                model_name=draft_binding.model_name,
            )

            final = initial
            passes = ["editorial.analysis", "writing.draft"]
            if polish_binding.enabled:
                final = await self._polish_draft(
                    initial,
                    analysis,
                    source_json,
                    polish_binding,
                    memory_prompt=memory.get("polish", ""),
                )
                passes.append("writing.de_translate")

            return {
                "analysis": analysis,
                "quality_passes": passes,
                "model": draft_binding.model_name or self.settings.model_name,
                "draft": {
                    "title": str(final.get("title") or initial.get("title") or ""),
                    "body": str(final.get("body") or initial.get("body") or ""),
                    "tags": self._tags_value(final.get("tags"))
                    or self._tags_value(initial.get("tags")),
                    "claims": self._map_model_claims(initial.get("claims"), context),
                },
            }
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    async def _polish_draft(
        self,
        initial: dict,
        analysis: dict,
        source_json: str,
        binding: SkillBinding,
        *,
        memory_prompt: str = "",
    ) -> dict:
        prompt = f"""
把下面初稿做最后一轮读者编辑。

保留事实、数字和来源归属，但做这些改变：
1. 第一段必须让不熟悉该领域的人知道发生了什么，以及为什么值得继续看。
2. 删除缩写堆叠、英文语序、机械小标题、同义反复和报告腔。
3. 技术名词第一次出现时补上一句极短的人话解释。
4. 把“限制、边界、不确定性”放回内部分析。只有它会改变核心结论时，才在相关句子中
   用一句来源限定表达，不能单独成节。
5. 删除任何“阅读提醒、注意以下边界、适用性判断、仍需确认、事实核查、本文基于来源整理”。
6. 结尾落在技术意义或判断上，不要以免责声明收尾。

编辑分析：{json.dumps(analysis, ensure_ascii=False)[:9000]}
原始来源：{source_json}
初稿：{json.dumps(initial, ensure_ascii=False)[:16000]}
当前任务冻结的个人记忆：{memory_prompt}
只输出 JSON：{{"title":"标题","body":"正文","tags":["标签"]}}
""".strip()
        try:
            return await self._chat_json(
                system_prompt=(
                    "你是中文母语科技内容总编。你的标准是让聪明但不熟悉细节的读者"
                    "一口气读完，而不是向读者展示编辑部的核查过程。"
                ),
                user_prompt=prompt,
                temperature=0.4,
                reasoning_effort=binding.reasoning_effort,
                model_name=binding.model_name,
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return initial

    def _fallback(self, context, style: str) -> dict:
        items = list(context)
        focal = items[0]
        pieces: list[tuple[SourceItem, str]] = []
        for item in items:
            for sentence in self._sentences(self._clean(item.text_original)):
                if sentence and all(sentence != existing for _, existing in pieces):
                    pieces.append((item, sentence))

        first = pieces[0][1] if pieces else "这条来源暂时没有可提取的正文。"
        supporting = [self._trim_sentence(text, 150) for _, text in pieces[1:5]]
        has_chinese = bool(re.search(r"[\u4e00-\u9fff]", first))
        handle = focal.author_handle or focal.author_name or "原作者"
        title = self._fallback_title(first, handle, has_chinese)

        body_parts = [
            self._trim_sentence(first, 180),
        ]
        if supporting:
            body_parts.append("真正值得看的，是它用了什么方法把结果做到这一步。")
            body_parts.extend(supporting[:3])
        body_parts.append("把这些做法连起来看，重点不在术语数量，而在它具体改变了哪一层性能瓶颈。")

        claims = [
            {
                "statement": text[:300],
                "source_id": item.id,
                "source_url": item.canonical_url,
                "verification": "source_only",
            }
            for item, text in pieces[:8]
        ]
        return {
            "title": title,
            "body": "\n\n".join(body_parts),
            "tags": ",".join(
                self._fallback_tags(
                    focal,
                    style,
                    " ".join(text for _, text in pieces),
                )
            ),
            "claims": claims,
        }

    def _sanitize_generated(
        self,
        generated: dict,
        context: list[SourceItem],
        style: str,
    ) -> dict:
        sanitized = super()._sanitize_generated(generated, context, style)
        cleaned_body = self._reader_body(str(sanitized.get("body") or ""))
        if len(re.sub(r"\s+", "", cleaned_body)) < 30:
            cleaned_body = self._reader_body(self._fallback(context, style)["body"])
        sanitized["body"] = cleaned_body[:4000]
        return sanitized

    @classmethod
    def _reader_body(cls, body: str) -> str:
        paragraphs = [
            paragraph.strip()
            for paragraph in re.split(r"\n\s*\n", body.replace("\r\n", "\n"))
            if paragraph.strip()
        ]
        output: list[str] = []
        skip_generic_followup = False

        for paragraph in paragraphs:
            compact = re.sub(r"\s+", "", paragraph).strip("：:—- ")
            if cls._starts_with_internal_heading(compact):
                skip_generic_followup = True
                continue
            if skip_generic_followup and cls._is_generic_disclaimer(compact):
                skip_generic_followup = False
                continue
            skip_generic_followup = False
            if cls._is_generic_disclaimer(compact):
                continue

            cleaned = paragraph
            for heading in _TEMPLATE_HEADINGS:
                cleaned = re.sub(
                    rf"^\s*{re.escape(heading)}\s*[：:]?\s*",
                    "",
                    cleaned,
                )
            cleaned = cleaned.strip()
            if cleaned:
                output.append(cleaned)

        return re.sub(r"\n{3,}", "\n\n", "\n\n".join(output)).strip()

    @staticmethod
    def _starts_with_internal_heading(compact: str) -> bool:
        normalized = re.sub(r"^[#*\d.、（）()一二三四五六七八九十]+", "", compact)
        return any(normalized.startswith(heading) for heading in _INTERNAL_HEADINGS)

    @staticmethod
    def _is_generic_disclaimer(compact: str) -> bool:
        if any(marker.replace(" ", "") in compact for marker in _GENERIC_DISCLAIMER_MARKERS):
            return True
        disclaimer_terms = sum(
            term in compact for term in ("核查", "验证", "边界", "适用性", "不确定", "公开资料")
        )
        return disclaimer_terms >= 2 and len(compact) <= 220
