from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_discovery_service, get_job_engine
from app.db.session import get_db
from app.domain.discovery import DiscoveryCandidate
from app.domain.discovery_schemas import (
    CandidateImportRequest,
    CandidateOut,
    CandidateStateRequest,
    DiscoveryQuotesRequest,
    DiscoveryResult,
    DiscoverySearchRequest,
    DiscoveryTimelineRequest,
    DiscoveryTrendsRequest,
)
from app.domain.jobs import Job
from app.domain.schemas import JobOut
from app.services.discovery import DiscoveryService
from app.services.jobs import JobEngine

router = APIRouter(prefix="/api/discovery", tags=["discovery"])


@router.post("/search", response_model=DiscoveryResult)
async def search_posts(
    body: DiscoverySearchRequest,
    db: Session = Depends(get_db),
    service: DiscoveryService = Depends(get_discovery_service),
) -> DiscoveryResult:
    try:
        return await service.search(
            db,
            query=body.query,
            feed=body.feed,
            count=body.count,
            cursor=body.cursor,
            language=body.language,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"搜索失败：{exc}") from exc


@router.post("/timeline", response_model=DiscoveryResult)
async def profile_timeline(
    body: DiscoveryTimelineRequest,
    db: Session = Depends(get_db),
    service: DiscoveryService = Depends(get_discovery_service),
) -> DiscoveryResult:
    try:
        return await service.timeline(
            db,
            handle=body.handle,
            count=body.count,
            cursor=body.cursor,
            since=body.since,
            media_only=body.media_only,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"时间线读取失败：{exc}") from exc


@router.post("/quotes", response_model=DiscoveryResult)
async def quotes(
    body: DiscoveryQuotesRequest,
    db: Session = Depends(get_db),
    service: DiscoveryService = Depends(get_discovery_service),
) -> DiscoveryResult:
    try:
        return await service.quotes(
            db,
            post_id=body.post_id,
            count=body.count,
            cursor=body.cursor,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"引用列表读取失败：{exc}") from exc


@router.post("/trends", response_model=DiscoveryResult)
async def trends(
    body: DiscoveryTrendsRequest,
    db: Session = Depends(get_db),
    service: DiscoveryService = Depends(get_discovery_service),
) -> DiscoveryResult:
    try:
        return await service.trends(db, count=body.count)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"趋势读取失败：{exc}") from exc


@router.get("/profile/{handle}")
async def profile(
    handle: str,
    db: Session = Depends(get_db),
    service: DiscoveryService = Depends(get_discovery_service),
) -> dict:
    try:
        return await service.profile(db, handle=handle)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"账号资料读取失败：{exc}") from exc


@router.get("/candidates", response_model=list[CandidateOut])
def list_candidates(
    candidate_state: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> list[DiscoveryCandidate]:
    query = select(DiscoveryCandidate)
    if candidate_state:
        query = query.where(DiscoveryCandidate.state == candidate_state)
    query = query.order_by(DiscoveryCandidate.updated_at.desc()).limit(max(1, min(limit, 500)))
    return list(db.scalars(query).all())


@router.patch("/candidates/{candidate_id}", response_model=CandidateOut)
def update_candidate_state(
    candidate_id: str,
    body: CandidateStateRequest,
    db: Session = Depends(get_db),
) -> DiscoveryCandidate:
    candidate = db.get(DiscoveryCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="候选不存在")
    candidate.state = body.state
    db.commit()
    db.refresh(candidate)
    return candidate


@router.post(
    "/candidates/{candidate_id}/import",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def import_candidate(
    candidate_id: str,
    body: CandidateImportRequest,
    db: Session = Depends(get_db),
    engine: JobEngine = Depends(get_job_engine),
) -> Job:
    candidate = db.get(DiscoveryCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="候选不存在")
    if not candidate.external_id.isdigit():
        raise HTTPException(status_code=400, detail="趋势候选需要先搜索并选择具体 Post")
    return engine.enqueue_intake(
        db,
        post_id=candidate.external_id,
        mode=body.mode,
        download_media=body.download_media,
        candidate_id=candidate.id,
    )
