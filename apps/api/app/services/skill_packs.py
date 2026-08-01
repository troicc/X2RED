from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.platform_schemas import SkillPackOut
from app.services.skills import binding_for


@dataclass(frozen=True)
class SkillPackDefinition:
    id: str
    label: str
    platform: str
    description: str
    source_repositories: tuple[str, ...]
    licenses: tuple[str, ...]
    integration_mode: str
    skills: tuple[str, ...]
    external_skill_names: tuple[str, ...] = ()
    notes: str = ""


PACKS: tuple[SkillPackDefinition, ...] = (
    SkillPackDefinition(
        id="xhs-editorial-growth",
        label="小红书选题与表达增强",
        platform="xiaohongshu",
        description="卖点排序、五类标题、发布配文、对标结构和去翻译味组合。",
        source_repositories=(
            "JuneYaooo/xhs-writer-skill",
            "JuneYaooo/social-account-doctor",
        ),
        licenses=("Apache-2.0", "MIT"),
        integration_mode="native-adaptation",
        skills=(
            "xhs.selling_points",
            "xhs.title_formulas",
            "xhs.caption_hashtags",
            "xhs.viral_structure",
            "writing.de_translate",
        ),
        external_skill_names=("xhs-writer-skill", "social-account-doctor"),
        notes="吸收可复用方法与流程，输出仍受 X2RED 的证据边界和多 Agent 审稿约束。",
    ),
    SkillPackDefinition(
        id="xhs-style-layout-matrix",
        label="小红书 Style × Layout 视觉矩阵",
        platform="xiaohongshu",
        description="将视觉风格、信息布局、色板和内容类型拆成独立维度组合。",
        source_repositories=("JimLiu/baoyu-skills",),
        licenses=("MIT",),
        integration_mode="native-adaptation",
        skills=(
            "visual.storyboard",
            "visual.art_direction",
            "visual.layout_selector",
            "visual.palette_selector",
        ),
        external_skill_names=("baoyu-xhs-images",),
        notes="使用 X2RED 自有 HTML/CSS 渲染器，不依赖运行时 Agent 图片工具。",
    ),
    SkillPackDefinition(
        id="material-first-social-design",
        label="真实素材优先的社交视觉",
        platform="multi",
        description="素材盘点、截图包壳、主体避让、安全区和公众号封面对。",
        source_repositories=("op7418/guizang-social-card-skill",),
        licenses=("AGPL-3.0",),
        integration_mode="independent-reimplementation",
        skills=(
            "visual.material_intake",
            "visual.screenshot_treatment",
            "visual.subject_safe_zone",
            "wechat.cover_pair",
        ),
        external_skill_names=("guizang-social-card-skill",),
        notes="只吸收公开方法论与能力边界；未复制 AGPL 模板、脚本、样式或资产。",
    ),
    SkillPackDefinition(
        id="article-illustration-planner",
        label="长文配图规划",
        platform="multi",
        description="按文章结构识别真正需要配图的位置，区分信息图、流程、对比和场景图。",
        source_repositories=("JimLiu/baoyu-skills",),
        licenses=("MIT",),
        integration_mode="native-adaptation",
        skills=("article.illustration_plan", "visual.material_intake"),
        external_skill_names=("baoyu-article-illustrator",),
        notes="首版输出可复用的配图 brief；真实生图后端可继续独立接入。",
    ),
    SkillPackDefinition(
        id="wechat-editorial-adapter",
        label="公众号长文编辑适配",
        platform="wechat",
        description="从同一证据和终稿生成公众号文章、摘要、短分享标题和文末来源。",
        source_repositories=(
            "JimLiu/baoyu-skills",
            "doocs/md",
        ),
        licenses=("MIT", "WTFPL-2.0"),
        integration_mode="native-adaptation",
        skills=(
            "wechat.adapt_longform",
            "wechat.title_summary",
            "wechat.citations",
            "article.illustration_plan",
        ),
        external_skill_names=("baoyu-markdown-to-html",),
        notes="公众号稿与小红书稿分开生成，不做简单扩写或直接复用 caption。",
    ),
    SkillPackDefinition(
        id="wechat-inline-design-system",
        label="公众号内联排版与质量门",
        platform="wechat",
        description="章节编号、关键词强调、六套主题、内联 HTML、预览复制和确定性校验。",
        source_repositories=("isjiamu/gzh-design-skill",),
        licenses=("AGPL-3.0",),
        integration_mode="independent-reimplementation",
        skills=(
            "wechat.format_article",
            "wechat.keyword_marking",
            "wechat.cover_pair",
            "wechat.qa",
        ),
        external_skill_names=("gzh-design", "gzh-design-skill"),
        notes="独立实现公众号平台约束与主题系统；未复制 AGPL 组件库、模板或校验脚本。",
    ),
    SkillPackDefinition(
        id="wechat-draft-publisher",
        label="公众号草稿箱适配器",
        platform="wechat",
        description="为后续 API/CDP 草稿箱写入保留标准接口，默认关闭并保留人工发布。",
        source_repositories=("JimLiu/baoyu-skills",),
        licenses=("MIT",),
        integration_mode="optional-adapter",
        skills=("wechat.publish_draft",),
        external_skill_names=("baoyu-post-to-wechat",),
        notes="本版本先输出经过校验的 HTML 与发布包；凭据和草稿箱写入必须显式启用。",
    ),
)

_PACK_MAP = {pack.id: pack for pack in PACKS}


def definition_for(pack_id: str) -> SkillPackDefinition:
    pack = _PACK_MAP.get(pack_id)
    if pack is None:
        raise ValueError(f"未知 Skill Pack：{pack_id}")
    return pack


def _candidate_roots() -> tuple[Path, ...]:
    home = Path.home()
    return (
        home / ".claude" / "skills",
        home / ".codex" / "skills",
        home / ".openclaw" / "skills",
    )


def installed_paths(pack: SkillPackDefinition) -> list[str]:
    output: list[str] = []
    for root in _candidate_roots():
        for name in pack.external_skill_names:
            candidate = root / name
            if (candidate / "SKILL.md").is_file():
                output.append(str(candidate))
    return output


def pack_payloads(db: Session, settings: Settings) -> list[SkillPackOut]:
    output: list[SkillPackOut] = []
    for pack in PACKS:
        bindings = [binding_for(db, name, settings.model_name) for name in pack.skills]
        output.append(
            SkillPackOut(
                id=pack.id,
                label=pack.label,
                platform=pack.platform,
                description=pack.description,
                source_repositories=list(pack.source_repositories),
                licenses=list(pack.licenses),
                integration_mode=pack.integration_mode,
                skills=list(pack.skills),
                enabled=all(binding.enabled for binding in bindings),
                installed_paths=installed_paths(pack),
                notes=pack.notes,
            )
        )
    return output


def set_pack_enabled(
    db: Session,
    settings: Settings,
    *,
    pack_id: str,
    enabled: bool,
) -> SkillPackOut:
    pack = definition_for(pack_id)
    for skill_name in pack.skills:
        binding = binding_for(db, skill_name, settings.model_name)
        binding.enabled = enabled
    db.flush()
    return next(item for item in pack_payloads(db, settings) if item.id == pack_id)
