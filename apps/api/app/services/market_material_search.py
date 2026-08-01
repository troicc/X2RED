from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from app.services.material_search_providers import (
    MaterialSearchEngine,
    MaterialSearchError,
    SearchCandidate,
)


_PROVIDER_META: dict[str, tuple[str, bool, str]] = {
    "serpapi_baidu": (
        "SerpApi · 百度",
        True,
        "百度自然搜索结果，适合发现简中网页。",
    ),
    "dataforseo_baidu": (
        "DataForSEO · 百度",
        True,
        "实时 Baidu SERP，可返回解析后的目标网址。",
    ),
    "firecrawl": (
        "Firecrawl Search",
        False,
        "商业搜索与抓取一体化服务。",
    ),
    "brave": (
        "Brave Search · zh-CN",
        False,
        "独立网页索引，支持中国地区、简中语言和时间过滤。",
    ),
    "jina": (
        "Jina Search",
        False,
        "面向机器消费的实时搜索，使用中文查询和中国地区偏好。",
    ),
    "tavily": (
        "Tavily · China",
        False,
        "面向 Agent 的实时搜索，使用 China 区域偏好。",
    ),
    "gdelt": (
        "GDELT 中文新闻",
        False,
        "无需密钥的新闻索引兜底，不代表完整简中互联网。",
    ),
}


