from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import (
    get_job_engine,
    get_signal_service,
    get_writing_service,
)
from app.db.session import get_db
from app.domain.discovery import CandidateState, DiscoveryCandidate
from app.domain.jobs import Job
from app.domain.models import RightsStatus, SourceItem
from app.domain.schemas import JobOut
from app.domain.studio import (
    AnalysisLevel,
    AnalysisStatus,
    ContentAnalysis,
    MonitorTarget,
    PatternCard,
)
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
    SignalPromoteRequest,
    SignalPromoteResult,
)
from app.services.jobs import JobEngine
from app.services.signal_studio import SignalStudioService
from app.services.writing_studio import MultiAgentWritingService

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
        l2 = db.scalar(
            select(ContentAnalysis)
            .where(
                ContentAnalysis.candidate_id == candidate.id,
                ContentAnalysis.level == AnalysisLevel.l2.value,
                ContentAnalysis.status == AnalysisStatus.succeeded.value,
            )
            .order_by(desc(ContentAnalysis.updated_at))
            .limit(1)
        )
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
                "l2_analysis": _json_object(l2.result_json) if l2 else None,
                "l2_analysis_id": l2.id if l2 else "",
                "promoted_source_id": l2.source_id if l2 and l2.source_id else "",
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


@router.post(
    "/candidates/{candidate_id}/promote",
    response_model=SignalPromoteResult,
    status_code=status.HTTP_201_CREATED,
)
def promote_candidate(
    candidate_id: str,
    body: SignalPromoteRequest,
    db: Session = Depends(get_db),
    signal_service: SignalStudioService = Depends(get_signal_service),
    writing_service: MultiAgentWritingService = Depends(get_writing_service),
) -> dict[str, Any]:
    candidate = db.get(DiscoveryCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="候选内容不存在")
    analysis = db.scalar(
        select(ContentAnalysis)
        .where(
            ContentAnalysis.candidate_id == candidate.id,
            ContentAnalysis.level == AnalysisLevel.l2.value,
            ContentAnalysis.status == AnalysisStatus.succeeded.value,
        )
        .order_by(desc(ContentAnalysis.updated_at))
        .limit(1)
    )
    if analysis is None:
        raise HTTPException(status_code=409, detail="请先完成深度拆解，再加入创作台")
    result = _json_object(analysis.result_json)
    l1 = db.scalar(
        select(ContentAnalysis)
        .where(
            ContentAnalysis.candidate_id == candidate.id,
            ContentAnalysis.level == AnalysisLevel.l1.value,
            ContentAnalysis.status == AnalysisStatus.succeeded.value,
        )
        .order_by(desc(ContentAnalysis.updated_at))
        .limit(1)
    )
    source = db.scalar(
        select(SourceItem).where(
            SourceItem.platform == "x",
            SourceItem.external_id == candidate.external_id,
        )
    )
    source_created = source is None
    score = signal_service.latest_score(db, candidate.id)
    structured = {
        "signal_intelligence": {
            "candidate_id": candidate.id,
            "l1_analysis_id": l1.id if l1 else "",
            "l1": _json_object(l1.result_json) if l1 else {},
            "l2_analysis_id": analysis.id,
            "l2": result,
            "score": {
                "grade": score.grade if score else "",
                "label": score.label if score else "",
                "r_value": score.r_value if score else 0,
                "m_value": score.m_value if score else 0,
                "velocity": score.velocity if score else 0,
            },
        }
    }
    if source is None:
        source = SourceItem(
            provider="signal-studio",
            platform="x",
            external_id=candidate.external_id,
            canonical_url=candidate.canonical_url,
            author_handle=candidate.author_handle,
            author_name=candidate.author_name,
            text_original=candidate.text,
            content_kind="post",
            structured_content_json=json.dumps(structured, ensure_ascii=False),
            editor_note=_editor_note(result),
            metrics_json=candidate.metadata_json or "{}",
            rights_status=RightsStatus.needs_review.value,
            rights_note="由信号台候选转入；发布前需要人工确认引用范围与媒体版权。",
        )
        db.add(source)
        db.flush()
    else:
        existing = _json_object(source.structured_content_json)
        existing.update(structured)
        source.structured_content_json = json.dumps(existing, ensure_ascii=False)
        if not source.editor_note.strip():
            source.editor_note = _editor_note(result)
    analysis.source_id = source.id
    if score is not None:
        score.source_id = source.id
    candidate.state = CandidateState.imported.value

    reader = body.reader.strip() or _reader_from_analysis(result)
    promise = body.promise.strip() or _promise_from_analysis(result)
    main_thesis = body.main_thesis.strip() or _thesis_from_analysis(result)
    try:
        project = writing_service.create_project(
            db,
            source=source,
            mode=body.mode,
            reader=reader,
            promise=promise,
            main_thesis=main_thesis,
            style_profile_id=body.style_profile_id,
            budget_limit_cents=body.budget_limit_cents,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(project)
    return {
        "candidate_id": candidate.id,
        "analysis_id": analysis.id,
        "source_id": source.id,
        "project_id": project.id,
        "source_created": source_created,
        "reader": reader,
        "promise": promise,
        "main_thesis": main_thesis,
    }


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


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _list_text(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value:
        if isinstance(item, dict):
            text = str(
                item.get("angle")
                or item.get("name")
                or item.get("description")
                or item.get("trigger")
                or item.get("statement")
                or ""
            ).strip()
        else:
            text = str(item).strip()
        if text:
            output.append(text)
    return output


def _reader_from_analysis(result: dict[str, Any]) -> str:
    triggers = _list_text(result.get("audience_triggers"))
    if triggers:
        return "会被这些问题触发的读者：" + "；".join(triggers[:3])
    return "关注该主题、希望快速理解其现实意义的中文读者"


def _promise_from_analysis(result: dict[str, Any]) -> str:
    angles = _list_text(result.get("writing_angles"))
    if angles:
        return angles[0][:2000]
    hook = str(result.get("hook") or "").strip()
    return f"解释这条信号为什么值得关注，并给出可验证的判断：{hook}"[:2000]


def _thesis_from_analysis(result: dict[str, Any]) -> str:
    hook = str(result.get("hook") or "").strip()
    mechanism = str(result.get("distribution_mechanism") or "").strip()
    if hook and mechanism:
        return f"{hook}；它的传播关键在于：{mechanism}"[:2000]
    return (hook or mechanism or "这条信号值得从来源证据、传播机制和可复制边界重新拆解")[:2000]


def _editor_note(result: dict[str, Any]) -> str:
    angles = _list_text(result.get("writing_angles"))
    risks = _list_text(result.get("fact_risks"))
    lines = []
    if angles:
        lines.append("可写角度：" + "；".join(angles[:3]))
    if risks:
        lines.append("事实风险：" + "；".join(risks[:3]))
    replicable = _list_text(result.get("replicable_elements"))
    if replicable:
        lines.append("可复用表达：" + "；".join(replicable[:3]))
    return "\n".join(lines)[:6000]
