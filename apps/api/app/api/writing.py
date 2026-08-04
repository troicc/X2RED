from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_job_engine, get_pool_memory_service, get_writing_service
from app.db.session import get_db
from app.domain.jobs import Job
from app.domain.models import SourceItem
from app.domain.pool_memory_schemas import PoolMemoryTargetCandidateRequest
from app.domain.schemas import JobOut
from app.domain.studio import StyleProfile, WritingArtifact, WritingFeedback, WritingProject
from app.domain.studio_schemas import (
    ArtifactApprovalRequest,
    StyleProfileCreate,
    StyleProfileOut,
    WritingFeedbackCreate,
    WritingProjectCreate,
    WritingProjectOut,
    WritingRunRequest,
)
from app.domain.style_schemas import StyleProfileTrainRequest
from app.services.jobs import JobEngine
from app.services.pool_memory import PoolMemoryError, PoolMemoryService
from app.services.writing_studio import MultiAgentWritingService

router = APIRouter(prefix="/api/writing", tags=["writing-studio"])


def project_payload(
    db: Session,
    service: MultiAgentWritingService,
    project: WritingProject,
) -> dict:
    memory_service = PoolMemoryService(service.settings, service.editorial)
    memory_snapshot = memory_service.snapshot_for_target(
        db,
        target_type="writing_project",
        target_id=project.id,
    )
    return {
        "id": project.id,
        "source_id": project.source_id,
        "mode": project.mode,
        "state": project.state,
        "current_stage": project.current_stage,
        "reader": project.reader,
        "promise": project.promise,
        "main_thesis": project.main_thesis,
        "style_profile_id": project.style_profile_id,
        "budget_limit_cents": project.budget_limit_cents,
        "spent_estimate_cents": project.spent_estimate_cents,
        "error": project.error,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        "artifacts": service.artifacts(db, project.id),
        "runs": service.runs(db, project.id),
        "memory_snapshot": memory_service.snapshot_summary(memory_snapshot),
    }


@router.get("/styles", response_model=list[StyleProfileOut])
def list_styles(db: Session = Depends(get_db)) -> list[StyleProfile]:
    return list(db.scalars(select(StyleProfile).order_by(StyleProfile.name)).all())


