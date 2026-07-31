from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import Asset, RawSnapshot
from app.providers.base import XSourceProvider
from app.services.media_store import MediaStore
from app.services.normalizer import upsert_payload
from app.services.raw_store import RawStore


class IntakeService:
    def __init__(
        self,
        settings: Settings,
        provider: XSourceProvider,
        raw_store: RawStore,
        media_store: MediaStore,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.raw_store = raw_store
        self.media_store = media_store

    async def import_post(
        self,
        db: Session,
        *,
        post_id: str,
        mode: str,
        download_media: bool,
    ) -> tuple[str, int, int, RawSnapshot]:
        endpoint = f"/2/{mode}/{post_id}"
        payload = (
            await self.provider.get_conversation(post_id)
            if mode == "conversation"
            else await self.provider.get_thread(post_id)
        )
        payload_path, payload_sha = self.raw_store.save(
            provider=self.provider.name,
            external_id=post_id,
            payload=payload,
        )
        snapshot = RawSnapshot(
            provider=self.provider.name,
            endpoint=endpoint,
            external_id=post_id,
            payload_path=payload_path,
            payload_sha256=payload_sha,
        )
        db.add(snapshot)
        focal, sources, _ = upsert_payload(db, payload, post_id)
        db.commit()

        source_ids = [source.id for source in sources]
        assets = list(db.scalars(select(Asset).where(Asset.source_id.in_(source_ids))).all())
        if download_media:
            for asset in assets:
                await self._download_one(db, asset)
        return focal.id, len(sources), len(assets), snapshot

    async def _download_one(self, db: Session, asset: Asset) -> None:
        if asset.state == "ready" and asset.local_path:
            return
        asset.state = "downloading"
        db.commit()
        try:
            local_path, digest, mime_type = await self.media_store.download(asset.remote_url)
            asset.local_path = local_path
            asset.sha256 = digest
            asset.mime_type = mime_type
            asset.state = "ready"
            asset.error = ""
        except Exception as exc:
            asset.state = "failed"
            asset.error = str(exc)[:1000]
        db.commit()
