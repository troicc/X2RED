from __future__ import annotations

import base64
import html
import importlib.util
import mimetypes
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.services.publication_safety import strip_internal_markers
from app.services.wechat_themes import get_theme


class WeChatCoverRenderer:
    """Render publish-ready WeChat covers without product/workflow branding."""

    wide_size = (2100, 900)
    square_size = (1080, 1080)

    def render_pair(
        self,
        output_dir: Path,
        *,
        title: str,
        short_title: str,
        subtitle: str,
        theme_id: str,
        hero_image: str = "",
        series_label: str = "",
    ) -> dict[str, str]:
        output_dir.mkdir(parents=True, exist_ok=True)
        wide = output_dir / "cover-21x9.png"
        square = output_dir / "cover-square.png"
        safe_label = strip_internal_markers(series_label)
        if self._playwright_available():
            try:
                self._render_playwright(
                    wide,
                    size=self.wide_size,
                    mode="wide",
                    title=title,
                    subtitle=subtitle,
                    theme_id=theme_id,
                    hero_image=hero_image,
                    series_label=safe_label,
                )
                self._render_playwright(
                    square,
                    size=self.square_size,
                    mode="square",
                    title=short_title or self.short_title(title),
                    subtitle="",
                    theme_id=theme_id,
                    hero_image=hero_image,
                    series_label=safe_label,
                )
                return {"wide": str(wide.resolve()), "square": str(square.resolve())}
            except Exception:
                pass
        self._render_pillow(
            wide,
            size=self.wide_size,
            mode="wide",
            title=title,
            subtitle=subtitle,
            theme_id=theme_id,
            hero_image=hero_image,
            series_label=safe_label,
        )
        self._render_pillow(
            square,
            size=self.square_size,
            mode="square",
            title=short_title or self.short_title(title),
            subtitle="",
            theme_id=theme_id,
            hero_image=hero_image,
            series_label=safe_label,
        )
        return {"wide": str(wide.resolve()), "square": str(square.resolve())}

    @staticmethod
    def short_title(title: str) -> str:
        clean = re.sub(r"[：:｜|—–-].*$", "", title.strip())
        clean = re.sub(r"[，。！？；、]", "", clean)
        if len(clean) <= 12:
            return clean
        chunks = re.split(r"(?:为什么|如何|背后|终于|从|一个)", clean, maxsplit=1)
        candidate = max(chunks, key=len).strip() if chunks else clean
        return (candidate or clean)[:12]

    @staticmethod
    def _playwright_available() -> bool:
        return importlib.util.find_spec("playwright") is not None

    def _render_playwright(
        self,
        path: Path,
        *,
        size: tuple[int, int],
        mode: str,
        title: str,
        subtitle: str,
        theme_id: str,
        hero_image: str,
        series_label: str,
    ) -> None:
        from playwright.sync_api import sync_playwright

        width, height = size
        document = self._document(
            width=width,
            height=height,
            mode=mode,
            title=title,
            subtitle=subtitle,
            theme_id=theme_id,
            hero_image=hero_image,
            series_label=series_label,
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(
                viewport={"width": width, "height": height},
                device_scale_factor=1,
            )
            page.set_content(document, wait_until="load")
            page.evaluate("document.fonts && document.fonts.ready")
            page.screenshot(path=str(path), full_page=False)
            browser.close()

    def _document(
        self,
        *,
        width: int,
        height: int,
        mode: str,
        title: str,
        subtitle: str,
        theme_id: str,
        hero_image: str,
        series_label: str = "",
    ) -> str:
        theme = get_theme(theme_id)
        safe_title = html.escape(title.strip())
        safe_subtitle = html.escape(subtitle.strip())
        safe_label = html.escape(strip_internal_markers(series_label))
        image = self._image_src(hero_image)
        wide = mode == "wide"
        has_image = bool(image)
        title_size = 80 if wide else 88
        content_width = "59%" if wide and has_image else "84%"
        image_html = ""
        if has_image:
            if wide:
                image_html = (
                    f'<figure class="hero wide"><img src="{image}" alt="">'
                    f'<span style="background:linear-gradient(90deg,{theme.paper} 0%,{theme.paper}e8 16%,transparent 62%);"></span></figure>'
                )
            else:
                image_html = (
                    f'<figure class="hero square"><img src="{image}" alt="">'
                    f'<span style="background:linear-gradient(180deg,transparent 15%,{theme.paper}12 48%,{theme.paper} 92%);"></span></figure>'
                )
        label_html = (
            f'<span class="series" style="background:{theme.accent_soft};color:{theme.accent};">{safe_label}</span>'
            if safe_label
            else ""
        )
        subtitle_html = (
            f'<p class="subtitle" style="color:{theme.muted};">{safe_subtitle}</p>'
            if safe_subtitle and wide
            else ""
        )
        return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}}html,body{{margin:0;width:{width}px;height:{height}px;overflow:hidden}}
