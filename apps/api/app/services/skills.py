from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import SkillBinding


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    label: str
    category: str
    description: str
    default_effort: str = "medium"


SKILLS: tuple[SkillDefinition, ...] = (
    SkillDefinition(
        "editorial.analysis",
        "来源分析",
        "理解与选题",
        "拆分来源事实、作者主张、不确定项、读者价值和候选角度。",
        "high",
    ),
    SkillDefinition(
        "writing.draft",
        "中文成稿",
        "内容写作",
        "根据推荐角度完成中文草稿，不逐句翻译原文。",
        "medium",
    ),
    SkillDefinition(
        "writing.de_translate",
        "去翻译味",
        "内容写作",
        "使用中文母语节奏重组表达，同时保持事实和判断边界。",
        "low",
    ),
    SkillDefinition(
        "writing.stronger_insight",
        "增强判断",
        "内容写作",
        "在来源证据允许的范围内强化编辑判断和读者价值。",
        "medium",
    ),
    SkillDefinition(
        "writing.concise",
        "精简正文",
        "内容写作",
        "删除同义重复和机械过渡，压缩信息而不损失事实。",
        "medium",
    ),
    SkillDefinition(
        "writing.rewrite_title",
        "重写标题",
        "内容写作",
        "生成具体、有信息增量且不过度承诺的中文标题。",
        "medium",
    ),
    SkillDefinition(
        "visual.storyboard",
        "卡片故事板",
        "视觉表达",
        "决定页面顺序、每页中心、封面方向和视觉节奏。",
        "medium",
    ),
    SkillDefinition(
        "visual.art_direction",
        "视觉风格选择",
        "视觉表达",
        "根据内容类型选择 Editorial、Tech、News 或 Warm 模板家族。",
        "low",
    ),
)

_SKILL_MAP = {definition.name: definition for definition in SKILLS}


def ensure_bindings(db: Session, default_model_name: str) -> list[SkillBinding]:
    existing = {item.skill_name: item for item in db.scalars(select(SkillBinding)).all()}
    changed = False
    for definition in SKILLS:
        if definition.name in existing:
            continue
        binding = SkillBinding(
            skill_name=definition.name,
            enabled=True,
            model_name=default_model_name,
            reasoning_effort=definition.default_effort,
            prompt_version="v1",
        )
        db.add(binding)
        existing[definition.name] = binding
        changed = True
    if changed:
        db.flush()
    return [existing[definition.name] for definition in SKILLS]


def binding_for(db: Session, skill_name: str, default_model_name: str) -> SkillBinding:
    if skill_name not in _SKILL_MAP:
        raise ValueError(f"未知 Skill：{skill_name}")
    binding = db.scalar(select(SkillBinding).where(SkillBinding.skill_name == skill_name))
    if binding is None:
        definition = _SKILL_MAP[skill_name]
        binding = SkillBinding(
            skill_name=skill_name,
            enabled=True,
            model_name=default_model_name,
            reasoning_effort=definition.default_effort,
            prompt_version="v1",
        )
        db.add(binding)
        db.flush()
    return binding


def definition_for(skill_name: str) -> SkillDefinition:
    definition = _SKILL_MAP.get(skill_name)
    if definition is None:
        raise ValueError(f"未知 Skill：{skill_name}")
    return definition
