from pathlib import Path

import httpx
import pytest

from app.services.media_store import MediaDownloadError, MediaStore


@pytest.mark.asyncio
async def test_rejects_redirect_to_untrusted_host(tmp_path: Path) -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(
            302,
            headers={"location": "http://127.0.0.1/private"},
            request=request,
        )

    store = MediaStore(
        tmp_path,
        max_bytes=1024,
        transport=httpx.MockTransport(handler),
    )
    try:
        with pytest.raises(MediaDownloadError, match="not allowed"):
            await store.download("https://pbs.twimg.com/media/source.jpg")
        assert requests == ["https://pbs.twimg.com/media/source.jpg"]
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_downloads_after_valid_relative_redirect(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("source.jpg"):
            return httpx.Response(
                302,
                headers={"location": "/media/final.jpg"},
                request=request,
            )
        return httpx.Response(
            200,
            content=b"image-bytes",
            headers={"content-type": "image/jpeg"},
            request=request,
        )

    store = MediaStore(
        tmp_path,
        max_bytes=1024,
        transport=httpx.MockTransport(handler),
    )
    try:
        local_path, digest, content_type = await store.download(
            "https://pbs.twimg.com/media/source.jpg"
        )
        assert Path(local_path).read_bytes() == b"image-bytes"
        assert len(digest) == 64
        assert content_type == "image/jpeg"
    finally:
        await store.close()
