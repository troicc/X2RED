from __future__ import annotations

import base64
import html
import importlib.util
import mimetypes
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.services.wechat_themes import get_theme


class WeChatCoverRenderer:
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
    ) -> dict[str, str]:
        output_dir.mkdir(parents=True, exist_ok=True)
        wide = output_dir / "cover-21x9.png"
        square = output_dir / "cover-square.png"
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
                )
                self._render_playwright(
                    square,
                    size=self.square_size,
                    mode="square",
                    title=short_title or self.short_title(title),
                    subtitle="",
                    theme_id=theme_id,
                    hero_image="",
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
        )
        self._render_pillow(
            square,
            size=self.square_size,
            mode="square",
            title=short_title or self.short_title(title),
            subtitle="",
            theme_id=theme_id,
            hero_image="",
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
        )
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
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
    ) -> str:
        theme = get_theme(theme_id)
        safe_title = html.escape(title)
        safe_subtitle = html.escape(subtitle)
        image = self._image_src(hero_image)
        wide = mode == "wide"
        title_size = 82 if wide else 94
        content_width = "58%" if wide and image else "78%"
        image_html = (
            f'<figure style="margin:0;position:absolute;right:0;top:0;width:38%;height:100%;overflow:hidden;">'
            f'<img src="{image}" style="width:100%;height:100%;object-fit:cover;object-position:center;display:block">'
            f'<span style="position:absolute;left:0;top:0;width:22%;height:100%;background:linear-gradient(90deg,{theme.paper},transparent);"></span></figure>'
            if wide and image
            else ""
        )
        subtitle_html = (
            f'<p style="margin:28px 0 0;max-width:900px;color:{theme.muted};font-size:31px;line-height:1.55;">{safe_subtitle}</p>'
            if safe_subtitle
            else ""
        )
        marker = "WECHAT / X2RED" if wide else "X2RED"
        return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}}html,body{{margin:0;width:{width}px;height:{height}px;overflow:hidden}}body{{font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Noto Sans CJK SC',sans-serif;background:{theme.background};color:{theme.text}}}
</style></head><body><main style="position:relative;width:100%;height:100%;padding:{70 if wide else 72}px;background:radial-gradient(circle at 8% 10%,{theme.accent_soft},transparent 38%),{theme.background};overflow:hidden;">
<section style="position:relative;width:100%;height:100%;padding:{68 if wide else 78}px;border:1px solid {theme.rule};border-radius:{30 if wide else 42}px;background:{theme.paper};overflow:hidden;box-shadow:0 28px 80px #00000012;">
{image_html}<div style="position:relative;z-index:2;width:{content_width};height:100%;display:flex;flex-direction:column;justify-content:center;">
<span style="display:inline-block;align-self:flex-start;padding:10px 16px;border-radius:999px;background:{theme.accent_soft};color:{theme.accent};font-size:20px;font-weight:800;letter-spacing:.14em;">{marker}</span>
<h1 style="margin:34px 0 0;color:{theme.text};font-size:{title_size}px;line-height:1.15;letter-spacing:-.045em;font-weight:820;">{safe_title}</h1>{subtitle_html}
<span style="display:block;width:120px;height:10px;margin-top:36px;border-radius:99px;background:{theme.accent};"></span>
</div><footer style="position:absolute;left:{68 if wide else 78}px;bottom:{42 if wide else 55}px;color:{theme.muted};font-size:20px;letter-spacing:.08em;">从一份来源，生成不同平台的表达</footer>
</section></main></body></html>"""

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
    ) -> None:
        theme = get_theme(theme_id)
        width, height = size
        image = Image.new("RGB", size, theme.background)
        draw = ImageDraw.Draw(image)
        margin = 70 if mode == "wide" else 64
        draw.rounded_rectangle(
            (margin, margin, width - margin, height - margin),
            radius=34 if mode == "wide" else 46,
            fill=theme.paper,
            outline=theme.rule,
            width=2,
        )
        content_right = width - margin - 70
        hero_path = Path(hero_image) if hero_image else None
        if mode == "wide" and hero_path and hero_path.is_file():
            with Image.open(hero_path).convert("RGB") as source:
                target_w = int(width * 0.36)
                target_h = height - margin * 2
                ratio = max(target_w / source.width, target_h / source.height)
                resized = source.resize((int(source.width * ratio), int(source.height * ratio)))
                left = max(0, (resized.width - target_w) // 2)
                top = max(0, (resized.height - target_h) // 2)
                crop = resized.crop((left, top, left + target_w, top + target_h))
                image.paste(crop, (width - margin - target_w, margin))
                content_right = width - margin - target_w - 55
        title_font = self._font(78 if mode == "wide" else 86, bold=True)
        subtitle_font = self._font(29, bold=False)
        meta_font = self._font(21, bold=True)
        x = margin + 70
        y = margin + (120 if mode == "wide" else 150)
        draw.rounded_rectangle((x, y, x + 235, y + 48), radius=24, fill=theme.accent_soft)
        draw.text((x + 18, y + 12), "WECHAT / X2RED", font=meta_font, fill=theme.accent)
        y += 92
        max_width = content_right - x
        for line in self._wrap(draw, title, title_font, max_width)[:5]:
            draw.text((x, y), line, font=title_font, fill=theme.text)
            y += int(title_font.size * 1.28)
        if subtitle and mode == "wide":
            y += 20
            for line in self._wrap(draw, subtitle, subtitle_font, max_width)[:3]:
                draw.text((x, y), line, font=subtitle_font, fill=theme.muted)
                y += int(subtitle_font.size * 1.55)
        draw.rounded_rectangle((x, min(height - margin - 110, y + 26), x + 120, min(height - margin - 100, y + 36)), radius=5, fill=theme.accent)
        image.save(path, format="PNG", optimize=True)

    @staticmethod
    def _font(size: int, *, bold: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        candidates = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
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