class MarketMaterialSearchEngine(MaterialSearchEngine):
    """Add market search APIs to the existing Baidu-first provider layer."""

    auto_priority = (
        "serpapi_baidu",
        "dataforseo_baidu",
        "firecrawl",
        "brave",
        "jina",
        "tavily",
        "gdelt",
    )

    def statuses(self) -> list[dict[str, Any]]:
        return [
            {
                "id": provider,
                "label": _PROVIDER_META[provider][0],
                "configured": self.configured(provider),
                "native_chinese": _PROVIDER_META[provider][1],
                "description": _PROVIDER_META[provider][2],
            }
            for provider in self.auto_priority
        ]

    def configured(self, provider: str) -> bool:
        if provider == "firecrawl":
            return bool(self.settings.firecrawl_api_key)
        if provider == "jina":
            return bool(self.settings.jina_api_key)
        return super().configured(provider)

    def _search_one(
        self,
        provider: str,
        *,
        query: str,
        max_results: int,
        timespan: str,
    ) -> list[SearchCandidate]:
        if provider == "firecrawl":
            return self._search_firecrawl(query, max_results, timespan)
        if provider == "jina":
            return self._search_jina(query, max_results)
        if provider == "brave":
            return self._search_brave_fresh(query, max_results, timespan)
        return super()._search_one(
            provider,
            query=query,
            max_results=max_results,
            timespan=timespan,
        )

    def _search_firecrawl(
        self,
        query: str,
        max_results: int,
        timespan: str,
    ) -> list[SearchCandidate]:
        body: dict[str, Any] = {
            "query": query,
            "limit": min(max(max_results, 1), 50),
            "sources": ["web"],
            "country": "CN",
            "location": "China",
            "timeout": int(max(self.settings.request_timeout_seconds, 45.0) * 1000),
            "ignoreInvalidURLs": True,
        }
        tbs = self._firecrawl_tbs(timespan)
        if tbs:
            body["tbs"] = tbs
        response = httpx.post(
            self.settings.firecrawl_base_url.rstrip("/") + "/v2/search",
            headers={
                **self.headers,
                "Authorization": f"Bearer {self.settings.firecrawl_api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=max(self.settings.request_timeout_seconds, 60.0),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("success") is False:
            raise MaterialSearchError(
                str(payload.get("error") or "Firecrawl 搜索失败")
                if isinstance(payload, dict)
                else "Firecrawl 响应格式错误"
            )
        data = payload.get("data")
        items = data.get("web") if isinstance(data, dict) else []
        return self._candidates(
            items,
            source="firecrawl-search",
            url_keys=("url",),
            summary_keys=("description",),
        )

    def _search_jina(self, query: str, max_results: int) -> list[SearchCandidate]:
        response = httpx.post(
            self.settings.jina_search_base_url,
            headers={
                **self.headers,
                "Authorization": f"Bearer {self.settings.jina_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "q": query,
                "gl": "cn",
                "hl": "zh-cn",
                "num": min(max(max_results, 1), 20),
            },
            timeout=max(self.settings.request_timeout_seconds, 45.0),
        )
        response.raise_for_status()
        payload = response.json()
        items: Any = []
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            items = (
                payload.get("data")
                or payload.get("results")
                or payload.get("organic_results")
                or (
                    (payload.get("web") or {}).get("results")
                    if isinstance(payload.get("web"), dict)
                    else []
                )
                or []
            )
        return self._candidates(
            items,
            source="jina-search",
            url_keys=("url", "link"),
            summary_keys=("description", "snippet", "content"),
            site_keys=("site", "domain"),
            date_keys=("date", "published_at"),
        )

    def _search_brave_fresh(
        self,
        query: str,
        max_results: int,
        timespan: str,
    ) -> list[SearchCandidate]:
        params: dict[str, Any] = {
            "q": query,
            "count": min(max(max_results, 1), 20),
            "country": "CN",
            "search_lang": "zh-hans",
            "ui_lang": "zh-CN",
            "safesearch": "moderate",
            "text_decorations": False,
            "extra_snippets": True,
        }
        freshness = self._brave_freshness(timespan)
        if freshness:
            params["freshness"] = freshness
        response = httpx.get(
            self.settings.brave_search_base_url,
            params=params,
            headers={
                **self.headers,
                "X-Subscription-Token": self.settings.brave_search_api_key,
            },
            timeout=max(self.settings.request_timeout_seconds, 30.0),
        )
        response.raise_for_status()
        payload = response.json()
        web = payload.get("web") if isinstance(payload, dict) else {}
        items = web.get("results") if isinstance(web, dict) else []
        output: list[SearchCandidate] = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            snippets = [str(item.get("description") or "")]
            extra = item.get("extra_snippets")
            if isinstance(extra, list):
                snippets.extend(str(value) for value in extra[:2])
            profile = item.get("profile")
            site = (
                str(profile.get("long_name") or "")
                if isinstance(profile, dict)
                else ""
            )
            output.append(
                SearchCandidate(
                    url=url,
                    title=self._text(item.get("title"), 260),
                    summary=self._text(" ".join(snippets), 900),
                    site=site or (urlparse(url).hostname or ""),
                    published_at=self._text(item.get("page_age"), 80),
                    image_url=self._image(item),
                    discovery_source="brave-zh-cn",
                )
            )
        return self._dedupe(output)

    def _candidates(
        self,
        items: Any,
        *,
        source: str,
        url_keys: tuple[str, ...],
        summary_keys: tuple[str, ...],
        site_keys: tuple[str, ...] = (),
        date_keys: tuple[str, ...] = (),
    ) -> list[SearchCandidate]:
        output: list[SearchCandidate] = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            url = self._first(item, url_keys)
            if not url:
                continue
            output.append(
                SearchCandidate(
                    url=url,
                    title=self._text(item.get("title"), 260),
                    summary=self._text(self._first(item, summary_keys), 900),
                    site=self._first(item, site_keys)
                    or (urlparse(url).hostname or ""),
                    published_at=self._text(self._first(item, date_keys), 80),
                    image_url=self._image(item),
                    discovery_source=source,
                )
            )
        return self._dedupe(output)

    @staticmethod
    def _first(item: dict[str, Any], keys: tuple[str, ...]) -> str:
        for key in keys:
            value = item.get(key)
            if value not in (None, ""):
                return str(value).strip()
        return ""

    @staticmethod
    def _brave_freshness(timespan: str) -> str:
        return {
            "24h": "pd",
            "1d": "pd",
            "7d": "pw",
            "30d": "pm",
            "90d": "py",
        }.get(timespan.lower().strip(), "")

    @staticmethod
    def _firecrawl_tbs(timespan: str) -> str:
        return {
            "24h": "qdr:d",
            "1d": "qdr:d",
            "7d": "qdr:w",
            "30d": "qdr:m",
            "90d": "qdr:y",
        }.get(timespan.lower().strip(), "")
