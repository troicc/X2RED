from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.platforms import PlatformVariant
from app.domain.review_artifacts import ReviewArtifact
from app.domain.review_schemas import (
    ReviewApplyResult,
    ReviewArtifactCreate,
    ReviewArtifactDecision,
    ReviewArtifactOut,
    ReviewArtifactUpdate,
    StoryboardRenderRequest,
    StoryboardRenderResult,
    WeChatPublisherPayload,
)
from app.services.review_flow import ReviewFlowError, ReviewFlowService

router = APIRouter(prefix="/api/reviews", tags=["review-edit"])


def _service(request: Request) -> ReviewFlowService:
    return request.app.state.review_flow_service


def _artifact(db: Session, artifact_id: str) -> ReviewArtifact:
    artifact = db.get(ReviewArtifact, artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail="审阅产物不存在")
    return artifact


@router.get("/artifacts", response_model=list[ReviewArtifactOut])
def list_artifacts(
    request: Request,
    scope_type: str = Query(default="", max_length=40),
    scope_id: str = Query(default="", max_length=64),
    artifact_type: str = Query(default="", max_length=60),
    db: Session = Depends(get_db),
) -> list[ReviewArtifact]:
    return _service(request).list_artifacts(
        db,
        scope_type=scope_type,
        scope_id=scope_id,
        artifact_type=artifact_type,
    )


@router.post(
    "/artifacts",
    response_model=ReviewArtifactOut,
    status_code=status.HTTP_201_CREATED,
)
def create_artifact(
    body: ReviewArtifactCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> ReviewArtifact:
    try:
        artifact = _service(request).create(
            db,
            scope_type=body.scope_type,
            scope_id=body.scope_id,
            artifact_type=body.artifact_type,
        )
        db.commit()
        db.refresh(artifact)
        return artifact
    except ReviewFlowError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/artifacts/{artifact_id}", response_model=ReviewArtifactOut)
def get_artifact(
    artifact_id: str,
    db: Session = Depends(get_db),
) -> ReviewArtifact:
    return _artifact(db, artifact_id)


@router.put("/artifacts/{artifact_id}", response_model=ReviewArtifactOut)
def revise_artifact(
    artifact_id: str,
    body: ReviewArtifactUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> ReviewArtifact:
    artifact = _artifact(db, artifact_id)
    try:
        revised = _service(request).revise(
            db,
            artifact,
            payload=body.payload,
            note=body.note,
        )
        db.commit()
        db.refresh(revised)
        return revised
    except ReviewFlowError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/artifacts/{artifact_id}/decision", response_model=ReviewArtifactOut)
def decide_artifact(
    artifact_id: str,
    body: ReviewArtifactDecision,
    request: Request,
    db: Session = Depends(get_db),
) -> ReviewArtifact:
    artifact = _artifact(db, artifact_id)
    try:
        decided = _service(request).decide(
            db,
            artifact,
            decision=body.decision,
            note=body.note,
        )
        db.commit()
        db.refresh(decided)
        return decided
    except ReviewFlowError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/artifacts/{artifact_id}/render-storyboard",
    response_model=StoryboardRenderResult,
)
def render_storyboard(
    artifact_id: str,
    body: StoryboardRenderRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    artifact = _artifact(db, artifact_id)
    try:
        render = _service(request).render_storyboard(
            db,
            artifact,
            template=body.template,
            preview=body.preview,
        )
        db.commit()
        db.refresh(artifact)
        return {
            "artifact": artifact,
            "card_render_id": render.id,
            "output_count": len(json.loads(render.output_paths_json or "[]")),
        }
    except (ReviewFlowError, RuntimeError, json.JSONDecodeError) as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/artifacts/{artifact_id}/apply-wechat-modules",
    response_model=ReviewApplyResult,
)
def apply_wechat_modules(
    artifact_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    artifact = _artifact(db, artifact_id)
    try:
        variant = _service(request).apply_wechat_modules(db, artifact)
        db.commit()
        db.refresh(artifact)
        return {"artifact": artifact, "applied_to_id": variant.id}
    except ReviewFlowError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/artifacts/{artifact_id}/render-wechat-cover",
    response_model=ReviewApplyResult,
)
def render_wechat_cover(
    artifact_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    artifact = _artifact(db, artifact_id)
    try:
        _service(request).render_wechat_cover(db, artifact)
        db.commit()
        db.refresh(artifact)
        return {"artifact": artifact, "applied_to_id": artifact.applied_to_id}
    except ReviewFlowError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/wechat/{variant_id}/publisher-payload",
    response_model=WeChatPublisherPayload,
)
def publisher_payload(
    variant_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    variant = db.get(PlatformVariant, variant_id)
    if variant is None:
        raise HTTPException(status_code=404, detail="公众号版本不存在")
    if not variant.body_html.strip():
        raise HTTPException(status_code=409, detail="请先排版生成公众号 HTML")
    try:
        payload = _service(request).publisher_payload(db, variant)
        payload["body_html"] = re.sub(
            r"<h1\b[^>]*>.*?</h1>",
            "",
            str(payload.get("body_html") or ""),
            count=1,
            flags=re.I | re.S,
        ).strip()
        return payload
    except ReviewFlowError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/wechat-assistant/extension.zip")
def publisher_extension() -> StreamingResponse:
    extension_dir = (
        Path(__file__).resolve().parents[2]
        / "extensions"
        / "wechat-publisher-assistant"
    )
    if not extension_dir.is_dir():
        raise HTTPException(status_code=404, detail="公众号发布助手尚未安装")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(extension_dir.rglob("*")):
            if path.is_file():
                archive.write(path, arcname=path.relative_to(extension_dir))
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                'attachment; filename="x2red-wechat-publisher-assistant.zip"'
            )
        },
    )
