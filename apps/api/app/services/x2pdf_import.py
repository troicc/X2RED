from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import (
    Asset,
    AssetState,
    RawSnapshot,
    RightsStatus,
    SourceItem,
    SourceState,
    WorkspaceState,
)
from app.services.raw_store import RawStore

_MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
_SAFE_MEDIA_HOSTS = {"pbs.twimg.com", "video.twimg.com", "abs.twimg.com"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = re.sub(r"\s+", " ", data).strip()
        if value:
            self.parts.append(value)


def _html_text(value: object) -> str:
    text = str(value or "")
    if not text:
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(text)
        return " ".join(parser.parts).strip()
    except Exception:
        return re.sub(r"<[^>]+>", " ", html.unescape(text)).strip()


def _parse_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _safe_media_url(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urlparse(text)
    except ValueError:
        return ""
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in _SAFE_MEDIA_HOSTS:
        return ""
    return text


def _external_id(document: dict) -> str:
    source = document.get("source") if isinstance(document.get("source"), dict) else {}
    direct = str(source.get("postId") or "").strip()
    if direct:
        return direct[:64]
    url = str(source.get("url") or "")
    match = re.search(r"/(?:article|status)/(\d+)", url)
    if match:
        return match.group(1)
    return "x2pdf_" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:40]


def _block_text(block: object) -> str:
    if not isinstance(block, dict):
        return ""
    block_type = str(block.get("type") or "")
    if block_type in {"heading", "paragraph"}:
        return _html_text(block.get("html") or block.get("text"))
    if block_type == "blockquote":
        values = block.get("paragraphs") if isinstance(block.get("paragraphs"), list) else []
        return "\n".join(filter(None, (_html_text(value) for value in values)))
    if block_type == "code":
        return str(block.get("text") or "").strip()
    if block_type == "formula":
        return str(block.get("latex") or block.get("text") or "").strip()
    if block_type in {"list", "table"}:
        return _recursive_text(block.get("items") or block.get("rows") or [])
    if block_type in {"embedded_post", "link_card"}:
        return _recursive_text(block)
    return _html_text(block.get("caption") or block.get("alt") or block.get("text") or "")


def _recursive_text(value: object) -> str:
    if isinstance(value, str):
        return _html_text(value)
    if isinstance(value, list):
        return "\n".join(filter(None, (_recursive_text(item) for item in value)))
    if isinstance(value, dict):
        preferred = []
        for key in ("title", "name", "text", "html", "label", "caption", "description"):
            if key in value:
                preferred.append(_recursive_text(value[key]))
        if preferred:
            return " ".join(filter(None, preferred))
        return "\n".join(filter(None, (_recursive_text(item) for item in value.values())))
    return ""


def flatten_document(document: dict) -> str:
    metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
    title = str(metadata.get("title") or "").strip()
    blocks = document.get("blocks") if isinstance(document.get("blocks"), list) else []
    parts = [title] if title else []
    for block in blocks:
        text = re.sub(r"[ \t]+", " ", _block_text(block)).strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts).strip()


def _media_candidates(document: dict) -> list[dict]:
    metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
    output: list[dict] = []
    cover = _safe_media_url(metadata.get("coverImage"))
    if cover:
        output.append({"url": cover, "kind": "image", "role": "cover", "alt": "Article cover"})
    blocks = document.get("blocks") if isinstance(document.get("blocks"), list) else []
    for block in blocks:
        if not isinstance(block, dict) or str(block.get("type") or "") not in {"image", "media"}:
            continue
        url = _safe_media_url(
            block.get("url")
            or block.get("src")
            or block.get("imageUrl")
            or block.get("thumbnailUrl")
        )
        if not url:
            continue
        media_type = str(block.get("mediaType") or block.get("kind") or "").lower()
        kind = "video" if media_type in {"video", "gif"} else "image"
        output.append(
            {
                "url": url,
                "kind": kind,
                "role": "article_media",
                "alt": str(block.get("alt") or block.get("caption") or ""),
                "width": int(block.get("width") or 0),
                "height": int(block.get("height") or 0),
            }
        )
    deduped: list[dict] = []
    seen: set[str] = set()
    for item in output:
        if item["url"] not in seen:
            seen.add(item["url"])
            deduped.append(item)
    return deduped


class X2PDFImportService:
    def __init__(self, raw_store: RawStore) -> None:
        self.raw_store = raw_store

    def import_document(self, db: Session, document: dict) -> tuple[SourceItem, int, bool]:
        encoded = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > _MAX_DOCUMENT_BYTES:
            raise ValueError("X2PDF 文档超过 16 MB，请关闭不必要的嵌入内容后重试")
        if int(document.get("version") or 0) < 1:
            raise ValueError("X2PDF 文档版本无效")
        blocks = document.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            raise ValueError("X2PDF 文档没有可导入的内容块")

        source_meta = document.get("source") if isinstance(document.get("source"), dict) else {}
        metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
        external_id = _external_id(document)
        canonical_url = str(source_meta.get("url") or "").strip()
        if not canonical_url.startswith("https://"):
            raise ValueError("X2PDF 文档缺少有效的 X 来源链接")

        source = db.scalar(
            select(SourceItem).where(
                SourceItem.platform == "x",
                SourceItem.external_id == external_id,
            )
        )
        updated = source is not None
        if source is None:
            source = SourceItem(platform="x", external_id=external_id, canonical_url=canonical_url)
            db.add(source)

        source.provider = "x2pdf"
        source.canonical_url = canonical_url
        source.author_handle = str(metadata.get("authorHandle") or "").lstrip("@")[:80]
        source.author_name = str(metadata.get("authorName") or "")[:160]
        source.author_avatar_url = _safe_media_url(metadata.get("avatarUrl"))
        source.text_original = flatten_document(document)
        source.language = str(metadata.get("language") or "")[:20]
        source.created_at = _parse_datetime(metadata.get("publishedAt"))
        source.state = SourceState.available.value
        source.workspace_state = WorkspaceState.active.value
        source.archived_at = None
        source.content_kind = str(document.get("type") or "article")[:30]
        source.structured_content_json = json.dumps(document, ensure_ascii=False)

        path, digest = self.raw_store.save(
            provider="x2pdf",
            external_id=external_id,
            payload=document,
        )
        db.add(
            RawSnapshot(
                provider="x2pdf",
                endpoint="browser-extension/document",
                external_id=external_id,
                payload_path=path,
                payload_sha256=digest,
            )
        )
        db.flush()

        existing_urls = {asset.remote_url for asset in source.assets}
        asset_count = 0
        for item in _media_candidates(document):
            if item["url"] in existing_urls:
                continue
            source.assets.append(
                Asset(
                    kind=item.get("kind", "image"),
                    role=item.get("role", "article_media"),
                    remote_url=item["url"],
                    width=item.get("width", 0),
                    height=item.get("height", 0),
                    alt_text=item.get("alt", ""),
                    state=AssetState.discovered.value,
                    rights_status=RightsStatus.needs_review.value,
                )
            )
            existing_urls.add(item["url"])
            asset_count += 1

        db.flush()
        return source, asset_count, updated
