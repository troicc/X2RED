from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_publish_service
from app.db.session import get_db
from app.domain.models import DraftRevision, PublishTask
from app.domain.schemas import PublishPrepareRequest, PublishResultRequest, PublishTaskOut
from app.services.publisher import PublishError, PublishService

router = APIRouter(prefix="/api/publish", tags=["publish"])


@router.post("/drafts/{draft_id}/prepare", response_model=PublishTaskOut)
def prepare_publish(
    draft_id: str,
    body: PublishPrepareRequest,
    db: Session = Depends(get_db),
    service: PublishService = Depends(get_publish_service),
) -> PublishTask:
    draft = db.get(DraftRevision, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="草稿不存在")
    try:
        return service.prepare(
            db,
            draft,
            include_cards=body.include_cards,
            include_source_assets=body.include_source_assets,
        )
    except PublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[PublishTaskOut])
def list_publish_tasks(db: Session = Depends(get_db)) -> list[PublishTask]:
    return list(db.scalars(select(PublishTask).order_by(PublishTask.created_at.desc())).all())


@router.post("/{task_id}/open-xhs", response_model=PublishTaskOut)
async def open_xhs(
    task_id: str,
    db: Session = Depends(get_db),
    service: PublishService = Depends(get_publish_service),
) -> PublishTask:
    task = db.get(PublishTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="发布任务不存在")
    try:
        return await service.open_xhs_preview(db, task)
    except PublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{task_id}/mark-published", response_model=PublishTaskOut)
def mark_published(
    task_id: str,
    body: PublishResultRequest,
    db: Session = Depends(get_db),
    service: PublishService = Depends(get_publish_service),
) -> PublishTask:
    task = db.get(PublishTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="发布任务不存在")
    try:
        return service.mark_published(db, task, body.result_url)
    except PublishError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
