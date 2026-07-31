from __future__ import annotations

import hashlib
import mimetypes
import uuid
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

_ALLOWED_MEDIA_SUFFIXES = (
    "twimg.com",
    "fxtwitter.com",
    "fixupx.com",
    "video.twimg.com",
    "pbs.twimg.com",
)
_REDIRECT_CODES = {301, 302, 303, 307, 308}


class MediaDownloadError(RuntimeError):
    pass


class MediaStore:
    def __init__(
        self,
        root: Path,
        max_bytes: int,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.root = root
        self.max_bytes = max_bytes
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            transport=transport,
        )

    async def close(self) -> None:
        await self.client.aclose()

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"}:
            raise MediaDownloadError("media URL must use HTTP(S)")
        if not any(host == suffix or host.endswith("." + suffix) for suffix in _ALLOWED_MEDIA_SUFFIXES):
            raise MediaDownloadError(f"media host is not allowed: {host}")

    async def download(self, url: str) -> tuple[str, str, str]:
        current_url = url
        temp_path: Path | None = None
        response: httpx.Response | None = None
        try:
            for _ in range(5):
                self._validate_url(current_url)
                request = self.client.build_request("GET", current_url)
                response = await self.client.send(request, stream=True)
                if response.status_code not in _REDIRECT_CODES:
                    break
                location = response.headers.get("location")
                await response.aclose()
                response = None
                if not location:
                    raise MediaDownloadError("media redirect is missing a Location header")
                current_url = urljoin(current_url, location)
            else:
                raise MediaDownloadError("too many media redirects")

            if response is None:
                raise MediaDownloadError("media request did not return a response")
            response.raise_for_status()
            self._validate_url(str(response.url))

            declared = int(response.headers.get("content-length") or 0)
            if declared and declared > self.max_bytes:
                raise MediaDownloadError("media file exceeds configured size limit")
            content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
            hasher = hashlib.sha256()
            temp = self.root / ".tmp"
            temp.mkdir(parents=True, exist_ok=True)
            temp_path = temp / f"{uuid.uuid4().hex}.part"
            total = 0
            with temp_path.open("wb") as handle:
                async for chunk in response.aiter_bytes(1024 * 1024):
                    total += len(chunk)
                    if total > self.max_bytes:
                        raise MediaDownloadError("media file exceeds configured size limit")
                    hasher.update(chunk)
                    handle.write(chunk)

            digest = hasher.hexdigest()
            extension = (
                mimetypes.guess_extension(content_type)
                or Path(urlparse(current_url).path).suffix
                or ".bin"
            )
            if extension == ".jpe":
                extension = ".jpg"
            target_dir = self.root / digest[:2]
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"{digest}{extension}"
            if target.exists():
                temp_path.unlink(missing_ok=True)
            else:
                temp_path.replace(target)
            return str(target.resolve()), digest, content_type
        finally:
            if response is not None:
                await response.aclose()
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
