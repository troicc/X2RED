from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_card_service
from app.db.session import get_db
from app.domain.models import CardRender, DraftRevision
from app.domain.schemas import CardGenerateRequest, CardRenderOut
from app.services.cards import CardRenderError, CardService

router = APIRouter(prefix="/api", tags=["cards"])


@router.post("/drafts/{draft_id}/cards", response_model=CardRenderOut)
def generate_cards(
    draft_id: str,
    body: CardGenerateRequest,
    db: Session = Depends(get_db),
    service: CardService = Depends(get_card_service),
) -> CardRender:
    draft = db.get(DraftRevision, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="草稿不存在")
    try:
        render = service.render(
            db,
            draft,
            template=body.template,
            visual_style=body.visual_style,
            layout=body.layout,
            palette=body.palette,
            material_strategy=body.material_strategy,
            max_cards=body.max_cards,
        )
        db.commit()
        db.refresh(render)
        return render
    except CardRenderError as exc:
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/drafts/{draft_id}/cards", response_model=list[CardRenderOut])
def list_cards(draft_id: str, db: Session = Depends(get_db)) -> list[CardRender]:
    return list(
        db.scalars(
            select(CardRender)
            .where(CardRender.draft_id == draft_id)
            .order_by(CardRender.created_at.desc())
        ).all()
    )


@router.get("/cards/{render_id}/files/{index}")
def card_file(render_id: str, index: int, db: Session = Depends(get_db)) -> FileResponse:
    render = db.get(CardRender, render_id)
    if render is None:
        raise HTTPException(status_code=404, detail="卡片渲染不存在")
    try:
        paths = json.loads(render.output_paths_json or "[]")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="卡片记录损坏") from exc
    if not isinstance(paths, list) or index < 0 or index >= len(paths):
        raise HTTPException(status_code=404, detail="卡片文件不存在")
    path = Path(str(paths[index])).resolve()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="卡片文件已丢失")
    return FileResponse(path, media_type="image/png", filename=path.name)
