from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.domain.schemas import SkillBindingOut, SkillBindingUpdate
from app.services.skills import binding_for, definition_for, ensure_bindings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/skills", response_model=list[SkillBindingOut])
def list_skills(db: Session = Depends(get_db)) -> list[SkillBindingOut]:
    settings = get_settings()
    bindings = ensure_bindings(db, settings.model_name)
    db.commit()
    output: list[SkillBindingOut] = []
    for binding in bindings:
        definition = definition_for(binding.skill_name)
        output.append(
            SkillBindingOut(
                skill_name=binding.skill_name,
                label=definition.label,
                category=definition.category,
                description=definition.description,
                enabled=binding.enabled,
                model_name=binding.model_name or settings.model_name,
                reasoning_effort=binding.reasoning_effort,
                prompt_version=binding.prompt_version,
            )
        )
    return output


@router.put("/skills/{skill_name}", response_model=SkillBindingOut)
def update_skill(
    skill_name: str,
    body: SkillBindingUpdate,
    db: Session = Depends(get_db),
) -> SkillBindingOut:
    settings = get_settings()
    try:
        binding = binding_for(db, skill_name, settings.model_name)
        definition = definition_for(skill_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    binding.enabled = body.enabled
    binding.model_name = body.model_name.strip() or settings.model_name
    binding.reasoning_effort = body.reasoning_effort
    binding.prompt_version = body.prompt_version.strip() or "v1"
    db.commit()
    db.refresh(binding)
    return SkillBindingOut(
        skill_name=binding.skill_name,
        label=definition.label,
        category=definition.category,
        description=definition.description,
        enabled=binding.enabled,
        model_name=binding.model_name or settings.model_name,
        reasoning_effort=binding.reasoning_effort,
        prompt_version=binding.prompt_version,
    )
