from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

import httpx

from app.core.config import Settings
from app.services.material_harvester import MaterialHarvesterError


@dataclass(frozen=True)
class ExtractedMaterial:
    final_url: str
    text: str
    title: str = ""
    author: str = ""
    published: str = ""
    image_url: str = ""
    site_name: str = ""
    description: str = ""
    engine: str = ""

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


class MaterialExtractionProviders:
    """Market article-extraction adapters used by the material library."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def statuses(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "firecrawl",
                "label": "Firecrawl Scrape",
                "configured": bool(self.settings.firecrawl_api_key),
                "description": "商业网页抓取，支持动态页面并返回 Markdown 与元数据。",
            },
            {
                "id": "jina",
                "label": "Jina Reader",
                "configured": True,
                "description": "Reader API 可无密钥低频使用；配置密钥后提高限额。",
            },
            {
                "id": "direct",
                "label": "HTTP + Trafilatura",
                "configured": True,
                "description": "本地公开 HTML 直读兜底。",
            },
            {
                "id": "playwright",
                "label": "本地 Playwright",
                "configured": bool(self.settings.material_browser_enabled),
                "description": "显式兼容兜底，默认关闭且不复用个人登录态。",
            },
        ]

    def configured(self, provider: str) -> bool:
        if provider == "firecrawl":
            return bool(self.settings.firecrawl_api_key)
        if provider == "jina":
            return True
        if provider == "direct":
            return True
        if provider == "playwright":
            return bool(self.settings.material_browser_enabled)
        return False

    def extract(self, provider: str, url: str) -> ExtractedMaterial:
        if provider == "firecrawl":
            return self._firecrawl(url)
        if provider == "jina":
            return self._jina(url)
        raise MaterialHarvesterError(f"未实现外部正文抓取供应商：{provider}")

    def _firecrawl(self, url: str) -> ExtractedMaterial:
        response = httpx.post(
            self.settings.firecrawl_base_url.rstrip("/") + "/v2/scrape",
            headers={
                "Authorization": f"Bearer {self.settings.firecrawl_api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "url": url,
                "formats": ["markdown"],
                "onlyMainContent": True,
                "removeBase64Images": True,
                "blockAds": True,
                "timeout": int(max(self.settings.request_timeout_seconds, 45.0) * 1000),
                "location": {
                    "country": "CN",
                    "languages": ["zh-CN"],
                },
            },
            timeout=max(self.settings.request_timeout_seconds, 60.0),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("success") is False:
            raise MaterialHarvesterError(
                str(payload.get("error") or "Firecrawl 抓取失败")
                if isinstance(payload, dict)
                else "Firecrawl 响应格式错误"
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise MaterialHarvesterError("Firecrawl 未返回正文数据")
        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        return ExtractedMaterial(
            final_url=str(
                metadata.get("sourceURL")
                or metadata.get("url")
                or data.get("url")
                or url
            ),
            text=self.markdown_to_text(str(data.get("markdown") or "")),
            title=self.clean(metadata.get("title"), 300),
            author=self.clean(metadata.get("author"), 160),
            published=str(
                metadata.get("publishedTime")
                or metadata.get("published_at")
                or metadata.get("date")
                or ""
            ),
            image_url=str(
                metadata.get("ogImage")
                or metadata.get("image")
                or metadata.get("og:image")
                or ""
            ).strip(),
            site_name=self.clean(
                metadata.get("siteName") or metadata.get("ogSiteName"),
                180,
            ),
            description=self.clean(
                metadata.get("description") or metadata.get("ogDescription"),
                1000,
            ),
            engine="firecrawl-v2",
        )

    def _jina(self, url: str) -> ExtractedMaterial:
        headers = {
            "Accept": "application/json",
            "User-Agent": self.settings.material_user_agent,
            "X-Return-Format": "markdown",
            "X-Remove-Selector": "nav,footer,aside,form",
        }
        if self.settings.jina_api_key:
            headers["Authorization"] = f"Bearer {self.settings.jina_api_key}"
        response = httpx.get(
            f"{self.settings.jina_reader_base_url.rstrip('/')}/{url}",
            headers=headers,
            timeout=max(self.settings.request_timeout_seconds, 60.0),
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "json" in content_type:
            payload = response.json()
            data: Any = payload.get("data") if isinstance(payload, dict) else payload
            if isinstance(data, list):
                data = data[0] if data else {}
            if not isinstance(data, dict):
                raise MaterialHarvesterError("Jina Reader 未返回正文数据")
            return ExtractedMaterial(
                final_url=str(data.get("url") or data.get("sourceURL") or url),
                text=self.markdown_to_text(
                    str(data.get("content") or data.get("markdown") or "")
                ),
                title=self.clean(data.get("title"), 300),
                author=self.clean(data.get("author"), 160),
                published=str(
                    data.get("publishedTime")
                    or data.get("published_at")
                    or data.get("date")
                    or ""
                ),
                image_url=str(data.get("image") or data.get("imageUrl") or "").strip(),
                site_name=self.clean(data.get("siteName"), 180),
                description=self.clean(data.get("description"), 1000),
                engine="jina-reader",
            )
        metadata, markdown = self.parse_jina_text(response.text)
        return ExtractedMaterial(
            final_url=metadata.get("URL Source") or url,
            text=self.markdown_to_text(markdown),
            title=self.clean(metadata.get("Title"), 300),
            published=metadata.get("Published Time", ""),
            description=self.clean(metadata.get("Description"), 1000),
            engine="jina-reader",
        )

    @staticmethod
    def parse_jina_text(value: str) -> tuple[dict[str, str], str]:
        metadata: dict[str, str] = {}
        marker = "Markdown Content:"
        head, separator, body = value.partition(marker)
        for line in head.splitlines():
            key, found, content = line.partition(":")
            if found and key.strip() in {
                "Title",
                "URL Source",
                "Published Time",
                "Description",
            }:
                metadata[key.strip()] = content.strip()
        return metadata, body.strip() if separator else value

    @staticmethod
    def markdown_to_text(value: str) -> str:
        text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", value)
        text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.M)
        text = re.sub(r"^\s*>\s?", "", text, flags=re.M)
        text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)
        text = re.sub(r"`{1,3}", "", text)
        lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
        return "\n\n".join(line for line in lines if line)

    @staticmethod
    def clean(value: Any, limit: int) -> str:
        return " ".join(str(value or "").split())[:limit]
