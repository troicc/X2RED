from __future__ import annotations

import json
from typing import Any

from app.core.config import Settings
from app.providers.base import XSourceProvider
from app.services.discovery import DiscoveryService
from app.services.editorial import EditorialService
from app.services.raw_store import RawStore


class SignalBase:
    def __init__(
        self,
        settings: Settings,
        provider: XSourceProvider,
        raw_store: RawStore,
        editorial_service: EditorialService,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.discovery = DiscoveryService(provider, raw_store)
        self.editorial = editorial_service

    @staticmethod
    def _json(value: str, fallback: Any) -> Any:
        try:
            parsed = json.loads(value or "")
        except (TypeError, json.JSONDecodeError):
            return fallback
        return parsed

    @staticmethod
    def _int(value: Any) -> int:
        try:
            return max(int(value or 0), 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _profile_followers(payload: dict[str, Any]) -> int:
        user = payload.get("user") if isinstance(payload.get("user"), dict) else payload
        for key in ("followers", "followers_count", "follower_count"):
            value = user.get(key) if isinstance(user, dict) else None
            if value is not None:
                try:
                    return max(int(value), 0)
                except (TypeError, ValueError):
                    pass
        return 0