@router.post("/styles", response_model=StyleProfileOut, status_code=status.HTTP_201_CREATED)
def create_style(body: StyleProfileCreate, db: Session = Depends(get_db)) -> StyleProfile:
    existing = db.scalar(select(StyleProfile).where(StyleProfile.name == body.name.strip()))
    if existing is not None:
        raise HTTPException(status_code=400, detail="同名风格档案已经存在")
    item = StyleProfile(
        name=body.name.strip(),
        description=body.description.strip(),
        rules_json=json.dumps(body.rules, ensure_ascii=False),
        forbidden_json=json.dumps(body.forbidden, ensure_ascii=False),
        samples_json=json.dumps(body.samples, ensure_ascii=False),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post(
    "/styles/train",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def train_style(
    body: StyleProfileTrainRequest,
    db: Session = Depends(get_db),
    engine: JobEngine = Depends(get_job_engine),
) -> Job:
    try:
        return engine.enqueue(
            db,
            kind="writing.train_style",
            payload=body.model_dump(),
            priority=108,
            max_attempts=2,
            dedupe_key=f"writing.train_style:{body.name.strip()}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/projects", response_model=list[WritingProjectOut])
def list_projects(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    service: MultiAgentWritingService = Depends(get_writing_service),
) -> list[dict]:
    projects = list(
        db.scalars(
            select(WritingProject).order_by(desc(WritingProject.updated_at)).limit(limit)
        ).all()
    )
    return [project_payload(db, service, project) for project in projects]


@router.post("/projects", response_model=WritingProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    body: WritingProjectCreate,
    db: Session = Depends(get_db),
    service: MultiAgentWritingService = Depends(get_writing_service),
) -> dict:
    source = db.get(SourceItem, body.source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="来源不存在")
    try:
        project = service.create_project(
            db,
            source=source,
            mode=body.mode,
            reader=body.reader,
            promise=body.promise,
            main_thesis=body.main_thesis,
            style_profile_id=body.style_profile_id,
            budget_limit_cents=body.budget_limit_cents,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(project)
    return project_payload(db, service, project)


@router.get("/projects/{project_id}", response_model=WritingProjectOut)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    service: MultiAgentWritingService = Depends(get_writing_service),
) -> dict:
    project = db.get(WritingProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="写作项目不存在")
    return project_payload(db, service, project)


@router.post(
    "/projects/{project_id}/run",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def run_project(
    project_id: str,
    body: WritingRunRequest,
    db: Session = Depends(get_db),
    engine: JobEngine = Depends(get_job_engine),
) -> Job:
    if db.get(WritingProject, project_id) is None:
        raise HTTPException(status_code=404, detail="写作项目不存在")
    try:
        return engine.enqueue(
            db,
            kind="writing.advance",
            payload={"project_id": project_id, "continuous": body.continuous},
            priority=115,
            max_attempts=2,
            dedupe_key=f"writing.advance:{project_id}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/projects/{project_id}/artifacts/{artifact_id}/approve", response_model=WritingProjectOut
)
def approve_artifact(
    project_id: str,
    artifact_id: str,
    body: ArtifactApprovalRequest,
    db: Session = Depends(get_db),
    service: MultiAgentWritingService = Depends(get_writing_service),
) -> dict:
    project = db.get(WritingProject, project_id)
    artifact = db.get(WritingArtifact, artifact_id)
    if project is None or artifact is None:
        raise HTTPException(status_code=404, detail="写作项目或阶段产物不存在")
    try:
        service.approve_artifact(
            db,
            project=project,
            artifact=artifact,
            approved=body.approved,
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(project)
    return project_payload(db, service, project)


@router.post("/projects/{project_id}/feedback", status_code=status.HTTP_201_CREATED)
def add_feedback(
    project_id: str,
    body: WritingFeedbackCreate,
    db: Session = Depends(get_db),
    service: MultiAgentWritingService = Depends(get_writing_service),
) -> dict:
    project = db.get(WritingProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="写作项目不存在")
    feedback = service.add_feedback(
        db,
        project=project,
        draft_before_id=body.draft_before_id,
        draft_after_id=body.draft_after_id,
        diff=body.diff,
        feedback_reason=body.feedback_reason,
        affected_rules=body.affected_rules,
    )
    db.commit()
    return {"id": feedback.id, "created_at": feedback.created_at}


@router.get("/projects/{project_id}/feedback")
def list_feedback(
    project_id: str,
    db: Session = Depends(get_db),
    memory_service: PoolMemoryService = Depends(get_pool_memory_service),
) -> list[dict]:
    if db.get(WritingProject, project_id) is None:
        raise HTTPException(status_code=404, detail="写作项目不存在")
    values = list(
        db.scalars(
            select(WritingFeedback)
            .where(WritingFeedback.project_id == project_id)
            .order_by(desc(WritingFeedback.created_at))
        ).all()
    )
    return [
        {
            "id": item.id,
            "draft_before_id": item.draft_before_id,
            "draft_after_id": item.draft_after_id,
            "diff": json.loads(item.diff_json or "{}"),
            "feedback_reason": item.feedback_reason,
            "affected_rules": json.loads(item.affected_rules_json or "[]"),
            "pool_memory": memory_service.source_memory_status(
                db,
                source_kind="writing_feedback",
                source_id=item.id,
            ),
            "created_at": item.created_at,
        }
        for item in values
    ]


@router.post(
    "/projects/{project_id}/feedback/{feedback_id}/memory-candidate",
    status_code=status.HTTP_201_CREATED,
)
async def feedback_memory_candidate(
    project_id: str,
    feedback_id: str,
    body: PoolMemoryTargetCandidateRequest,
    db: Session = Depends(get_db),
    service: PoolMemoryService = Depends(get_pool_memory_service),
) -> dict:
    feedback = db.get(WritingFeedback, feedback_id)
    if feedback is None or feedback.project_id != project_id:
        raise HTTPException(status_code=404, detail="写作反馈不存在")
    try:
        candidate = await service.create_candidate(
            db,
            source_kind="writing_feedback",
            source_id=feedback.id,
            title=body.title,
            dimensions=[str(item) for item in body.dimensions],
            scope=body.scope.model_dump(),
            usage_policy=body.usage_policy,
            note=body.note,
        )
        db.commit()
        db.refresh(candidate)
        return {"candidate_id": candidate.id, "state": candidate.state}
    except PoolMemoryError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/projects/{project_id}/final-memory-candidate",
    status_code=status.HTTP_201_CREATED,
)
async def final_memory_candidate(
    project_id: str,
    body: PoolMemoryTargetCandidateRequest,
    db: Session = Depends(get_db),
    service: MultiAgentWritingService = Depends(get_writing_service),
    memory_service: PoolMemoryService = Depends(get_pool_memory_service),
) -> dict:
    project = db.get(WritingProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="写作项目不存在")
    artifact = service.latest_artifact(db, project.id, "final_draft")
    if artifact is None:
        raise HTTPException(status_code=404, detail="当前项目还没有终稿")
    try:
        candidate = await memory_service.create_candidate(
            db,
            source_kind="writing_artifact",
            source_id=artifact.id,
            title=body.title,
            dimensions=[str(item) for item in body.dimensions],
            scope=body.scope.model_dump(),
            usage_policy=body.usage_policy,
            note=body.note,
        )
        db.commit()
        db.refresh(candidate)
        return {"candidate_id": candidate.id, "state": candidate.state}
    except PoolMemoryError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
