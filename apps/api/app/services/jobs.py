from __future__ import annotations

import asyncio
import json
import logging
import socket
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

import app.db.session as db_session
from app.domain.discovery import CandidateState, DiscoveryCandidate
from app.domain.jobs import Job, JobState
from app.domain.models import utcnow
from app.services.intake import IntakeService

log = logging.getLogger("x2red.jobs")
JobHandler = Callable[[Session, dict[str, Any]], Awaitable[dict[str, Any]]]


class JobEngine:
    def __init__(self, intake_service: IntakeService | None = None, poll_seconds: float = 0.4) -> None:
        self.intake_service = intake_service
        self.poll_seconds = poll_seconds
        self.worker_id = f"{socket.gethostname()}:{id(self)}"
        self._handlers: dict[str, JobHandler] = {}
        self._task: asyncio.Task[None] | None = None
        self._running = False
        if intake_service is not None:
            self.register("intake_x", self._handle_intake)

    def register(self, kind: str, handler: JobHandler) -> None:
        if not kind.strip():
            raise ValueError("任务类型不能为空")
        self._handlers[kind] = handler

    async def start(self) -> None:
        if self._task is not None:
            return
        with db_session.SessionLocal() as db:
            interrupted = db.scalars(select(Job).where(Job.state == JobState.running.value)).all()
            for job in interrupted:
                job.state = JobState.pending.value
                job.error = "应用重启，任务已重新排队"
                job.started_at = None
                job.locked_by = ""
                job.available_at = utcnow()
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

    def enqueue(
        self,
        db: Session,
        *,
        kind: str,
        payload: dict[str, Any],
        priority: int = 100,
        max_attempts: int = 3,
        dedupe_key: str = "",
        delay_seconds: float = 0,
    ) -> Job:
        if kind not in self._handlers:
            raise ValueError(f"没有注册任务处理器：{kind}")
        if dedupe_key:
            existing = db.scalar(
                select(Job)
                .where(
                    Job.dedupe_key == dedupe_key,
                    Job.state.in_([JobState.pending.value, JobState.running.value]),
                )
                .order_by(Job.created_at.desc())
                .limit(1)
            )
            if existing is not None:
                return existing
        job = Job(
            kind=kind,
            state=JobState.pending.value,
            payload_json=json.dumps(payload, ensure_ascii=False),
            priority=priority,
            max_attempts=max(max_attempts, 1),
            dedupe_key=dedupe_key[:255],
            available_at=utcnow() + timedelta(seconds=max(delay_seconds, 0)),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def enqueue_intake(
        self,
        db: Session,
        *,
        post_id: str,
        mode: str,
        download_media: bool,
        candidate_id: str | None = None,
    ) -> Job:
        if candidate_id:
            candidate = db.get(DiscoveryCandidate, candidate_id)
            if candidate is not None:
                candidate.state = CandidateState.saved.value
        return self.enqueue(
            db,
            kind="intake_x",
            payload={
                "post_id": post_id,
                "mode": mode,
                "download_media": download_media,
                "candidate_id": candidate_id,
            },
            priority=120,
            dedupe_key=f"intake_x:{post_id}:{mode}",
        )

    def retry(self, db: Session, job: Job) -> Job:
        if job.state not in {JobState.failed.value, JobState.canceled.value}:
            raise ValueError(f"当前任务状态不可重试：{job.state}")
        job.state = JobState.pending.value
        job.result_json = "{}"
        job.error = ""
        job.started_at = None
        job.finished_at = None
        job.locked_by = ""
        job.available_at = utcnow()
        db.commit()
        db.refresh(job)
        return job

    async def _loop(self) -> None:
        while self._running:
            try:
                job_id = self._claim_next()
                if job_id is None:
                    await asyncio.sleep(self.poll_seconds)
                    continue
                await self._process(job_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("job engine iteration failed")
                await asyncio.sleep(self.poll_seconds)

    def _claim_next(self) -> str | None:
        with db_session.SessionLocal() as db:
            job = db.scalar(
                select(Job)
                .where(
                    Job.state == JobState.pending.value,
                    Job.available_at <= utcnow(),
                )
                .order_by(Job.priority.desc(), Job.created_at, Job.id)
                .limit(1)
            )
            if job is None:
                return None
            job.state = JobState.running.value
            job.attempts += 1
            job.started_at = utcnow()
            job.finished_at = None
            job.error = ""
            job.locked_by = self.worker_id
            db.commit()
            return job.id

    async def _process(self, job_id: str) -> None:
        with db_session.SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is None or job.state != JobState.running.value:
                return
            handler = self._handlers.get(job.kind)
            if handler is None:
                self._fail_or_retry(db, job, RuntimeError(f"不支持的任务类型：{job.kind}"))
                return
            try:
                payload = json.loads(job.payload_json or "{}")
                result = await handler(db, payload)
                job = db.get(Job, job_id)
                if job is None:
                    return
                job.result_json = json.dumps(result or {}, ensure_ascii=False)
                job.state = JobState.succeeded.value
                job.finished_at = utcnow()
                job.error = ""
                job.locked_by = ""
                db.commit()
            except Exception as exc:
                db.rollback()
                job = db.get(Job, job_id)
                if job is None:
                    return
                self._fail_or_retry(db, job, exc)

    def _fail_or_retry(self, db: Session, job: Job, exc: Exception) -> None:
        job.error = str(exc)[:2000]
        job.locked_by = ""
        if job.attempts < job.max_attempts:
            job.state = JobState.pending.value
            job.available_at = utcnow() + timedelta(seconds=min(2 ** job.attempts, 60))
            job.started_at = None
            job.finished_at = None
        else:
            job.state = JobState.failed.value
            job.finished_at = utcnow()
        db.commit()

    async def _handle_intake(self, db: Session, payload: dict[str, Any]) -> dict[str, Any]:
        if self.intake_service is None:
            raise RuntimeError("intake service is not configured")
        source_id, imported_count, asset_count, snapshot = await self.intake_service.import_post(
            db,
            post_id=str(payload["post_id"]),
            mode=str(payload.get("mode") or "thread"),
            download_media=bool(payload.get("download_media", True)),
        )
        candidate_id = str(payload.get("candidate_id") or "")
        if candidate_id:
            candidate = db.get(DiscoveryCandidate, candidate_id)
            if candidate is not None:
                candidate.state = CandidateState.imported.value
        return {
            "source_id": source_id,
            "external_id": str(payload["post_id"]),
            "imported_count": imported_count,
            "asset_count": asset_count,
            "snapshot_id": snapshot.id,
            "candidate_id": candidate_id,
        }
