from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import socket
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.db.session as db_session
from app.core.config import Settings, get_settings
from app.core.security import redact_sensitive
from app.domain.discovery import CandidateState, DiscoveryCandidate
from app.domain.jobs import Job, JobState
from app.domain.models import utcnow
from app.services.intake import IntakeService
from app.services.model_client import ModelClientError

log = logging.getLogger("x2red.jobs")
JobHandler = Callable[[Session, dict[str, Any]], Awaitable[dict[str, Any]]]


class JobEngine:
    def __init__(
        self,
        intake_service: IntakeService | None = None,
        poll_seconds: float = 0.4,
        settings: Settings | None = None,
    ) -> None:
        self.intake_service = intake_service
        self.poll_seconds = poll_seconds
        self.settings = settings or get_settings()
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:12]}"
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
        self._recover_expired_leases()
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
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if not dedupe_key:
                raise
            existing = db.scalar(
                select(Job)
                .where(
                    Job.dedupe_key == dedupe_key,
                    Job.state.in_([JobState.pending.value, JobState.running.value]),
                )
                .order_by(Job.created_at.desc())
                .limit(1)
            )
            if existing is None:
                raise
            return existing
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
        if job.state not in {
            JobState.failed.value,
            JobState.dead_letter.value,
            JobState.canceled.value,
        }:
            raise ValueError(f"当前任务状态不可重试：{job.state}")
        job.state = JobState.pending.value
        job.result_json = "{}"
        job.error = ""
        job.started_at = None
        job.finished_at = None
        job.locked_by = ""
        job.lease_expires_at = None
        job.heartbeat_at = None
        job.dead_lettered_at = None
        job.last_error_code = ""
        job.attempts = 0
        job.available_at = utcnow()
        db.commit()
        db.refresh(job)
        return job

    async def _loop(self) -> None:
        while self._running:
            try:
                self._recover_expired_leases()
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
            now = utcnow()
            job_id = db.scalar(
                select(Job.id)
                .where(
                    Job.state == JobState.pending.value,
                    Job.available_at <= now,
                )
                .order_by(Job.priority.desc(), Job.created_at, Job.id)
                .limit(1)
            )
            if job_id is None:
                return None
            claimed = db.execute(
                update(Job)
                .where(
                    Job.id == job_id,
                    Job.state == JobState.pending.value,
                    Job.available_at <= now,
                )
                .values(
                    state=JobState.running.value,
                    attempts=Job.attempts + 1,
                    started_at=now,
                    finished_at=None,
                    error="",
                    last_error_code="",
                    locked_by=self.worker_id,
                    last_worker_id=self.worker_id,
                    heartbeat_at=now,
                    lease_expires_at=now + timedelta(seconds=self.settings.job_lease_seconds),
                )
            )
            if claimed.rowcount != 1:
                db.rollback()
                return None
            db.commit()
            return str(job_id)

    async def _process(self, job_id: str) -> None:
        with db_session.SessionLocal() as db:
            job = db.get(Job, job_id)
            if (
                job is None
                or job.state != JobState.running.value
                or job.locked_by != self.worker_id
            ):
                return
            handler = self._handlers.get(job.kind)
            if handler is None:
                self._fail_or_retry(db, job, RuntimeError(f"不支持的任务类型：{job.kind}"))
                return
            heartbeat = asyncio.create_task(
                self._heartbeat(job_id),
                name=f"x2red-job-heartbeat-{job_id}",
            )
            try:
                payload = json.loads(job.payload_json or "{}")
                result = await handler(db, payload)
                db.flush()
                db.expire_all()
                job = db.get(Job, job_id)
                if (
                    job is None
                    or job.state != JobState.running.value
                    or job.locked_by != self.worker_id
                ):
                    db.rollback()
                    return
                job.result_json = json.dumps(result or {}, ensure_ascii=False)
                job.state = JobState.succeeded.value
                job.finished_at = utcnow()
                job.error = ""
                job.locked_by = ""
                job.lease_expires_at = None
                db.commit()
            except asyncio.CancelledError:
                db.rollback()
                raise
            except Exception as exc:  # noqa: BLE001 - handler failures become durable state
                db.rollback()
                job = db.get(Job, job_id)
                if (
                    job is None
                    or job.state != JobState.running.value
                    or job.locked_by != self.worker_id
                ):
                    return
                self._fail_or_retry(db, job, exc)
            finally:
                heartbeat.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat

    def _fail_or_retry(self, db: Session, job: Job, exc: Exception) -> None:
        job.error = redact_sensitive(exc, max_length=2000)
        job.last_error_code = (
            exc.code
            if isinstance(exc, ModelClientError)
            else type(exc).__name__.lower()[:80]
        )
        job.locked_by = ""
        job.lease_expires_at = None
        if job.attempts < job.max_attempts:
            job.state = JobState.pending.value
            delay = min(
                self.settings.job_retry_base_seconds * (2 ** max(job.attempts - 1, 0)),
                300,
            )
            job.available_at = utcnow() + timedelta(
                seconds=delay + random.uniform(0, min(delay * 0.2, 5.0))
            )
            job.started_at = None
            job.finished_at = None
        else:
            job.state = JobState.dead_letter.value
            job.finished_at = utcnow()
            job.dead_lettered_at = job.finished_at
        db.commit()

    def _recover_expired_leases(self) -> int:
        now = utcnow()
        with db_session.SessionLocal() as db:
            expired = db.scalars(
                select(Job).where(
                    Job.state == JobState.running.value,
                    or_(Job.lease_expires_at.is_(None), Job.lease_expires_at <= now),
                )
            ).all()
            for job in expired:
                job.last_error_code = "lease_expired"
                job.started_at = None
                job.locked_by = ""
                job.lease_expires_at = None
                if job.attempts >= job.max_attempts:
                    job.state = JobState.dead_letter.value
                    job.error = "任务租约过期且已达到最大尝试次数"
                    job.finished_at = now
                    job.dead_lettered_at = now
                else:
                    job.state = JobState.pending.value
                    job.error = "任务租约过期，已安全重新排队"
                    job.finished_at = None
                    job.available_at = now
            db.commit()
            return len(expired)

    async def _heartbeat(self, job_id: str) -> None:
        interval = min(
            float(self.settings.job_heartbeat_seconds),
            max(float(self.settings.job_lease_seconds) / 3, 1.0),
        )
        while True:
            await asyncio.sleep(interval)
            now = utcnow()
            try:
                with db_session.SessionLocal() as db:
                    refreshed = db.execute(
                        update(Job)
                        .where(
                            Job.id == job_id,
                            Job.state == JobState.running.value,
                            Job.locked_by == self.worker_id,
                        )
                        .values(
                            heartbeat_at=now,
                            lease_expires_at=now
                            + timedelta(seconds=self.settings.job_lease_seconds),
                        )
                    )
                    db.commit()
                    if refreshed.rowcount != 1:
                        return
            except Exception:
                log.exception("job heartbeat failed", extra={"job_id": job_id})

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
