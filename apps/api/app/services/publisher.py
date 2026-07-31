from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import Asset, DraftRevision, PublishState, PublishTask, ReviewDecision


class PublishError(RuntimeError):
    pass


class PublishService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def prepare(self, db: Session, draft: DraftRevision) -> PublishTask:
        approved = db.scalar(
            select(ReviewDecision)
            .where(
                ReviewDecision.draft_id == draft.id,
                ReviewDecision.decision == "approved",
            )
            .order_by(ReviewDecision.created_at.desc())
        )
        if approved is None:
            raise PublishError("草稿尚未通过人工审核")

        assets = db.scalars(
            select(Asset).where(Asset.source_id == draft.source_id, Asset.state == "ready")
        ).all()
        payload = {
            "draft_id": draft.id,
            "source_id": draft.source_id,
            "title": draft.title,
            "body": draft.body,
            "tags": [tag.strip().lstrip("#") for tag in draft.tags.split(",") if tag.strip()],
            "assets": [asset.local_path for asset in assets if asset.local_path],
        }
        seed = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        seed_digest = hashlib.sha256(seed).hexdigest()
        package_dir = self.settings.export_dir / f"{draft.id}_{seed_digest[:12]}"
        package_dir.mkdir(parents=True, exist_ok=True)
        package_path = package_dir / "publish.json"
        (package_dir / "caption.txt").write_text(
            draft.body
            + ("\n\n" + " ".join(f"#{tag}" for tag in payload["tags"]) if payload["tags"] else ""),
            encoding="utf-8",
        )
        media_dir = package_dir / "media"
        media_dir.mkdir(exist_ok=True)
        packaged_assets = []
        for index, asset in enumerate(assets, start=1):
            if not asset.local_path:
                continue
            source_path = Path(asset.local_path)
            target = media_dir / f"{index:02d}_{source_path.name}"
            if not target.exists():
                shutil.copy2(source_path, target)
            packaged_assets.append(str(target.resolve()))
        payload["assets"] = packaged_assets
        final_encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        digest = hashlib.sha256(final_encoded).hexdigest()
        package_path.write_bytes(final_encoded)

        task = PublishTask(
            draft_id=draft.id,
            state=PublishState.packaged.value,
            title=draft.title,
            body=draft.body,
            tags=draft.tags,
            asset_ids_json=json.dumps([asset.id for asset in assets]),
            payload_sha256=digest,
            package_path=str(package_path.resolve()),
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    async def open_xhs_preview(self, db: Session, task: PublishTask) -> PublishTask:
        if task.state not in {PublishState.packaged.value, PublishState.failed.value}:
            raise PublishError(f"当前发布状态不可打开预览：{task.state}")
        package = Path(task.package_path)
        if not package.is_file():
            raise PublishError("发布包不存在，请重新生成")

        import subprocess
        import sys

        command = [
            sys.executable,
            "-m",
            "app.services.xhs_preview_worker",
            str(package),
            str(self.settings.browser_profile_dir),
        ]
        try:
            subprocess.Popen(
                command,
                cwd=str(Path(__file__).resolve().parents[2]),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            task.state = PublishState.failed.value
            task.error = str(exc)[:1000]
            db.commit()
            return task

        task.state = PublishState.awaiting_user_confirmation.value
        task.error = ""
        db.commit()
        db.refresh(task)
        return task
