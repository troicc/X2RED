from __future__ import annotations

from typing import Protocol


class XSourceProvider(Protocol):
    name: str

    async def get_status(self, post_id: str) -> dict: ...

    async def get_thread(self, post_id: str) -> dict: ...

    async def get_conversation(self, post_id: str) -> dict: ...

    async def get_quotes(
        self,
        post_id: str,
        *,
        count: int = 20,
        cursor: str | None = None,
    ) -> dict: ...

    async def get_profile(self, handle: str, *, about_account: bool = True) -> dict: ...

    async def get_timeline(
        self,
        handle: str,
        *,
        count: int = 20,
        cursor: str | None = None,
        since: int | None = None,
        media_only: bool = False,
    ) -> dict: ...

    async def search(
        self,
        query: str,
        *,
        feed: str = "latest",
        count: int = 30,
        cursor: str | None = None,
        language: str | None = None,
    ) -> dict: ...

    async def trends(self, *, count: int = 20) -> dict: ...
