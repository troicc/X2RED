from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import CardRender, DraftRevision

_TEMPLATES = {
    "warm_editorial": {
        "background": "#F4EFEA",
        "panel": "#FFFDFC",
        "foreground": "#20191B",
        "accent": "#E94B68",
        "accent2": "#F5A65B",
        "muted": "#7B6D70",
        "soft": "#F7E5E9",
        "shadow": "#DED4CF",
        "line": "#E8DFDB",
    },
    "dark_tech": {
        "background": "#080B12",
        "panel": "#111725",
        "foreground": "#F7F8FC",
        "accent": "#79E6FF",
        "accent2": "#A988FF",
        "muted": "#9AA7BC",
        "soft": "#1D2638",
        "shadow": "#03050A",
        "line": "#29344A",
    },
    "clean_news": {
        "background": "#E9EFF7",
        "panel": "#FCFDFE",
        "foreground": "#101E34",
        "accent": "#356DF3",
        "accent2": "#16A085",
        "muted": "#64728A",
        "soft": "#E6EEFF",
        "shadow": "#CED8E7",
        "line": "#DCE4F0",
    },
}

_SECTION_HEADINGS = {
    "先说结论",
    "值得关注的 3 个点",
    "值得关注的3个点",
    "这对读者有什么用",
    "这意味着什么",
    "阅读提醒",
    "发生了什么",
    "核心信息",
    "为什么值得关注",
    "仍需确认",
    "我的判断",
    "判断依据",
    "需要警惕的地方",
    "给读者的判断框架",
    "留给读者的问题",
    "来源与提醒",
}

_SAFE_MEDIA_RIGHTS = {"owned", "licensed", "open_license"}


class CardRenderError(RuntimeError):
    pass


