from __future__ import annotations

import httpx


class FxTwitterProvider:
    def __init__(self, base_url: str = "https://api.fxtwitter.com"):
        self.base_url = base_url.rstrip("/")

    async def get_thread(self, post_id: str) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{self.base_url}/2/thread/{post_id}")
            response.raise_for_status()
            return response.json()

    async def get_conversation(self, post_id: str) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{self.base_url}/2/conversation/{post_id}")
            response.raise_for_status()
            return response.json()
