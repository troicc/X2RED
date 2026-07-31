from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_editorial_service
from app.db.session import get_db
from app.domain.models import DraftRevision, ReviewDecision, SourceItem
from app.domain.schemas import (
    DraftGenerateRequest,
    DraftOut,
    DraftUpdateRequest,
    ReviewRequest,
)
from app.services.editorial import EditorialService

router = APIRouter(prefix="/api", tags=["drafts"])


@router.post("/sources/{source_id}/drafts", response_model=DraftOut)
async def generate_draft(
    source_id: str,
    body: DraftGenerateRequest,
    db: Session = Depends(get_db),
    service: EditorialService = Depends(get_editorial_service),
) -> DraftRevision:
    source = db.get(SourceItem, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="来源不存在")
    draft = await service.generate(db, source, body.style)
    db.commit()
    db.refresh(draft)
    return draft


@router.get("/sources/{source_id}/drafts", response_model=list[DraftOut])
def list_drafts(source_id: str, db: Session = Depends(get_db)) -> list[DraftRevision]:
    return list(
        db.scalars(
            select(DraftRevision)
            .where(DraftRevision.source_id == source_id)
            .order_by(DraftRevision.version.desc())
        ).all()
    )


@router.put("/drafts/{draft_id}", response_model=DraftOut)
def revise_draft(
    draft_id: str,
    body: DraftUpdateRequest,
    db: Session = Depends(get_db),
    service: EditorialService = Depends(get_editorial_service),
) -> DraftRevision:
    draft = db.get(DraftRevision, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="草稿不存在")
    revised = service.revise(
        db,
        draft,
        title=body.title,
        body=body.body,
        tags=body.tags,
    )
    db.commit()
    db.refresh(revised)
    return revised


@router.post("/drafts/{draft_id}/review")
def review_draft(
    draft_id: str,
    body: ReviewRequest,
    db: Session = Depends(get_db),
) -> dict:
    draft = db.get(DraftRevision, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="草稿不存在")
    decision = ReviewDecision(
        draft_id=draft.id,
        decision=body.decision,
        reason=body.reason,
    )
    db.add(decision)
    db.commit()
    return {"id": decision.id, "decision": decision.decision}
