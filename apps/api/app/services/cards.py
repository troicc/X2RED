from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import CardRender, DraftRevision
from app.services.card_html_renderer import HtmlCardRenderer
from app.services.publication_safety import public_card_spec, strip_internal_markers
from app.services.skills import binding_for

_TEMPLATE_ALIASES = {
    "warm_editorial": "editorial_minimal",
    "dark_tech": "tech_minimal",
    "editorial_minimal": "editorial_minimal",
    "tech_minimal": "tech_minimal",
    "clean_news": "clean_news",
    "warm_note": "warm_note",
}
_ALLOWED_KINDS = {
    "hero_cover",
    "key_result",
    "concept_diagram",
    "before_after",
    "workflow_flow",
    "key_takeaways",
    "opinion_close",
    "source_note",
}
_SECTION_HEADINGS = {
    "先说结论",
    "值得关注的 3 个点",
    "值得关注的3个点",
    "这对读者有什么用",
    "阅读提醒",
    "发生了什么",
    "核心信息",
    "为什么值得关注",
    "仍需确认",
    "我的判断",
    "判断依据",
    "需要警惕的地方",
    "给读者的判断框架",
    "来源与提醒",
}


class CardRenderError(RuntimeError):
    pass


class CardService:
    width = 1242
    height = 1656

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.html_renderer = HtmlCardRenderer()

    def render(
        self,
        db: Session,
        draft: DraftRevision,
        *,
        template: str,
        max_cards: int,
        **_: Any,
    ) -> CardRender:
        resolved_template = _TEMPLATE_ALIASES.get(template)
        if resolved_template is None:
            raise CardRenderError(f"未知卡片模板：{template}")
        storyboard = binding_for(db, "visual.storyboard", self.settings.model_name)
        art_direction = binding_for(db, "visual.art_direction", self.settings.model_name)
        if not art_direction.enabled:
            resolved_template = "clean_news"

        render = CardRender(
            draft_id=draft.id,
            template=resolved_template,
            status="rendering",
        )
        db.add(render)
        db.flush()
        output_dir = self.settings.media_dir / "cards" / render.id
        output_dir.mkdir(parents=True, exist_ok=True)
        specs = self._build_specs(
            draft,
            max_cards=max_cards,
            use_analysis=storyboard.enabled,
        )
        for index, spec in enumerate(specs, start=1):
            spec["page"] = index
            spec["total"] = len(specs)

        try:
            output_paths = self.html_renderer.render_many(
                output_dir,
                specs,
                resolved_template,
            )
            renderer = "html-playwright"
            if len(output_paths) != len(specs):
                output_paths = []
                renderer = "pillow-fallback"
                for index, spec in enumerate(specs, start=1):
                    path = output_dir / f"{index:02d}.png"
                    self._draw_fallback(path, spec, resolved_template)
                    output_paths.append(str(path.resolve()))
            for spec in specs:
                spec["renderer"] = renderer
            render.spec_json = json.dumps(specs, ensure_ascii=False)
            render.output_paths_json = json.dumps(output_paths, ensure_ascii=False)
            render.status = "rendered"
            render.error = ""
        except Exception as exc:
            render.status = "failed"
            render.error = str(exc)[:1000]
            db.flush()
            raise CardRenderError(str(exc)) from exc
        db.flush()
        return render

    def _build_specs(
        self,
        draft: DraftRevision,
        *,
        max_cards: int,
        use_analysis: bool = True,
    ) -> list[dict[str, Any]]:
        max_cards = max(3, min(max_cards, 9))
        provenance = self._provenance(draft)
        analysis = self._analysis_from_provenance(provenance) if use_analysis else {}
        pack = provenance.get("xhs_skill_pack") if isinstance(provenance, dict) else {}
        pack = pack if isinstance(pack, dict) else {}
        specs = self._storyboard_from_pack(draft, pack, max_cards=max_cards)
        if not specs:
            specs = self._fallback_storyboard(
                draft,
                analysis=analysis,
                pack=pack,
                max_cards=max_cards,
            )
        specs = self._ensure_story_arc(draft, specs, max_cards=max_cards)
        return [public_card_spec(spec) for spec in specs[:max_cards]]

    def _storyboard_from_pack(
        self,
        draft: DraftRevision,
        pack: dict[str, Any],
        *,
        max_cards: int,
    ) -> list[dict[str, Any]]:
        raw_pages = pack.get("card_storyboard")
        if not isinstance(raw_pages, list):
            return []
        source_image = self._hero_image(draft)
        output: list[dict[str, Any]] = []
        for raw in raw_pages[:max_cards]:
            if not isinstance(raw, dict):
                continue
            kind = str(raw.get("kind") or "").strip()
            if kind not in _ALLOWED_KINDS or kind == "source_note":
                continue
            title = self._clean_text(raw.get("title"), 42)
            if not title:
                continue
            items = self._clean_items(raw.get("items"), limit=4, item_limit=92)
            body = self._clean_text(raw.get("subtitle") or raw.get("body"), 220)
            asset_role = str(raw.get("asset_role") or "none")
            output.append(
                {
                    "kind": kind,
                    "kicker": self._clean_text(raw.get("label"), 14)
                    or self._label_for_kind(kind),
                    "title": title,
                    "body": body,
                    "items": items,
                    "hero_image": source_image
                    if asset_role == "source" or (kind == "hero_cover" and source_image)
                    else "",
                    "visual_brief": self._clean_text(raw.get("visual_brief"), 180),
                    "asset_role": asset_role,
                    "content_type": str(pack.get("content_type") or ""),
                }
            )
        return output

    def _fallback_storyboard(
        self,
        draft: DraftRevision,
        *,
        analysis: dict[str, Any],
        pack: dict[str, Any],
        max_cards: int,
    ) -> list[dict[str, Any]]:
        content_type = self._content_type(draft, analysis)
        label = self._content_label(content_type)
        summary = self._clean_text(analysis.get("one_sentence_summary"), 150) or self._summary(
            draft.body,
            150,
        )
        selling_points = self._selling_points(pack)
        if not selling_points:
            selling_points = self._analysis_values(analysis.get("audience_value"))
        facts = self._analysis_values(analysis.get("verified_facts"), "statement")
        sentences = self._meaningful_sentences(draft.body)
        sections = self._parse_sections(draft.body)
        if not selling_points:
            selling_points = sentences[:3]

        hero = self._hero_image(draft)
        pages: list[dict[str, Any]] = [
            {
                "kind": "hero_cover",
                "kicker": label,
                "title": draft.title or "这件事真正改变了什么",
                "body": summary,
                "items": [],
                "hero_image": hero,
                "visual_brief": "优先使用来源主图；标题只表达一个核心判断。",
                "asset_role": "source" if hero else "none",
                "content_type": content_type,
            }
        ]

        result_items = (selling_points or facts or sentences)[:3]
        pages.append(
            {
                "kind": "key_result",
                "kicker": "先看变化",
                "title": self._result_title(content_type),
                "body": summary,
                "items": self._clean_items(result_items, limit=3, item_limit=88),
                "hero_image": "",
                "visual_brief": "用三个短信息块兑现封面承诺，不堆术语。",
                "asset_role": "none",
                "content_type": content_type,
            }
        )

        mechanism = self._mechanism_items(sections, facts, sentences)
        if mechanism and len(pages) < max_cards - 1:
            pages.append(
                {
                    "kind": "concept_diagram",
                    "kicker": "拆开来看",
                    "title": self._mechanism_title(content_type),
                    "body": "",
                    "items": mechanism[:4],
                    "hero_image": "",
                    "visual_brief": "中心概念连接 3-4 个节点；每个节点只保留一个动作或含义。",
                    "asset_role": "diagram",
                    "content_type": content_type,
                }
            )

        comparison = self._comparison_items(draft.body)
        if comparison and len(pages) < max_cards - 1:
            pages.append(
                {
                    "kind": "before_after",
                    "kicker": "变化发生在这里",
                    "title": "过去和现在，差别不只是效率",
                    "body": "",
                    "items": comparison[:4],
                    "hero_image": "",
                    "visual_brief": "左右对照：旧方式与新方式，每侧最多两个要点。",
                    "asset_role": "diagram",
                    "content_type": content_type,
                }
            )
        elif len(pages) < max_cards - 1:
            steps = self._workflow_items(draft.body, sections)
            if steps:
                pages.append(
                    {
                        "kind": "workflow_flow",
                        "kicker": "工作方式",
                        "title": self._workflow_title(content_type),
                        "body": "",
                        "items": steps[:4],
                        "hero_image": "",
                        "visual_brief": "按顺序展示 3-4 个动作，不使用长段正文。",
                        "asset_role": "diagram",
                        "content_type": content_type,
                    }
                )

        takeaways = self._takeaway_items(sections, facts, selling_points, sentences)
        if takeaways and len(pages) < max_cards - 1:
            pages.append(
                {
                    "kind": "key_takeaways",
                    "kicker": "记住这些",
                    "title": "最值得带走的几点",
                    "body": "",
                    "items": takeaways[:4],
                    "hero_image": "",
                    "visual_brief": "四条以内的结论清单；每条都能单独成立。",
                    "asset_role": "none",
                    "content_type": content_type,
                }
            )

        recommended = analysis.get("recommended_angle")
        recommendation = recommended if isinstance(recommended, dict) else {}
        judgment = self._clean_text(
            recommendation.get("thesis") or recommendation.get("reason"),
            220,
        )
        if not judgment:
            judgment = self._closing_judgment(draft.body, summary)
        pages.append(
            {
                "kind": "opinion_close",
                "kicker": "我的判断",
                "title": self._judgment_title(content_type),
                "body": judgment,
                "items": [],
                "hero_image": "",
                "visual_brief": "用一句清晰判断收束，不放免责声明或来源说明。",
                "asset_role": "none",
                "content_type": content_type,
            }
        )
        return pages[:max_cards]

    def _ensure_story_arc(
        self,
        draft: DraftRevision,
        specs: list[dict[str, Any]],
        *,
        max_cards: int,
    ) -> list[dict[str, Any]]:
        if not specs or specs[0].get("kind") != "hero_cover":
            hero = self._hero_image(draft)
            specs.insert(
                0,
                {
                    "kind": "hero_cover",
                    "kicker": self._content_label(self._content_type(draft, {})),
                    "title": draft.title,
                    "body": self._summary(draft.body, 150),
                    "items": [],
                    "hero_image": hero,
                    "visual_brief": "发布封面",
                    "asset_role": "source" if hero else "none",
                },
            )
        if len(specs) < max_cards and not any(
            item.get("kind") == "opinion_close" for item in specs
        ):
            specs.append(
                {
                    "kind": "opinion_close",
                    "kicker": "我的判断",
                    "title": "真正值得关注的是工作方式的变化",
                    "body": self._closing_judgment(draft.body, self._summary(draft.body, 150)),
                    "items": [],
                    "hero_image": "",
                    "visual_brief": "发布收束页",
                    "asset_role": "none",
                }
            )
        return specs[:max_cards]

    @staticmethod
    def _provenance(draft: DraftRevision) -> dict[str, Any]:
        try:
            value = json.loads(draft.provenance_json or "{}")
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _analysis_from_provenance(provenance: dict[str, Any]) -> dict[str, Any]:
        value = provenance.get("editorial_analysis")
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _analysis_values(value: object, field: str = "") -> list[str]:
        if not isinstance(value, list):
            return []
        output: list[str] = []
        for raw in value:
            text = str(raw.get(field) or "") if field and isinstance(raw, dict) else str(raw or "")
            text = re.sub(r"\s+", " ", text).strip()
            if text and text not in output:
                output.append(text)
        return output

    @staticmethod
    def _selling_points(pack: dict[str, Any]) -> list[str]:
        value = pack.get("selling_points")
        if not isinstance(value, list):
            return []
        ranked: list[tuple[float, str]] = []
        for raw in value:
            if isinstance(raw, dict):
                text = re.sub(r"\s+", " ", str(raw.get("text") or "")).strip()
                try:
                    score = float(raw.get("score") or 0)
                except (TypeError, ValueError):
                    score = 0
            else:
                text = re.sub(r"\s+", " ", str(raw or "")).strip()
                score = 0
            if text:
                ranked.append((score, text))
        return [text for _, text in sorted(ranked, reverse=True)]

    @staticmethod
    def _content_type(draft: DraftRevision, analysis: dict[str, Any]) -> str:
        text = " ".join(
            [draft.title, draft.body[:2400], str(analysis.get("topic") or "")]
        ).lower()
        if any(token in text for token in ("cuda", "gpu", "模型", "mcp", "agent", "api", "内核", "推理", "算法", "3d")):
            return "technology"
        if any(token in text for token in ("教程", "步骤", "清单", "怎么做", "方法")):
            return "tutorial"
        if any(token in text for token in ("设计", "ui", "ux", "交互", "视觉")):
            return "design"
        if draft.style == "opinion" or any(token in text for token in ("观点", "判断", "争议", "趋势")):
            return "opinion"
        if draft.style == "news":
            return "news"
        return "explainer"

    @staticmethod
    def _content_label(content_type: str) -> str:
        return {
            "technology": "技术趋势",
            "tutorial": "方法拆解",
            "design": "设计观察",
            "opinion": "趋势判断",
            "news": "新鲜事",
            "explainer": "知识拆解",
        }.get(content_type, "内容拆解")

    @staticmethod
    def _result_title(content_type: str) -> str:
        return {
            "technology": "这件事到底新在哪？",
            "tutorial": "先把结果说清楚",
            "design": "它改变的不是一个按钮",
            "opinion": "先看最重要的变化",
            "news": "发生了什么？",
        }.get(content_type, "先看最重要的变化")

    @staticmethod
    def _mechanism_title(content_type: str) -> str:
        return {
            "technology": "它是怎么做到的？",
            "tutorial": "方法拆成这几步",
            "design": "背后的设计逻辑",
            "opinion": "判断依据在哪里？",
        }.get(content_type, "背后的关键逻辑")

    @staticmethod
    def _workflow_title(content_type: str) -> str:
        if content_type == "technology":
            return "从输入到反馈，流程变了"
        if content_type == "tutorial":
            return "照着这个顺序做"
        return "变化是一步步发生的"

    @staticmethod
    def _judgment_title(content_type: str) -> str:
        return {
            "technology": "真正重要的不是参数，而是闭环",
            "tutorial": "方法好不好，看它是否能复用",
            "design": "值得关注的是职责重新分配",
            "opinion": "我的最终判断",
            "news": "这件事接下来值得看什么",
        }.get(content_type, "我的最终判断")

    @staticmethod
    def _label_for_kind(kind: str) -> str:
        return {
            "hero_cover": "主题",
            "key_result": "先看变化",
            "concept_diagram": "拆开来看",
            "before_after": "前后对比",
            "workflow_flow": "工作方式",
            "key_takeaways": "记住这些",
            "opinion_close": "我的判断",
        }.get(kind, "内容")

    @staticmethod
    def _summary(body: str, limit: int = 150) -> str:
        text = re.sub(r"\s+", " ", body).strip()
        return text if len(text) <= limit else text[: limit - 1].rstrip("，。； ") + "…"

    @staticmethod
    def _clean_text(value: object, limit: int) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        return text if len(text) <= limit else text[: limit - 1].rstrip("，。； ") + "…"

    @classmethod
    def _clean_items(
        cls,
        value: object,
        *,
        limit: int,
        item_limit: int,
    ) -> list[str]:
        if not isinstance(value, list):
            return []
        output: list[str] = []
        for raw in value:
            text = cls._clean_text(raw, item_limit)
            if text and text not in output:
                output.append(text)
            if len(output) >= limit:
                break
        return output

    @staticmethod
    def _meaningful_sentences(body: str) -> list[str]:
        text = re.sub(r"\n+", "。", body)
        output: list[str] = []
        for raw in re.split(r"(?<=[。！？；])", text):
            sentence = re.sub(r"\s+", " ", raw).strip(" -—\n。")
            if 18 <= len(sentence) <= 130 and sentence not in output:
                if sentence in _SECTION_HEADINGS:
                    continue
                output.append(sentence)
        return output

    def _parse_sections(self, body: str) -> list[dict[str, str]]:
        paragraphs = [value.strip() for value in re.split(r"\n\s*\n", body) if value.strip()]
        output: list[dict[str, str]] = []
        heading = "核心内容"
        values: list[str] = []

        def flush() -> None:
            nonlocal values
            if values:
                output.append({"heading": heading, "body": "\n\n".join(values)})
                values = []

        for paragraph in paragraphs:
            normalized = re.sub(r"\s+", " ", paragraph)
            if normalized in _SECTION_HEADINGS or (
                len(normalized) <= 14 and not re.search(r"[。！？；，：]$", normalized)
            ):
                flush()
                heading = normalized
            else:
                values.append(paragraph)
        flush()
        return output or [{"heading": "核心内容", "body": body}]

    @classmethod
    def _mechanism_items(
        cls,
        sections: list[dict[str, str]],
        facts: list[str],
        sentences: list[str],
    ) -> list[str]:
        candidates: list[str] = []
        for section in sections:
            heading = section["heading"]
            if any(token in heading for token in ("怎么", "原理", "机制", "方法", "实现", "核心")):
                candidates.extend(cls._meaningful_sentences(section["body"]))
        candidates.extend(facts)
        candidates.extend(sentences)
        return cls._dedupe(candidates, limit=4, text_limit=90)

    @classmethod
    def _comparison_items(cls, body: str) -> list[str]:
        text = re.sub(r"\s+", " ", body)
        pairs: list[str] = []
        patterns = (
            (r"过去([^。！？]{6,90})[。！？].{0,60}?现在([^。！？]{6,90})", "过去：{}", "现在：{}"),
            (r"从([^。！？]{6,80})到([^。！？]{6,80})", "以前：{}", "现在：{}"),
            (r"不是([^。！？]{6,80})，?而是([^。！？]{6,80})", "不是：{}", "而是：{}"),
        )
        for pattern, left_label, right_label in patterns:
            match = re.search(pattern, text, flags=re.I)
            if match:
                pairs = [
                    left_label.format(match.group(1).strip()),
                    right_label.format(match.group(2).strip()),
                ]
                break
        return cls._dedupe(pairs, limit=4, text_limit=92)

    @classmethod
    def _workflow_items(
        cls,
        body: str,
        sections: list[dict[str, str]],
    ) -> list[str]:
        numbered = []
        for line in body.splitlines():
            match = re.match(r"\s*(?:\d+[.)、]|[-•])\s*(.+)", line)
            if match:
                numbered.append(match.group(1).strip())
        if len(numbered) >= 3:
            return cls._dedupe(numbered, limit=4, text_limit=88)
        candidates: list[str] = []
        for section in sections:
            if any(token in section["heading"] for token in ("流程", "步骤", "怎么", "过程", "工作")):
                candidates.extend(cls._meaningful_sentences(section["body"]))
        if len(candidates) < 3:
            candidates = cls._meaningful_sentences(body)
        return cls._dedupe(candidates, limit=4, text_limit=88)

    @classmethod
    def _takeaway_items(
        cls,
        sections: list[dict[str, str]],
        facts: list[str],
        selling_points: list[str],
        sentences: list[str],
    ) -> list[str]:
        candidates = list(selling_points)
        for section in sections:
            if any(token in section["heading"] for token in ("值得", "影响", "亮点", "总结", "判断")):
                candidates.extend(cls._meaningful_sentences(section["body"]))
        candidates.extend(facts)
        candidates.extend(sentences)
        return cls._dedupe(candidates, limit=4, text_limit=92)

    @classmethod
    def _dedupe(cls, values: list[str], *, limit: int, text_limit: int) -> list[str]:
        output: list[str] = []
        for value in values:
            text = cls._clean_text(value, text_limit)
            if text and text not in output:
                output.append(text)
            if len(output) >= limit:
                break
        return output

    @classmethod
    def _closing_judgment(cls, body: str, fallback: str) -> str:
        sentences = cls._meaningful_sentences(body)
        for sentence in reversed(sentences):
            if any(token in sentence for token in ("真正", "意味着", "值得", "关键", "变化", "判断")):
                return cls._clean_text(sentence, 220)
        return cls._clean_text(sentences[-1] if sentences else fallback, 220)

    @staticmethod
    def _hero_image(draft: DraftRevision) -> str:
        source = draft.source
        if source is None:
            return ""
        for asset in source.assets:
            if asset.kind != "image":
                continue
            if asset.local_path and Path(asset.local_path).is_file():
                return asset.local_path
            if asset.remote_url.startswith("https://pbs.twimg.com/"):
                return asset.remote_url
        return ""

    def _draw_fallback(self, path: Path, spec: dict[str, Any], template: str) -> None:
        palettes = {
            "editorial_minimal": ("#F2F4F7", "#FFFFFF", "#171A21", "#5267F6", "#E9ECF6"),
            "tech_minimal": ("#080B12", "#111827", "#F8FAFC", "#6EE7F9", "#1E293B"),
            "clean_news": ("#EDF2F8", "#FFFFFF", "#10213B", "#316FF6", "#E4EBF5"),
            "warm_note": ("#F7F0E8", "#FFFAF4", "#2A211D", "#E86D4C", "#F1E1D5"),
        }
        bg, panel, fg, accent, soft = palettes[template]
        image = Image.new("RGB", (self.width, self.height), bg)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((58, 58, 1184, 1598), radius=46, fill=panel)
        draw.rounded_rectangle((104, 104, 1138, 1548), radius=34, outline=soft, width=3)
        title_font = self._font(76 if spec.get("kind") == "hero_cover" else 62, True)
        body_font = self._font(34, False)
        meta_font = self._font(23, True)
        label = strip_internal_markers(str(spec.get("kicker") or ""))
        y = 138
        if label:
            draw.rounded_rectangle((132, y, 132 + min(370, 34 + len(label) * 27), y + 52), radius=26, fill=soft)
            draw.text((150, y + 12), label, font=meta_font, fill=accent)
            y += 105
        for line in self._wrap(draw, str(spec.get("title") or ""), title_font, 930)[:4]:
            draw.text((132, y), line, font=title_font, fill=fg)
            y += int(getattr(title_font, "size", 68) * 1.25)
        y += 28
        values = spec.get("items") if isinstance(spec.get("items"), list) else []
        if values:
            for index, value in enumerate(values[:4], start=1):
                height = 170
                draw.rounded_rectangle((132, y, 1110, y + height), radius=28, fill=soft)
                draw.rounded_rectangle((158, y + 48, 218, y + 108), radius=18, fill=accent)
                draw.text((172, y + 62), f"{index}", font=meta_font, fill=panel)
                line_y = y + 34
                for line in self._wrap(draw, str(value), body_font, 800)[:2]:
                    draw.text((250, line_y), line, font=body_font, fill=fg)
                    line_y += 54
                y += height + 22
        else:
            for line in self._wrap(draw, str(spec.get("body") or ""), body_font, 920)[:10]:
                draw.text((132, y), line, font=body_font, fill=fg)
                y += 58
        counter = f"{int(spec.get('page') or 1):02d} / {int(spec.get('total') or 1):02d}"
        draw.text((985, 1488), counter, font=meta_font, fill=accent)
        image.save(path, format="PNG", optimize=True)

    @staticmethod
    def _font(size: int, bold: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        candidates = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
            if bold
            else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for value in candidates:
            if Path(value).is_file():
                return ImageFont.truetype(value, size=size)
        return ImageFont.load_default()

    @staticmethod
    def _wrap(
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.ImageFont,
        max_width: int,
    ) -> list[str]:
        lines: list[str] = []
        current = ""
        for character in text.replace("\r", ""):
            if character == "\n":
                if current.strip():
                    lines.append(current.strip())
                current = ""
                continue
            candidate = current + character
            if current and draw.textlength(candidate, font=font) > max_width:
                lines.append(current.rstrip())
                current = character.lstrip()
            else:
                current = candidate
        if current.strip():
            lines.append(current.strip())
        return lines
