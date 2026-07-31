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


class EditorialService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(self, db: Session, source: SourceItem, style: str) -> DraftRevision:
        context = self._context(db, source)
        generated = await self._model_generate(context, style)
        generator = "model"
        if generated is None:
            generated = self._fallback(context, style)
            generator = "structured-fallback"
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
                    "model": self.settings.model_name if generator == "model" else "",
                },
                ensure_ascii=False,
            ),
            created_by="model" if generator == "model" else "system",
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

        prompt = f"""
请把下列 X 来源整理成一篇真正可发布的中文小红书笔记。

写作类型：{_STYLE_LABELS.get(style, style)}
具体要求：{_STYLE_GUIDES.get(style, _STYLE_GUIDES["explain"])}

必须遵守：
1. 标题 12-22 个汉字，具体、有信息量，不使用“震惊”“炸裂”“必看”等廉价标题党。
2. 开头两行必须让读者立刻知道发生了什么以及为什么值得关注。
3. 正文 450-900 个汉字；短段落；每段不超过 4 行；最多使用 4 个克制的 emoji。
4. 不要逐句翻译或复述。先提炼，再解释，再给出判断边界。
5. 原作者事实、原作者观点、编辑补充必须明确区分。
6. 不得补写来源中没有的人名、数字、日期、因果关系或行业结论。
7. 对不确定信息使用“据原作者描述”“目前尚不能确认”等表述。
8. 标签给出 4-7 个，不带 #，避免“热门”“干货”等空泛标签。
9. claims 中每一项必须包含 statement、source_index、verification，verification 只能是 source_only 或 needs_external_check。

只输出合法 JSON：
{{
  "title": "标题",
  "body": "完整正文",
  "tags": ["标签1", "标签2"],
  "claims": [
    {{"statement": "可核查陈述", "source_index": 1, "verification": "source_only"}}
  ]
}}

来源数据：
{json.dumps(source_blocks, ensure_ascii=False)[:18000]}
""".strip()

        request_body = {
            "model": self.settings.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是一名严谨但有表达力的中文内容主编，熟悉小红书阅读节奏。"
                        "你的任务是提高信息密度和可读性，不是制造情绪或伪造事实。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.55,
            "response_format": {"type": "json_object"},
        }
        headers = {"Content-Type": "application/json"}
        if self.settings.model_api_key:
            headers["Authorization"] = f"Bearer {self.settings.model_api_key}"

        try:
            async with httpx.AsyncClient(timeout=75) as client:
                endpoint = self.settings.model_base_url.rstrip("/") + "/chat/completions"
                response = await client.post(endpoint, headers=headers, json=request_body)
                # Some local gateways do not support response_format. Retry once
                # without it rather than silently falling back to low-quality copy.
                if response.status_code in {400, 404, 422}:
                    request_body.pop("response_format", None)
                    response = await client.post(endpoint, headers=headers, json=request_body)
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                parsed = self._parse_json_object(content)
                tags = parsed.get("tags")
                if isinstance(tags, list):
                    tags_value = ",".join(str(tag) for tag in tags)
                else:
                    tags_value = str(tags or "")
                claims = self._map_model_claims(parsed.get("claims"), context)
                return {
                    "title": str(parsed.get("title") or ""),
                    "body": str(parsed.get("body") or ""),
                    "tags": tags_value,
                    "claims": claims,
                }
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

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
