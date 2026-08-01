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
    default_enabled: bool = True


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
        "xhs.selling_points",
        "卖点优先级",
        "小红书适配",
        "按稀缺性、实用性和可感知性排序，只保留一到两个真正值得上封面的点。",
        "medium",
    ),
    SkillDefinition(
        "xhs.title_formulas",
        "小红书标题公式",
        "小红书适配",
        "按痛点、提问、发现、热点和身份共鸣生成候选标题，再以事实边界过滤。",
        "medium",
    ),
    SkillDefinition(
        "xhs.caption_hashtags",
        "Caption 与标签",
        "小红书适配",
        "从卡片组提炼发布配文和高相关标签，不把 caption 当成长文正文。",
        "low",
    ),
    SkillDefinition(
        "xhs.viral_structure",
        "对标结构与钩子",
        "小红书适配",
        "把信号台和历史模式库中的高表现结构用于选题，而不是照搬具体文案。",
        "high",
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
        "根据内容类型选择 Editorial、Swiss、Knowledge、News 或 Warm 视觉系统。",
        "low",
    ),
    SkillDefinition(
        "visual.material_intake",
        "真实素材盘点",
        "视觉表达",
        "识别对比图、产品截图、数据图和氛围图，优先使用能够证明内容的真实素材。",
        "low",
    ),
    SkillDefinition(
        "visual.layout_selector",
        "Style × Layout 选择",
        "视觉表达",
        "在稀疏、均衡、密集、清单、对比、流程、矩阵等布局中选择最合适结构。",
        "medium",
    ),
    SkillDefinition(
        "visual.palette_selector",
        "配色系统选择",
        "视觉表达",
        "按内容语气选择稳定色板，不让每次生成随机漂移。",
        "low",
    ),
    SkillDefinition(
        "visual.screenshot_treatment",
        "截图与设备框处理",
        "视觉表达",
        "对产品截图使用浏览器框、设备框、裁切和留白，而不是简单铺满画布。",
        "low",
    ),
    SkillDefinition(
        "visual.subject_safe_zone",
        "主体避让与安全区",
        "视觉表达",
        "规划图片主体与文字的安全区域，避免标题压住人脸、产品和关键界面。",
        "medium",
    ),
    SkillDefinition(
        "article.illustration_plan",
        "长文配图规划",
        "跨平台配图",
        "识别真正需要视觉解释的位置，并输出信息图、流程图、对比图或场景图提示。",
        "medium",
    ),
    SkillDefinition(
        "wechat.adapt_longform",
        "公众号长文适配",
        "公众号写作",
        "把同一份证据和终稿重构为公众号长文，不把小红书 caption 直接放大。",
        "high",
    ),
    SkillDefinition(
        "wechat.title_summary",
        "公众号标题与摘要",
        "公众号写作",
        "生成适合公众号列表页和转发场景的标题、摘要与短分享标题。",
        "medium",
    ),
    SkillDefinition(
        "wechat.citations",
        "外链与来源整理",
        "公众号写作",
        "把外部来源整理为文末引用，保留原始 X 链接和证据归属。",
        "low",
    ),
    SkillDefinition(
        "wechat.format_article",
        "公众号内联排版",
        "公众号排版",
        "把 Markdown 转成可复制到公众号编辑器的全内联 HTML。",
        "low",
    ),
    SkillDefinition(
        "wechat.keyword_marking",
        "章节与关键词标记",
        "公众号排版",
        "自动编号章节，并对每段一到三个真正重要的短语做克制强调。",
        "medium",
    ),
    SkillDefinition(
        "wechat.cover_pair",
        "公众号封面对",
        "公众号视觉",
        "生成视觉一致的 21:9 主封面和 1:1 分享封面。",
        "medium",
    ),
    SkillDefinition(
        "wechat.qa",
        "公众号 HTML 质量门",
        "公众号排版",
        "确定性检查禁用标签、危险样式、空内容、图片和标题密度。",
        "low",
    ),
    SkillDefinition(
        "wechat.publish_draft",
        "发布到公众号草稿箱",
        "公众号发布",
        "通过可选的 API 或浏览器适配器写入草稿箱；始终保留人工最终发布。",
        "low",
        False,
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
            enabled=definition.default_enabled,
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
            enabled=definition.default_enabled,
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
