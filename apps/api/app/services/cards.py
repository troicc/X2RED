from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import CardRender, DraftRevision

_TEMPLATES = {
    "warm_editorial": {
        "background": "#F7EDE7",
        "panel": "#FFFDFC",
        "foreground": "#27191C",
        "accent": "#E9415F",
        "accent2": "#FFB25B",
        "muted": "#826F73",
        "soft": "#FBE3E8",
        "shadow": "#E7D6D0",
    },
    "dark_tech": {
        "background": "#090C12",
        "panel": "#141925",
        "foreground": "#F5F7FB",
        "accent": "#72E4FF",
        "accent2": "#B28CFF",
        "muted": "#99A6BA",
        "soft": "#20283A",
        "shadow": "#05070B",
    },
    "clean_news": {
        "background": "#EAF0F8",
        "panel": "#FFFFFF",
        "foreground": "#13223A",
        "accent": "#246BFD",
        "accent2": "#15A68A",
        "muted": "#65748B",
        "soft": "#E8F0FF",
        "shadow": "#D4DEEC",
    },
}

_SECTION_HEADINGS = {
    "先说结论",
    "值得关注的 3 个点",
    "值得关注的3个点",
    "这意味着什么",
    "阅读提醒",
    "发生了什么",
    "核心信息",
    "为什么值得关注",
    "仍需确认",
    "我的判断",
    "判断依据",
    "需要警惕的地方",
    "留给读者的问题",
    "来源与提醒",
}


class CardRenderError(RuntimeError):
    pass


