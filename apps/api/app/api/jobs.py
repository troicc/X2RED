from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_job_engine
from app.core.config import get_settings
from app.db.session import get_db
from app.domain.jobs import Job
from app.domain.schemas import IntakeRequest, JobOut
from app.services.jobs import JobEngine
from app.services.url_parser import extract_x_post_id

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
settings = get_settings()


@router.post("/intake", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def enqueue_intake(
    body: IntakeRequest,
    db: Session = Depends(get_db),
    engine: JobEngine = Depends(get_job_engine),
) -> Job:
    try:
        post_id = extract_x_post_id(body.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    download_media = settings.download_media if body.download_media is None else body.download_media
    return engine.enqueue_intake(
        db,
        post_id=post_id,
        mode=body.mode,
        download_media=download_media,
    )


@router.get("", response_model=list[JobOut])
def list_jobs(limit: int = 50, db: Session = Depends(get_db)) -> list[Job]:
    bounded_limit = max(1, min(limit, 200))
    return list(db.scalars(select(Job).order_by(Job.created_at.desc()).limit(bounded_limit)).all())


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@router.post("/{job_id}/retry", response_model=JobOut)
def retry_job(
    job_id: str,
    db: Session = Depends(get_db),
    engine: JobEngine = Depends(get_job_engine),
) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        return engine.retry(db, job)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
