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
        "intelligence.l1",
        "爆款快评 L1",
        "情报与选题",
        "对达到评分门槛的候选做低成本归因、时效判断与处理建议。",
        "low",
    ),
    SkillDefinition(
        "intelligence.l2",
        "深度拆解 L2",
        "情报与选题",
        "拆解钩子、结构、受众触发点、可复制要素和不可复制上下文。",
        "high",
    ),
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
        "快速写作",
        "根据推荐角度完成中文草稿，不逐句翻译原文。",
        "medium",
    ),
    SkillDefinition(
        "writing.de_translate",
        "去翻译味",
        "快速写作",
        "使用中文母语节奏重组表达，同时保持事实和判断边界。",
        "low",
    ),
    SkillDefinition(
        "writing.stronger_insight",
        "增强判断",
        "快速写作",
        "在来源证据允许的范围内强化编辑判断和读者价值。",
        "medium",
    ),
    SkillDefinition(
        "writing.concise",
        "精简正文",
        "快速写作",
        "删除同义重复和机械过渡，压缩信息而不损失事实。",
        "medium",
    ),
    SkillDefinition(
        "writing.rewrite_title",
        "重写标题",
        "快速写作",
        "生成具体、有信息增量且不过度承诺的中文标题。",
        "medium",
    ),
    SkillDefinition(
        "writing.style_train",
        "个人风格训练 Agent",
        "风格实验室",
        "从原创样本提炼规则，用留出样本和作者改稿反馈验证并版本化。",
        "high",
    ),
    SkillDefinition(
        "writing.editor",
        "总编辑 Agent",
        "多 Agent 写作",
        "澄清目标读者、文章承诺、唯一主线、必用证据和禁止主张。",
        "high",
    ),
    SkillDefinition(
        "writing.research",
        "证据研究 Agent",
        "多 Agent 写作",
        "构建事实、作者自测、未知项、术语和来源定位清晰的证据包。",
        "high",
    ),
    SkillDefinition(
        "writing.outline",
        "大纲与解释 Agent",
        "多 Agent 写作",
        "按读者认知顺序设计开头、章节职责、术语首次出现和证据分配。",
        "high",
    ),
    SkillDefinition(
        "writing.writer",
        "写手 Agent",
        "多 Agent 写作",
        "严格根据已确认任务单、证据包、大纲与风格规则完成初稿。",
        "medium",
    ),
    SkillDefinition(
        "review.reader",
        "读者代表 Agent",
        "独立审稿",
        "定位第一屏理解障碍、概念过载、数字无解释和读者退出点。",
        "medium",
    ),
    SkillDefinition(
        "review.fact",
        "事实核查 Agent",
        "独立审稿",
        "核查数字、来源归属、局部与整体范围、作者主张与客观事实。",
        "high",
    ),
    SkillDefinition(
        "review.style",
        "风格与去 AI 味 Agent",
        "独立审稿",
        "对照作者规则检查空话、匀速排比、模板转折、讲课味和身份错位。",
        "medium",
    ),
    SkillDefinition(
        "writing.chief_editor",
        "资深主编 Agent",
        "多 Agent 写作",
        "裁决三路审稿意见，形成最小修改计划并保留作者最终决定权。",
        "high",
    ),
    SkillDefinition(
        "writing.final_revision",
        "终稿修订 Agent",
        "多 Agent 写作",
        "只落实获批修改计划，不扩大主张、不自由重写。",
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
