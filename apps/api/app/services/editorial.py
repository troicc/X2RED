from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import datetime

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import DraftRevision, SourceItem
from app.services.source_graph import connected_sources

_STYLE_LABELS = {
    "news": "资讯速览",
    "explain": "解释拆解",
    "opinion": "编辑观察",
}

_STYLE_GUIDES = {
    "news": (
        "写成克制、清楚的资讯笔记。正文依次包含：发生了什么、核心信息、为什么值得关注、"
        "仍需确认。不要使用夸张语气，不要虚构行业背景。"
    ),
    "explain": (
        "写成容易读懂的解释型笔记。正文依次包含：先说结论、值得关注的3个点、"
        "这意味着什么、阅读提醒。每个要点必须具体，避免重复原文。"
    ),
    "opinion": (
        "写成有依据的编辑观察。正文依次包含：我的判断、判断依据、需要警惕的地方、"
        "给读者的一个问题。明确区分原作者观点与编辑判断。"
    ),
}

_KEYWORD_TAGS = {
    "openai": "OpenAI",
    "chatgpt": "ChatGPT",
    "agent": "AI智能体",
    "agents": "AI智能体",
    "model": "大模型",
    "llm": "大模型",
    "artificial intelligence": "人工智能",
    " ai ": "人工智能",
    "workflow": "效率工具",
    "local-first": "本地优先",
    "local first": "本地优先",
    "xiaohongshu": "小红书",
    "小红书": "小红书",
    "python": "Python",
    "product": "产品观察",
    "startup": "创业观察",
    "design": "设计思考",
    "creator": "内容创作",
    "content": "内容创作",
}

_ANALYSIS_FIELDS = (
    "topic",
    "one_sentence_summary",
    "verified_facts",
    "author_claims",
    "uncertainties",
    "audience_value",
    "angles",
    "recommended_angle",
    "title_candidates",
    "outline",
    "avoid",
)