body{{font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Noto Sans CJK SC',sans-serif;background:{theme.background};color:{theme.text}}}
main{{position:relative;width:100%;height:100%;padding:{58 if wide else 54}px;background:radial-gradient(circle at 10% 8%,{theme.accent_soft},transparent 36%),{theme.background};overflow:hidden}}
article{{position:relative;width:100%;height:100%;overflow:hidden;border:1px solid {theme.rule};border-radius:{28 if wide else 40}px;background:{theme.paper};box-shadow:0 28px 80px #00000012}}
.content{{position:relative;z-index:3;width:{content_width};height:100%;display:flex;flex-direction:column;justify-content:center;padding:{70 if wide else 68}px {76 if wide else 64}px}}
.series{{display:inline-flex;align-self:flex-start;padding:10px 16px;border-radius:999px;font-size:20px;font-weight:800;letter-spacing:.1em}}
h1{{margin:{28 if safe_label else 0}px 0 0;color:{theme.text};font-size:{title_size}px;line-height:1.13;letter-spacing:-.045em;font-weight:850}}
.subtitle{{margin:26px 0 0;max-width:930px;font-size:30px;line-height:1.55}}
.accent{{width:128px;height:9px;margin-top:34px;border-radius:99px;background:{theme.accent}}}
.hero{{position:absolute;margin:0;overflow:hidden}}.hero img{{display:block;width:100%;height:100%;object-fit:cover}}.hero span{{position:absolute;inset:0}}
.hero.wide{{right:0;top:0;width:43%;height:100%}}.hero.square{{inset:0;height:58%}}
.hero.square + .content{{width:100%;height:54%;position:absolute;left:0;right:0;bottom:0;justify-content:flex-start;padding-top:74px}}
</style></head><body><main><article>{image_html}<section class="content">{label_html}<h1>{safe_title}</h1>{subtitle_html}<i class="accent"></i></section></article></main></body></html>"""

    @staticmethod
    def _image_src(value: str) -> str:
        if not value:
            return ""
        path = Path(value)
        if not path.is_file():
            return ""
        mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"

    def _render_pillow(
        self,
        path: Path,
        *,
        size: tuple[int, int],
        mode: str,
        title: str,
        subtitle: str,
        theme_id: str,
        hero_image: str,
        series_label: str = "",
    ) -> None:
        theme = get_theme(theme_id)
        width, height = size
        image = Image.new("RGB", size, theme.background)
        draw = ImageDraw.Draw(image)
        margin = 58 if mode == "wide" else 54
        draw.rounded_rectangle(
            (margin, margin, width - margin, height - margin),
            radius=34 if mode == "wide" else 44,
            fill=theme.paper,
            outline=theme.rule,
            width=2,
        )
        content_right = width - margin - 76
        hero_path = Path(hero_image) if hero_image else None
        if hero_path and hero_path.is_file():
            with Image.open(hero_path).convert("RGB") as source:
                if mode == "wide":
                    target_w = int(width * 0.41)
                    target_h = height - margin * 2
                    ratio = max(target_w / source.width, target_h / source.height)
                    resized = source.resize((int(source.width * ratio), int(source.height * ratio)))
                    left = max(0, (resized.width - target_w) // 2)
                    top = max(0, (resized.height - target_h) // 2)
                    crop = resized.crop((left, top, left + target_w, top + target_h))
                    image.paste(crop, (width - margin - target_w, margin))
                    content_right = width - margin - target_w - 48
                else:
                    target_w = width - margin * 2
                    target_h = int((height - margin * 2) * 0.52)
                    ratio = max(target_w / source.width, target_h / source.height)
                    resized = source.resize((int(source.width * ratio), int(source.height * ratio)))
                    left = max(0, (resized.width - target_w) // 2)
                    top = max(0, (resized.height - target_h) // 2)
                    crop = resized.crop((left, top, left + target_w, top + target_h))
                    image.paste(crop, (margin, margin))
        title_font = self._font(76 if mode == "wide" else 82, bold=True)
        subtitle_font = self._font(29, bold=False)
        label_font = self._font(21, bold=True)
        x = margin + 70
        y = margin + (126 if mode == "wide" else (600 if hero_path and hero_path.is_file() else 145))
        safe_label = strip_internal_markers(series_label)
        if safe_label:
            label_width = min(390, int(draw.textlength(safe_label, font=label_font)) + 40)
            draw.rounded_rectangle((x, y, x + label_width, y + 48), radius=24, fill=theme.accent_soft)
            draw.text((x + 20, y + 11), safe_label, font=label_font, fill=theme.accent)
            y += 88
        max_width = max(360, content_right - x)
        for line in self._wrap(draw, title, title_font, max_width)[:5]:
            draw.text((x, y), line, font=title_font, fill=theme.text)
            y += int(getattr(title_font, "size", 76) * 1.25)
        if subtitle and mode == "wide":
            y += 18
            for line in self._wrap(draw, subtitle, subtitle_font, max_width)[:3]:
                draw.text((x, y), line, font=subtitle_font, fill=theme.muted)
                y += int(getattr(subtitle_font, "size", 29) * 1.52)
        accent_y = min(height - margin - 72, y + 26)
        draw.rounded_rectangle((x, accent_y, x + 128, accent_y + 10), radius=5, fill=theme.accent)
        image.save(path, format="PNG", optimize=True)

    @staticmethod
    def _font(size: int, *, bold: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        candidates = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
            if bold
            else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for candidate in candidates:
            if Path(candidate).is_file():
                return ImageFont.truetype(candidate, size=size)
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
        for character in text.strip():
            candidate = current + character
            if current and draw.textlength(candidate, font=font) > max_width:
                lines.append(current)
                current = character
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines
