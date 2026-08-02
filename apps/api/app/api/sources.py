from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.session import get_db
from app.domain.discovery import CandidateState, DiscoveryCandidate
from app.domain.models import (
    Asset,
    CorpusPool,
    CorpusPoolSource,
    RightsStatus,
    SourceItem,
    SourceRelation,
    WorkspaceState,
    utcnow,
)
from app.domain.schemas import (
    RightsUpdateRequest,
    SourceDetail,
    SourceListItem,
    SourceNoteUpdateRequest,
)
from app.services.corpus_pools import CorpusPoolService
from app.services.source_graph import connected_sources

router = APIRouter(prefix="/api/sources", tags=["sources"])


def _source_detail(db: Session, source_id: str) -> SourceDetail:
    source = db.scalar(
        select(SourceItem)
        .options(selectinload(SourceItem.assets))
        .where(SourceItem.id == source_id)
    )
    if source is None:
        raise HTTPException(status_code=404, detail="来源不存在")

    related = [item for item in connected_sources(db, source_id) if item.id != source_id]
    return SourceDetail(
        id=source.id,
        provider=source.provider,
        platform=source.platform,
        external_id=source.external_id,
        canonical_url=source.canonical_url,
        author_handle=source.author_handle,
        author_name=source.author_name,
        author_avatar_url=source.author_avatar_url,
        text_original=source.text_original,
        content_kind=source.content_kind,
        workspace_state=source.workspace_state,
        created_at=source.created_at,
        captured_at=source.captured_at,
        archived_at=source.archived_at,
        last_published_at=source.last_published_at,
        published_count=source.published_count,
        state=source.state,
        rights_status=source.rights_status,
        rights_note=source.rights_note,
        structured_content_json=source.structured_content_json,
        editor_note=source.editor_note,
        metrics_json=source.metrics_json,
        assets=source.assets,
        related=related,
    )


def _pool_ids_for_source(db: Session, source_id: str) -> list[str]:
    return list(
        db.scalars(
            select(CorpusPoolSource.pool_id).where(
                CorpusPoolSource.source_id == source_id
            )
        ).all()
    )


def _recompile_pools(db: Session, pool_ids: list[str]) -> None:
    if not pool_ids:
        return
    service = CorpusPoolService(get_settings())
    for pool_id in dict.fromkeys(pool_ids):
        pool = db.get(CorpusPool, pool_id)
        if pool is not None:
            service.compile_pool(db, pool)


