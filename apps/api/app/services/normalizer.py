from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import Asset, AssetVariant, SourceItem, SourceRelation


def _timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _user(raw: dict) -> dict:
    author = raw.get("author") or raw.get("user") or {}
    return {
        "id": str(author.get("id") or author.get("rest_id") or ""),
        "handle": str(author.get("screen_name") or author.get("username") or ""),
        "name": str(author.get("name") or author.get("display_name") or ""),
        "avatar": str(author.get("avatar_url") or author.get("avatar") or ""),
    }


def _status_id(raw: dict) -> str:
    return str(raw.get("id") or raw.get("tweet_id") or raw.get("rest_id") or "")


def _canonical_url(raw: dict, status_id: str, handle: str) -> str:
    return str(raw.get("url") or f"https://x.com/{handle or 'i'}/status/{status_id}")


def _status_list(payload: dict) -> list[dict]:
    items: list[dict] = []
    focal = payload.get("status") or payload.get("tweet")
    if isinstance(focal, dict):
        items.append(focal)
    for key in ("thread", "conversation", "replies", "tweets"):
        value = payload.get(key)
        if isinstance(value, list):
            items.extend(item for item in value if isinstance(item, dict))
    deduped: dict[str, dict] = {}
    for item in items:
        sid = _status_id(item)
        if sid:
            deduped[sid] = item
    return list(deduped.values())


def _media_items(raw: dict) -> list[dict]:
    media = raw.get("media") or {}
    if isinstance(media, list):
        return media
    all_items = media.get("all") if isinstance(media, dict) else None
    if isinstance(all_items, list):
        return all_items
    result: list[dict] = []
    for key in ("photos", "videos"):
        value = media.get(key) if isinstance(media, dict) else None
        if isinstance(value, list):
            result.extend(value)
    return result


def upsert_payload(db: Session, payload: dict, focal_id: str) -> tuple[SourceItem, list[SourceItem], int]:
    raw_statuses = _status_list(payload)
    if not raw_statuses:
        raise ValueError("FxTwitter 响应中没有可用 Post")

    sources: list[SourceItem] = []
    discovered_asset_count = 0
    raw_by_id = {_status_id(item): item for item in raw_statuses}
    for raw in raw_statuses:
        sid = _status_id(raw)
        author = _user(raw)
        source = db.scalar(
            select(SourceItem).where(SourceItem.platform == "x", SourceItem.external_id == sid)
        )
        values = {
            "provider": "fxtwitter",
            "platform": "x",
            "external_id": sid,
            "canonical_url": _canonical_url(raw, sid, author["handle"]),
            "author_id": author["id"],
            "author_handle": author["handle"],
            "author_name": author["name"],
            "author_avatar_url": author["avatar"],
            "text_original": str(raw.get("text") or raw.get("full_text") or ""),
            "language": str(raw.get("lang") or raw.get("language") or ""),
            "created_at": _timestamp(raw.get("created_at")),
            "state": "available" if raw.get("type") != "tombstone" else "unavailable",
            "possibly_sensitive": bool(raw.get("possibly_sensitive") or False),
            "metrics_json": json.dumps(
                {
                    "likes": raw.get("likes", 0),
                    "reposts": raw.get("reposts", 0),
                    "quotes": raw.get("quotes", 0),
                    "replies": raw.get("replies", 0),
                    "views": raw.get("views", 0),
                },
                ensure_ascii=False,
            ),
        }
        if source is None:
            source = SourceItem(**values)
            db.add(source)
            db.flush()
        else:
            for key, value in values.items():
                setattr(source, key, value)
        sources.append(source)

        existing_remote = {asset.remote_url for asset in source.assets}
        for media in _media_items(raw):
            media_type = str(media.get("type") or "other")
            remote_url = str(media.get("url") or media.get("thumbnail_url") or "")
            formats = media.get("formats") if isinstance(media.get("formats"), list) else []
            selected_variant = choose_video_variant(formats) if formats else None
            if selected_variant:
                remote_url = str(selected_variant.get("url") or remote_url)
            if not remote_url or remote_url in existing_remote:
                continue
            asset = Asset(
                source_id=source.id,
                kind="video" if media_type in {"video", "gif"} and formats else "image",
                remote_url=remote_url,
                width=int(media.get("width") or 0),
                height=int(media.get("height") or 0),
                alt_text=str(media.get("altText") or media.get("alt_text") or ""),
            )
            db.add(asset)
            db.flush()
            discovered_asset_count += 1
            for variant_raw in formats:
                variant = AssetVariant(
                    asset_id=asset.id,
                    remote_url=str(variant_raw.get("url") or ""),
                    container=str(variant_raw.get("container") or ""),
                    codec=str(variant_raw.get("codec") or ""),
                    bitrate=int(variant_raw.get("bitrate") or 0),
                    width=int(variant_raw.get("width") or 0),
                    height=int(variant_raw.get("height") or 0),
                    selected=bool(selected_variant and variant_raw.get("url") == selected_variant.get("url")),
                )
                db.add(variant)

    source_by_external = {source.external_id: source for source in sources}
    focal = source_by_external.get(focal_id) or sources[0]
    ordered = [source for source in sources if source.author_id == focal.author_id]
    ordered.sort(key=lambda item: item.created_at.timestamp() if item.created_at else 0)
    for index in range(1, len(ordered)):
        relation = db.scalar(
            select(SourceRelation).where(
                SourceRelation.from_source_id == ordered[index - 1].id,
                SourceRelation.to_source_id == ordered[index].id,
                SourceRelation.relation_type == "thread_next",
            )
        )
        if relation is None:
            db.add(
                SourceRelation(
                    from_source_id=ordered[index - 1].id,
                    to_source_id=ordered[index].id,
                    relation_type="thread_next",
                    position=index,
                )
            )

    for sid, raw in raw_by_id.items():
        source = source_by_external[sid]
        reply_id = str(raw.get("replying_to_status") or raw.get("in_reply_to_status_id") or "")
        if reply_id and reply_id in source_by_external:
            relation = db.scalar(
                select(SourceRelation).where(
                    SourceRelation.from_source_id == source.id,
                    SourceRelation.to_source_id == source_by_external[reply_id].id,
                    SourceRelation.relation_type == "reply_to",
                )
            )
            if relation is None:
                db.add(
                    SourceRelation(
                        from_source_id=source.id,
                        to_source_id=source_by_external[reply_id].id,
                        relation_type="reply_to",
                    )
                )

    db.flush()
    return focal, sources, discovered_asset_count


def choose_video_variant(formats: list[dict], max_height: int = 1080) -> dict | None:
    candidates = [
        item
        for item in formats
        if item.get("url")
        and item.get("container") == "mp4"
        and item.get("codec") in (None, "", "h264")
        and int(item.get("height") or 0) <= max_height
    ]
    if not candidates:
        candidates = [item for item in formats if item.get("url") and item.get("container") == "mp4"]
    if not candidates:
        candidates = [item for item in formats if item.get("url")]
    if not candidates:
        return None
    return max(candidates, key=lambda item: (int(item.get("height") or 0), int(item.get("bitrate") or 0)))
