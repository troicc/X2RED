from __future__ import annotations

import asyncio
import json
from contextlib import suppress

from sqlalchemy import select

from app.db.session import SessionLocal
from app.domain.jobs import Job, JobState
from app.domain.models import utcnow
from app.services.intake import IntakeService


class JobEngine:
    def __init__(self, intake_service: IntakeService, poll_seconds: float = 0.4) -> None:
        self.intake_service = intake_service
        self.poll_seconds = poll_seconds
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        if self._task is not None:
            return
        with SessionLocal() as db:
            interrupted = db.scalars(select(Job).where(Job.state == JobState.running.value)).all()
            for job in interrupted:
                job.state = JobState.pending.value
                job.error = "应用重启，任务已重新排队"
                job.started_at = None
            db.commit()
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="x2red-job-engine")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _loop(self) -> None:
        while self._running:
            job_id = self._claim_next()
            if job_id is None:
                await asyncio.sleep(self.poll_seconds)
                continue
            await self._process(job_id)

    def _claim_next(self) -> str | None:
        with SessionLocal() as db:
            job = db.scalar(
                select(Job)
                .where(Job.state == JobState.pending.value)
                .order_by(Job.created_at, Job.id)
                .limit(1)
            )
            if job is None:
                return None
            job.state = JobState.running.value
            job.attempts += 1
            job.started_at = utcnow()
            job.finished_at = None
            job.error = ""
            db.commit()
            return job.id

    async def _process(self, job_id: str) -> None:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is None or job.state != JobState.running.value:
                return
            try:
                payload = json.loads(job.payload_json or "{}")
                if job.kind != "intake_x":
                    raise RuntimeError(f"不支持的任务类型：{job.kind}")
                source_id, imported_count, asset_count, snapshot = (
                    await self.intake_service.import_post(
                        db,
                        post_id=str(payload["post_id"]),
                        mode=str(payload.get("mode") or "thread"),
                        download_media=bool(payload.get("download_media", True)),
                    )
                )
                job = db.get(Job, job_id)
                if job is None:
                    return
                job.result_json = json.dumps(
                    {
                        "source_id": source_id,
                        "external_id": str(payload["post_id"]),
                        "imported_count": imported_count,
                        "asset_count": asset_count,
                        "snapshot_id": snapshot.id,
                    },
                    ensure_ascii=False,
                )
                job.state = JobState.succeeded.value
                job.finished_at = utcnow()
                job.error = ""
                db.commit()
            except Exception as exc:
                db.rollback()
                job = db.get(Job, job_id)
                if job is None:
                    return
                job.state = JobState.failed.value
                job.finished_at = utcnow()
                job.error = str(exc)[:2000]
                db.commit()
