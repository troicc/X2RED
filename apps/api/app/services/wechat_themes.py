from __future__ import annotations

from dataclasses import dataclass

from app.domain.platform_schemas import WeChatThemeOut


@dataclass(frozen=True)
class WeChatTheme:
    id: str
    label: str
    description: str
    suitable_for: tuple[str, ...]
    background: str
    paper: str
    text: str
    muted: str
    accent: str
    accent_soft: str
    rule: str
    quote: str
    code_background: str
    code_text: str
    heading_style: str

    def payload(self) -> WeChatThemeOut:
        return WeChatThemeOut(
            id=self.id,
            label=self.label,
            description=self.description,
            suitable_for=list(self.suitable_for),
            palette={
                "background": self.background,
                "paper": self.paper,
                "text": self.text,
                "muted": self.muted,
                "accent": self.accent,
                "accent_soft": self.accent_soft,
            },
        )


THEMES: tuple[WeChatTheme, ...] = (
    WeChatTheme(
        id="editorial_blue",
        label="编辑蓝",
        description="克制的编辑部蓝色系统，兼顾长文阅读与信息卡片。",
        suitable_for=("教程", "工具盘点", "方法论", "知识整理"),
        background="#F4F7FB",
        paper="#FFFFFF",
        text="#192131",
        muted="#667085",
        accent="#315EFB",
        accent_soft="#EDF2FF",
        rule="#DDE5F5",
        quote="#F2F5FA",
        code_background="#111827",
        code_text="#E5EDFF",
        heading_style="band",
    ),
    WeChatTheme(
        id="vermillion",
        label="朱砂编辑",
        description="强调判断和力量感的朱砂红，适合观点与深度分析。",
        suitable_for=("观点", "深度分析", "行业评论", "人物特稿"),
        background="#FAF7F4",
        paper="#FFFDFC",
        text="#241B18",
        muted="#756660",
        accent="#C63C32",
        accent_soft="#FBECEA",
        rule="#E9D8D2",
        quote="#F8EFEC",
        code_background="#241B18",
        code_text="#FFF5F1",
        heading_style="numbered",
    ),
    WeChatTheme(
        id="graphite",
        label="石墨专业",
        description="高对比灰阶与冷蓝点缀，适合技术、设计和专业评测。",
        suitable_for=("技术", "设计", "专业评测", "产品分析"),
        background="#F5F5F4",
        paper="#FFFFFF",
        text="#18181B",
        muted="#71717A",
        accent="#2563EB",
        accent_soft="#EFF6FF",
        rule="#E4E4E7",
        quote="#F4F4F5",
        code_background="#18181B",
        code_text="#F4F4F5",
        heading_style="minimal",
    ),
    WeChatTheme(
        id="zen",
        label="留白纸本",
        description="低饱和纸色与大留白，适合随笔、叙事和慢阅读。",
        suitable_for=("随笔", "生活观察", "阅读", "叙事"),
        background="#F7F4EE",
        paper="#FFFDF8",
        text="#312C26",
        muted="#81786E",
        accent="#8A6A45",
        accent_soft="#F3ECE1",
        rule="#E8DED1",
        quote="#F6F0E7",
        code_background="#39332C",
        code_text="#F9F4EC",
        heading_style="serif",
    ),
    WeChatTheme(
        id="receipt",
        label="清单票据",
        description="单色票据感和明确编号，适合工具对比、步骤与清单。",
        suitable_for=("工具对比", "清单", "操作指南", "复盘"),
        background="#F6F4EF",
        paper="#FFFEFA",
        text="#20201D",
        muted="#6D6B64",
        accent="#0F766E",
        accent_soft="#E9F6F3",
        rule="#D8D5CC",
        quote="#F1F0EA",
        code_background="#15312E",
        code_text="#ECFDF8",
        heading_style="ticket",
    ),
    WeChatTheme(
        id="olive",
        label="橄榄内刊",
        description="像内部刊物一样沉静，适合案例、复盘、访谈和长评。",
        suitable_for=("案例复盘", "访谈", "内刊", "长评"),
        background="#F1F1E9",
        paper="#FCFCF6",
        text="#292B23",
        muted="#6F7164",
        accent="#66733F",
        accent_soft="#EEF0DF",
        rule="#D9DDC8",
        quote="#F0F1E6",
        code_background="#2C3025",
        code_text="#F5F7EA",
        heading_style="ledger",
    ),
)

_THEME_MAP = {theme.id: theme for theme in THEMES}


def get_theme(theme_id: str) -> WeChatTheme:
    return _THEME_MAP.get(theme_id, _THEME_MAP["editorial_blue"])


def list_theme_payloads() -> list[WeChatThemeOut]:
    return [theme.payload() for theme in THEMES]


def auto_theme(title: str, body: str) -> str:
    text = f"{title} {body[:5000]}".lower()
    if any(token in text for token in ("代码", "gpu", "cuda", "api", "模型", "性能", "设计", "产品")):
        return "graphite"
    if any(token in text for token in ("步骤", "清单", "工具", "对比", "教程", "操作")):
        return "receipt"
    if any(token in text for token in ("我认为", "判断", "争议", "观点", "行业")):
        return "vermillion"
    if any(token in text for token in ("采访", "访谈", "案例", "复盘", "内刊")):
        return "olive"
    if any(token in text for token in ("生活", "阅读", "随笔", "旅行", "感受")):
        return "zen"
    return "editorial_blue"
