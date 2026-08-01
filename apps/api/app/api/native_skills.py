from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
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
]


class NativeSkillInstallRequest(BaseModel):
    name: NativeSkillName
    install_runtime: bool = True


class MinimalZineRenderRequest(BaseModel):
    regenerate: bool = False


@router.get("")
def list_native_skills() -> dict:
    settings = get_settings()
    manager = NativeSkillManager(settings)
    return {
        "skills": manager.statuses(),
        "image_generation": {
            "configured": MinimalZineNativeService(settings).image_configured,
            "model": settings.image_model,
            "size": settings.image_size,
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
            regenerate=body.regenerate,
        )
        db.commit()
        db.refresh(variant)
        return {
            "variant_id": variant.id,
            "status": variant.status,
            "output_paths_json": variant.output_paths_json,
            "metadata_json": variant.metadata_json,
            "pages": results,
        }
    except NativeSkillError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
