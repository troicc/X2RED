from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class LightContentFit:
    allowed: bool
    score: float
    source_kind: str
    reason: str
    suggested_recipes: tuple[str, ...]


TECHNICAL_PATTERNS = (
    r"\bCUDA\b",
    r"\bGPU\b",
    r"\bMCP\b",
    r"\bAPI\b",
    r"\bSDK\b",
    r"\bLLM\b",
    r"\bAI\b",
    r"\bBlender\b",
    r"\bClaude\b",
    r"\bPython\b",
    r"\bJavaScript\b",
    r"\bTransformer\b",
    r"\bTriton\b",
    r"\bBlackwell\b",
    r"模型|推理|内核|算法|框架|代码|编程|架构|吞吐|延迟|显存|算力|接口|插件|渲染|软件|工具",
)

LIFE_PATTERNS = (
    r"生活|日子|工作压力|加班|疲惫|情绪|家庭|父母|孩子|伴侣|关系|睡眠|失眠",
    r"三餐|吃饭|饮食|散步|退休|年纪|中年|老年|照顾自己|独处|心情|焦虑",
)

SEASONAL_PATTERNS = (
    r"节气|立春|雨水|惊蛰|春分|清明|谷雨|立夏|小满|芒种|夏至|小暑|大暑",
    r"立秋|处暑|白露|秋分|寒露|霜降|立冬|小雪|大雪|冬至|小寒|大寒|入伏|三伏|换季|物候",
)

PHOTO_PATTERNS = (
    r"照片|摄影|影像|风景|光影|街道|窗|树影|茶杯|旧椅|月亮|食物|餐桌|人物|肖像",
)


def _hits(text: str, patterns: tuple[str, ...]) -> int:
    return sum(1 for pattern in patterns if re.search(pattern, text, flags=re.I))


def assess_source_fit(
    *,
    source_text: str,
    recipe: str,
    seasonal_topic: str = "",
    audience: str = "",
    feedback: str = "",
) -> LightContentFit:
    combined = " ".join((source_text, seasonal_topic, audience, feedback)).strip()
    technical = _hits(source_text, TECHNICAL_PATTERNS)
    life = _hits(combined, LIFE_PATTERNS)
    seasonal = _hits(combined, SEASONAL_PATTERNS)
    photo = _hits(combined, PHOTO_PATTERNS)

    if technical >= 3 and life == 0:
        source_kind = "technical"
    elif seasonal > 0:
        source_kind = "seasonal_life"
    elif life > 0:
        source_kind = "life"
    elif photo > 0:
        source_kind = "visual_life"
    else:
        source_kind = "general"

    if recipe == "short_commentary":
        return LightContentFit(
            allowed=True,
            score=0.9 if technical else 0.78,
            source_kind=source_kind,
            reason="短评可以围绕原来源的现实矛盾展开，但仍需保留事实边界。",
            suggested_recipes=("short_commentary",),
        )

    if source_kind == "technical":
        label = {
            "comfort": "人生慰藉",
            "mature_life": "中老年生活",
            "seasonal": "节气时令",
            "photo_quote": "照片短句",
        }.get(recipe, recipe)
        return LightContentFit(
            allowed=False,
            score=0.12,
            source_kind=source_kind,
            reason=(
                f"当前来源主要是技术/工具内容，与“{label}”没有可验证的生活语义连接。"
                "系统已阻止把技术文章强行改成泛鸡汤。请选择“一句短评”、公众号长文，"
                "或更换真正包含生活、人物、节气或照片叙事的来源。"
            ),
            suggested_recipes=("short_commentary",),
        )

    if recipe == "mature_life" and life == 0:
        return LightContentFit(
            allowed=False,
            score=0.28,
            source_kind=source_kind,
            reason=(
                "来源没有中年、年长读者、家庭、关系、三餐、睡眠或生活经验等材料。"
                "系统不会凭空编造“中老年共鸣”。请换生活类来源，或选择一句短评。"
            ),
            suggested_recipes=("short_commentary", "comfort"),
        )

    if recipe == "seasonal" and seasonal == 0:
        return LightContentFit(
            allowed=False,
            score=0.25,
            source_kind=source_kind,
            reason=(
                "来源和任务说明里都没有明确节气、物候、换季或时令主题。"
                "请填写具体节气/时令并使用相关生活来源，系统不会借题发挥编造饮食功效。"
            ),
            suggested_recipes=("short_commentary",),
        )

    if recipe == "photo_quote" and photo == 0:
        return LightContentFit(
            allowed=False,
            score=0.32,
            source_kind=source_kind,
            reason=(
                "来源没有照片、影像、人物或可承担叙事的生活场景。"
                "照片短句必须建立在真实图片或明确视觉场景上，不能只画一个无意义占位方块。"
            ),
            suggested_recipes=("short_commentary", "comfort"),
        )

    score = 0.72
    if recipe == "comfort" and life > 0:
        score = 0.88
    elif recipe == "mature_life" and life > 0:
        score = 0.9
    elif recipe == "seasonal" and seasonal > 0:
        score = 0.92
    elif recipe == "photo_quote" and photo > 0:
        score = 0.9

    return LightContentFit(
        allowed=True,
        score=score,
        source_kind=source_kind,
        reason="来源与内容配方存在明确语义连接，可以继续策划。",
        suggested_recipes=(recipe, "short_commentary"),
    )
