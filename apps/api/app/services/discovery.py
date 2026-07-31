from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.discovery import DiscoveryCandidate, DiscoveryRun
from app.domain.discovery_schemas import DiscoveryResult
from app.domain.models import RawSnapshot
from app.providers.base import XSourceProvider
from app.services.raw_store import RawStore


class DiscoveryService:
    def __init__(self, provider: XSourceProvider, raw_store: RawStore) -> None:
        self.provider = provider
        self.raw_store = raw_store

    async def search(
        self,
        db: Session,
        *,
        query: str,
        feed: str,
        count: int,
        cursor: str | None,
        language: str | None,
    ) -> DiscoveryResult:
        payload = await self.provider.search(
            query,
            feed=feed,
            count=count,
            cursor=cursor,
            language=language,
        )
        return self._persist_posts(
            db,
            kind="search",
            query=query,
            params={"feed": feed, "count": count, "cursor": cursor, "language": language},
            payload=payload,
        )

    async def timeline(
        self,
        db: Session,
        *,
        handle: str,
        count: int,
        cursor: str | None,
        since: int | None,
        media_only: bool,
    ) -> DiscoveryResult:
        payload = await self.provider.get_timeline(
            handle,
            count=count,
            cursor=cursor,
            since=since,
            media_only=media_only,
        )
        return self._persist_posts(
            db,
            kind="profile_media" if media_only else "profile_timeline",
            query=handle,
            params={"count": count, "cursor": cursor, "since": since},
            payload=payload,
        )

    async def quotes(
        self,
        db: Session,
        *,
        post_id: str,
        count: int,
        cursor: str | None,
    ) -> DiscoveryResult:
        payload = await self.provider.get_quotes(post_id, count=count, cursor=cursor)
        return self._persist_posts(
            db,
            kind="quotes",
            query=post_id,
            params={"count": count, "cursor": cursor},
            payload=payload,
        )

    async def trends(self, db: Session, *, count: int) -> DiscoveryResult:
        payload = await self.provider.trends(count=count)
        snapshot = self._snapshot(db, kind="trends", query="trending", payload=payload)
        run = DiscoveryRun(
            provider=self.provider.name,
            kind="trends",
            query="trending",
            params_json=json.dumps({"count": count}, ensure_ascii=False),
            cursor_json=json.dumps(payload.get("cursor") or {}, ensure_ascii=False),
            raw_snapshot_id=snapshot.id,
        )
        db.add(run)
        db.flush()

        candidates: list[DiscoveryCandidate] = []
        raw_trends = payload.get("trends") or payload.get("results") or []
        for raw in raw_trends if isinstance(raw_trends, list) else []:
            if isinstance(raw, str):
                name = raw
                metadata: dict[str, Any] = {}
            elif isinstance(raw, dict):
                name = str(raw.get("name") or raw.get("trend") or raw.get("query") or "")
                metadata = raw
            else:
                continue
            if not name.strip():
                continue
            canonical_url = str(
                metadata.get("url")
                or f"https://x.com/search?q={quote(name.strip())}&src=trend_click"
            )
            candidate = self._upsert_candidate(
                db,
                run=run,
                dedupe_key=f"trend:{name.strip().casefold()}",
                kind="trend",
                external_id="",
                canonical_url=canonical_url,
                author_handle="",
                author_name="",
                text=name.strip(),
                metadata=metadata,
            )
            candidates.append(candidate)
        run.candidate_count = len(candidates)
        db.commit()
        return DiscoveryResult(
            run_id=run.id,
            kind=run.kind,
            query=run.query,
            cursor=payload.get("cursor") if isinstance(payload.get("cursor"), dict) else {},
            candidates=candidates,
        )

    async def profile(self, db: Session, *, handle: str) -> dict:
        payload = await self.provider.get_profile(handle, about_account=True)
        self._snapshot(db, kind="profile", query=handle, payload=payload)
        db.commit()
        return payload

    def _persist_posts(
        self,
        db: Session,
        *,
        kind: str,
        query: str,
        params: dict[str, Any],
        payload: dict,
    ) -> DiscoveryResult:
        snapshot = self._snapshot(db, kind=kind, query=query, payload=payload)
        cursor = payload.get("cursor") if isinstance(payload.get("cursor"), dict) else {}
        run = DiscoveryRun(
            provider=self.provider.name,
            kind=kind,
            query=query,
            params_json=json.dumps(params, ensure_ascii=False),
            cursor_json=json.dumps(cursor, ensure_ascii=False),
            raw_snapshot_id=snapshot.id,
        )
        db.add(run)
        db.flush()

        raw_results = payload.get("results") or payload.get("statuses") or payload.get("tweets") or []
        candidates: list[DiscoveryCandidate] = []
        for raw in raw_results if isinstance(raw_results, list) else []:
            if not isinstance(raw, dict):
                continue
            external_id = str(raw.get("id") or raw.get("rest_id") or "")
            if not external_id:
                continue
            author = raw.get("author") if isinstance(raw.get("author"), dict) else {}
            metadata = {
                "likes": raw.get("likes", 0),
                "reposts": raw.get("reposts", raw.get("retweets", 0)),
                "quotes": raw.get("quotes", 0),
                "replies": raw.get("replies", 0),
                "views": raw.get("views", 0),
                "created_at": raw.get("created_at"),
                "created_timestamp": raw.get("created_timestamp"),
                "has_media": bool(raw.get("media")),
                "possibly_sensitive": bool(raw.get("possibly_sensitive", False)),
            }
            candidate = self._upsert_candidate(
                db,
                run=run,
                dedupe_key=f"status:{external_id}",
                kind="status",
                external_id=external_id,
                canonical_url=str(raw.get("url") or ""),
                author_handle=str(author.get("screen_name") or author.get("username") or ""),
                author_name=str(author.get("name") or author.get("display_name") or ""),
                text=str(raw.get("text") or raw.get("full_text") or ""),
                metadata=metadata,
            )
            candidates.append(candidate)
        run.candidate_count = len(candidates)
        db.commit()
        return DiscoveryResult(
            run_id=run.id,
            kind=run.kind,
            query=run.query,
            cursor=cursor,
            candidates=candidates,
        )

    def _snapshot(self, db: Session, *, kind: str, query: str, payload: dict) -> RawSnapshot:
        identifier = hashlib.sha256(f"{kind}:{query}".encode()).hexdigest()[:24]
        payload_path, payload_sha = self.raw_store.save(
            provider=self.provider.name,
            external_id=f"discovery-{identifier}",
            payload=payload,
        )
        snapshot = RawSnapshot(
            provider=self.provider.name,
            endpoint=f"discovery:{kind}",
            external_id=query[:64],
            payload_path=payload_path,
            payload_sha256=payload_sha,
        )
        db.add(snapshot)
        db.flush()
        return snapshot

    @staticmethod
    def _upsert_candidate(
        db: Session,
        *,
        run: DiscoveryRun,
        dedupe_key: str,
        kind: str,
        external_id: str,
        canonical_url: str,
        author_handle: str,
        author_name: str,
        text: str,
        metadata: dict[str, Any],
    ) -> DiscoveryCandidate:
        candidate = db.scalar(
            select(DiscoveryCandidate).where(DiscoveryCandidate.dedupe_key == dedupe_key)
        )
        if candidate is None:
            candidate = DiscoveryCandidate(run_id=run.id, dedupe_key=dedupe_key, kind=kind)
            db.add(candidate)
        candidate.run_id = run.id
        candidate.external_id = external_id
        candidate.canonical_url = canonical_url
        candidate.author_handle = author_handle
        candidate.author_name = author_name
        candidate.text = text
        candidate.metadata_json = json.dumps(metadata, ensure_ascii=False)
        db.flush()
        return candidate
