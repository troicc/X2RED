from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.domain.platforms import PlatformVariant
from app.services.minimal_zine_native import MinimalZineNativeService
from app.services.native_skill_manager import NATIVE_SKILLS, NativeSkillError, NativeSkillManager

router = APIRouter(prefix="/api/native-skills", tags=["native-skills"])

NativeSkillName = Literal[
    "guizang-social-card-skill",
    "gc-minimal-zine-poster-v0-1",
    "gc-minimal-zine-poster-v0-3",
]


class NativeSkillInstallRequest(BaseModel):
    name: NativeSkillName
    install_runtime: bool = True


class MinimalZineRenderRequest(BaseModel):
    """Keep legacy regenerate clients while exposing page-granular render modes."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["render_missing", "recompose", "regenerate"] | None = None
    pages: list[int] | None = Field(default=None, max_length=6)
    regenerate: bool = False

    @field_validator("pages")
    @classmethod
    def validate_requested_pages(cls, values: list[int] | None) -> list[int] | None:
        if values is None:
            return None
        if len(set(values)) != len(values):
            raise ValueError("pages 不能包含重复页码")
        if any(value < 1 for value in values):
            raise ValueError("pages 必须从第 1 页开始")
        return values

    @model_validator(mode="after")
    def validate_legacy_precedence(self) -> MinimalZineRenderRequest:
        if self.mode is not None and self.regenerate:
            raise ValueError("显式 mode 与 regenerate=true 不能同时使用")
        return self


class MinimalZineWebHandoffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pages: list[int] | None = Field(default=None, max_length=6)
    force_recompile: bool = False

    @field_validator("pages")
    @classmethod
    def validate_requested_pages(cls, values: list[int] | None) -> list[int] | None:
        if values is None:
            return None
        if len(set(values)) != len(values):
            raise ValueError("pages 不能包含重复页码")
        if any(value < 1 for value in values):
            raise ValueError("pages 必须从第 1 页开始")
        return values


class ImageCandidateReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(pattern=r"^imgcand_[a-f0-9]{24}$")
    action: Literal["keep", "reject", "approve"]
    reason: str = Field(default="", max_length=600)


class ImageCandidateSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(pattern=r"^imgcand_[a-f0-9]{24}$")


class ImageCandidateRepairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(pattern=r"^imgcand_[a-f0-9]{24}$")


@router.get("")
def list_native_skills() -> dict:
    settings = get_settings()
    manager = NativeSkillManager(settings)
    native_service = MinimalZineNativeService(settings)
    return {
        "skills": manager.statuses(),
        "image_generation": {
            "configured": native_service.image_configured,
            "model": settings.image_model,
            "size": settings.image_size,
            "candidate_mode": settings.image_candidate_mode,
            "candidate_count": settings.image_candidate_count,
            "capabilities": native_service.model.image_capabilities().model_dump(
                mode="json"
            ),
            "auto_repair_limit": 1,
        },
        "policy": {
            "upstream_checkouts_are_separate": True,
            "licenses_preserved": True,
            "guizang_source_offer": NATIVE_SKILLS["guizang-social-card-skill"].repository.removesuffix(".git"),
        },
    }


@router.post("/install")
def install_native_skill(body: NativeSkillInstallRequest) -> dict:
    manager = NativeSkillManager(get_settings())
    try:
        manager.install(body.name, install_runtime=body.install_runtime)
        return manager.status(body.name)
    except NativeSkillError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/minimal-zine/variants/{variant_id}/render")
def render_minimal_zine_variant(
    variant_id: str,
    body: MinimalZineRenderRequest,
    db: Session = Depends(get_db),
) -> dict:
    variant = db.get(PlatformVariant, variant_id)
    if variant is None:
        raise HTTPException(status_code=404, detail="平台版本不存在")
    service = MinimalZineNativeService(get_settings())
    try:
        variant, results = service.render_variant(
            db,
            variant,
            mode=body.mode,
            pages=body.pages,
            regenerate=body.regenerate,
        )
        db.commit()
        db.refresh(variant)
        return {
            "variant_id": variant.id,
            "status": variant.status,
            "output_paths_json": variant.output_paths_json,
            "metadata_json": variant.metadata_json,
            "mode": body.mode or ("regenerate" if body.regenerate else "render_missing"),
            "pages": results,
        }
    except NativeSkillError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/minimal-zine/variants/{variant_id}/web-handoff")
def prepare_minimal_zine_web_handoff(
    variant_id: str,
    body: MinimalZineWebHandoffRequest,
    db: Session = Depends(get_db),
) -> dict:
    variant = db.get(PlatformVariant, variant_id)
    if variant is None:
        raise HTTPException(status_code=404, detail="平台版本不存在")
    try:
        result = MinimalZineNativeService(get_settings()).prepare_web_handoff(
            variant,
            pages=body.pages,
            force_recompile=body.force_recompile,
        )
        db.commit()
        return result
    except NativeSkillError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/minimal-zine/variants/{variant_id}/external-anchor")
async def import_minimal_zine_external_anchor(
    variant_id: str,
    page: int = Query(..., ge=1, le=6),
    files: list[UploadFile] = File(..., alias="file"),
    db: Session = Depends(get_db),
) -> dict:
    variant = db.get(PlatformVariant, variant_id)
    if variant is None:
        raise HTTPException(status_code=404, detail="平台版本不存在")
    service = MinimalZineNativeService(get_settings())
    try:
        if not 1 <= len(files) <= 4:
            raise NativeSkillError("手工网页路径每页必须上传 1 到 4 张图片")
        payloads = [await file.read(12 * 1024 * 1024 + 1) for file in files]
        variant, result, complete = service.import_external_anchor(
            db,
            variant,
            page=page,
            image_candidates=payloads,
            provider="chatgpt-web",
        )
        db.commit()
        db.refresh(variant)
        return {
            "variant_id": variant.id,
            "status": variant.status,
            "output_paths_json": variant.output_paths_json,
            "metadata_json": variant.metadata_json,
            "provider": "chatgpt-web",
            "api_used": False,
            "complete": complete,
            "pages": [result],
        }
    except NativeSkillError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        for file in files:
            await file.close()


@router.post("/minimal-zine/variants/{variant_id}/candidates/{page}/review")
def review_minimal_zine_image_candidate(
    variant_id: str,
    page: int,
    body: ImageCandidateReviewRequest,
    db: Session = Depends(get_db),
) -> dict:
    variant = db.get(PlatformVariant, variant_id)
    if variant is None:
        raise HTTPException(status_code=404, detail="平台版本不存在")
    service = MinimalZineNativeService(get_settings())
    try:
        result = service.review_image_candidate(
            db,
            variant,
            page=page,
            candidate_id=body.candidate_id,
            action=body.action,
            reason=body.reason,
        )
        db.commit()
        db.refresh(variant)
        return result
    except NativeSkillError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/minimal-zine/variants/{variant_id}/candidates/{page}/select")
def select_minimal_zine_image_candidate(
    variant_id: str,
    page: int,
    body: ImageCandidateSelectionRequest,
    db: Session = Depends(get_db),
) -> dict:
    variant = db.get(PlatformVariant, variant_id)
    if variant is None:
        raise HTTPException(status_code=404, detail="平台版本不存在")
    try:
        variant, result = MinimalZineNativeService(
            get_settings()
        ).select_image_candidate(
            db,
            variant,
            page=page,
            candidate_id=body.candidate_id,
        )
        db.commit()
        db.refresh(variant)
        return result
    except NativeSkillError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/minimal-zine/variants/{variant_id}/candidates/{page}/repair")
def repair_minimal_zine_image_candidate(
    variant_id: str,
    page: int,
    body: ImageCandidateRepairRequest,
    db: Session = Depends(get_db),
) -> dict:
    variant = db.get(PlatformVariant, variant_id)
    if variant is None:
        raise HTTPException(status_code=404, detail="平台版本不存在")
    try:
        variant, result = MinimalZineNativeService(
            get_settings()
        ).repair_image_candidate(
            db,
            variant,
            page=page,
            candidate_id=body.candidate_id,
        )
        db.commit()
        db.refresh(variant)
        return result
    except NativeSkillError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