class CardService:
    # 3:4 portrait at a higher export resolution than the old 1080×1440 cards.
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
        max_cards = max(2, min(max_cards, 10))
        title = re.sub(r"\s+", " ", draft.title).strip() or "这条 X 更新讲了什么"
        source = draft.source
        handle = source.author_handle if source else ""
        author = source.author_name if source else ""
        sections = self._parse_sections(draft.body)
        summary = self._cover_summary(sections, draft.body)

        specs: list[dict] = [
            {
                "kind": "cover",
                "kicker": self._style_kicker(draft.style),
                "title": title,
                "body": summary,
                "source": self._source_label(author, handle),
                "footer": "向左滑，看完整拆解",
            }
        ]

        available_content = max_cards - 2
        for section in sections:
            if len(specs) - 1 >= available_content:
                break
            chunks = self._chunk_text(section["body"], 430)
            for chunk_index, chunk in enumerate(chunks):
                if len(specs) - 1 >= available_content:
                    break
                heading = section["heading"]
                if chunk_index:
                    heading = f"{heading} · 续"
                specs.append(
                    {
                        "kind": "content",
                        "kicker": self._style_kicker(draft.style),
                        "title": heading,
                        "body": chunk,
                        "source": self._source_label(author, handle),
                        "footer": "原作者观点与编辑补充以正文标注为准",
                    }
                )

        specs.append(
            {
                "kind": "source",
                "kicker": "SOURCE NOTE",
                "title": "信息有出处，判断留边界",
                "body": (
                    f"来源：{self._source_label(author, handle)}\n\n"
                    "这组卡片基于已归档的 X 原帖与上下文整理。涉及数字、日期、效果和因果关系时，"
                    "请回到原帖并结合公开资料复核。"
                ),
                "source": source.canonical_url if source else "",
                "footer": "收藏的是线索，不是未经核实的结论",
            }
        )
        return specs[:max_cards]

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
            chunks = self._chunk_text(body, 430)
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

        if spec.get("kind") == "cover":
            self._draw_cover(draw, spec, palette)
        elif spec.get("kind") == "source":
            self._draw_source(draw, spec, palette)
        else:
            self._draw_content(draw, spec, palette)

        self._draw_footer(draw, spec, palette)
        image.save(path, format="PNG", optimize=True)

    def _draw_background(self, draw: ImageDraw.ImageDraw, palette: dict, spec: dict) -> None:
        # Large cropped circles produce depth without external assets.
        draw.ellipse((-170, -130, 330, 370), fill=palette["accent"])
        draw.ellipse((self.width - 260, 70, self.width + 170, 500), fill=palette["accent2"])
        if spec.get("kind") != "cover":
            draw.ellipse((self.width - 170, self.height - 260, self.width + 140, self.height + 50), fill=palette["soft"])

    def _draw_panel(self, draw: ImageDraw.ImageDraw, palette: dict) -> None:
        panel_box = (62, 62, self.width - 62, self.height - 62)
        shadow_box = (72, 82, self.width - 52, self.height - 42)
        draw.rounded_rectangle(shadow_box, radius=58, fill=palette["shadow"])
        draw.rounded_rectangle(panel_box, radius=58, fill=palette["panel"])

    def _draw_cover(self, draw: ImageDraw.ImageDraw, spec: dict, palette: dict) -> None:
        self._draw_top_meta(draw, spec, palette)
        title = str(spec.get("title") or "")
        title_size = 104 if len(title) <= 14 else 88 if len(title) <= 22 else 76
        title_font = self._font(title_size, bold=True)
        title_lines = self._wrap(draw, title, title_font, self.width - self.margin * 2)
        y = 300
        for line in title_lines[:4]:
            draw.text((self.margin, y), line, font=title_font, fill=palette["foreground"])
            y += int(title_size * 1.28)

        y += 34
        draw.rounded_rectangle(
            (self.margin, y, self.margin + 168, y + 14),
            radius=7,
            fill=palette["accent"],
        )
        y += 60

        body = str(spec.get("body") or "")
        body_font = self._font(45)
        body_lines = self._wrap(draw, body, body_font, self.width - self.margin * 2 - 72)
        box_height = max(190, min(390, len(body_lines[:5]) * 66 + 82))
        draw.rounded_rectangle(
            (self.margin, y, self.width - self.margin, y + box_height),
            radius=34,
            fill=palette["soft"],
        )
        text_y = y + 40
        for line in body_lines[:5]:
            draw.text((self.margin + 38, text_y), line, font=body_font, fill=palette["foreground"])
            text_y += 66

        source_font = self._font(31)
        draw.text(
            (self.margin, self.height - 260),
            str(spec.get("source") or "X 原帖"),
            font=source_font,
            fill=palette["muted"],
        )

    def _draw_content(self, draw: ImageDraw.ImageDraw, spec: dict, palette: dict) -> None:
        self._draw_top_meta(draw, spec, palette)
        title_font = self._font(72, bold=True)
        body_font = self._font(43)
        bullet_font = self._font(36, bold=True)

        y = 270
        title_lines = self._wrap(draw, str(spec.get("title") or "核心内容"), title_font, 920)
        for line in title_lines[:2]:
            draw.text((self.margin, y), line, font=title_font, fill=palette["foreground"])
            y += 92
        y += 28
        draw.rounded_rectangle(
            (self.margin, y, self.margin + 124, y + 10),
            radius=5,
            fill=palette["accent"],
        )
        y += 56

        body = str(spec.get("body") or "")
        blocks = [part.strip() for part in re.split(r"\n+", body) if part.strip()]
        for block in blocks:
            if y > self.height - 290:
                break
            marker_match = re.match(r"^([1-9]️⃣|[①②③④⑤⑥⑦⑧⑨]|[•·\-—])\s*(.*)$", block)
            if marker_match:
                marker = marker_match.group(1)
                text = marker_match.group(2)
                draw.rounded_rectangle(
                    (self.margin, y + 2, self.margin + 70, y + 72),
                    radius=22,
                    fill=palette["accent"],
                )
                marker_color = "#FFFFFF" if template_contrast(palette["accent"]) == "dark" else "#091018"
                marker_text = marker.replace("️⃣", "")
                marker_width = draw.textlength(marker_text, font=bullet_font)
                draw.text(
                    (self.margin + (70 - marker_width) / 2, y + 13),
                    marker_text,
                    font=bullet_font,
                    fill=marker_color,
                )
                lines = self._wrap(draw, text, body_font, 820)
                line_y = y
                for line in lines[:4]:
                    draw.text((self.margin + 98, line_y), line, font=body_font, fill=palette["foreground"])
                    line_y += 63
                y = max(y + 96, line_y + 24)
            else:
                lines = self._wrap(draw, block, body_font, self.width - self.margin * 2)
                for line in lines:
                    if y > self.height - 290:
                        break
                    draw.text((self.margin, y), line, font=body_font, fill=palette["foreground"])
                    y += 64
                y += 28

    def _draw_source(self, draw: ImageDraw.ImageDraw, spec: dict, palette: dict) -> None:
        self._draw_top_meta(draw, spec, palette)
        title_font = self._font(82, bold=True)
        body_font = self._font(42)
        quote_font = self._font(150, bold=True)

        draw.text((self.margin, 255), "“", font=quote_font, fill=palette["accent"])
        y = 390
        for line in self._wrap(draw, str(spec.get("title") or ""), title_font, 920)[:3]:
            draw.text((self.margin, y), line, font=title_font, fill=palette["foreground"])
            y += 104

        y += 42
        draw.rounded_rectangle(
            (self.margin, y, self.width - self.margin, y + 480),
            radius=38,
            fill=palette["soft"],
        )
        text_y = y + 52
        for line in self._wrap(draw, str(spec.get("body") or ""), body_font, 850)[:8]:
            draw.text((self.margin + 44, text_y), line, font=body_font, fill=palette["foreground"])
            text_y += 63

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
            fill=palette["soft"],
            width=3,
        )
        footer_font = self._font(28)
        footer = str(spec.get("footer") or "")
        footer_lines = self._wrap(draw, footer, footer_font, 800)
        for line in footer_lines[:2]:
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
