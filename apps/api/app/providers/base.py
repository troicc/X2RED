from __future__ import annotations

from typing import Protocol


class XSourceProvider(Protocol):
    name: str

    async def get_thread(self, post_id: str) -> dict: ...

    async def get_conversation(self, post_id: str) -> dict: ...
