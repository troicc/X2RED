from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_pool_memory_service
from app.db.session import get_db
from app.domain.pool_memory import PoolMemorySnapshot
from app.domain.pool_memory_schemas import (
    PoolMemoryApproveRequest,
    PoolMemoryArtifactOut,
    PoolMemoryCandidateCreate,
    PoolMemoryCandidateOut,
    PoolMemoryCandidateUpdate,
    PoolMemoryManualCreate,
    PoolMemoryRetrievePreview,
    PoolMemoryRetrieveRequest,
    PoolMemoryRevokeRequest,
    PoolMemorySnapshotOut,
    PoolMemorySourceOption,
    PoolMemorySupersedeRequest,
    PoolMemoryUsageOut,
)
from app.domain.review_artifacts import ReviewArtifact
from app.services.pool_memory import PoolMemoryError, PoolMemoryService

router = APIRouter(prefix="/api/pool-memory", tags=["pool-memory"])


def _artifact(db: Session, artifact_id: str) -> ReviewArtifact:
    artifact = db.get(ReviewArtifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="池子记忆或候选不存在")
    return artifact


@router.get("/items", response_model=list[PoolMemoryArtifactOut])
def list_items(
    include_inactive: bool = False,
    scope_id: str = Query(default="", max_length=64),
    platform: str = Query(default="", max_length=40),
    format: str = Query(default="", max_length=40),
    article_type: str = Query(default="", max_length=80),
    style_profile_id: str = Query(default="", max_length=64),
    topic: str = Query(default="", max_length=120),
    state: str = Query(default="", pattern="^(|all|effective|inactive|superseded|revoked)$"),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    service: PoolMemoryService = Depends(get_pool_memory_service),
) -> list[dict]:
    include_inactive = include_inactive or state in {
        "all",
        "inactive",
        "superseded",
        "revoked",
    }
    return service.list_items(
        db,
        include_inactive=include_inactive,
        scope_id=scope_id,
        platform=platform,
        format=format,
        article_type=article_type,
        style_profile_id=style_profile_id,
        topic=topic,
        state=state,
        limit=limit,
    )


@router.get("/candidates", response_model=list[PoolMemoryCandidateOut])
def list_candidates(
    limit: int = Query(default=100, ge=1, le=300),
    db: Session = Depends(get_db),
    service: PoolMemoryService = Depends(get_pool_memory_service),
) -> list[dict]:
    return service.list_candidates(db, limit=limit)


@router.get("/source-options", response_model=list[PoolMemorySourceOption])
def source_options(
    limit: int = Query(default=80, ge=1, le=300),
    db: Session = Depends(get_db),
    service: PoolMemoryService = Depends(get_pool_memory_service),
) -> list[dict]:
    return service.source_options(db, limit=limit)


