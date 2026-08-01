from __future__ import annotations

from typing import Any

import httpx

from app.services.material_search_providers import (
    MaterialSearchEngine,
    MaterialSearchError,
)


class ResilientMaterialSearchEngine(MaterialSearchEngine):
    """Keep automatic provider failover alive when a vendor returns malformed JSON."""

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
        provider_errors = (
            httpx.HTTPError,
            ValueError,
            KeyError,
            TypeError,
            AttributeError,
            MaterialSearchError,
        )
        for name in order:
            if not self.configured(name):
                attempts.append(
                    {"provider": name, "status": "skipped", "detail": "未配置凭据"}
                )
                continue
            try:
                items = self._search_one(
                    name,
                    query=query,
                    max_results=max_results,
                    timespan=timespan,
                )
            except provider_errors as exc:
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
