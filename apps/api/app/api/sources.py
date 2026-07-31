from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.domain.models import Asset, SourceItem
from app.domain.schemas import RightsUpdateRequest, SourceDetail, SourceListItem
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
        external_id=source.external_id,
        canonical_url=source.canonical_url,
        author_handle=source.author_handle,
        author_name=source.author_name,
        text_original=source.text_original,
        created_at=source.created_at,
        captured_at=source.captured_at,
        state=source.state,
        rights_status=source.rights_status,
        rights_note=source.rights_note,
        assets=source.assets,
        related=related,
    )


@router.get("", response_model=list[SourceListItem])
def list_sources(db: Session = Depends(get_db)) -> list[SourceItem]:
    return list(db.scalars(select(SourceItem).order_by(SourceItem.captured_at.desc()).limit(200)).all())


@router.get("/{source_id}", response_model=SourceDetail)
def get_source(source_id: str, db: Session = Depends(get_db)) -> SourceDetail:
    return _source_detail(db, source_id)


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
