from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx
import trafilatura
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import Asset, AssetState, RightsStatus, SourceItem, SourceState
from app.services.material_extraction_providers import (
    ExtractedMaterial,
    MaterialExtractionProviders,
)
from app.services.material_harvester import MaterialHarvesterError
from app.services.safe_material_harvester import SafeMaterialHarvester


class MarketMaterialHarvester(SafeMaterialHarvester):
    """Use market extraction APIs for the Simplified-Chinese material library."""

    extractor_priority = ("firecrawl", "jina", "direct", "playwright")

    def __init__(self, settings) -> None:
        super().__init__(settings)
        self.extractors = MaterialExtractionProviders(settings)

    def discovery_query(self, *, category: str, query: str = "") -> str:
        requested = " ".join(query.split()).strip()
        if requested:
            return requested
        _, terms = self._category_definition(category)
        return " ".join(terms)

    def extractor_statuses(self) -> list[dict[str, Any]]:
        return self.extractors.statuses()

    def import_url(
        self,
        db: Session,
        *,
        url: str,
        category: str,
        editor_note: str = "",
        extractor: str = "auto",
    ) -> SourceItem:
        result, attempts = self.extract_public(url, extractor=extractor)
        text = self._clean(result.text, 60_000, preserve_paragraphs=True)
        if len(text) < 120:
            raise MaterialHarvesterError("公开页面没有提取到足够正文")

        published_at = self._parse_datetime(result.published)
        language = "zh-CN" if self._chinese_ratio(text) >= 0.15 else ""
        external_id = hashlib.sha256(result.final_url.encode("utf-8")).hexdigest()[:40]
        existing = db.scalar(
            select(SourceItem).where(
                SourceItem.platform == "web",
                SourceItem.external_id == external_id,
            )
        )
        site_name = result.site_name or urlparse(result.final_url).hostname or ""
        structured = {
            "title": result.title,
            "category": category,
            "fit_score": self.fit_score(
                category=category,
                text=f"{result.title} {text[:8000]}",
            ),
            "site_name": site_name,
            "description": result.description,
            "published_raw": result.published,
            "discovery": "market-search-public-web",
            "extraction_engine": result.engine,
            "extraction_attempts": attempts,
            "usage_policy": (
                "local research; summary and limited quotation until human rights review"
            ),
        }
        if existing is None:
            source = SourceItem(
                provider="public_web",
                platform="web",
                external_id=external_id,
                canonical_url=result.final_url,
                author_id=urlparse(result.final_url).hostname or "",
                author_handle=urlparse(result.final_url).hostname or "",
                author_name=result.author or site_name,
                text_original=text,
                language=language,
                created_at=published_at,
                captured_at=datetime.now(UTC),
                state=SourceState.available.value,
                content_kind="web_material",
                structured_content_json=json.dumps(structured, ensure_ascii=False),
                editor_note=editor_note.strip()[:6000],
                rights_status=RightsStatus.limited_quote.value,
                rights_note=(
                    "公开网页研究材料；默认仅用于摘要、事实线索与有限引用，"
                    "发布前人工复核。"
                ),
            )
            db.add(source)
            db.flush()
        else:
            source = existing
            source.canonical_url = result.final_url
            source.author_name = result.author or source.author_name
            source.text_original = text
            source.language = language
            source.created_at = published_at or source.created_at
            source.captured_at = datetime.now(UTC)
            source.structured_content_json = json.dumps(structured, ensure_ascii=False)
            source.editor_note = editor_note.strip()[:6000] or source.editor_note
            source.state = SourceState.available.value
            source.rights_status = RightsStatus.limited_quote.value
            source.rights_note = (
                "公开网页研究材料；默认仅用于摘要、事实线索与有限引用，"
                "发布前人工复核。"
            )

        if result.image_url and not any(
            asset.remote_url == result.image_url for asset in source.assets
        ):
            try:
                self.validate_public_url(result.image_url, resolve_dns=False)
                db.add(
                    Asset(
                        source_id=source.id,
                        kind="image",
                        role="source_hero",
                        remote_url=result.image_url,
                        state=AssetState.discovered.value,
                        rights_status=RightsStatus.needs_review.value,
                        rights_note="网页元数据中的主图；下载或发布前核对许可。",
                    )
                )
            except MaterialHarvesterError:
                pass
        db.flush()
        return source

    def extract_public(
        self,
        url: str,
        *,
        extractor: str = "auto",
    ) -> tuple[ExtractedMaterial, list[dict[str, str]]]:
        initial = self.validate_public_url(url)
        self._respect_rate_limit(urlparse(initial).hostname or "")
        self._check_robots(initial)

        requested = extractor or self.settings.material_extract_provider or "auto"
        if requested not in {"auto", *self.extractor_priority}:
            raise MaterialHarvesterError(f"未知正文抓取供应商：{requested}")
        if requested == "auto":
            order: list[str] = []
            if self.settings.firecrawl_api_key:
                order.append("firecrawl")
            order.extend(["jina", "direct"])
            if self.settings.material_browser_enabled:
                order.append("playwright")
        else:
            order = [requested]

        attempts: list[dict[str, str]] = []
        for name in order:
            if not self.extractors.configured(name):
                attempts.append(
                    {"extractor": name, "status": "skipped", "detail": "未配置或已关闭"}
                )
                continue
            try:
                result = self._extract_one(name, initial)
                result = self._validated_result(result)
            except (
                httpx.HTTPError,
                ValueError,
                KeyError,
                TypeError,
                MaterialHarvesterError,
            ) as exc:
                attempts.append(
                    {"extractor": name, "status": "failed", "detail": str(exc)[:300]}
                )
                continue
            status = "ok" if len(result.text) >= 120 else "empty"
            attempts.append(
                {
                    "extractor": name,
                    "status": status,
                    "detail": f"{len(result.text)} chars",
                }
            )
            if status == "ok":
                return result, attempts

        details = "；".join(
            f"{item['extractor']}={item['status']}({item['detail']})"
            for item in attempts
        )
        raise MaterialHarvesterError(f"所有正文抓取方式均失败：{details}")

    def _extract_one(self, name: str, url: str) -> ExtractedMaterial:
        if name in {"firecrawl", "jina"}:
            return self.extractors.extract(name, url)
        if name == "direct":
            final_url, markup, content_type = self.fetch_public(url, expected="html")
            if "html" not in content_type and "xhtml" not in content_type:
                raise MaterialHarvesterError("当前原料收录器只支持公开 HTML 文章页")
            return self._extract_html(markup, final_url, "http+trafilatura")
        if name == "playwright":
            final_url, markup = self.fetch_browser_public(url)
            return self._extract_html(markup, final_url, "playwright+trafilatura")
        raise MaterialHarvesterError(f"未实现正文抓取供应商：{name}")

    def _validated_result(self, result: ExtractedMaterial) -> ExtractedMaterial:
        final_url = self.validate_public_url(result.final_url)
        self._check_robots(final_url)
        if final_url == result.final_url:
            return result
        return ExtractedMaterial(**{**result.as_dict(), "final_url": final_url})

    def _extract_html(
        self,
        markup: str,
        final_url: str,
        engine: str,
    ) -> ExtractedMaterial:
        extracted = trafilatura.bare_extraction(
            markup,
            url=final_url,
            include_comments=False,
            include_tables=True,
            include_images=True,
            favor_precision=True,
            with_metadata=True,
        )
        document = (
            extracted.as_dict()
            if extracted is not None and hasattr(extracted, "as_dict")
            else {}
        )
        if not isinstance(document, dict):
            document = {}
        primary_text = self._clean(
            str(document.get("text") or ""),
            60_000,
            preserve_paragraphs=True,
        )
        text = primary_text if len(primary_text) >= 120 else self._fallback_text(markup)
        meta = self._html_metadata(markup)
        return ExtractedMaterial(
            final_url=final_url,
            text=text,
            title=self._clean(
                str(
                    document.get("title")
                    or meta.get("og:title")
                    or meta.get("title")
                    or ""
                ),
                300,
            ),
            author=self._clean(
                str(document.get("author") or meta.get("author") or ""),
                160,
            ),
            published=str(
                document.get("date")
                or meta.get("article:published_time")
                or ""
            ),
            image_url=str(
                document.get("image")
                or meta.get("og:image")
                or meta.get("twitter:image")
                or ""
            ).strip(),
            site_name=self._clean(
                str(
                    document.get("sitename")
                    or meta.get("og:site_name")
                    or urlparse(final_url).hostname
                    or ""
                ),
                180,
            ),
            description=self._clean(
                str(document.get("description") or meta.get("description") or ""),
                1000,
            ),
            engine=engine,
        )

    def fetch_browser_public(self, url: str) -> tuple[str, str]:
        if importlib.util.find_spec("playwright") is None:
            raise MaterialHarvesterError("本地 Playwright 未安装")
        from playwright.sync_api import Route, sync_playwright

        initial = self.validate_public_url(url)
        self._respect_rate_limit(urlparse(initial).hostname or "")
        self._check_robots(initial)

        def guard(route: Route) -> None:
            request_url = route.request.url
            if request_url.startswith(("data:", "blob:", "about:")):
                route.continue_()
                return
            try:
                safe_url = self.validate_public_url(request_url)
                if route.request.is_navigation_request():
                    self._check_robots(safe_url)
            except MaterialHarvesterError:
                route.abort()
                return
            route.continue_()

        timeout_ms = int(self.settings.material_browser_timeout_seconds * 1000)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=self.settings.material_user_agent,
                locale="zh-CN",
                java_script_enabled=True,
                accept_downloads=False,
            )
            page = context.new_page()
            page.route("**/*", guard)
            response = page.goto(initial, wait_until="domcontentloaded", timeout=timeout_ms)
            if response is not None and response.status >= 400:
                browser.close()
                raise MaterialHarvesterError(f"动态页面返回 HTTP {response.status}")
            page.wait_for_timeout(self.settings.material_browser_wait_ms)
            final_url = self.validate_public_url(page.url)
            self._check_robots(final_url)
            markup = page.content()
            browser.close()
        if len(markup.encode("utf-8")) > self.settings.material_max_page_bytes:
            raise MaterialHarvesterError("动态页面超过原料采集大小上限")
        return final_url, markup
