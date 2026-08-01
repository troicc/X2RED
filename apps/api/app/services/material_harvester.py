from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
import threading
import time
import urllib.robotparser
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import Asset, AssetState, RightsStatus, SourceItem, SourceState


class MaterialHarvesterError(RuntimeError):
    pass


@dataclass(frozen=True)
class MaterialCandidate:
    url: str
    title: str
    summary: str
    site: str
    published_at: str
    image_url: str
    discovery_source: str
    category: str
    fit_score: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "summary": self.summary,
            "site": self.site,
            "published_at": self.published_at,
            "image_url": self.image_url,
            "discovery_source": self.discovery_source,
            "category": self.category,
            "fit_score": self.fit_score,
        }


_CATEGORY_QUERIES = {
    "mature_life": (
        "older adults daily life family retirement caregiving sleep meals community China",
        ("退休", "养老", "中老年", "老年", "父母", "照护", "家庭", "社区", "三餐", "睡眠"),
    ),
    "comfort": (
        "work stress family pressure loneliness emotional wellbeing daily life China",
        ("压力", "疲惫", "焦虑", "独处", "情绪", "家庭", "关系", "加班", "生活", "照顾自己"),
    ),
    "seasonal": (
        "Chinese solar terms seasonal food weather daily life China",
        ("节气", "物候", "换季", "春分", "清明", "谷雨", "夏至", "处暑", "秋分", "冬至"),
    ),
    "photo_quote": (
        "Chinese documentary photography ordinary people daily life photo essay",
        ("摄影", "照片", "影像", "人物", "街道", "社区", "家庭", "生活记录", "纪实"),
    ),
    "short_commentary": (
        "China society work technology daily life public discussion",
        ("社会", "工作", "生活", "变化", "趋势", "公共", "讨论"),
    ),
}

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_META_RE = re.compile(
    r"<meta\s+[^>]*(?:property|name)=[\"']([^\"']+)[\"'][^>]*content=[\"']([^\"']*)[\"'][^>]*>",
    re.I,
)
_LANG_RE = re.compile(r"[\u4e00-\u9fff]")


