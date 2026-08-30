from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import app.db.session as db_session
from app.core.config import Settings
from app.db.base import Base
from app.domain.jobs import Job, JobState
from app.domain.models import utcnow
from app.services.jobs import JobEngine
from app.services.model_client import ModelClientError


@pytest.fixture()
def job_session_factory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> sessionmaker[Session]:
    for module_name in (
        "app.domain.discovery",
        "app.domain.models",
        "app.domain.platforms",
        "app.domain.pool_memory",
        "app.domain.review_artifacts",
        "app.domain.studio",
        "app.domain.style_snapshot",
    ):
        __import__(module_name)
    engine = create_engine(
        f"sqlite:///{tmp_path / 'jobs.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    monkeypatch.setattr(db_session, "SessionLocal", factory)
    yield factory
    engine.dispose()


def _settings() -> Settings:
    return Settings(
        job_lease_seconds=15,
        job_heartbeat_seconds=5,
        job_retry_base_seconds=0.1,
    )


@pytest.mark.asyncio
async def test_two_workers_claim_and_execute_one_job_exactly_once(
    job_session_factory: sessionmaker[Session],
) -> None:
    executions = 0

    async def handler(_db: Session, payload: dict) -> dict:
        nonlocal executions
        executions += 1
        await asyncio.sleep(0)
        return {"value": payload["value"]}

    first = JobEngine(settings=_settings())
    second = JobEngine(settings=_settings())
    first.register("ops.once", handler)
    second.register("ops.once", handler)
    with job_session_factory() as db:
        job = first.enqueue(
            db,
            kind="ops.once",
            payload={"value": 7},
            dedupe_key="ops.once:7",
        )
        job_id = job.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            (first, pool.submit(first._claim_next)),
            (second, pool.submit(second._claim_next)),
        ]
        claims = [(engine, future.result()) for engine, future in futures]
    claimed = [(engine, value) for engine, value in claims if value is not None]
    assert len(claimed) == 1
    assert claimed[0][1] == job_id

    await claimed[0][0]._process(job_id)
    assert executions == 1
    with job_session_factory() as db:
        stored = db.get(Job, job_id)
        assert stored is not None
        assert stored.state == JobState.succeeded.value
        assert stored.attempts == 1
        assert stored.last_worker_id == claimed[0][0].worker_id
        assert stored.heartbeat_at is not None
        assert stored.lease_expires_at is None


def test_only_expired_lease_is_recovered_and_reclaimed(
    job_session_factory: sessionmaker[Session],
) -> None:
    worker = JobEngine(settings=_settings())
    worker.register("ops.recover", lambda *_args: None)  # type: ignore[arg-type]
    now = utcnow()
    with job_session_factory() as db:
        expired = Job(
            kind="ops.recover",
            state=JobState.running.value,
            payload_json="{}",
            locked_by="dead-worker",
            last_worker_id="dead-worker",
            attempts=1,
            lease_expires_at=now - timedelta(seconds=1),
            heartbeat_at=now - timedelta(seconds=20),
            available_at=now,
        )
        live = Job(
            kind="ops.recover",
            state=JobState.running.value,
            payload_json="{}",
            locked_by="live-worker",
            last_worker_id="live-worker",
            attempts=1,
            lease_expires_at=now + timedelta(minutes=5),
            heartbeat_at=now,
            available_at=now,
        )
        db.add_all([expired, live])
        db.commit()
        expired_id, live_id = expired.id, live.id

    assert worker._recover_expired_leases() == 1
    assert worker._claim_next() == expired_id
    with job_session_factory() as db:
        recovered = db.get(Job, expired_id)
        untouched = db.get(Job, live_id)
        assert recovered is not None and recovered.locked_by == worker.worker_id
        assert recovered.last_error_code == ""
        assert untouched is not None and untouched.locked_by == "live-worker"
        assert untouched.state == JobState.running.value


def test_terminal_failure_moves_to_dead_letter_and_manual_retry_resets_it(
    job_session_factory: sessionmaker[Session],
) -> None:
    worker = JobEngine(settings=_settings())
    with job_session_factory() as db:
        job = Job(
            kind="ops.fail",
            state=JobState.running.value,
            payload_json="{}",
            attempts=2,
            max_attempts=2,
            locked_by=worker.worker_id,
            lease_expires_at=utcnow() + timedelta(seconds=15),
            available_at=utcnow(),
        )
        db.add(job)
        db.commit()
        worker._fail_or_retry(db, job, ValueError("broken payload"))
        assert job.state == JobState.dead_letter.value
        assert job.dead_lettered_at is not None
        assert job.last_error_code == "valueerror"

        retried = worker.retry(db, job)
        assert retried.state == JobState.pending.value
        assert retried.attempts == 0
        assert retried.dead_lettered_at is None
        assert retried.last_error_code == ""


def test_expired_lease_at_attempt_limit_moves_to_dead_letter(
    job_session_factory: sessionmaker[Session],
) -> None:
    worker = JobEngine(settings=_settings())
    with job_session_factory() as db:
        job = Job(
            kind="ops.crashed",
            state=JobState.running.value,
            payload_json="{}",
            attempts=3,
            max_attempts=3,
            locked_by="crashed-worker",
            lease_expires_at=utcnow() - timedelta(seconds=1),
            available_at=utcnow(),
        )
        db.add(job)
        db.commit()
        job_id = job.id

    assert worker._recover_expired_leases() == 1
    with job_session_factory() as db:
        stored = db.get(Job, job_id)
        assert stored is not None
        assert stored.state == JobState.dead_letter.value
        assert stored.dead_lettered_at is not None
        assert stored.last_error_code == "lease_expired"
        assert stored.locked_by == ""
    assert worker._claim_next() is None


def test_job_failure_redacts_provider_credentials(
    job_session_factory: sessionmaker[Session],
) -> None:
    worker = JobEngine(settings=_settings())
    secret = "job-secret-value"
    with job_session_factory() as db:
        job = Job(
            kind="ops.fail",
            state=JobState.running.value,
            payload_json="{}",
            attempts=1,
            max_attempts=1,
            locked_by=worker.worker_id,
            lease_expires_at=utcnow() + timedelta(seconds=15),
            available_at=utcnow(),
        )
        db.add(job)
        db.commit()
        worker._fail_or_retry(
            db,
            job,
            ModelClientError(
                "provider failure",
                code="authentication_error",
                detail=f"api_key={secret}",
            ),
        )
        assert secret not in job.error
        assert job.last_error_code == "authentication_error"


def test_active_dedupe_key_returns_existing_job(
    job_session_factory: sessionmaker[Session],
) -> None:
    worker = JobEngine(settings=_settings())

    async def handler(_db: Session, _payload: dict) -> dict:
        return {}

    worker.register("ops.dedupe", handler)
    with job_session_factory() as db:
        first = worker.enqueue(
            db,
            kind="ops.dedupe",
            payload={"sequence": 1},
            dedupe_key="same-active-key",
        )
        second = worker.enqueue(
            db,
            kind="ops.dedupe",
            payload={"sequence": 2},
            dedupe_key="same-active-key",
        )
        assert first.id == second.id
        jobs = list(db.scalars(select(Job)).all())
        assert len(jobs) == 1
