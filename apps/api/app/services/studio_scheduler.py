from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import app.db.session as db_session
from app.core.config import Settings
from app.services.jobs import JobEngine
from app.services.signal_studio import SignalStudioService

log = logging.getLogger("x2red.scheduler")


class StudioScheduler:
    def __init__(
        self,
        settings: Settings,
        job_engine: JobEngine,
        signal_service: SignalStudioService,
    ) -> None:
        self.settings = settings
        self.job_engine = job_engine
        self.signal_service = signal_service
        self.scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)

    def start(self) -> None:
        if not self.settings.scheduler_enabled:
            return
        self.scheduler.add_job(
            self._tick,
            "interval",
            seconds=self.settings.scheduler_poll_seconds,
            id="x2red-monitor-due-targets",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
        )
        self.scheduler.start()

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def _tick(self) -> None:
        try:
            with db_session.SessionLocal() as db:
                for target_id in self.signal_service.due_target_ids(
                    db,
                    limit=self.settings.scheduler_batch_size,
                ):
                    self.job_engine.enqueue(
                        db,
                        kind="signal.scan_target",
                        payload={"target_id": target_id},
                        priority=90,
                        max_attempts=3,
                        dedupe_key=f"signal.scan_target:{target_id}",
                    )
        except Exception:
            log.exception("failed to enqueue due monitor targets")
