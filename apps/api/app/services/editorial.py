from __future__ import annotations

import json
import re
from collections.abc import Iterable

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


class EditorialService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(self, db: Session, source: SourceItem, style: str) -> DraftRevision:
        context = self._context(db, source)
        generated = await self._model_generate(context, style)
        if generated is None:
            generated = self._fallback(context, style)

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
                    "generator": "model" if self.settings.model_name else "deterministic-fallback",
                },
                ensure_ascii=False,
            ),
            created_by="model" if self.settings.model_name else "system",
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
        if not (
            self.settings.model_base_url
            and self.settings.model_api_key
            and self.settings.model_name
        ):
            return None

        source_text = "\n\n".join(
            f"[{item.author_handle or item.author_name}] {item.text_original}\n来源：{item.canonical_url}"
            for item in context
        )
        prompt = (
            "把以下 X 内容整理成中文小红书草稿。必须忠实区分原作者事实、观点和编辑补充；"
            "不确定的事实用保守措辞；不要伪造背景。只输出 JSON，字段为 title、body、tags、claims。"
            f"\n写作风格：{_STYLE_LABELS.get(style, style)}\n\n{source_text[:12000]}"
        )
        body = {
            "model": self.settings.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "你是严谨的中文社媒编辑，只输出合法 JSON。",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        }
        try:
            async with httpx.AsyncClient(timeout=45) as client:
                response = await client.post(
                    self.settings.model_base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {self.settings.model_api_key}"},
                    json=body,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                return {
                    "title": str(parsed.get("title") or ""),
                    "body": str(parsed.get("body") or ""),
                    "tags": str(parsed.get("tags") or ""),
                    "claims": parsed.get("claims") if isinstance(parsed.get("claims"), list) else [],
                }
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _fallback(self, context: Iterable[SourceItem], style: str) -> dict:
        items = list(context)
        focal = items[0]
        cleaned_pairs = [
            (item, self._clean(item.text_original))
            for item in items
            if item.text_original.strip()
        ]
        cleaned = [text for _, text in cleaned_pairs]
        first = cleaned[0] if cleaned else "这条 X 内容暂无可用正文。"
        title_seed = re.sub(r"https?://\S+", "", first).strip()
        title = title_seed[:18].rstrip("，。！？；：") or "一条值得关注的 X 更新"

        sections = []
        if style == "news":
            sections.append("发生了什么")
            sections.append(first)
        elif style == "opinion":
            sections.append("我为什么关注这条信息")
            sections.append(first)
            sections.append("编辑观察：这部分需要结合更多来源再形成结论，当前先保留原作者观点。")
        else:
            sections.append("先说结论")
            sections.append(first)
            if len(cleaned) > 1:
                sections.append("作者随后补充")
                sections.extend(f"• {text}" for text in cleaned[1:6])
            sections.append("阅读提醒：以上主要来自原作者 Thread，涉及数字、日期或因果判断时建议查看原帖和外部来源。")

        body = "\n\n".join(sections)
        claims = [
            {
                "statement": text[:300],
                "source_id": item.id,
                "source_url": item.canonical_url,
                "verification": "source_only",
            }
            for item, text in cleaned_pairs
        ]
        handle_tag = focal.author_handle.replace("_", "") if focal.author_handle else "X观察"
        return {
            "title": title,
            "body": body,
            "tags": f"X观察,信息整理,{handle_tag}",
            "claims": claims,
        }

    @staticmethod
    def _clean(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()