class MaterialHarvester:
    """Discover and import public Chinese web material without bypassing access controls."""

    _host_times: dict[str, float] = {}
    _rate_lock = threading.Lock()

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.headers = {
            "User-Agent": settings.material_user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/rss+xml;q=0.8,application/json;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
        }

    def discover_gdelt(
        self,
        *,
        category: str,
        query: str = "",
        max_records: int = 30,
        timespan: str = "7d",
    ) -> list[dict[str, Any]]:
        english_query, _ = self._category_definition(category)
        requested = re.sub(r"\s+", " ", query).strip()
        search = requested or english_query
        gdelt_query = f"({search}) sourcelang:chinese"
        params = {
            "query": gdelt_query,
            "mode": "ArtList",
            "maxrecords": min(max(max_records, 1), 100),
            "format": "json",
            "sort": "HybridRel",
            "timespan": timespan,
        }
        response = httpx.get(
            self.settings.material_gdelt_base_url,
            params=params,
            headers=self.headers,
            timeout=max(self.settings.request_timeout_seconds, 30.0),
            follow_redirects=True,
        )
        response.raise_for_status()
        data = response.json()
        articles = data.get("articles") if isinstance(data, dict) else []
        output: list[MaterialCandidate] = []
        seen: set[str] = set()
        for raw in articles if isinstance(articles, list) else []:
            if not isinstance(raw, dict):
                continue
            url = str(raw.get("url") or "").strip()
            if not url or url in seen:
                continue
            try:
                self.validate_public_url(url, resolve_dns=False)
            except MaterialHarvesterError:
                continue
            seen.add(url)
            title = self._clean(str(raw.get("title") or ""), 240)
            summary = self._clean(
                str(raw.get("seendate") or raw.get("socialimage") or ""),
                320,
            )
            site = str(raw.get("domain") or urlparse(url).hostname or "")
            published = str(raw.get("seendate") or "")
            image = str(raw.get("socialimage") or "")
            score = self.fit_score(
                category=category,
                text=" ".join((title, str(raw.get("language") or ""), site)),
            )
            output.append(
                MaterialCandidate(
                    url=url,
                    title=title or site,
                    summary=summary,
                    site=site,
                    published_at=published,
                    image_url=image,
                    discovery_source="gdelt-doc-2",
                    category=category,
                    fit_score=score,
                )
            )
        return [item.as_dict() for item in output]

    def discover_feed(
        self,
        *,
        url: str,
        category: str,
        max_records: int = 50,
    ) -> list[dict[str, Any]]:
        final_url, content, content_type = self.fetch_public(url, expected="xml")
        if "xml" not in content_type and not content.lstrip().startswith("<"):
            raise MaterialHarvesterError("该地址不是 RSS/Atom/站点地图 XML")
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            raise MaterialHarvesterError("无法解析 RSS/Atom/站点地图") from exc
        candidates: list[MaterialCandidate] = []
        is_sitemap = root.tag.lower().endswith("urlset") or root.tag.lower().endswith("sitemapindex")
        if is_sitemap:
            for node in root.iter():
                if not node.tag.lower().endswith("loc") or not (node.text or "").strip():
                    continue
                target = (node.text or "").strip()
                try:
                    self.validate_public_url(target, resolve_dns=False)
                except MaterialHarvesterError:
                    continue
                candidates.append(
                    MaterialCandidate(
                        url=target,
                        title=urlparse(target).path.rstrip("/").split("/")[-1] or target,
                        summary="来自公开站点地图，收录前会再次检查 robots.txt。",
                        site=urlparse(target).hostname or "",
                        published_at="",
                        image_url="",
                        discovery_source="sitemap",
                        category=category,
                        fit_score=0.5,
                    )
                )
                if len(candidates) >= max_records:
                    break
        else:
            for item in root.iter():
                local = item.tag.rsplit("}", 1)[-1].lower()
                if local not in {"item", "entry"}:
                    continue
                values: dict[str, str] = {}
                for child in list(item):
                    key = child.tag.rsplit("}", 1)[-1].lower()
                    text = " ".join(child.itertext()).strip()
                    if key == "link":
                        text = child.attrib.get("href") or text
                    if text and key not in values:
                        values[key] = text
                target = values.get("link") or values.get("guid") or values.get("id") or ""
                if not target:
                    continue
                target = urljoin(final_url, target)
                try:
                    self.validate_public_url(target, resolve_dns=False)
                except MaterialHarvesterError:
                    continue
                title = self._clean(values.get("title", ""), 240)
                summary = self._clean(
                    values.get("summary") or values.get("description") or values.get("content", ""),
                    360,
                )
                published = values.get("published") or values.get("updated") or values.get("pubdate") or ""
                candidates.append(
                    MaterialCandidate(
                        url=target,
                        title=title or target,
                        summary=summary,
                        site=urlparse(target).hostname or "",
                        published_at=published,
                        image_url="",
                        discovery_source="rss-atom",
                        category=category,
                        fit_score=self.fit_score(category=category, text=f"{title} {summary}"),
                    )
                )
                if len(candidates) >= max_records:
                    break
        return [item.as_dict() for item in candidates]

    def import_url(
        self,
        db: Session,
        *,
        url: str,
        category: str,
        editor_note: str = "",
    ) -> SourceItem:
        final_url, markup, content_type = self.fetch_public(url, expected="html")
        if "html" not in content_type and "xhtml" not in content_type:
            raise MaterialHarvesterError("当前原料收录器只支持公开 HTML 文章页")
        extracted = trafilatura.bare_extraction(
            markup,
            url=final_url,
            include_comments=False,
            include_tables=True,
            include_images=True,
            favor_precision=True,
            with_metadata=True,
        )
        document = extracted.as_dict() if extracted is not None and hasattr(extracted, "as_dict") else {}
        if not isinstance(document, dict):
            document = {}
        text = self._clean(str(document.get("text") or ""), 60_000, preserve_paragraphs=True)
        if len(text) < 120:
            text = self._fallback_text(markup)
        if len(text) < 120:
            raise MaterialHarvesterError("公开页面没有提取到足够正文，可能是动态页面或访问受限")
        meta = self._html_metadata(markup)
        title = self._clean(
            str(document.get("title") or meta.get("og:title") or meta.get("title") or ""),
            300,
        )
        author = self._clean(str(document.get("author") or meta.get("author") or ""), 160)
        published = str(document.get("date") or meta.get("article:published_time") or "")
        published_at = self._parse_datetime(published)
        image_url = str(
            document.get("image")
            or meta.get("og:image")
            or meta.get("twitter:image")
            or ""
        ).strip()
        language = "zh-CN" if self._chinese_ratio(text) >= 0.15 else str(document.get("language") or "")
        external_id = hashlib.sha256(final_url.encode("utf-8")).hexdigest()[:40]
        existing = db.scalar(
            select(SourceItem).where(
                SourceItem.platform == "web",
                SourceItem.external_id == external_id,
            )
        )
        structured = {
            "title": title,
            "category": category,
            "fit_score": self.fit_score(category=category, text=f"{title} {text[:8000]}"),
            "site_name": str(document.get("sitename") or meta.get("og:site_name") or urlparse(final_url).hostname or ""),
            "description": self._clean(str(document.get("description") or meta.get("description") or ""), 1000),
            "published_raw": published,
            "discovery": "public-web-material",
            "extraction_engine": "trafilatura",
            "usage_policy": "local research; summary and limited quotation only until human rights review",
        }
        if existing is None:
            source = SourceItem(
                provider="public_web",
                platform="web",
                external_id=external_id,
                canonical_url=final_url,
                author_id=urlparse(final_url).hostname or "",
                author_handle=urlparse(final_url).hostname or "",
                author_name=author or str(structured["site_name"]),
                text_original=text,
                language=language,
                created_at=published_at,
                captured_at=datetime.now(UTC),
                state=SourceState.available.value,
                content_kind="web_material",
                structured_content_json=json.dumps(structured, ensure_ascii=False),
                editor_note=editor_note.strip()[:6000],
                rights_status=RightsStatus.limited_quote.value,
                rights_note="公开网页研究材料；默认仅用于摘要、事实线索与有限引用，发布前人工复核。",
            )
            db.add(source)
            db.flush()
        else:
            source = existing
            source.canonical_url = final_url
            source.author_name = author or source.author_name
            source.text_original = text
            source.language = language
            source.created_at = published_at or source.created_at
            source.captured_at = datetime.now(UTC)
            source.structured_content_json = json.dumps(structured, ensure_ascii=False)
            source.editor_note = editor_note.strip()[:6000] or source.editor_note
            source.state = SourceState.available.value
            source.rights_status = RightsStatus.limited_quote.value
            source.rights_note = "公开网页研究材料；默认仅用于摘要、事实线索与有限引用，发布前人工复核。"
        if image_url and not any(asset.remote_url == image_url for asset in source.assets):
            try:
                self.validate_public_url(image_url, resolve_dns=False)
                db.add(
                    Asset(
                        source_id=source.id,
                        kind="image",
                        role="source_hero",
                        remote_url=image_url,
                        state=AssetState.discovered.value,
                        rights_status=RightsStatus.needs_review.value,
                        rights_note="网页元数据中的主图；下载或发布前核对许可。",
                    )
                )
            except MaterialHarvesterError:
                pass
        db.flush()
        return source

    def fetch_public(self, url: str, *, expected: str) -> tuple[str, str, str]:
        current = self.validate_public_url(url)
        for _ in range(6):
            parsed = urlparse(current)
            self._respect_rate_limit(parsed.hostname or "")
            self._check_robots(current)
            with httpx.Client(
                headers=self.headers,
                timeout=max(self.settings.request_timeout_seconds, 30.0),
                follow_redirects=False,
            ) as client:
                with client.stream("GET", current) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise MaterialHarvesterError("网页重定向缺少 Location")
                        current = self.validate_public_url(urljoin(current, location))
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").lower()
                    if expected == "html" and not any(token in content_type for token in ("html", "xhtml")):
                        raise MaterialHarvesterError(f"不支持的页面类型：{content_type or '未知'}")
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > self.settings.material_max_page_bytes:
                            raise MaterialHarvesterError("页面超过原料采集大小上限")
                        chunks.append(chunk)
                    encoding = response.encoding or "utf-8"
                    return current, b"".join(chunks).decode(encoding, errors="replace"), content_type
        raise MaterialHarvesterError("网页重定向次数过多")

    def validate_public_url(self, url: str, *, resolve_dns: bool = True) -> str:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise MaterialHarvesterError("只允许公开的 HTTP/HTTPS 地址")
        hostname = parsed.hostname.rstrip(".").lower()
        if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith((".local", ".internal", ".lan")):
            raise MaterialHarvesterError("禁止访问本机或内网地址")
        try:
            address = ipaddress.ip_address(hostname)
            self._reject_address(address)
        except ValueError:
            if resolve_dns:
                try:
                    infos = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
                except socket.gaierror as exc:
                    raise MaterialHarvesterError("无法解析网页域名") from exc
                for info in infos:
                    self._reject_address(ipaddress.ip_address(info[4][0]))
        return parsed.geturl()

    def _check_robots(self, url: str) -> None:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)
        try:
            response = httpx.get(
                robots_url,
                headers=self.headers,
                timeout=min(max(self.settings.request_timeout_seconds, 10.0), 30.0),
                follow_redirects=True,
            )
            if response.status_code == 200:
                parser.parse(response.text.splitlines())
            elif response.status_code in {401, 403}:
                raise MaterialHarvesterError("站点 robots.txt 禁止自动访问")
            else:
                parser.parse([])
        except httpx.HTTPError:
            parser.parse([])
        if not parser.can_fetch(self.settings.material_user_agent, url):
            raise MaterialHarvesterError("站点 robots.txt 不允许采集该页面")

    def fit_score(self, *, category: str, text: str) -> float:
        _, terms = self._category_definition(category)
        normalized = text.lower()
        hits = sum(1 for term in terms if term.lower() in normalized)
        chinese_bonus = 0.12 if self._chinese_ratio(text) >= 0.15 else 0.0
        score = 0.35 + min(hits, 5) * 0.11 + chinese_bonus
        return round(min(score, 0.98), 2)

    @staticmethod
    def _reject_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
        if any(
            (
                address.is_private,
                address.is_loopback,
                address.is_link_local,
                address.is_multicast,
                address.is_reserved,
                address.is_unspecified,
            )
        ):
            raise MaterialHarvesterError("禁止访问本机、内网或保留地址")

    def _respect_rate_limit(self, host: str) -> None:
        with self._rate_lock:
            now = time.monotonic()
            last = self._host_times.get(host, 0.0)
            wait = self.settings.material_min_interval_seconds - (now - last)
            if wait > 0:
                time.sleep(wait)
            self._host_times[host] = time.monotonic()

    @staticmethod
    def _category_definition(category: str) -> tuple[str, tuple[str, ...]]:
        value = _CATEGORY_QUERIES.get(category)
        if value is None:
            raise MaterialHarvesterError("未知的生活原料类别")
        return value

    @staticmethod
    def _html_metadata(markup: str) -> dict[str, str]:
        output: dict[str, str] = {}
        title = _TITLE_RE.search(markup)
        if title:
            output["title"] = re.sub(r"\s+", " ", title.group(1)).strip()
        for key, value in _META_RE.findall(markup[:500_000]):
            output[key.lower()] = value.strip()
        return output

    @staticmethod
    def _fallback_text(markup: str) -> str:
        without_scripts = re.sub(r"<(script|style|noscript)\b[^>]*>.*?</\1>", " ", markup, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", "\n", without_scripts)
        text = html_unescape(text)
        return MaterialHarvester._clean(text, 60_000, preserve_paragraphs=True)

    @staticmethod
    def _clean(value: str, limit: int, *, preserve_paragraphs: bool = False) -> str:
        text = html_unescape(value)
        if preserve_paragraphs:
            lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
            text = "\n\n".join(line for line in lines if line)
        else:
            text = re.sub(r"\s+", " ", text).strip()
        return text[:limit]

    @staticmethod
    def _chinese_ratio(text: str) -> float:
        if not text:
            return 0.0
        chinese = len(_LANG_RE.findall(text[:20_000]))
        visible = len(re.sub(r"\s+", "", text[:20_000]))
        return chinese / max(visible, 1)

    @staticmethod
    def _parse_datetime(value: str) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            try:
                parsed = parsedate_to_datetime(value)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
            except (TypeError, ValueError):
                return None


def html_unescape(value: str) -> str:
    import html

    return html.unescape(value)
