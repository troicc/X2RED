from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import (
    Asset,
    CardRender,
    DraftRevision,
    PublishState,
    PublishTask,
    ReviewDecision,
    SourceItem,
    SourceWorkbench,
    WorkspaceState,
    utcnow,
)
from app.services.source_graph import connected_source_ids
from app.services.source_workbenches import set_source_workbench_state


class PublishError(RuntimeError):
    pass


class PublishService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def prepare(
        self,
        db: Session,
        draft: DraftRevision,
        *,
        include_cards: bool,
        include_source_assets: bool,
    ) -> PublishTask:
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
        if not approved.facts_checked:
            raise PublishError("最新批准记录尚未完成人工事实核对")

        source_ids = connected_source_ids(db, draft.source_id)
        sources = list(db.scalars(select(SourceItem).where(SourceItem.id.in_(source_ids))).all())

        media_paths: list[str] = []
        selected_asset_ids: list[str] = []
        card_render_id = ""
        if include_cards:
            card_render = db.scalar(
                select(CardRender)
                .where(CardRender.draft_id == draft.id, CardRender.status == "rendered")
                .order_by(CardRender.created_at.desc())
            )
            if card_render is None:
                raise PublishError("尚未生成此草稿的图片卡片")
            try:
                card_paths = json.loads(card_render.output_paths_json or "[]")
            except json.JSONDecodeError as exc:
                raise PublishError("卡片记录已损坏，请重新生成") from exc
            media_paths.extend(str(path) for path in card_paths if Path(str(path)).is_file())
            card_render_id = card_render.id

        if include_source_assets:
            source_assets = list(
                db.scalars(
                    select(Asset).where(
                        Asset.source_id.in_(source_ids),
                        Asset.state == "ready",
                    )
                ).all()
            )
            media_paths.extend(asset.local_path for asset in source_assets if asset.local_path)
            selected_asset_ids = [asset.id for asset in source_assets if asset.local_path]

        if not media_paths:
            raise PublishError("发布包没有可用图片或视频，请先生成卡片")

        payload = {
            "draft_id": draft.id,
            "source_id": draft.source_id,
            "title": draft.title,
            "body": draft.body,
            "tags": [tag.strip().lstrip("#") for tag in draft.tags.split(",") if tag.strip()],
            "assets": media_paths,
            "card_render_id": card_render_id,
            "review_id": approved.id,
            "source_urls": [item.canonical_url for item in sources],
            "source_asset_ids": selected_asset_ids,
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
        for index, source_value in enumerate(media_paths, start=1):
            source_path = Path(source_value)
            if not source_path.is_file():
                continue
            target = media_dir / f"{index:02d}_{source_path.name}"
            if not target.exists():
                shutil.copy2(source_path, target)
            packaged_assets.append(str(target.resolve()))
        if not packaged_assets:
            raise PublishError("发布素材文件已丢失，请重新生成")
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
            asset_ids_json=json.dumps(selected_asset_ids),
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
        if importlib.util.find_spec("playwright") is None:
            raise PublishError(
                "Playwright 未安装。请执行 pip install -e '.[publisher]'，然后运行 playwright install chromium"
            )

        import sys

        log_path = package.parent / "xhs-preview.log"
        command = [
            sys.executable,
            "-m",
            "app.services.xhs_preview_worker",
            str(package),
            str(self.settings.browser_profile_dir),
        ]
        log_handle = None
        try:
            log_handle = log_path.open("ab")
            await asyncio.create_subprocess_exec(
                *command,
                cwd=str(Path(__file__).resolve().parents[2]),
                stdout=log_handle,
                stderr=log_handle,
                start_new_session=True,
            )
        except OSError as exc:
            task.state = PublishState.failed.value
            task.error = str(exc)[:1000]
            db.commit()
            return task
        finally:
            if log_handle is not None:
                log_handle.close()

        task.state = PublishState.awaiting_user_confirmation.value
        task.error = ""
        db.commit()
        db.refresh(task)
        return task

    def mark_published(self, db: Session, task: PublishTask, result_url: str) -> PublishTask:
        if task.state != PublishState.awaiting_user_confirmation.value:
            raise PublishError(f"当前发布状态不可确认：{task.state}")
        parsed = urlparse(result_url.strip())
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not (
            host == "xiaohongshu.com" or host.endswith(".xiaohongshu.com")
        ):
            raise PublishError("请输入有效的小红书 HTTPS 作品链接")

        now = utcnow()
        task.result_url = result_url.strip()
        task.state = PublishState.published.value
        task.error = ""
        draft = db.get(DraftRevision, task.draft_id)
        if draft is not None:
            source = db.get(SourceItem, draft.source_id)
            if source is not None:
                set_source_workbench_state(
                    db,
                    source.id,
                    SourceWorkbench.xhs,
                    WorkspaceState.archived,
                    at=now,
                )
                source.last_published_at = now
                source.published_count += 1
        db.commit()
        db.refresh(task)
        return task
