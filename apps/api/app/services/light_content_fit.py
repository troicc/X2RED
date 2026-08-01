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
    source = source_text.strip()
    intent = " ".join((seasonal_topic, audience, feedback)).strip()
    technical = _hits(source, TECHNICAL_PATTERNS)
    source_life = _hits(source, LIFE_PATTERNS)
    source_seasonal = _hits(source, SEASONAL_PATTERNS)
    source_photo = _hits(source, PHOTO_PATTERNS)
    intent_life = _hits(intent, LIFE_PATTERNS)
    intent_seasonal = _hits(intent, SEASONAL_PATTERNS)
    intent_photo = _hits(intent, PHOTO_PATTERNS)

    if technical >= 3 and source_life == 0 and source_seasonal == 0:
        source_kind = "technical"
    elif source_seasonal > 0:
        source_kind = "seasonal_life"
    elif source_life > 0:
        source_kind = "life"
    elif source_photo > 0:
        source_kind = "visual_life"
    else:
        source_kind = "general"

    if recipe == "short_commentary":
        return LightContentFit(
            allowed=True,
            score=0.9 if source_kind == "technical" else 0.78,
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
                "目标读者、语气或修改要求不能改变来源类型。系统已阻止把技术文章强行改成泛鸡汤。"
                "请选择“一句短评”、公众号长文，或更换真正包含生活、人物、节气或照片叙事的来源。"
            ),
            suggested_recipes=("short_commentary",),
        )

    if recipe == "mature_life" and source_life == 0:
        return LightContentFit(
            allowed=False,
            score=0.28,
            source_kind=source_kind,
            reason=(
                "原始来源没有中年、年长读者、家庭、关系、三餐、睡眠或生活经验等材料。"
                "仅在目标读者里填写年龄不能制造来源证据。请换生活类来源，或选择一句短评。"
            ),
            suggested_recipes=("short_commentary", "comfort"),
        )

    if recipe == "comfort" and source_life == 0:
        return LightContentFit(
            allowed=False,
            score=0.35,
            source_kind=source_kind,
            reason=(
                "原始来源没有压力、疲惫、关系、家庭或具体生活处境，无法可靠生成慰藉内容。"
                "系统不会只靠用户填写的语气把无关来源改写成鸡汤。"
            ),
            suggested_recipes=("short_commentary",),
        )

    if recipe == "seasonal" and source_seasonal == 0 and intent_seasonal == 0:
        return LightContentFit(
            allowed=False,
            score=0.25,
            source_kind=source_kind,
            reason=(
                "来源和任务说明里都没有明确节气、物候、换季或时令主题。"
                "请填写具体节气并使用相关生活来源，系统不会借题发挥编造饮食功效。"
            ),
            suggested_recipes=("short_commentary",),
        )

    if recipe == "seasonal" and source_life == 0 and source_seasonal == 0:
        return LightContentFit(
            allowed=False,
            score=0.3,
            source_kind=source_kind,
            reason=(
                "虽然填写了节气主题，但原始来源没有相应的物候、饮食或生活材料。"
                "请换用真正的时令来源；系统不会把无关内容包装成节气文章。"
            ),
            suggested_recipes=("short_commentary",),
        )

    if recipe == "photo_quote" and source_photo == 0:
        return LightContentFit(
            allowed=False,
            score=0.32,
            source_kind=source_kind,
            reason=(
                "原始来源没有照片、影像、人物或可承担叙事的生活场景。"
                "仅在修改要求里描述画面不能替代真实素材，照片短句不会再生成无意义占位方块。"
            ),
            suggested_recipes=("short_commentary", "comfort"),
        )

    score = 0.72
    if recipe == "comfort" and source_life > 0:
        score = 0.88
    elif recipe == "mature_life" and source_life > 0:
        score = 0.9
    elif recipe == "seasonal" and (source_seasonal > 0 or (source_life > 0 and intent_seasonal > 0)):
        score = 0.9
    elif recipe == "photo_quote" and source_photo > 0:
        score = 0.9

    intent_note = ""
    if intent_life > 0 or intent_photo > 0:
        intent_note = " 用户要求会作为编辑方向，但不会被当作来源事实。"
    return LightContentFit(
        allowed=True,
        score=score,
        source_kind=source_kind,
        reason=f"来源与内容配方存在明确语义连接，可以继续策划。{intent_note}",
        suggested_recipes=(recipe, "short_commentary"),
    )
