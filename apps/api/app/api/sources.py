from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.domain.models import Asset, SourceItem, SourceRelation, WorkspaceState, utcnow
from app.domain.schemas import (
    RightsUpdateRequest,
    SourceDetail,
    SourceListItem,
    SourceNoteUpdateRequest,
)
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
    return SourceDetail.model_validate(
        source,
        update={"assets": source.assets, "related": related},
    )


@router.get("", response_model=list[SourceListItem])
def list_sources(
    workspace_state: str = Query(default=WorkspaceState.active.value),
    db: Session = Depends(get_db),
) -> list[SourceItem]:
    query = select(SourceItem).order_by(SourceItem.captured_at.desc()).limit(300)
    if workspace_state != "all":
        if workspace_state not in {WorkspaceState.active.value, WorkspaceState.archived.value}:
            raise HTTPException(status_code=400, detail="未知的来源箱状态")
        query = query.where(SourceItem.workspace_state == workspace_state)
    return list(db.scalars(query).all())


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
    source.editor_note = body.editor_note.strip()
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
    db.execute(
        delete(SourceRelation).where(
            or_(
                SourceRelation.from_source_id == source_id,
                SourceRelation.to_source_id == source_id,
            )
        )
    )
    db.delete(source)
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