@router.get("", response_model=list[SourceListItem])
def list_sources(
    workspace_state: str = Query(default=WorkspaceState.active.value),
    platform: str = Query(default="", max_length=30),
    provider: str = Query(default="", max_length=40),
    content_kind: str = Query(default="", max_length=40),
    include_pool_batches: bool = Query(default=True),
    limit: int = Query(default=1000, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> list[SourceItem]:
    query = select(SourceItem).order_by(SourceItem.captured_at.desc()).limit(limit)
    if not include_pool_batches:
        query = query.where(SourceItem.provider != "corpus_pool")
    if platform:
        query = query.where(SourceItem.platform == platform)
    if provider:
        query = query.where(SourceItem.provider == provider)
    if content_kind:
        query = query.where(SourceItem.content_kind == content_kind)
    if workspace_state != "all":
        if workspace_state not in {
            WorkspaceState.active.value,
            WorkspaceState.archived.value,
        }:
            raise HTTPException(status_code=400, detail="未知的来源箱状态")
        query = query.where(SourceItem.workspace_state == workspace_state)
    return list(db.scalars(query).all())


@router.post(
    "/from-signal/{candidate_id}",
    response_model=SourceDetail,
    status_code=status.HTTP_201_CREATED,
)
def materialize_signal_candidate(
    candidate_id: str,
    db: Session = Depends(get_db),
) -> SourceDetail:
    candidate = db.get(DiscoveryCandidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="信号候选不存在")
    source = db.scalar(
        select(SourceItem).where(
            SourceItem.platform == "x",
            SourceItem.external_id == candidate.external_id,
        )
    )
    if source is None:
        source = SourceItem(
            provider="signal-studio",
            platform="x",
            external_id=candidate.external_id,
            canonical_url=candidate.canonical_url,
            author_handle=candidate.author_handle,
            author_name=candidate.author_name,
            text_original=candidate.text,
            language="",
            content_kind="post",
            structured_content_json=json.dumps(
                {
                    "source_origin": "signal_studio",
                    "signal_candidate_id": candidate.id,
                    "signal_metadata": json.loads(candidate.metadata_json or "{}"),
                },
                ensure_ascii=False,
            ),
            metrics_json=candidate.metadata_json or "{}",
            rights_status=RightsStatus.needs_review.value,
            rights_note="由信号台 X 候选转入素材库；发布前需人工确认引用范围和媒体版权。",
        )
        db.add(source)
        db.flush()
    candidate.state = CandidateState.imported.value
    db.commit()
    return _source_detail(db, source.id)


@router.get("/{source_id}", response_model=SourceDetail)
def get_source(source_id: str, db: Session = Depends(get_db)) -> SourceDetail:
    return _source_detail(db, source_id)


@router.put("/{source_id}/note", response_model=SourceDetail)
def update_editor_note(
    source_id: str,
    body: SourceNoteUpdateRequest,
    db: Session = Depends(get_db),
) -> SourceDetail:
    source = db.get(SourceItem, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="来源不存在")
    pool_ids = _pool_ids_for_source(db, source_id)
    source.editor_note = body.editor_note.strip()
    db.flush()
    _recompile_pools(db, pool_ids)
    db.commit()
    return _source_detail(db, source_id)


@router.post("/{source_id}/archive", response_model=SourceDetail)
def archive_source(source_id: str, db: Session = Depends(get_db)) -> SourceDetail:
    source = db.get(SourceItem, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="来源不存在")
    source.workspace_state = WorkspaceState.archived.value
    source.archived_at = utcnow()
    db.commit()
    return _source_detail(db, source_id)


@router.post("/{source_id}/restore", response_model=SourceDetail)
def restore_source(source_id: str, db: Session = Depends(get_db)) -> SourceDetail:
    source = db.get(SourceItem, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="来源不存在")
    source.workspace_state = WorkspaceState.active.value
    source.archived_at = None
    db.commit()
    return _source_detail(db, source_id)


@router.delete("/{source_id}", status_code=204)
def delete_source(source_id: str, db: Session = Depends(get_db)) -> None:
    source = db.get(SourceItem, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="来源不存在")
    pool_ids = _pool_ids_for_source(db, source_id)
    db.execute(
        delete(CorpusPoolSource).where(CorpusPoolSource.source_id == source_id)
    )
    db.execute(
        delete(SourceRelation).where(
            or_(
                SourceRelation.from_source_id == source_id,
                SourceRelation.to_source_id == source_id,
            )
        )
    )
    db.delete(source)
    db.flush()
    _recompile_pools(db, pool_ids)
    db.commit()


@router.put("/{source_id}/rights", response_model=SourceDetail)
def update_rights(
    source_id: str,
    body: RightsUpdateRequest,
    db: Session = Depends(get_db),
) -> SourceDetail:
    source = db.get(SourceItem, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="来源不存在")

    sources = connected_sources(db, source_id) if body.apply_to_related else [source]
    source_ids = [item.id for item in sources]
    for item in sources:
        item.rights_status = body.source_status
        item.rights_note = body.source_note.strip()

    if body.asset_status is not None:
        assets = db.scalars(select(Asset).where(Asset.source_id.in_(source_ids))).all()
        for asset in assets:
            asset.rights_status = body.asset_status
            asset.rights_note = body.asset_note.strip()

    db.commit()
    return _source_detail(db, source_id)
