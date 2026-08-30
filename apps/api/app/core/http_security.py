from __future__ import annotations

import ipaddress
import json
import re
import secrets
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit

from app.core.config import Settings

_EXTENSION_ORIGIN_RE = re.compile(r"^chrome-extension://[a-z]{32}$")
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def is_loopback_host(host: str) -> bool:
    normalized = host.strip().strip("[]").lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def request_hostname(raw_host: str) -> str:
    try:
        return (urlsplit(f"//{raw_host}").hostname or "").lower()
    except ValueError:
        return ""


class LocalSecurityMiddleware:
    """Protect local APIs from accidental public exposure and browser CSRF."""

    def __init__(self, app: Callable[..., Awaitable[Any]], settings: Settings) -> None:
        self.app = app
        self.settings = settings
        self.explicit_origins = {
            item.strip().rstrip("/")
            for item in settings.allowed_origins.split(",")
            if item.strip()
        }

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers") or []
        }
        path = str(scope.get("path") or "/")
        method = str(scope.get("method") or "GET").upper()
        host_header = headers.get("host", "")
        hostname = request_hostname(host_header)
        protected = path.startswith("/api/") or path in {"/api", "/ready"}

        if (
            protected
            and hostname not in {"", "testserver"}
            and not is_loopback_host(hostname)
            and not self.settings.local_api_token
            and not self.settings.allow_insecure_non_loopback
        ):
            await self._reject(send, 403, "非回环访问必须配置 X2RED_LOCAL_API_TOKEN")
            return

        if protected and method != "OPTIONS" and self.settings.local_api_token:
            supplied = self._supplied_token(headers)
            if not supplied or not secrets.compare_digest(
                supplied,
                self.settings.local_api_token,
            ):
                await self._reject(send, 401, "缺少或无效的本地 API 令牌")
                return

        if protected and method in _UNSAFE_METHODS:
            if headers.get("sec-fetch-site", "").lower() == "cross-site":
                await self._reject(send, 403, "拒绝跨站 API 请求")
                return
            origin = headers.get("origin", "").rstrip("/")
            if origin and not self._origin_allowed(
                origin,
                scheme=str(scope.get("scheme") or "http"),
                host_header=host_header,
            ):
                await self._reject(send, 403, "请求 Origin 不在允许列表")
                return

        async def send_with_security(message: dict) -> None:
            if message.get("type") == "http.response.start":
                response_headers = list(message.get("headers") or [])
                response_headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                        (b"x-frame-options", b"DENY"),
                        (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                    ]
                )
                message["headers"] = response_headers
            await send(message)

        await self.app(scope, receive, send_with_security)

    def _origin_allowed(self, origin: str, *, scheme: str, host_header: str) -> bool:
        if origin in self.explicit_origins or _EXTENSION_ORIGIN_RE.fullmatch(origin):
            return True
        try:
            parsed = urlsplit(origin)
        except ValueError:
            return False
        if parsed.scheme not in {"http", "https"}:
            return False
        same_origin = f"{scheme}://{host_header}".rstrip("/")
        return bool(host_header and origin == same_origin)

    @staticmethod
    def _supplied_token(headers: dict[str, str]) -> str:
        authorization = headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            return authorization[7:].strip()
        return headers.get("x-x2red-token", "").strip()

    @staticmethod
    async def _reject(send: Callable, status_code: int, detail: str) -> None:
        payload = json.dumps({"detail": detail}, ensure_ascii=False).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(payload)).encode("ascii")),
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": payload})
