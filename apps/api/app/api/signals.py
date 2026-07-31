from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_job_engine, get_signal_service
from app.db.session import get_db
from app.domain.jobs import Job
from app.domain.schemas import JobOut
from app.domain.studio import ContentAnalysis, MonitorTarget, PatternCard
from app.domain.studio_schemas import (
    AnalysisOut,
    AnalysisRequest,
    MonitorTargetCreate,
    MonitorTargetOut,
    MonitorTargetUpdate,
    PatternCardCreate,
    PatternCardOut,
    SignalDashboard,
    SignalFeedItem,
)
from app.services.jobs import JobEngine
from app.services.signal_studio import SignalStudioService

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("/dashboard", response_model=SignalDashboard)
def dashboard(
    db: Session = Depends(get_db),
    service: SignalStudioService = Depends(get_signal_service),
) -> dict:
    return service.dashboard(db)


@router.get("/targets", response_model=list[MonitorTargetOut])
def list_targets(db: Session = Depends(get_db)) -> list[MonitorTarget]:
    return list(db.scalars(select(MonitorTarget).order_by(MonitorTarget.created_at)).all())


@router.post("/targets", response_model=MonitorTargetOut, status_code=status.HTTP_201_CREATED)
def create_target(
    body: MonitorTargetCreate,
    db: Session = Depends(get_db),
    service: SignalStudioService = Depends(get_signal_service),
) -> MonitorTarget:
    try:
        item = service.create_target(
            db,
            name=body.name,
            kind=body.kind,
            target=body.target,
            interval_minutes=body.interval_minutes,
            enabled=body.enabled,
            config=body.config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(item)
    return item


@router.put("/targets/{target_id}", response_model=MonitorTargetOut)
def update_target(
    target_id: str,
    body: MonitorTargetUpdate,
    db: Session = Depends(get_db),
    service: SignalStudioService = Depends(get_signal_service),
) -> MonitorTarget:
    target = db.get(MonitorTarget, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="监控目标不存在")
    service.update_target(
        target,
        name=body.name,
        interval_minutes=body.interval_minutes,
        enabled=body.enabled,
        config=body.config,
    )
    db.commit()
    db.refresh(target)
    return target


@router.delete("/targets/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_target(target_id: str, db: Session = Depends(get_db)) -> None:
    target = db.get(MonitorTarget, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="监控目标不存在")
    db.delete(target)
    db.commit()


@router.post("/targets/{target_id}/run", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def run_target(
    target_id: str,
    db: Session = Depends(get_db),
    engine: JobEngine = Depends(get_job_engine),
) -> Job:
    if db.get(MonitorTarget, target_id) is None:
        raise HTTPException(status_code=404, detail="监控目标不存在")
    try:
        return engine.enqueue(
            db,
            kind="signal.scan_target",
            payload={"target_id": target_id},
            priority=110,
            max_attempts=3,
            dedupe_key=f"signal.scan_target:{target_id}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/feed", response_model=list[SignalFeedItem])
def feed(
    grade: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    service: SignalStudioService = Depends(get_signal_service),
) -> list[dict]:
    output = []
    for item in service.feed(db, grade=grade, limit=limit):
        candidate = item["candidate"]
        output.append(
            {
                "candidate_id": candidate.id,
                "canonical_url": candidate.canonical_url,
                "author_handle": candidate.author_handle,
                "author_name": candidate.author_name,
                "text": candidate.text,
                "discovered_at": candidate.discovered_at,
                "metadata": item["metadata"],
                "score": item["score"],
                "l1_analysis": item["l1_analysis"],
            }
        )
    return output


@router.post(
    "/candidates/{candidate_id}/analyze",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def analyze_candidate(
    candidate_id: str,
    body: AnalysisRequest,
    db: Session = Depends(get_db),
    engine: JobEngine = Depends(get_job_engine),
) -> Job:
    try:
        return engine.enqueue(
            db,
            kind="signal.analyze",
            payload={"candidate_id": candidate_id, "level": body.level},
            priority=100 if body.level == "l1" else 105,
            max_attempts=2,
            dedupe_key=f"signal.analyze:{candidate_id}:{body.level}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/candidates/{candidate_id}/analyses", response_model=list[AnalysisOut])
def list_analyses(candidate_id: str, db: Session = Depends(get_db)) -> list[ContentAnalysis]:
    return list(
        db.scalars(
            select(ContentAnalysis)
            .where(ContentAnalysis.candidate_id == candidate_id)
            .order_by(desc(ContentAnalysis.updated_at))
        ).all()
    )


@router.get("/patterns", response_model=list[PatternCardOut])
def list_patterns(db: Session = Depends(get_db)) -> list[PatternCard]:
    return list(db.scalars(select(PatternCard).order_by(desc(PatternCard.updated_at))).all())


@router.post("/patterns", response_model=PatternCardOut, status_code=status.HTTP_201_CREATED)
def create_pattern(body: PatternCardCreate, db: Session = Depends(get_db)) -> PatternCard:
    item = PatternCard(
        name=body.name.strip(),
        category=body.category.strip() or "general",
        source_ids_json=json.dumps(body.source_ids, ensure_ascii=False),
        hook_pattern=body.hook_pattern.strip(),
        structure_pattern=body.structure_pattern.strip(),
        audience_trigger=body.audience_trigger.strip(),
        evidence_pattern=body.evidence_pattern.strip(),
        replicable_elements_json=json.dumps(body.replicable_elements, ensure_ascii=False),
        non_replicable_context_json=json.dumps(body.non_replicable_context, ensure_ascii=False),
        suitable_topics_json=json.dumps(body.suitable_topics, ensure_ascii=False),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
