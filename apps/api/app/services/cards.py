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
        "background": "#FFF8F4",
        "foreground": "#241B1E",
        "accent": "#FF2442",
        "muted": "#816E74",
        "panel": "#FFFFFF",
    },
    "dark_tech": {
        "background": "#101217",
        "foreground": "#F4F6FA",
        "accent": "#6DE4FF",
        "muted": "#9CA7B7",
        "panel": "#191D25",
    },
    "clean_news": {
        "background": "#F4F7FB",
        "foreground": "#152033",
        "accent": "#2563EB",
        "muted": "#667085",
        "panel": "#FFFFFF",
    },
}


class CardRenderError(RuntimeError):
    pass


class CardService:
    width = 1080
    height = 1440
    margin = 92

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
        title = re.sub(r"\s+", " ", draft.title).strip() or "一条值得关注的 X 更新"
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", draft.body) if part.strip()]
        chunks: list[str] = []
        for paragraph in paragraphs:
            chunks.extend(self._chunk_text(paragraph, 280))

        specs: list[dict] = [
            {
                "kind": "cover",
                "kicker": "X2RED · 编辑整理",
                "title": title,
                "body": "来自 X 的信息，经过本地归档、编辑与人工审核。",
                "footer": f"草稿 v{draft.version}",
            }
        ]
        available_content = max(0, max_cards - 2)
        for index, chunk in enumerate(chunks[:available_content], start=1):
            specs.append(
                {
                    "kind": "content",
                    "kicker": f"要点 {index:02d}",
                    "title": title if index == 1 else "继续拆解",
                    "body": chunk,
                    "footer": "原文观点与编辑补充请以正文标注为准",
                }
            )
        specs.append(
            {
                "kind": "source",
                "kicker": "来源与提醒",
                "title": "先看原帖，再下结论",
                "body": "本内容由 X2RED 基于已归档来源整理。涉及数字、日期、因果关系和争议观点时，请返回原始链接核对完整上下文。",
                "footer": "人工终审后发布",
            }
        )
        return specs[:max_cards]

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
                for mark in ("。", "！", "？", "；", "\n")
            )
            if cut < limit // 2:
                cut = limit
            else:
                cut += 1
            chunks.append(remaining[:cut].strip())
            remaining = remaining[cut:].strip()
        return chunks

    def _draw_card(self, path: Path, spec: dict, template: str) -> None:
        palette = _TEMPLATES[template]
        image = Image.new("RGB", (self.width, self.height), palette["background"])
        draw = ImageDraw.Draw(image)
        title_font = self._font(72)
        body_font = self._font(43)
        small_font = self._font(30)
        kicker_font = self._font(28)

        draw.rounded_rectangle(
            (52, 52, self.width - 52, self.height - 52),
            radius=44,
            fill=palette["panel"],
        )
        draw.rounded_rectangle(
            (self.margin, 102, self.margin + 250, 158),
            radius=28,
            fill=palette["accent"],
        )
        draw.text(
            (self.margin + 24, 113),
            str(spec.get("kicker") or "X2RED"),
            font=kicker_font,
            fill="#FFFFFF" if template != "dark_tech" else "#081018",
        )

        y = 230
        title_lines = self._wrap(draw, str(spec.get("title") or ""), title_font, 850)
        for line in title_lines[:4]:
            draw.text((self.margin, y), line, font=title_font, fill=palette["foreground"])
            y += 92
        y += 40
        draw.line((self.margin, y, self.width - self.margin, y), fill=palette["accent"], width=8)
        y += 54

        body_lines = self._wrap(draw, str(spec.get("body") or ""), body_font, 850)
        for line in body_lines:
            if y > self.height - 210:
                break
            draw.text((self.margin, y), line, font=body_font, fill=palette["foreground"])
            y += 66

        footer = str(spec.get("footer") or "")
        footer_lines = self._wrap(draw, footer, small_font, 820)
        footer_y = self.height - 156
        draw.line(
            (self.margin, footer_y - 30, self.width - self.margin, footer_y - 30),
            fill=palette["muted"],
            width=2,
        )
        for line in footer_lines[:2]:
            draw.text((self.margin, footer_y), line, font=small_font, fill=palette["muted"])
            footer_y += 42
        image.save(path, format="PNG", optimize=True)

    def _font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        candidates = []
        if self.settings.card_font_path:
            candidates.append(self.settings.card_font_path)
        candidates.extend(
            Path(path)
            for path in (
                "C:/Windows/Fonts/msyh.ttc",
                "C:/Windows/Fonts/simhei.ttf",
                "/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/STHeiti Medium.ttc",
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