class EditorialService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(self, db: Session, source: SourceItem, style: str) -> DraftRevision:
        context = self._context(db, source)
        model_result = await self._model_generate(context, style)
        analysis: dict = {}
        if model_result is None:
            generated = self._fallback(context, style)
            generator = "structured-fallback"
        else:
            generated = model_result["draft"]
            analysis = self._compact_analysis(model_result["analysis"])
            generator = "model-two-pass"
        generated = self._sanitize_generated(generated, context, style)

        version = int(
            db.scalar(select(func.max(DraftRevision.version)).where(DraftRevision.source_id == source.id))
            or 0
        ) + 1
        draft = DraftRevision(
            source_id=source.id,
            version=version,
            style=style,
            title=generated["title"][:80],
            body=generated["body"][:4000],
            tags=generated["tags"][:500],
            claims_json=json.dumps(generated["claims"], ensure_ascii=False),
            provenance_json=json.dumps(
                {
                    "source_ids": [item.id for item in context],
                    "source_urls": [item.canonical_url for item in context],
                    "generator": generator,
                    "model": self.settings.model_name if generator == "model-two-pass" else "",
                    "editorial_analysis": analysis,
                },
                ensure_ascii=False,
            ),
            created_by="model" if generator == "model-two-pass" else "system",
        )
        db.add(draft)
        db.flush()
        return draft

    def revise(
        self,
        db: Session,
        current: DraftRevision,
        *,
        title: str,
        body: str,
        tags: str,
    ) -> DraftRevision:
        version = int(
            db.scalar(
                select(func.max(DraftRevision.version)).where(
                    DraftRevision.source_id == current.source_id
                )
            )
            or current.version
        ) + 1
        revised = DraftRevision(
            source_id=current.source_id,
            version=version,
            style=current.style,
            title=title.strip(),
            body=body.strip(),
            tags=tags.strip(),
            claims_json=current.claims_json,
            provenance_json=current.provenance_json,
            created_by="human",
        )
        db.add(revised)
        db.flush()
        return revised

    def _context(self, db: Session, source: SourceItem) -> list[SourceItem]:
        connected = connected_sources(db, source.id)
        return [source, *(item for item in connected if item.id != source.id)]

    async def _model_generate(self, context: list[SourceItem], style: str) -> dict | None:
        # API keys are optional so local OpenAI-compatible servers such as Ollama
        # and LM Studio work without fake credentials.
        if not (self.settings.model_base_url and self.settings.model_name):
            return None

        source_blocks = self._source_blocks(context)
        source_json = json.dumps(source_blocks, ensure_ascii=False)[:20000]
        style_label = _STYLE_LABELS.get(style, style)

        analysis_prompt = f"""
你将收到一组来自 X 的原帖或 Thread。先完成编辑分析，不要直接写小红书正文。

写作类型：{style_label}

分析任务：
1. 用一句话说明真正发生了什么，不要逐句翻译。
2. 区分“来源直接陈述的事实”“原作者自己的判断/宣传”“目前无法确认的内容”。
3. 找出这条信息对中文读者真正有用的地方，避免泛泛而谈。
4. 提出 3 个明显不同的选题角度，并推荐其中一个，说明推荐理由。
5. 给出 5 个不标题党、但有信息增量的中文标题候选。
6. 设计正文结构：每一节写什么、依据来自哪些 source_index。
7. 列出写作时必须避免的误读、夸大和事实跳跃。

只输出合法 JSON：
{{
  "topic": "主题",
  "one_sentence_summary": "一句话总结",
  "verified_facts": [{{"statement": "来源直接支持的事实", "source_index": 1}}],
  "author_claims": [{{"statement": "原作者的观点或自我评价", "source_index": 1}}],
  "uncertainties": ["尚待外部核查的点"],
  "audience_value": ["对中文读者的具体价值"],
  "angles": [
    {{"name": "角度名", "thesis": "核心判断", "why": "为什么成立"}}
  ],
  "recommended_angle": {{"name": "推荐角度", "reason": "推荐理由"}},
  "title_candidates": ["标题1", "标题2", "标题3", "标题4", "标题5"],
  "outline": [
    {{"heading": "段落标题", "purpose": "这一节解决什么问题", "source_indices": [1]}}
  ],
  "avoid": ["必须避免的表达"]
}}

来源数据：
{source_json}
""".strip()

        try:
            analysis = await self._chat_json(
                system_prompt=(
                    "你是一名资深中文内容主编和事实核查编辑。先分析证据、价值和叙事角度，"
                    "再决定怎么写；不把原作者的宣传自动视为事实。"
                ),
                user_prompt=analysis_prompt,
                temperature=0.2,
                reasoning_effort="high",
            )

            writing_prompt = f"""
请根据“编辑分析”和“原始来源”写出一篇真正可发布的中文小红书笔记。

写作类型：{style_label}
具体要求：{_STYLE_GUIDES.get(style, _STYLE_GUIDES["explain"])}

编辑分析：
{json.dumps(analysis, ensure_ascii=False)[:12000]}

原始来源：
{source_json}

必须遵守：
1. 采用编辑分析中的 recommended_angle，不要把所有角度混成一篇流水账。
2. 标题 12-22 个汉字，优先从 title_candidates 中择优改写；具体、有信息量，拒绝标题党。
3. 开头两行直接交代“发生了什么”和“为什么值得读”。
4. 正文 500-1000 个汉字，短段落，每节都要推进信息，不复述同一句话。
5. 必须把来源事实、作者观点和编辑判断清楚区分。
6. 不得添加来源和分析中没有的人名、数字、日期、效果、因果关系或行业结论。
7. uncertainties 中的内容必须用保守措辞呈现，不得写成确定事实。
8. 结尾给读者一个具体判断框架或行动建议，不写空洞互动话术。
9. 标签给出 4-7 个，不带 #，避免“热门”“干货”等空泛词。
10. claims 中每一项包含 statement、source_index、verification；verification 只能是 source_only 或 needs_external_check。

只输出合法 JSON：
{{
  "title": "标题",
  "body": "完整正文",
  "tags": ["标签1", "标签2"],
  "claims": [
    {{"statement": "可核查陈述", "source_index": 1, "verification": "source_only"}}
  ]
}}
""".strip()

            parsed = await self._chat_json(
                system_prompt=(
                    "你是一名严谨、有判断力、熟悉小红书阅读节奏的中文主编。"
                    "你根据已经完成的编辑分析写作，而不是机械翻译或堆砌原文。"
                ),
                user_prompt=writing_prompt,
                temperature=0.5,
                reasoning_effort="medium",
            )
            tags = parsed.get("tags")
            if isinstance(tags, list):
                tags_value = ",".join(str(tag) for tag in tags)
            else:
                tags_value = str(tags or "")
            claims = self._map_model_claims(parsed.get("claims"), context)
            return {
                "analysis": analysis,
                "draft": {
                    "title": str(parsed.get("title") or ""),
                    "body": str(parsed.get("body") or ""),
                    "tags": tags_value,
                    "claims": claims,
                },
            }
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    async def _chat_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        reasoning_effort: str,
    ) -> dict:
        request_body: dict = {
            "model": self.settings.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        request_body.update(self._reasoning_options(reasoning_effort))

        headers = {"Content-Type": "application/json"}
        if self.settings.model_api_key:
            headers["Authorization"] = f"Bearer {self.settings.model_api_key}"

        endpoint = self.settings.model_base_url.rstrip("/") + "/chat/completions"
        variants = [request_body]
        without_format = dict(request_body)
        without_format.pop("response_format", None)
        variants.append(without_format)
        if "thinking" in request_body or "reasoning_effort" in request_body:
            portable = dict(without_format)
            portable.pop("thinking", None)
            portable.pop("reasoning_effort", None)
            variants.append(portable)

        last_response: httpx.Response | None = None
        async with httpx.AsyncClient(timeout=120) as client:
            for index, payload in enumerate(variants):
                response = await client.post(endpoint, headers=headers, json=payload)
                last_response = response
                if response.status_code not in {400, 404, 422} or index == len(variants) - 1:
                    response.raise_for_status()
                    message = response.json()["choices"][0]["message"]
                    content = str(message.get("content") or "")
                    return self._parse_json_object(content)
        if last_response is not None:
            last_response.raise_for_status()
        raise ValueError("model returned no response")

    def _reasoning_options(self, effort: str) -> dict:
        model = self.settings.model_name.lower()
        base_url = self.settings.model_base_url.lower()
        if model.startswith("glm-5") or "bigmodel.cn" in base_url:
            return {
                "thinking": {"type": "enabled"},
                "reasoning_effort": effort,
            }
        return {}

    @staticmethod
    def _source_blocks(context: list[SourceItem]) -> list[dict]:
        source_blocks = []
        for index, item in enumerate(context, start=1):
            try:
                metrics = json.loads(item.metrics_json or "{}")
            except json.JSONDecodeError:
                metrics = {}
            created = item.created_at.isoformat() if isinstance(item.created_at, datetime) else ""
            source_blocks.append(
                {
                    "index": index,
                    "author": item.author_name,
                    "handle": item.author_handle,
                    "published_at": created,
                    "metrics": metrics,
                    "text": item.text_original,
                    "url": item.canonical_url,
                }
            )
        return source_blocks

    @staticmethod
    def _compact_analysis(analysis: dict) -> dict:
        compact = {key: analysis.get(key) for key in _ANALYSIS_FIELDS if key in analysis}
        encoded = json.dumps(compact, ensure_ascii=False)
        if len(encoded) <= 12000:
            return compact
        return {
            "topic": str(analysis.get("topic") or "")[:300],
            "one_sentence_summary": str(analysis.get("one_sentence_summary") or "")[:600],
            "recommended_angle": analysis.get("recommended_angle") or {},
            "uncertainties": (analysis.get("uncertainties") or [])[:8],
            "title_candidates": (analysis.get("title_candidates") or [])[:5],
        }

    @staticmethod
    def _parse_json_object(content: str) -> dict:
        cleaned = content.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        if not cleaned.startswith("{"):
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start >= 0 and end > start:
                cleaned = cleaned[start : end + 1]
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise ValueError("model response is not a JSON object")
        return parsed

    @staticmethod
    def _map_model_claims(value: object, context: list[SourceItem]) -> list[dict]:
        if not isinstance(value, list):
            return []
        claims: list[dict] = []
        for raw in value:
            if not isinstance(raw, dict):
                continue
            try:
                source_index = max(1, int(raw.get("source_index") or 1))
            except (TypeError, ValueError):
                source_index = 1
            item = context[min(source_index - 1, len(context) - 1)]
            verification = str(raw.get("verification") or "source_only")
            if verification not in {"source_only", "needs_external_check"}:
                verification = "source_only"
            statement = str(raw.get("statement") or "").strip()
            if statement:
                claims.append(
                    {
                        "statement": statement[:300],
                        "source_id": item.id,
                        "source_url": item.canonical_url,
                        "verification": verification,
                    }
                )
        return claims

    def _fallback(self, context: Iterable[SourceItem], style: str) -> dict:
        items = list(context)
        focal = items[0]
        cleaned_pairs = [
            (item, self._clean(item.text_original))
            for item in items
            if item.text_original.strip()
        ]
        pieces: list[tuple[SourceItem, str]] = []
        for item, text in cleaned_pairs:
            for sentence in self._sentences(text):
                if sentence and all(sentence != existing for _, existing in pieces):
                    pieces.append((item, sentence))

        first = pieces[0][1] if pieces else "这条 X 内容暂时没有可提取的正文。"
        has_chinese = bool(re.search(r"[\u4e00-\u9fff]", " ".join(text for _, text in pieces)))
        handle = focal.author_handle or focal.author_name or "原作者"
        title = self._fallback_title(first, handle, has_chinese)
        summary = self._trim_sentence(first, 110)
        supporting = [self._trim_sentence(text, 120) for _, text in pieces[1:5]]

        if style == "news":
            body_parts = [
                "发生了什么",
                f"据 @{handle} 发布的内容，{summary}" if has_chinese else f"@{handle} 发布了一条值得跟进的更新：{summary}",
                "核心信息",
                *[f"• {text}" for text in supporting[:3]],
                "为什么值得关注",
                "这条信息的价值在于，它给出了来自原作者的一手描述；但目前材料仍主要来自单一 X 来源。",
                "仍需确认",
                "涉及具体数字、时间、效果或因果判断时，应回到原帖，并结合公开资料做二次核查。",
            ]
        elif style == "opinion":
            body_parts = [
                "我的判断",
                f"这条内容值得关注，但更适合作为一个观察信号，而不是可以直接下结论的完整证据。{summary}",
                "判断依据",
                *[f"• {text}" for text in ([summary, *supporting][:3])],
                "需要警惕的地方",
                "当前信息主要来自原作者自己的表述。没有外部材料支撑的效果、数字和趋势判断，都应保持保留。",
                "留给读者的问题",
                "这条更新真正改变的是产品能力、使用体验，还是只是表达方式？",
            ]
        else:
            body_parts = [
                "先说结论",
                f"@{handle} 的这条更新，核心信息是：{summary}",
                "值得关注的 3 个点",
            ]
            points = [summary, *supporting]
            for index, point in enumerate(points[:3], start=1):
                body_parts.append(f"{index}️⃣ {point}")
            if len(points) < 3:
                body_parts.append("3️⃣ 目前来源信息有限，关键细节仍需要结合原帖上下文确认。")
            body_parts.extend(
                [
                    "这意味着什么",
                    "它至少提供了一个来自原作者的一手信号。真正的影响范围、适用条件和实际效果，还需要更多公开材料验证。",
                    "阅读提醒",
                    "本文是基于 X 原帖的结构化整理，不把作者观点自动当作已验证事实。",
                ]
            )

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
            "body": "\n\n".join(part for part in body_parts if part),
            "tags": ",".join(self._fallback_tags(focal, style, " ".join(text for _, text in pieces))),
            "claims": claims,
        }

    def _sanitize_generated(
        self,
        generated: dict,
        context: list[SourceItem],
        style: str,
    ) -> dict:
        title = re.sub(r"^[#\s]+|[#\s]+$", "", str(generated.get("title") or ""))
        title = re.sub(r"\s+", " ", title).strip("，。！？；：-—")
        body = str(generated.get("body") or "").replace("\r\n", "\n").strip()
        body = re.sub(r"\n{3,}", "\n\n", body)
        if not title:
            focal = context[0]
            title = self._fallback_title(
                self._clean(focal.text_original),
                focal.author_handle or focal.author_name or "原作者",
                bool(re.search(r"[\u4e00-\u9fff]", focal.text_original)),
            )
        if not body:
            body = self._fallback(context, style)["body"]

        raw_tags = str(generated.get("tags") or "")
        tags = []
        for value in re.split(r"[,，#\n]+", raw_tags):
            tag = re.sub(r"\s+", "", value).strip()
            if 1 < len(tag) <= 18 and tag not in tags:
                tags.append(tag)
        if len(tags) < 4:
            tags.extend(
                tag
                for tag in self._fallback_tags(context[0], style, body)
                if tag not in tags
            )

        claims = generated.get("claims") if isinstance(generated.get("claims"), list) else []
        return {
            "title": title[:36],
            "body": body,
            "tags": ",".join(tags[:7]),
            "claims": claims,
        }

    @staticmethod
    def _fallback_title(text: str, handle: str, has_chinese: bool) -> str:
        cleaned = re.sub(r"https?://\S+", "", text)
        cleaned = re.sub(r"[@#]\S+", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip("，。！？；：-— ")
        if has_chinese and cleaned:
            first_sentence = re.split(r"[。！？\n]", cleaned)[0].strip()
            if 8 <= len(first_sentence) <= 24:
                return first_sentence
            if first_sentence:
                return first_sentence[:22].rstrip("，。！？；：")
        handle_text = re.sub(r"[^A-Za-z0-9_\u4e00-\u9fff]", "", handle)[:14]
        return f"来自@{handle_text}的关键信息" if handle_text else "这条X更新讲了什么"

    def _fallback_tags(self, focal: SourceItem, style: str, text: str) -> list[str]:
        normalized = f" {text.lower()} "
        tags = [
            {"news": "科技资讯", "opinion": "编辑观察"}.get(style, "信息拆解"),
            "X平台观察",
        ]
        for needle, tag in _KEYWORD_TAGS.items():
            if needle in normalized and tag not in tags:
                tags.append(tag)
        handle_tag = re.sub(r"[^A-Za-z0-9_\u4e00-\u9fff]", "", focal.author_handle or "")
        if handle_tag and handle_tag not in tags:
            tags.append(handle_tag[:18])
        if "内容创作" not in tags:
            tags.append("内容创作")
        return tags[:7]

    @staticmethod
    def _sentences(text: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized:
            return []
        parts = re.split(r"(?<=[。！？!?；;])\s*|(?<=\.)\s+(?=[A-Z0-9])", normalized)
        return [part.strip() for part in parts if len(part.strip()) >= 4]

    @staticmethod
    def _trim_sentence(text: str, limit: int) -> str:
        cleaned = re.sub(r"https?://\S+", "", text)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) <= limit:
            return cleaned
        cut = max(cleaned.rfind(mark, 0, limit) for mark in ("。", "！", "？", "；", ",", "，"))
        if cut < limit // 2:
            cut = limit
        else:
            cut += 1
        return cleaned[:cut].rstrip("，,；; ") + "…"

    @staticmethod
    def _clean(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()
