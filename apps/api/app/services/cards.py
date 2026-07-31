from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import CardRender, DraftRevision
from app.services.card_html_renderer import HtmlCardRenderer
from app.services.skills import binding_for

_TEMPLATE_ALIASES = {
    "warm_editorial": "editorial_minimal",
    "dark_tech": "tech_minimal",
    "editorial_minimal": "editorial_minimal",
    "tech_minimal": "tech_minimal",
    "clean_news": "clean_news",
    "warm_note": "warm_note",
}
_SECTION_HEADINGS = {
    "先说结论", "值得关注的 3 个点", "值得关注的3个点", "这对读者有什么用", "阅读提醒",
    "发生了什么", "核心信息", "为什么值得关注", "仍需确认", "我的判断", "判断依据",
    "需要警惕的地方", "给读者的判断框架", "来源与提醒",
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
        self, db: Session, draft: DraftRevision, *, template: str, max_cards: int
    ) -> CardRender:
        resolved_template = _TEMPLATE_ALIASES.get(template)
        if resolved_template is None:
            raise CardRenderError(f"未知卡片模板：{template}")
        storyboard = binding_for(db, "visual.storyboard", self.settings.model_name)
        art_direction = binding_for(db, "visual.art_direction", self.settings.model_name)
        if not art_direction.enabled:
            resolved_template = "clean_news"

        render = CardRender(draft_id=draft.id, template=resolved_template, status="rendering")
        db.add(render)
        db.flush()
        output_dir = self.settings.media_dir / "cards" / render.id
        output_dir.mkdir(parents=True, exist_ok=True)
        specs = self._build_specs(draft, max_cards=max_cards, use_analysis=storyboard.enabled)
        for index, spec in enumerate(specs, start=1):
            spec["page"] = index
            spec["total"] = len(specs)

        try:
            output_paths = self.html_renderer.render_many(output_dir, specs, resolved_template)
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
        self, draft: DraftRevision, *, max_cards: int, use_analysis: bool = True
    ) -> list[dict]:
        max_cards = max(2, min(max_cards, 9))
        source = draft.source
        analysis = self._analysis(draft) if use_analysis else {}
        sections = self._parse_sections(draft.body)
        source_label = self._source_label(
            source.author_name if source else "", source.author_handle if source else ""
        )
        summary = str(analysis.get("one_sentence_summary") or "").strip()
        if not summary:
            summary = self._summary(draft.body)
        specs: list[dict] = [
            {
                "kind": "cover",
                "kicker": self._art_direction(draft, analysis),
                "title": draft.title or "这条 X 内容讲了什么",
                "body": summary,
                "source": source_label,
                "footer": "从来源到判断 · X2RED",
                "hero_image": self._hero_image(draft),
            }
        ]
        recommended = analysis.get("recommended_angle")
        if isinstance(recommended, dict) and recommended.get("name") and len(specs) < max_cards - 1:
            specs.append(
                {
                    "kind": "thesis",
                    "kicker": "EDITORIAL ANGLE",
                    "title": str(recommended.get("name")),
                    "body": str(recommended.get("reason") or summary),
                    "source": source_label,
                    "footer": "先选一个角度，再组织整篇内容",
                }
            )
        facts = self._analysis_values(analysis.get("verified_facts"), "statement")
        if facts and len(specs) < max_cards - 1:
            specs.append(
                {
                    "kind": "facts",
                    "kicker": "SOURCE-BACKED",
                    "title": "来源直接支持的事实",
                    "items": facts[:4],
                    "body": "\n".join(facts[:4]),
                    "source": source_label,
                    "footer": "把事实与作者判断分开",
                }
            )
        uncertainties = self._analysis_values(analysis.get("uncertainties"))
        reserved = 1 + int(bool(uncertainties))
        for section in sections:
            if len(specs) >= max_cards - reserved:
                break
            for chunk in self._chunks(section["body"], 360):
                if len(specs) >= max_cards - reserved:
                    break
                specs.append(
                    {
                        "kind": "content",
                        "kicker": "KEY EXPLAINER",
                        "title": section["heading"],
                        "body": chunk,
                        "source": source_label,
                        "footer": "一页只解决一个问题",
                    }
                )
        if uncertainties and len(specs) < max_cards - 1:
            specs.append(
                {
                    "kind": "caution",
                    "kicker": "CHECK THE BOUNDARY",
                    "title": "这些结论还不能下",
                    "items": uncertainties[:4],
                    "body": "\n".join(uncertainties[:4]),
                    "source": source_label,
                    "footer": "保留不确定性，比强行完整更重要",
                }
            )
        specs.append(
            {
                "kind": "source",
                "kicker": "SOURCE NOTE",
                "title": "回到原文，保留自己的判断",
                "body": source.canonical_url if source else "",
                "source": source_label,
                "footer": "X2RED 本地创作工作台",
            }
        )
        return specs[:max_cards]

    @staticmethod
    def _analysis(draft: DraftRevision) -> dict:
        try:
            provenance = json.loads(draft.provenance_json or "{}")
        except json.JSONDecodeError:
            return {}
        value = provenance.get("editorial_analysis") if isinstance(provenance, dict) else {}
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
    def _source_label(author: str, handle: str) -> str:
        return f"{author}  @{handle}" if author and handle else f"@{handle}" if handle else author or "X 来源"

    @staticmethod
    def _summary(body: str) -> str:
        text = re.sub(r"\s+", " ", body).strip()
        return text if len(text) <= 110 else text[:108].rstrip("，。； ") + "…"

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
            if normalized in _SECTION_HEADINGS or (len(normalized) <= 14 and not re.search(r"[。！？；，：]$", normalized)):
                flush(); heading = normalized
            else:
                values.append(paragraph)
        flush()
        return output or [{"heading": "核心内容", "body": body}]

    @staticmethod
    def _chunks(text: str, limit: int) -> list[str]:
        remaining = text.strip(); output: list[str] = []
        while remaining:
            if len(remaining) <= limit:
                output.append(remaining); break
            cut = max(remaining.rfind(mark, 0, limit) for mark in ("\n\n", "。", "！", "？", "；", "\n"))
            cut = limit if cut < limit // 2 else cut + 1
            output.append(remaining[:cut].strip()); remaining = remaining[cut:].strip()
        return output

    @staticmethod
    def _art_direction(draft: DraftRevision, analysis: dict) -> str:
        text = " ".join(
            [draft.title, draft.body[:1000], str(analysis.get("topic") or "")]
        ).lower()
        if any(token in text for token in ("design", "ui", "ux", "设计", "交互")):
            return "EDITORIAL DESIGN"
        if any(token in text for token in ("ai", "model", "agent", "模型", "智能体")):
            return "AI / PRODUCT"
        if draft.style == "news":
            return "NEWS BRIEF"
        return "EDITORIAL NOTE"

    @staticmethod
    def _hero_image(draft: DraftRevision) -> str:
        source = draft.source
        if source is None:
            return ""
        for asset in source.assets:
            if asset.kind == "image":
                if asset.local_path and Path(asset.local_path).is_file():
                    return asset.local_path
                if asset.remote_url.startswith("https://pbs.twimg.com/"):
                    return asset.remote_url
        return ""

    def _draw_fallback(self, path: Path, spec: dict, template: str) -> None:
        palettes = {
            "editorial_minimal": ("#F4F1ED", "#FFFDF9", "#171719", "#FF375F"),
            "tech_minimal": ("#070A11", "#111827", "#F8FAFC", "#7DD3FC"),
            "clean_news": ("#EEF2F7", "#FFFFFF", "#10213B", "#316FF6"),
            "warm_note": ("#F7F0E8", "#FFFAF4", "#2A211D", "#E86D4C"),
        }
        bg, panel, fg, accent = palettes[template]
        image = Image.new("RGB", (self.width, self.height), bg)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((72, 72, 1170, 1584), radius=48, fill=panel)
        draw.rectangle((72, 72, 88, 1584), fill=accent)
        font = self._font(72, True); body_font = self._font(38, False); meta_font = self._font(24, True)
        draw.text((140, 130), str(spec.get("kicker") or "X2RED"), font=meta_font, fill=accent)
        y = 280
        for line in self._wrap(draw, str(spec.get("title") or ""), font, 910)[:4]:
            draw.text((140, y), line, font=font, fill=fg); y += 96
        y += 35
        values = spec.get("items") if isinstance(spec.get("items"), list) else []
        if values:
            for index, value in enumerate(values[:5], start=1):
                draw.rounded_rectangle((140, y, 1080, y + 150), radius=28, fill=bg)
                draw.text((170, y + 45), f"{index:02d}", font=meta_font, fill=accent)
                line_y = y + 30
                for line in self._wrap(draw, str(value), body_font, 780)[:2]:
                    draw.text((260, line_y), line, font=body_font, fill=fg); line_y += 55
                y += 175
        else:
            for line in self._wrap(draw, str(spec.get("body") or ""), body_font, 900)[:14]:
                draw.text((140, y), line, font=body_font, fill=fg); y += 58
        draw.text((140, 1495), str(spec.get("source") or "X2RED"), font=meta_font, fill=fg)
        image.save(path, format="PNG", optimize=True)

    @staticmethod
    def _font(size: int, bold: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        candidates = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for value in candidates:
            if Path(value).is_file():
                return ImageFont.truetype(value, size=size)
        return ImageFont.load_default()

    @staticmethod
    def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
        lines: list[str] = []; current = ""
        for character in text.replace("\r", ""):
            if character == "\n":
                if current.strip(): lines.append(current.strip())
                current = ""; continue
            candidate = current + character
            if current and draw.textlength(candidate, font=font) > max_width:
                lines.append(current.rstrip()); current = character.lstrip()
            else: current = candidate
        if current.strip(): lines.append(current.strip())
        return lines
