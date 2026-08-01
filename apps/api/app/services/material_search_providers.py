from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import Settings


class MaterialSearchError(RuntimeError):
    pass


@dataclass(frozen=True)
class SearchProviderStatus:
    id: str
    label: str
    configured: bool
    native_chinese: bool
    description: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SearchCandidate:
    url: str
    title: str
    summary: str = ""
    site: str = ""
    published_at: str = ""
    image_url: str = ""
    discovery_source: str = ""

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


_PROVIDER_META: dict[str, tuple[str, bool, str]] = {
    "serpapi_baidu": (
        "SerpApi · 百度",
        True,
        "直接返回百度自然搜索结果，适合简中网页发现。",
    ),
    "dataforseo_baidu": (
        "DataForSEO · 百度",
        True,
        "实时 Baidu SERP；启用直接网址解析，调用费用较高。",
    ),
    "tavily": (
        "Tavily · China",
        False,
        "面向 Agent 的实时搜索，使用 China 区域偏好和中文查询。",
    ),
    "brave": (
        "Brave Search · zh-CN",
        False,
        "独立网页索引，作为简中补充搜索源。",
    ),
    "gdelt": (
        "GDELT 中文新闻",
        False,
        "无需密钥的新闻索引兜底，覆盖不等同于完整简中互联网。",
    ),
}


