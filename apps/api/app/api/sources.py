from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.domain.models import SourceItem, SourceRelation
from app.domain.schemas import SourceDetail, SourceListItem


router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("", response_model=list[SourceListItem])
def list_sources(db: Session = Depends(get_db)) -> list[SourceItem]:
    return list(db.scalars(select(SourceItem).order_by(SourceItem.captured_at.desc()).limit(200)).all())


@router.get("/{source_id}", response_model=SourceDetail)
def get_source(source_id: str, db: Session = Depends(get_db)) -> SourceDetail:
    source = db.scalar(
        select(SourceItem)
        .options(selectinload(SourceItem.assets))
        .where(SourceItem.id == source_id)
    )
    if source is None:
        raise HTTPException(status_code=404, detail="来源不存在")

    relations = db.scalars(
        select(SourceRelation).where(
            or_(
                SourceRelation.from_source_id == source_id,
                SourceRelation.to_source_id == source_id,
            )
        )
    ).all()
    related_ids = {
        relation.to_source_id if relation.from_source_id == source_id else relation.from_source_id
        for relation in relations
    }
    related = list(db.scalars(select(SourceItem).where(SourceItem.id.in_(related_ids))).all()) if related_ids else []
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
        assets=source.assets,
        related=related,
    )
