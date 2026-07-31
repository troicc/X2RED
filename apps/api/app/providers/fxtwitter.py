from __future__ import annotations

import asyncio
from typing import Any

import httpx


class FxTwitterError(RuntimeError):
    pass


class FxTwitterProvider:
    name = "fxtwitter"

    def __init__(self, base_url: str, timeout_seconds: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            headers={
                "Accept": "application/json",
                "User-Agent": "X2RED/0.1 local editorial client",
            },
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await self.client.get(f"{self.base_url}{path}", params=params)
                if response.status_code == 204:
                    return {"code": 204, "status": None, "thread": []}
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise FxTwitterError(f"temporary upstream error: {response.status_code}")
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise FxTwitterError("unexpected FxTwitter payload")
                code = int(payload.get("code", response.status_code))
                if code >= 400:
                    raise FxTwitterError(f"FxTwitter returned code {code}")
                return payload
            except (httpx.HTTPError, ValueError, FxTwitterError) as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(0.5 * (2**attempt))
        raise FxTwitterError(str(last_error or "FxTwitter request failed"))

    async def get_thread(self, post_id: str) -> dict:
        return await self._get(f"/2/thread/{post_id}")

    async def get_conversation(self, post_id: str) -> dict:
        return await self._get(
            f"/2/conversation/{post_id}",
            params={"ranking_mode": "likes"},
        )