class CardService:
    width = 1242
    height = 1656
    margin = 104

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def render(
        self,
        db: Session,
        draft: DraftRevision,
        *,
        template: str,
        max_cards: int,
    ) -> CardRender:
        if template not in _TEMPLATES:
            raise CardRenderError(f"未知卡片模板：{template}")
        render = CardRender(draft_id=draft.id, template=template, status="rendering")
        db.add(render)
        db.flush()

        output_dir = self.settings.media_dir / "cards" / render.id
        output_dir.mkdir(parents=True, exist_ok=True)
        specs = self._build_specs(draft, max_cards=max_cards)
        total = len(specs)
        for index, spec in enumerate(specs, start=1):
            spec["page"] = index
            spec["total"] = total

        output_paths: list[str] = []
        try:
            for index, spec in enumerate(specs, start=1):
                path = output_dir / f"{index:02d}.png"
                self._draw_card(path, spec, template)
                output_paths.append(str(path.resolve()))
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

    def _build_specs(self, draft: DraftRevision, *, max_cards: int) -> list[dict]:
        max_cards = max(2, min(max_cards, 9))
        title = re.sub(r"\s+", " ", draft.title).strip() or "这条 X 内容讲了什么"
        source = draft.source
        handle = source.author_handle if source else ""
        author = source.author_name if source else ""
        source_label = self._source_label(author, handle)
        analysis = self._analysis(draft)
        sections = self._parse_sections(draft.body)
        summary = str(analysis.get("one_sentence_summary") or "").strip()
        if not summary:
            summary = self._cover_summary(sections, draft.body)
        hero_image = self._hero_image(draft)
        art_direction = self._art_direction(draft, analysis)

        specs: list[dict] = [
            {
                "kind": "cover",
                "kicker": art_direction,
                "title": title,
                "body": summary,
                "source": source_label,
                "footer": "X2RED · 从来源到判断",
                "hero_image": hero_image,
            }
        ]

        recommended = analysis.get("recommended_angle")
        if isinstance(recommended, dict) and (recommended.get("name") or recommended.get("reason")):
            specs.append(
                {
                    "kind": "thesis",
                    "kicker": "EDITORIAL ANGLE",
                    "title": str(recommended.get("name") or "这篇内容的切入点"),
                    "body": str(recommended.get("reason") or summary),
                    "source": source_label,
                    "footer": "先选角度，再组织信息",
                }
            )

        facts = self._analysis_statements(analysis.get("verified_facts"))
        if facts and len(specs) < max_cards - 1:
            specs.append(
                {
                    "kind": "facts",
                    "kicker": "SOURCE-BACKED",
                    "title": "来源直接支持的事实",
                    "items": facts[:3],
                    "body": "\n".join(facts[:3]),
                    "source": source_label,
                    "footer": "事实与作者判断分开呈现",
                }
            )

        reserved = 1
        uncertainties = self._analysis_strings(analysis.get("uncertainties"))
        if uncertainties:
            reserved += 1
        for section in sections:
            if len(specs) >= max_cards - reserved:
                break
            for chunk in self._chunk_text(section["body"], 420):
                if len(specs) >= max_cards - reserved:
                    break
                specs.append(
                    {
                        "kind": "content",
                        "kicker": self._style_kicker(draft.style),
                        "title": section["heading"],
                        "body": chunk,
                        "source": source_label,
                        "footer": "一页只讲清一个问题",
                    }
                )

        if uncertainties and len(specs) < max_cards - 1:
            specs.append(
                {
                    "kind": "caution",
                    "kicker": "CHECK THE BOUNDARY",
                    "title": "这些结论还不能下",
                    "items": uncertainties[:3],
                    "body": "\n".join(uncertainties[:3]),
                    "source": source_label,
                    "footer": "保留不确定性，比强行完整更重要",
                }
            )

        specs.append(
            {
                "kind": "source",
                "kicker": "SOURCE NOTE",
                "title": "信息有出处，判断留边界",
                "body": (
                    f"来源：{source_label}\n\n"
                    "这组卡片基于已归档的 X 原帖与上下文整理。涉及数字、日期、效果和因果关系时，"
                    "请回到原帖并结合公开资料复核。"
                ),
                "source": source.canonical_url if source else "",
                "footer": "收藏的是线索，不是未经核实的结论",
            }
        )
        return specs[:max_cards]

    @staticmethod
    def _analysis(draft: DraftRevision) -> dict:
        try:
            provenance = json.loads(draft.provenance_json or "{}")
        except json.JSONDecodeError:
            return {}
        analysis = provenance.get("editorial_analysis") if isinstance(provenance, dict) else {}
        return analysis if isinstance(analysis, dict) else {}

    @staticmethod
    def _analysis_statements(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        items: list[str] = []
        for raw in value:
            text = str(raw.get("statement") or "") if isinstance(raw, dict) else str(raw or "")
            text = re.sub(r"\s+", " ", text).strip()
            if text and text not in items:
                items.append(text)
        return items

    @staticmethod
    def _analysis_strings(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for raw in value:
            text = str(raw or "").strip()
            if text and text not in result:
                result.append(text)
        return result

    @staticmethod
    def _style_kicker(style: str) -> str:
        return {
            "news": "NEWS BRIEF",
            "opinion": "EDITOR'S NOTE",
            "explain": "KEY EXPLAINER",
        }.get(style, "X2RED EDITORIAL")

    @staticmethod
    def _source_label(author: str, handle: str) -> str:
        if author and handle:
            return f"{author}  @{handle}"
        if handle:
            return f"@{handle}"
        return author or "X 原帖"

    def _art_direction(self, draft: DraftRevision, analysis: dict) -> str:
        haystack = " ".join(
            [
                draft.title,
                draft.body[:1000],
                str(analysis.get("topic") or ""),
            ]
        ).lower()
        if any(token in haystack for token in ("ui", "ux", "design", "设计", "交互", "界面")):
            return "DESIGN SIGNAL"
        if any(token in haystack for token in ("ai", "model", "agent", "大模型", "智能体")):
            return "AI / TECH BRIEF"
        if draft.style == "opinion":
            return "EDITORIAL OBSERVATION"
        if draft.style == "news":
            return "CURRENT SIGNAL"
        return "X2RED EXPLAINER"

    @staticmethod
    def _hero_image(draft: DraftRevision) -> str:
        source = draft.source
        if source is None:
            return ""
        for asset in source.assets:
            if (
                asset.kind == "image"
                and asset.state == "ready"
                and asset.local_path
                and asset.rights_status in _SAFE_MEDIA_RIGHTS
                and Path(asset.local_path).is_file()
            ):
                return asset.local_path
        return ""

    def _parse_sections(self, body: str) -> list[dict[str, str]]:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", body) if part.strip()]
        sections: list[dict[str, str]] = []
        current_heading = "核心内容"
        current_parts: list[str] = []

        def flush() -> None:
            nonlocal current_parts
            text = "\n\n".join(current_parts).strip()
            if text:
                sections.append({"heading": current_heading, "body": text})
            current_parts = []

        for paragraph in paragraphs:
            normalized = re.sub(r"\s+", " ", paragraph).strip()
            is_heading = normalized in _SECTION_HEADINGS or (
                len(normalized) <= 16
                and "\n" not in paragraph
                and not re.search(r"[。！？!?；;，,：:]$", normalized)
                and not re.match(r"^[•·\-—\d①②③④⑤⑥⑦⑧⑨1-9]", normalized)
            )
            if is_heading:
                flush()
                current_heading = normalized
            else:
                current_parts.append(paragraph)
        flush()

        if not sections:
            chunks = self._chunk_text(body, 420)
            sections = [
                {"heading": f"核心要点 {index:02d}", "body": chunk}
                for index, chunk in enumerate(chunks, start=1)
            ]
        return sections

    @staticmethod
    def _cover_summary(sections: list[dict[str, str]], body: str) -> str:
        candidate = sections[0]["body"] if sections else body
        candidate = re.sub(r"^[•·\-—\s]+", "", candidate)
        candidate = re.sub(r"\s+", " ", candidate).strip()
        if len(candidate) <= 105:
            return candidate
        cut = max(candidate.rfind(mark, 0, 105) for mark in ("。", "！", "？", "；", "，", ","))
        if cut < 55:
            cut = 105
        else:
            cut += 1
        return candidate[:cut].rstrip("，,；; ") + "…"

    @staticmethod
    def _chunk_text(text: str, limit: int) -> list[str]:
        normalized = re.sub(r"[ \t]+", " ", text).strip()
        if len(normalized) <= limit:
            return [normalized]
        chunks: list[str] = []
        remaining = normalized
        while remaining:
            if len(remaining) <= limit:
                chunks.append(remaining)
                break
            cut = max(
                remaining.rfind(mark, 0, limit)
                for mark in ("\n\n", "。", "！", "？", "；", "\n")
            )
            if cut < limit // 2:
                cut = limit
            else:
                cut += 2 if remaining[cut : cut + 2] == "\n\n" else 1
            chunks.append(remaining[:cut].strip())
            remaining = remaining[cut:].strip()
        return chunks

    def _draw_card(self, path: Path, spec: dict, template: str) -> None:
        palette = _TEMPLATES[template]
        image = Image.new("RGB", (self.width, self.height), palette["background"])
        draw = ImageDraw.Draw(image)
        self._draw_background(draw, palette, spec)
        self._draw_panel(draw, palette)

        kind = spec.get("kind")
        if kind == "cover":
            self._draw_cover(image, draw, spec, palette)
        elif kind == "source":
            self._draw_source(draw, spec, palette)
        elif kind in {"facts", "caution"}:
            self._draw_list(draw, spec, palette, caution=kind == "caution")
        elif kind == "thesis":
            self._draw_thesis(draw, spec, palette)
        else:
            self._draw_content(draw, spec, palette)

        self._draw_footer(draw, spec, palette)
        image.save(path, format="PNG", optimize=True)

    def _draw_background(self, draw: ImageDraw.ImageDraw, palette: dict, spec: dict) -> None:
        draw.ellipse((-210, -190, 280, 300), fill=palette["accent"])
        draw.ellipse((self.width - 230, 30, self.width + 190, 450), fill=palette["accent2"])
        if spec.get("kind") != "cover":
            draw.ellipse(
                (self.width - 170, self.height - 250, self.width + 150, self.height + 70),
                fill=palette["soft"],
            )

    def _draw_panel(self, draw: ImageDraw.ImageDraw, palette: dict) -> None:
        panel_box = (62, 62, self.width - 62, self.height - 62)
        shadow_box = (74, 84, self.width - 50, self.height - 40)
        draw.rounded_rectangle(shadow_box, radius=58, fill=palette["shadow"])
        draw.rounded_rectangle(panel_box, radius=58, fill=palette["panel"])

    def _draw_cover(
        self,
        image: Image.Image,
        draw: ImageDraw.ImageDraw,
        spec: dict,
        palette: dict,
    ) -> None:
        self._draw_top_meta(draw, spec, palette)
        hero = str(spec.get("hero_image") or "")
        has_hero = bool(hero and Path(hero).is_file())
        if has_hero:
            self._paste_hero(image, hero, (self.margin, 760, self.width - self.margin, 1320))

        title = str(spec.get("title") or "")
        title_size = 100 if len(title) <= 14 else 86 if len(title) <= 22 else 74
        title_font = self._font(title_size, bold=True)
        title_lines = self._wrap(draw, title, title_font, self.width - self.margin * 2)
        y = 270
        for line in title_lines[:4]:
            draw.text((self.margin, y), line, font=title_font, fill=palette["foreground"])
            y += int(title_size * 1.23)

        y += 30
        draw.rounded_rectangle(
            (self.margin, y, self.margin + 180, y + 12),
            radius=6,
            fill=palette["accent"],
        )
        y += 50

        body = str(spec.get("body") or "")
        body_font = self._font(40)
        max_body_y = 700 if has_hero else 1240
        for line in self._wrap(draw, body, body_font, self.width - self.margin * 2 - 10)[:5]:
            if y > max_body_y:
                break
            draw.text((self.margin, y), line, font=body_font, fill=palette["muted"])
            y += 58

        source_font = self._font(28)
        draw.text(
            (self.margin, 1362 if has_hero else self.height - 260),
            str(spec.get("source") or "X 原帖"),
            font=source_font,
            fill=palette["muted"],
        )

    def _paste_hero(self, canvas: Image.Image, path: str, box: tuple[int, int, int, int]) -> None:
        left, top, right, bottom = box
        target_w = right - left
        target_h = bottom - top
        with Image.open(path) as raw:
            hero = raw.convert("RGB")
            scale = max(target_w / hero.width, target_h / hero.height)
            resized = hero.resize(
                (max(1, int(hero.width * scale)), max(1, int(hero.height * scale))),
                Image.Resampling.LANCZOS,
            )
            crop_left = max(0, (resized.width - target_w) // 2)
            crop_top = max(0, (resized.height - target_h) // 2)
            cropped = resized.crop((crop_left, crop_top, crop_left + target_w, crop_top + target_h))
            cropped = ImageEnhance.Contrast(cropped).enhance(0.94)
            cropped = ImageEnhance.Color(cropped).enhance(0.86)
            mask = Image.new("L", (target_w, target_h), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rounded_rectangle((0, 0, target_w, target_h), radius=38, fill=255)
            shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            shadow_draw = ImageDraw.Draw(shadow)
            shadow_draw.rounded_rectangle(
                (left + 8, top + 16, right + 8, bottom + 16),
                radius=38,
                fill=(0, 0, 0, 48),
            )
            shadow = shadow.filter(ImageFilter.GaussianBlur(12))
            canvas.paste(shadow.convert("RGB"), (0, 0), shadow.getchannel("A"))
            canvas.paste(cropped, (left, top), mask)

    def _draw_thesis(self, draw: ImageDraw.ImageDraw, spec: dict, palette: dict) -> None:
        self._draw_top_meta(draw, spec, palette)
        label_font = self._font(28, bold=True)
        draw.text((self.margin, 270), "推荐切入点", font=label_font, fill=palette["accent"])
        title_font = self._font(84, bold=True)
        y = 340
        for line in self._wrap(draw, str(spec.get("title") or ""), title_font, 940)[:3]:
            draw.text((self.margin, y), line, font=title_font, fill=palette["foreground"])
            y += 108
        y += 38
        draw.rounded_rectangle(
            (self.margin, y, self.width - self.margin, y + 470),
            radius=42,
            fill=palette["soft"],
        )
        body_font = self._font(43)
        text_y = y + 58
        for line in self._wrap(draw, str(spec.get("body") or ""), body_font, 850)[:7]:
            draw.text((self.margin + 48, text_y), line, font=body_font, fill=palette["foreground"])
            text_y += 64

    def _draw_list(
        self,
        draw: ImageDraw.ImageDraw,
        spec: dict,
        palette: dict,
        *,
        caution: bool,
    ) -> None:
        self._draw_top_meta(draw, spec, palette)
        title_font = self._font(72, bold=True)
        y = 270
        for line in self._wrap(draw, str(spec.get("title") or ""), title_font, 920)[:2]:
            draw.text((self.margin, y), line, font=title_font, fill=palette["foreground"])
            y += 92
        y += 38
        items = spec.get("items") if isinstance(spec.get("items"), list) else []
        body_font = self._font(38)
        number_font = self._font(32, bold=True)
        for index, item in enumerate(items[:3], start=1):
            box_h = 245
            draw.rounded_rectangle(
                (self.margin, y, self.width - self.margin, y + box_h),
                radius=34,
                fill=palette["soft"],
                outline=palette["line"],
                width=2,
            )
            badge_fill = palette["accent2"] if caution else palette["accent"]
            draw.rounded_rectangle(
                (self.margin + 28, y + 32, self.margin + 94, y + 98),
                radius=22,
                fill=badge_fill,
            )
            number = f"{index:02d}"
            number_width = draw.textlength(number, font=number_font)
            draw.text(
                (self.margin + 61 - number_width / 2, y + 44),
                number,
                font=number_font,
                fill="#FFFFFF" if template_contrast(badge_fill) == "dark" else "#071018",
            )
            text_y = y + 38
            for line in self._wrap(draw, str(item), body_font, 790)[:4]:
                draw.text((self.margin + 126, text_y), line, font=body_font, fill=palette["foreground"])
                text_y += 56
            y += box_h + 28

    def _draw_content(self, draw: ImageDraw.ImageDraw, spec: dict, palette: dict) -> None:
        self._draw_top_meta(draw, spec, palette)
        title_font = self._font(70, bold=True)
        body_font = self._font(42)
        bullet_font = self._font(34, bold=True)

        y = 270
        title_lines = self._wrap(draw, str(spec.get("title") or "核心内容"), title_font, 920)
        for line in title_lines[:2]:
            draw.text((self.margin, y), line, font=title_font, fill=palette["foreground"])
            y += 90
        y += 26
        draw.rounded_rectangle(
            (self.margin, y, self.margin + 128, y + 10),
            radius=5,
            fill=palette["accent"],
        )
        y += 52

        blocks = [part.strip() for part in re.split(r"\n+", str(spec.get("body") or "")) if part.strip()]
        for block in blocks:
            if y > self.height - 290:
                break
            marker_match = re.match(r"^([1-9]️⃣|[①②③④⑤⑥⑦⑧⑨]|[•·\-—])\s*(.*)$", block)
            if marker_match:
                marker = marker_match.group(1).replace("️⃣", "")
                text = marker_match.group(2)
                draw.rounded_rectangle(
                    (self.margin, y + 2, self.margin + 68, y + 70),
                    radius=21,
                    fill=palette["accent"],
                )
                marker_width = draw.textlength(marker, font=bullet_font)
                draw.text(
                    (self.margin + (68 - marker_width) / 2, y + 13),
                    marker,
                    font=bullet_font,
                    fill="#FFFFFF" if template_contrast(palette["accent"]) == "dark" else "#071018",
                )
                line_y = y
                for line in self._wrap(draw, text, body_font, 820)[:4]:
                    draw.text((self.margin + 96, line_y), line, font=body_font, fill=palette["foreground"])
                    line_y += 62
                y = max(y + 94, line_y + 24)
            else:
                for line in self._wrap(draw, block, body_font, self.width - self.margin * 2):
                    if y > self.height - 290:
                        break
                    draw.text((self.margin, y), line, font=body_font, fill=palette["foreground"])
                    y += 62
                y += 26

    def _draw_source(self, draw: ImageDraw.ImageDraw, spec: dict, palette: dict) -> None:
        self._draw_top_meta(draw, spec, palette)
        title_font = self._font(80, bold=True)
        body_font = self._font(41)
        quote_font = self._font(150, bold=True)

        draw.text((self.margin, 250), "“", font=quote_font, fill=palette["accent"])
        y = 390
        for line in self._wrap(draw, str(spec.get("title") or ""), title_font, 920)[:3]:
            draw.text((self.margin, y), line, font=title_font, fill=palette["foreground"])
            y += 102

        y += 38
        draw.rounded_rectangle(
            (self.margin, y, self.width - self.margin, y + 500),
            radius=38,
            fill=palette["soft"],
        )
        text_y = y + 50
        for line in self._wrap(draw, str(spec.get("body") or ""), body_font, 850)[:8]:
            draw.text((self.margin + 44, text_y), line, font=body_font, fill=palette["foreground"])
            text_y += 62

    def _draw_top_meta(self, draw: ImageDraw.ImageDraw, spec: dict, palette: dict) -> None:
        kicker_font = self._font(27, bold=True)
        page_font = self._font(29, bold=True)
        kicker = str(spec.get("kicker") or "X2RED EDITORIAL")
        draw.text((self.margin, 128), kicker, font=kicker_font, fill=palette["accent"])

        page_text = f"{int(spec.get('page') or 1):02d} / {int(spec.get('total') or 1):02d}"
        page_width = draw.textlength(page_text, font=page_font)
        pill_left = self.width - self.margin - page_width - 42
        draw.rounded_rectangle(
            (pill_left, 113, self.width - self.margin, 166),
            radius=26,
            fill=palette["soft"],
        )
        draw.text((pill_left + 21, 122), page_text, font=page_font, fill=palette["muted"])

    def _draw_footer(self, draw: ImageDraw.ImageDraw, spec: dict, palette: dict) -> None:
        footer_y = self.height - 190
        draw.line(
            (self.margin, footer_y - 32, self.width - self.margin, footer_y - 32),
            fill=palette["line"],
            width=3,
        )
        footer_font = self._font(28)
        footer = str(spec.get("footer") or "")
        for line in self._wrap(draw, footer, footer_font, 800)[:2]:
            draw.text((self.margin, footer_y), line, font=footer_font, fill=palette["muted"])
            footer_y += 40
        brand_font = self._font(25, bold=True)
        brand = "X2RED"
        brand_width = draw.textlength(brand, font=brand_font)
        draw.text(
            (self.width - self.margin - brand_width, self.height - 148),
            brand,
            font=brand_font,
            fill=palette["muted"],
        )

    def _font(
        self,
        size: int,
        *,
        bold: bool = False,
    ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        candidates: list[Path] = []
        if self.settings.card_font_path:
            candidates.append(self.settings.card_font_path)
        if bold:
            candidates.extend(
                Path(path)
                for path in (
                    "/System/Library/Fonts/PingFang.ttc",
                    "/System/Library/Fonts/STHeiti Medium.ttc",
                    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                    "C:/Windows/Fonts/msyhbd.ttc",
                    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                )
            )
        candidates.extend(
            Path(path)
            for path in (
                "/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/STHeiti Medium.ttc",
                "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                "C:/Windows/Fonts/msyh.ttc",
                "C:/Windows/Fonts/simhei.ttf",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            )
        )
        for candidate in candidates:
            if candidate.is_file():
                return ImageFont.truetype(str(candidate), size=size)
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size=size)
        except OSError:
            return ImageFont.load_default()

    @staticmethod
    def _wrap(
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
        max_width: int,
    ) -> list[str]:
        lines: list[str] = []
        current = ""
        for character in text.replace("\r", ""):
            if character == "\n":
                if current.rstrip():
                    lines.append(current.rstrip())
                current = ""
                continue
            candidate = current + character
            if current and draw.textlength(candidate, font=font) > max_width:
                lines.append(current.rstrip())
                current = character.lstrip()
            else:
                current = candidate
        if current or not lines:
            lines.append(current.rstrip())
        return [line for line in lines if line]


def template_contrast(hex_color: str) -> str:
    value = hex_color.lstrip("#")
    red, green, blue = (int(value[index : index + 2], 16) for index in (0, 2, 4))
    luminance = (0.299 * red + 0.587 * green + 0.114 * blue) / 255
    return "light" if luminance > 0.62 else "dark"