class MaterialSearchEngine:
    """Commercial search-provider adapters with deterministic failover."""

    auto_priority = (
        "serpapi_baidu",
        "dataforseo_baidu",
        "tavily",
        "brave",
        "gdelt",
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.headers = {
            "User-Agent": settings.material_user_agent,
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
        }

    def statuses(self) -> list[dict[str, Any]]:
        return [
            SearchProviderStatus(
                id=provider,
                label=_PROVIDER_META[provider][0],
                configured=self.configured(provider),
                native_chinese=_PROVIDER_META[provider][1],
                description=_PROVIDER_META[provider][2],
            ).as_dict()
            for provider in self.auto_priority
        ]

    def configured(self, provider: str) -> bool:
        if provider == "serpapi_baidu":
            return bool(self.settings.serpapi_api_key)
        if provider == "dataforseo_baidu":
            return bool(self.settings.dataforseo_login and self.settings.dataforseo_password)
        if provider == "tavily":
            return bool(self.settings.tavily_api_key)
        if provider == "brave":
            return bool(self.settings.brave_search_api_key)
        if provider == "gdelt":
            return True
        return False

    def search(
        self,
        *,
        provider: str,
        query: str,
        max_results: int = 30,
        timespan: str = "7d",
    ) -> dict[str, Any]:
        requested = provider or self.settings.material_search_provider or "auto"
        if requested != "auto" and requested not in self.auto_priority:
            raise MaterialSearchError(f"未知搜索供应商：{requested}")
        order = self.auto_priority if requested == "auto" else (requested,)
        attempts: list[dict[str, str]] = []
        for name in order:
            if not self.configured(name):
                attempts.append({"provider": name, "status": "skipped", "detail": "未配置凭据"})
                continue
            try:
                items = self._search_one(
                    name,
                    query=query,
                    max_results=max_results,
                    timespan=timespan,
                )
            except (httpx.HTTPError, ValueError, KeyError, MaterialSearchError) as exc:
                attempts.append(
                    {"provider": name, "status": "failed", "detail": str(exc)[:300]}
                )
                continue
            attempts.append(
                {
                    "provider": name,
                    "status": "ok" if items else "empty",
                    "detail": f"{len(items)} results",
                }
            )
            if items:
                return {
                    "provider": name,
                    "items": [item.as_dict() for item in items[:max_results]],
                    "attempts": attempts,
                }
        details = "；".join(
            f"{item['provider']}={item['status']}({item['detail']})" for item in attempts
        )
        raise MaterialSearchError(f"所有搜索供应商均不可用或无结果：{details}")

    def _search_one(
        self,
        provider: str,
        *,
        query: str,
        max_results: int,
        timespan: str,
    ) -> list[SearchCandidate]:
        if provider == "serpapi_baidu":
            return self._search_serpapi(query, max_results)
        if provider == "dataforseo_baidu":
            return self._search_dataforseo(query, max_results)
        if provider == "tavily":
            return self._search_tavily(query, max_results, timespan)
        if provider == "brave":
            return self._search_brave(query, max_results)
        if provider == "gdelt":
            return self._search_gdelt(query, max_results, timespan)
        raise MaterialSearchError(f"未实现搜索供应商：{provider}")

    def _search_serpapi(self, query: str, max_results: int) -> list[SearchCandidate]:
        response = httpx.get(
            self.settings.serpapi_base_url,
            params={
                "engine": "baidu",
                "q": query,
                "ct": 2,
                "rn": min(max(max_results, 1), 50),
                "api_key": self.settings.serpapi_api_key,
            },
            headers=self.headers,
            timeout=max(self.settings.request_timeout_seconds, 30.0),
        )
        response.raise_for_status()
        data = response.json()
        error = str(data.get("error") or "").strip() if isinstance(data, dict) else ""
        if error:
            raise MaterialSearchError(error)
        results = data.get("organic_results") if isinstance(data, dict) else []
        output: list[SearchCandidate] = []
        for item in results if isinstance(results, list) else []:
            if not isinstance(item, dict):
                continue
            url = str(item.get("link") or item.get("redirect_link") or "").strip()
            if not url:
                continue
            output.append(
                SearchCandidate(
                    url=url,
                    title=self._text(item.get("title"), 260),
                    summary=self._text(item.get("snippet") or item.get("description"), 600),
                    site=self._site(item.get("displayed_link") or item.get("domain"), url),
                    published_at=self._text(item.get("date"), 80),
                    image_url=self._image(item),
                    discovery_source="serpapi-baidu",
                )
            )
        return self._dedupe(output)

    def _search_dataforseo(self, query: str, max_results: int) -> list[SearchCandidate]:
        endpoint = (
            self.settings.dataforseo_base_url.rstrip("/")
            + "/v3/serp/baidu/organic/live/advanced"
        )
        response = httpx.post(
            endpoint,
            auth=(self.settings.dataforseo_login, self.settings.dataforseo_password),
            headers={**self.headers, "Content-Type": "application/json"},
            json=[
                {
                    "keyword": query,
                    "language_code": "zh_CN",
                    "location_code": 2156,
                    "device": "desktop",
                    "os": "macos",
                    "depth": min(max(max_results, 1), 50),
                    "get_website_url": True,
                }
            ],
            timeout=max(self.settings.request_timeout_seconds, 60.0),
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or int(data.get("status_code") or 0) != 20000:
            raise MaterialSearchError(str(data.get("status_message") or "DataForSEO 请求失败"))
        output: list[SearchCandidate] = []
        for task in data.get("tasks") or []:
            if not isinstance(task, dict) or int(task.get("status_code") or 0) != 20000:
                continue
            for result in task.get("result") or []:
                if not isinstance(result, dict):
                    continue
                for item in result.get("items") or []:
                    if not isinstance(item, dict) or item.get("type") != "organic":
                        continue
                    url = str(item.get("website_url") or item.get("url") or "").strip()
                    if not url:
                        continue
                    output.append(
                        SearchCandidate(
                            url=url,
                            title=self._text(item.get("title"), 260),
                            summary=self._text(item.get("description"), 600),
                            site=self._site(item.get("domain"), url),
                            published_at=self._text(item.get("timestamp"), 80),
                            image_url=self._image(item),
                            discovery_source="dataforseo-baidu",
                        )
                    )
        return self._dedupe(output)

    def _search_tavily(
        self,
        query: str,
        max_results: int,
        timespan: str,
    ) -> list[SearchCandidate]:
        body: dict[str, Any] = {
            "query": query,
            "search_depth": self.settings.tavily_search_depth,
            "max_results": min(max(max_results, 1), 20),
            "include_answer": False,
            "include_raw_content": False,
            "include_images": True,
            "country": "china",
            "topic": "general",
        }
        time_range = self._time_range(timespan)
        if time_range:
            body["time_range"] = time_range
        response = httpx.post(
            self.settings.tavily_base_url.rstrip("/") + "/search",
            headers={
                **self.headers,
                "Authorization": f"Bearer {self.settings.tavily_api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=max(self.settings.request_timeout_seconds, 45.0),
        )
        response.raise_for_status()
        data = response.json()
        output: list[SearchCandidate] = []
        for item in data.get("results") or [] if isinstance(data, dict) else []:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            output.append(
                SearchCandidate(
                    url=url,
                    title=self._text(item.get("title"), 260),
                    summary=self._text(item.get("content"), 700),
                    site=self._site("", url),
                    published_at=self._text(
                        item.get("published_date") or item.get("published_at"), 80
                    ),
                    image_url=self._image(item),
                    discovery_source="tavily-china",
                )
            )
        return self._dedupe(output)

    def _search_brave(self, query: str, max_results: int) -> list[SearchCandidate]:
        response = httpx.get(
            self.settings.brave_search_base_url,
            params={
                "q": query,
                "count": min(max(max_results, 1), 20),
                "country": "CN",
                "search_lang": "zh-hans",
                "ui_lang": "zh-CN",
                "safesearch": "moderate",
                "text_decorations": False,
            },
            headers={
                **self.headers,
                "X-Subscription-Token": self.settings.brave_search_api_key,
            },
            timeout=max(self.settings.request_timeout_seconds, 30.0),
        )
        response.raise_for_status()
        data = response.json()
        web = data.get("web") if isinstance(data, dict) else {}
        results = web.get("results") if isinstance(web, dict) else []
        output: list[SearchCandidate] = []
        for item in results if isinstance(results, list) else []:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            output.append(
                SearchCandidate(
                    url=url,
                    title=self._text(item.get("title"), 260),
                    summary=self._text(item.get("description"), 700),
                    site=self._site(
                        (item.get("profile") or {}).get("long_name")
                        if isinstance(item.get("profile"), dict)
                        else "",
                        url,
                    ),
                    published_at=self._text(item.get("page_age"), 80),
                    image_url=self._image(item),
                    discovery_source="brave-zh-cn",
                )
            )
        return self._dedupe(output)

    def _search_gdelt(
        self,
        query: str,
        max_results: int,
        timespan: str,
    ) -> list[SearchCandidate]:
        response = httpx.get(
            self.settings.material_gdelt_base_url,
            params={
                "query": f"({query}) sourcelang:chinese",
                "mode": "ArtList",
                "maxrecords": min(max(max_results, 1), 100),
                "format": "json",
                "sort": "HybridRel",
                "timespan": timespan,
            },
            headers=self.headers,
            timeout=max(self.settings.request_timeout_seconds, 30.0),
        )
        response.raise_for_status()
        data = response.json()
        output: list[SearchCandidate] = []
        for item in data.get("articles") or [] if isinstance(data, dict) else []:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url:
                continue
            output.append(
                SearchCandidate(
                    url=url,
                    title=self._text(item.get("title"), 260),
                    summary=self._text(item.get("seendate"), 200),
                    site=self._site(item.get("domain"), url),
                    published_at=self._text(item.get("seendate"), 80),
                    image_url=self._text(item.get("socialimage"), 2000),
                    discovery_source="gdelt-doc-2",
                )
            )
        return self._dedupe(output)

    @staticmethod
    def _dedupe(items: list[SearchCandidate]) -> list[SearchCandidate]:
        output: list[SearchCandidate] = []
        seen: set[str] = set()
        for item in items:
            key = item.url.split("#", 1)[0].rstrip("/")
            if not key or key in seen:
                continue
            seen.add(key)
            output.append(item)
        return output

    @staticmethod
    def _text(value: Any, limit: int) -> str:
        return " ".join(str(value or "").split())[:limit]

    @staticmethod
    def _site(value: Any, url: str) -> str:
        text = " ".join(str(value or "").split())
        if text:
            return text[:180]
        return (urlparse(url).hostname or "")[:180]

    @staticmethod
    def _image(item: dict[str, Any]) -> str:
        thumbnail = item.get("thumbnail")
        if isinstance(thumbnail, str):
            return thumbnail[:2000]
        if isinstance(thumbnail, dict):
            return str(thumbnail.get("src") or thumbnail.get("url") or "")[:2000]
        images = item.get("images")
        if isinstance(images, list) and images:
            first = images[0]
            if isinstance(first, str):
                return first[:2000]
            if isinstance(first, dict):
                return str(first.get("url") or first.get("src") or "")[:2000]
        return ""

    @staticmethod
    def _time_range(timespan: str) -> str:
        normalized = timespan.lower().strip()
        if normalized in {"24h", "1d", "day"}:
            return "day"
        if normalized in {"7d", "week"}:
            return "week"
        if normalized in {"30d", "month"}:
            return "month"
        if normalized in {"90d", "year"}:
            return "year"
        return ""
