from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, delete, or_, select
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
    SourceWorkbench,
    SourceWorkbenchState,
    WorkspaceState,
    utcnow,
)
from app.domain.schemas import (
    ManualSourceCreateRequest,
    RightsUpdateRequest,
    SourceDetail,
    SourceListItem,
    SourceNoteUpdateRequest,
)
from app.services.corpus_pools import CorpusPoolService
from app.services.source_graph import connected_sources
from app.services.source_workbenches import (
    set_source_workbench_state,
    source_workbench_state_value,
)

router = APIRouter(prefix="/api/sources", tags=["sources"])


def _source_list_item(
    source: SourceItem,
    workbench_state: str = WorkspaceState.active.value,
) -> SourceListItem:
    return SourceListItem.model_validate(source).model_copy(
        update={"workbench_state": workbench_state}
    )


def _source_detail(
    db: Session,
    source_id: str,
    workbench: SourceWorkbench | None = None,
) -> SourceDetail:
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
        workbench_state=source_workbench_state_value(
            db,
            source.id,
            workbench,
        ),
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
    workbench: SourceWorkbench | None = Query(default=None),
    workbench_state: WorkspaceState | None = Query(default=None),
    platform: str = Query(default="", max_length=30),
    provider: str = Query(default="", max_length=40),
    content_kind: str = Query(default="", max_length=40),
    include_pool_batches: bool = Query(default=True),
    limit: int = Query(default=1000, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> list[SourceListItem]:
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
    if workbench_state is not None and workbench is None:
        raise HTTPException(
            status_code=400,
            detail="指定工作台归档状态时必须同时指定工作台",
        )
    effective_workbench_state = (
        workbench_state or WorkspaceState.active
        if workbench is not None
        else None
    )
    if workbench is not None:
        query = query.outerjoin(
            SourceWorkbenchState,
            and_(
                SourceWorkbenchState.source_id == SourceItem.id,
                SourceWorkbenchState.workbench == workbench.value,
            ),
        )
        if effective_workbench_state is WorkspaceState.active:
            query = query.where(
                or_(
                    SourceWorkbenchState.id.is_(None),
                    SourceWorkbenchState.state == WorkspaceState.active.value,
                )
            )
        elif effective_workbench_state is WorkspaceState.archived:
            query = query.where(
                SourceWorkbenchState.state == WorkspaceState.archived.value
            )
    sources = list(db.scalars(query).unique().all())
    states: dict[str, str] = {}
    if workbench is not None and sources:
        source_ids = [source.id for source in sources]
        states = {
            record.source_id: record.state
            for record in db.scalars(
                select(SourceWorkbenchState).where(
                    SourceWorkbenchState.source_id.in_(source_ids),
                    SourceWorkbenchState.workbench == workbench.value,
                )
            ).all()
        }
    return [
        _source_list_item(
            source,
            states.get(source.id, WorkspaceState.active.value),
        )
        for source in sources
    ]


@router.post(
    "/manual",
    response_model=SourceDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_manual_source(
    body: ManualSourceCreateRequest,
    db: Session = Depends(get_db),
) -> SourceDetail:
    text_original = re.sub(r"\r\n?", "\n", body.text_original).strip()
    if len(text_original) < 20:
        raise HTTPException(status_code=400, detail="粘贴内容至少需要 20 个字符")

    canonical_url = body.canonical_url.strip()
    if canonical_url:
        parsed = urlparse(canonical_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(status_code=400, detail="原文链接必须是 http 或 https 地址")

    normalized = re.sub(r"\s+", " ", text_original).strip()
    fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    external_id = f"manual-{fingerprint[:48]}"
    source = db.scalar(
        select(SourceItem).where(
            SourceItem.platform == "web",
            SourceItem.external_id == external_id,
        )
    )
    if source is None:
        title = body.title.strip() or normalized[:80].rstrip("，。；： ") or "手工粘贴来源"
        source = SourceItem(
            provider="manual",
            platform="web",
            external_id=external_id,
            canonical_url=canonical_url,
            author_name=body.author_name.strip(),
            text_original=text_original,
            language="zh-CN",
            created_at=utcnow(),
            content_kind="article",
            structured_content_json=json.dumps(
                {
                    "title": title,
                    "source_origin": "manual_paste",
                    "content_sha256": fingerprint,
                },
                ensure_ascii=False,
            ),
            rights_status=RightsStatus.needs_review.value,
            rights_note="由用户手工粘贴进入素材库；发布前需人工确认事实、引用范围和版权。",
        )
        db.add(source)
        db.flush()
    elif source.workspace_state == WorkspaceState.archived.value:
        source.workspace_state = WorkspaceState.active.value
        source.archived_at = None

    db.commit()
    return _source_detail(db, source.id)


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
def get_source(
    source_id: str,
    workbench: SourceWorkbench | None = Query(default=None),
    db: Session = Depends(get_db),
) -> SourceDetail:
    return _source_detail(db, source_id, workbench)


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


@router.post(
    "/{source_id}/workbenches/{workbench}/archive",
    response_model=SourceDetail,
)
def archive_source_in_workbench(
    source_id: str,
    workbench: SourceWorkbench,
    db: Session = Depends(get_db),
) -> SourceDetail:
    source = db.get(SourceItem, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="来源不存在")
    set_source_workbench_state(
        db,
        source_id,
        workbench,
        WorkspaceState.archived,
    )
    db.commit()
    return _source_detail(db, source_id, workbench)


@router.post(
    "/{source_id}/workbenches/{workbench}/restore",
    response_model=SourceDetail,
)
def restore_source_in_workbench(
    source_id: str,
    workbench: SourceWorkbench,
    db: Session = Depends(get_db),
) -> SourceDetail:
    source = db.get(SourceItem, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="来源不存在")
    set_source_workbench_state(
        db,
        source_id,
        workbench,
        WorkspaceState.active,
    )
    db.commit()
    return _source_detail(db, source_id, workbench)


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
    db.execute(
        delete(SourceWorkbenchState).where(
            SourceWorkbenchState.source_id == source_id
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