@router.post(
    "/candidates",
    response_model=PoolMemoryCandidateOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_candidate(
    body: PoolMemoryCandidateCreate,
    db: Session = Depends(get_db),
    service: PoolMemoryService = Depends(get_pool_memory_service),
) -> dict:
    try:
        candidate = await service.create_candidate(
            db,
            source_kind=body.source_kind,
            source_id=body.source_id,
            title=body.title,
            dimensions=[str(item) for item in body.dimensions],
            scope=body.scope.model_dump(),
            usage_policy=body.usage_policy,
            note=body.note,
        )
        db.commit()
        db.refresh(candidate)
    except PoolMemoryError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    values = service.list_candidates(db, limit=300)
    return next(item for item in values if item["id"] == candidate.id)


@router.put("/candidates/{candidate_id}", response_model=PoolMemoryCandidateOut)
def update_candidate(
    candidate_id: str,
    body: PoolMemoryCandidateUpdate,
    db: Session = Depends(get_db),
    service: PoolMemoryService = Depends(get_pool_memory_service),
) -> dict:
    try:
        candidate = service.update_candidate(
            db,
            _artifact(db, candidate_id),
            title=body.title,
            dimensions=[str(item) for item in body.dimensions],
            scope=body.scope.model_dump(),
            memory=body.memory.model_dump(),
            usage_policy=body.usage_policy,
            note=body.note,
        )
        db.commit()
        db.refresh(candidate)
    except PoolMemoryError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    values = service.list_candidates(db, limit=300)
    return next(item for item in values if item["id"] == candidate.id)


@router.post(
    "/candidates/{candidate_id}/approve",
    response_model=PoolMemoryArtifactOut,
    status_code=status.HTTP_201_CREATED,
)
def approve_candidate(
    candidate_id: str,
    body: PoolMemoryApproveRequest,
    db: Session = Depends(get_db),
    service: PoolMemoryService = Depends(get_pool_memory_service),
) -> dict:
    try:
        card = service.approve_candidate(
            db,
            _artifact(db, candidate_id),
            review_note=body.review_note,
            confirm_source_authorized=body.confirm_source_authorized,
        )
        db.commit()
        db.refresh(card)
    except PoolMemoryError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    values = service.list_items(db, include_inactive=True, limit=500)
    return next(item for item in values if item["id"] == card.id)


@router.post(
    "/items",
    response_model=PoolMemoryArtifactOut,
    status_code=status.HTTP_201_CREATED,
)
def create_manual_memory(
    body: PoolMemoryManualCreate,
    db: Session = Depends(get_db),
    service: PoolMemoryService = Depends(get_pool_memory_service),
) -> dict:
    try:
        card = service.add_manual_memory(
            db,
            title=body.title,
            dimensions=[str(item) for item in body.dimensions],
            scope=body.scope.model_dump(),
            memory=body.memory.model_dump(),
            usage_policy=body.usage_policy,
            note=body.note,
            confirm_original_or_authorized=body.confirm_original_or_authorized,
        )
        db.commit()
        db.refresh(card)
    except PoolMemoryError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    values = service.list_items(db, include_inactive=True, limit=500)
    return next(item for item in values if item["id"] == card.id)


@router.post(
    "/items/{memory_id}/supersede",
    response_model=PoolMemoryArtifactOut,
    status_code=status.HTTP_201_CREATED,
)
def supersede_memory(
    memory_id: str,
    body: PoolMemorySupersedeRequest,
    db: Session = Depends(get_db),
    service: PoolMemoryService = Depends(get_pool_memory_service),
) -> dict:
    try:
        replacement = service.supersede_memory(
            db,
            _artifact(db, memory_id),
            title=body.title,
            dimensions=[str(item) for item in body.dimensions],
            scope=body.scope.model_dump(),
            memory=body.memory.model_dump(),
            usage_policy=body.usage_policy,
            note=body.note,
            reason=body.reason,
        )
        db.commit()
        db.refresh(replacement)
    except PoolMemoryError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    values = service.list_items(db, include_inactive=True, limit=500)
    return next(item for item in values if item["id"] == replacement.id)


@router.post(
    "/items/{memory_id}/revoke",
    status_code=status.HTTP_201_CREATED,
)
def revoke_memory(
    memory_id: str,
    body: PoolMemoryRevokeRequest,
    db: Session = Depends(get_db),
    service: PoolMemoryService = Depends(get_pool_memory_service),
) -> dict:
    try:
        event = service.revoke_memory(
            db,
            _artifact(db, memory_id),
            reason=body.reason,
        )
        db.commit()
        db.refresh(event)
    except PoolMemoryError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"event_id": event.id, "memory_id": memory_id, "revoked": True}


@router.post("/retrieve-preview", response_model=PoolMemoryRetrievePreview)
def retrieve_preview(
    body: PoolMemoryRetrieveRequest,
    db: Session = Depends(get_db),
    service: PoolMemoryService = Depends(get_pool_memory_service),
) -> dict:
    return service.retrieve_preview(db, body.model_dump())


@router.get("/snapshots", response_model=list[PoolMemorySnapshotOut])
def list_snapshots(
    target_type: str = Query(default="", max_length=60),
    target_id: str = Query(default="", max_length=64),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[PoolMemorySnapshot]:
    query = select(PoolMemorySnapshot)
    if target_type:
        query = query.where(PoolMemorySnapshot.target_type == target_type)
    if target_id:
        query = query.where(PoolMemorySnapshot.target_id == target_id)
    return list(db.scalars(query.order_by(desc(PoolMemorySnapshot.created_at)).limit(limit)).all())


@router.get("/usages", response_model=list[PoolMemoryUsageOut])
def list_usages(
    memory_id: str = Query(default="", max_length=64),
    target_type: str = Query(default="", max_length=60),
    target_id: str = Query(default="", max_length=64),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    service: PoolMemoryService = Depends(get_pool_memory_service),
) -> list[PoolMemoryUsageOut]:
    return service.list_usages(
        db,
        memory_id=memory_id,
        target_type=target_type,
        target_id=target_id,
        limit=limit,
    )
