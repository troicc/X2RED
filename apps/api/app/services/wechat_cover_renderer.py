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
    """Render review-driven, publication-safe WeChat cover pairs."""

    wide_size = (2100, 900)
    square_size = (1080, 1080)
    styles = {"auto", "image_cinema", "tech_blueprint", "data_poster", "editorial_split"}

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
        cover_style: str = "auto",
        emphasis: str = "",
    ) -> dict[str, str]:
        output_dir.mkdir(parents=True, exist_ok=True)
        wide = output_dir / "cover-21x9.png"
        square = output_dir / "cover-square.png"
        safe_label = strip_internal_markers(series_label)
        style = self._resolve_style(cover_style, title, hero_image)
        values = (
            (wide, self.wide_size, "wide", title, subtitle),
            (
                square,
                self.square_size,
                "square",
                short_title or self.short_title(title),
                "",
            ),
        )
        for path, size, mode, resolved_title, resolved_subtitle in values:
            rendered = False
            if self._playwright_available():
                try:
                    self._render_playwright(
                        path,
                        size=size,
                        mode=mode,
                        title=resolved_title,
                        subtitle=resolved_subtitle,
                        theme_id=theme_id,
                        hero_image=hero_image,
                        series_label=safe_label,
                        cover_style=style,
                        emphasis=emphasis,
                    )
                    rendered = True
                except Exception:
                    rendered = False
            if not rendered:
                self._render_pillow(
                    path,
                    size=size,
                    mode=mode,
                    title=resolved_title,
                    subtitle=resolved_subtitle,
                    theme_id=theme_id,
                    hero_image=hero_image,
                    series_label=safe_label,
                    cover_style=style,
                    emphasis=emphasis,
                )
        return {"wide": str(wide.resolve()), "square": str(square.resolve())}

    @staticmethod
    def short_title(title: str) -> str:
        clean = re.sub(r"[：:｜|—–-].*$", "", title.strip())
        clean = re.sub(r"[，。！？；、]", "", clean)
        return clean if len(clean) <= 12 else clean[:12]

    @classmethod
    def _resolve_style(cls, requested: str, title: str, hero_image: str) -> str:
        if requested in cls.styles and requested != "auto":
            return requested
        if hero_image and Path(hero_image).is_file():
            return "image_cinema"
        if re.search(r"\d+(?:\.\d+)?\s*(?:倍|%|秒|万|亿)", title):
            return "data_poster"
        # A generic grid/orbit "AI look" ages quickly and made most technical
        # articles indistinguishable.  The default is now a restrained editorial
        # composition; blueprint remains available only when explicitly stored.
        return "editorial_split"

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
        cover_style: str,
        emphasis: str,
    ) -> None:
        from playwright.sync_api import sync_playwright

        width, height = size
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(
                viewport={"width": width, "height": height},
                device_scale_factor=1,
            )
            page.set_content(
                self._document(
                    width=width,
                    height=height,
                    mode=mode,
                    title=title,
                    subtitle=subtitle,
                    theme_id=theme_id,
                    hero_image=hero_image,
                    series_label=series_label,
                    cover_style=cover_style,
                    emphasis=emphasis,
                ),
                wait_until="load",
            )
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
        series_label: str,
        cover_style: str,
        emphasis: str,
    ) -> str:
        theme = get_theme(theme_id)
        safe_title = html.escape(strip_internal_markers(title.strip()))
        safe_subtitle = html.escape(strip_internal_markers(subtitle.strip()))
        safe_label = html.escape(strip_internal_markers(series_label.strip()))
        safe_emphasis = html.escape(emphasis.strip())
        image = self._image_src(hero_image)
        wide = mode == "wide"
        label_html = f'<span class="series">{safe_label}</span>' if safe_label else ""
        subtitle_html = f'<p class="subtitle">{safe_subtitle}</p>' if safe_subtitle and wide else ""
        emphasis_html = f'<strong class="emphasis">{safe_emphasis}</strong>' if safe_emphasis else ""
        hero_html = f'<img class="hero-image" src="{image}" alt="">' if image else ""

        if cover_style == "image_cinema" and image:
            composition = f"""
<article class="cover cinema">{hero_html}<div class="shade"></div><section class="copy">{label_html}{emphasis_html}<h1>{safe_title}</h1>{subtitle_html}</section></article>"""
        elif cover_style == "data_poster":
            primary = safe_emphasis or html.escape(self._extract_emphasis(title) or "NEW")
            composition = f"""
<article class="cover data"><span class="data-mark">{primary}</span><section class="copy">{label_html}<h1>{safe_title}</h1>{subtitle_html}</section><div class="data-grid"></div></article>"""
        elif cover_style == "editorial_split":
            visual = hero_html if image else '<div class="editorial-shape"><i></i><b></b></div>'
            composition = f"""
<article class="cover split {mode}"><section class="copy">{label_html}<h1>{safe_title}</h1>{subtitle_html}<span class="rule"></span></section><figure class="visual">{visual}</figure></article>"""
        else:
            composition = f"""
<article class="cover blueprint"><div class="grid"></div><div class="orbit o1"></div><div class="orbit o2"></div><section class="copy">{label_html}{emphasis_html}<h1>{safe_title}</h1>{subtitle_html}<span class="rule"></span></section><div class="coordinate">01 / SIGNAL<br>02 / SYSTEM<br>03 / CHANGE</div></article>"""

        title_size = 80 if wide else 92
        return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}}html,body{{margin:0;width:{width}px;height:{height}px;overflow:hidden}}
body{{font-family:Inter,-apple-system,BlinkMacSystemFont,'PingFang SC','Noto Sans CJK SC',sans-serif;background:{theme.background};color:{theme.text}}}
main{{width:100%;height:100%;padding:{42 if wide else 38}px;background:{theme.background}}}
.cover{{position:relative;width:100%;height:100%;overflow:hidden;border-radius:{30 if wide else 42}px;background:{theme.paper};box-shadow:0 30px 90px #0003}}
.copy{{position:absolute;z-index:5;display:flex;flex-direction:column;justify-content:center}}
.series{{display:inline-flex;align-self:flex-start;margin-bottom:28px;padding:10px 16px;border:1px solid currentColor;border-radius:999px;font-size:18px;font-weight:850;letter-spacing:.09em}}
h1{{margin:0;max-width:{1120 if wide else 900}px;font-size:{title_size}px;line-height:1.08;letter-spacing:-.055em;font-weight:920}}
.subtitle{{margin:28px 0 0;max-width:950px;font-size:30px;line-height:1.5}}
.rule{{display:block;width:138px;height:10px;margin-top:36px;border-radius:99px;background:{theme.accent}}}
.emphasis{{display:block;margin-bottom:20px;color:{theme.accent};font-size:{98 if wide else 116}px;line-height:.9;letter-spacing:-.06em;font-weight:950}}
.hero-image{{position:absolute;width:100%;height:100%;object-fit:cover}}
.cinema .shade{{position:absolute;inset:0;background:linear-gradient(90deg,#05070bf2 0%,#080b12c7 46%,#06080b35 78%),linear-gradient(180deg,#0001,#0007)}}
.cinema .copy{{left:{72 if wide else 62}px;right:{820 if wide else 62}px;top:0;bottom:0;color:#fff}}.cinema .subtitle{{color:#ffffffd9}}
.blueprint{{background:#081322;color:#f5fbff}}.blueprint .grid{{position:absolute;inset:0;background:linear-gradient(#52ddff18 1px,transparent 1px),linear-gradient(90deg,#52ddff18 1px,transparent 1px);background-size:56px 56px}}.blueprint .copy{{left:{82 if wide else 64}px;right:{520 if wide else 64}px;top:0;bottom:0}}.blueprint .subtitle{{color:#a8c0d8}}.blueprint .orbit{{position:absolute;border:2px solid #5ee7ff70;border-radius:50%}}.blueprint .o1{{width:620px;height:620px;right:-80px;top:-130px}}.blueprint .o2{{width:360px;height:360px;right:120px;bottom:-120px}}.coordinate{{position:absolute;right:72px;bottom:58px;color:#5ee7ff;font:700 18px/1.8 ui-monospace,SFMono-Regular,monospace;letter-spacing:.08em}}
.data{{background:{theme.paper};color:{theme.text}}}.data-mark{{position:absolute;right:-20px;top:-70px;color:{theme.accent_soft};font-size:{350 if wide else 290}px;line-height:1;font-weight:950;letter-spacing:-.1em}}.data .copy{{left:{78 if wide else 62}px;right:{700 if wide else 62}px;top:0;bottom:0}}.data-grid{{position:absolute;right:70px;bottom:58px;width:460px;height:230px;background:repeating-linear-gradient(0deg,{theme.accent}25 0 2px,transparent 2px 42px),repeating-linear-gradient(90deg,{theme.accent}25 0 2px,transparent 2px 42px)}}
.split{{display:grid;grid-template-columns:{'62% 38%' if wide else '1fr'};background:{theme.paper}}}.split .copy{{position:relative;left:auto;right:auto;top:auto;bottom:auto;padding:{74 if wide else 62}px;align-self:stretch}}.split .visual{{position:relative;margin:0;overflow:hidden;background:{theme.accent_soft}}}.split .visual .hero-image{{inset:0}}.editorial-shape{{position:absolute;inset:0;background:linear-gradient(156deg,{theme.accent_soft} 0 44%,{theme.accent} 44% 57%,{theme.text} 57% 100%)}}.editorial-shape i{{position:absolute;width:220px;height:220px;right:64px;top:74px;border:2px solid {theme.paper}aa;border-radius:50%}}.editorial-shape b{{position:absolute;width:2px;height:56%;left:34%;bottom:0;background:{theme.paper}aa;transform:rotate(24deg);transform-origin:bottom}}.split.square{{display:block}}.split.square .copy{{position:absolute;inset:0;z-index:2;padding:72px 64px 300px}}.split.square .visual{{position:absolute;right:0;bottom:0;width:48%;height:38%;border-radius:180px 0 0 0}}.split.square h1{{max-width:900px}}
</style></head><body><main>{composition}</main></body></html>"""

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
        series_label: str,
        cover_style: str,
        emphasis: str,
    ) -> None:
        theme = get_theme(theme_id)
        width, height = size
        canvas = Image.new("RGB", size, theme.background)
        draw = ImageDraw.Draw(canvas)
        margin = 42 if mode == "wide" else 38
        draw.rounded_rectangle(
            (margin, margin, width - margin, height - margin),
            radius=34,
            fill="#081322" if cover_style == "tech_blueprint" else theme.paper,
        )
        fg = "#f5fbff" if cover_style == "tech_blueprint" else theme.text
        if cover_style == "editorial_split":
            if mode == "wide":
                art_box = (
                    int(width * 0.64),
                    margin,
                    width - margin,
                    height - margin,
                )
            else:
                art_box = (
                    int(width * 0.52),
                    int(height * 0.64),
                    width - margin,
                    height - margin,
                )
            left, top, right, bottom = art_box
            draw.rounded_rectangle(art_box, radius=80, fill=theme.accent_soft)
            draw.polygon(
                ((left, top), (right, top), (right, bottom), (left + (right - left) // 3, bottom)),
                fill=theme.accent,
            )
            draw.polygon(
                (
                    (left + (right - left) // 2, top),
                    (right, top),
                    (right, bottom),
                    (left + (right - left) * 3 // 4, bottom),
                ),
                fill=theme.text,
            )
            diameter = max(90, min(right - left, bottom - top) // 3)
            draw.ellipse(
                (right - diameter - 54, top + 54, right - 54, top + 54 + diameter),
                outline=theme.paper,
                width=4,
            )
        elif cover_style == "data_poster":
            signal = emphasis or self._extract_emphasis(title)
            if signal:
                signal_font = self._font(260 if mode == "wide" else 210, bold=True)
                signal_width = draw.textlength(signal, font=signal_font)
                draw.text(
                    (width - margin - signal_width - 36, height - margin - 300),
                    signal,
                    font=signal_font,
                    fill=theme.accent_soft,
                )
        hero = Path(hero_image) if hero_image else None
        if cover_style == "image_cinema" and hero and hero.is_file():
            with Image.open(hero).convert("RGB") as source:
                target_w, target_h = width - margin * 2, height - margin * 2
                ratio = max(target_w / source.width, target_h / source.height)
                resized = source.resize((int(source.width * ratio), int(source.height * ratio)))
                left = max(0, (resized.width - target_w) // 2)
                top = max(0, (resized.height - target_h) // 2)
                canvas.paste(resized.crop((left, top, left + target_w, top + target_h)), (margin, margin))
            overlay = Image.new("RGBA", size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            overlay_draw.rectangle((margin, margin, width - margin, height - margin), fill=(0, 0, 0, 125))
            canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
            draw = ImageDraw.Draw(canvas)
            fg = "#ffffff"
        x = margin + 68
        y = margin + 92
        max_width = int(width * (0.58 if mode == "wide" else 0.82))
        label = strip_internal_markers(series_label)
        if label:
            font = self._font(20, bold=True)
            draw.text((x, y), label, font=font, fill=theme.accent)
            y += 58
        if emphasis:
            font = self._font(92 if mode == "wide" else 104, bold=True)
            draw.text((x, y), emphasis, font=font, fill=theme.accent)
            y += 118
        title_font = self._font(76 if mode == "wide" else 84, bold=True)
        for line in self._wrap(draw, strip_internal_markers(title), title_font, max_width)[:5]:
            draw.text((x, y), line, font=title_font, fill=fg)
            y += int(getattr(title_font, "size", 76) * 1.18)
        if subtitle and mode == "wide":
            y += 18
            subtitle_font = self._font(28, bold=False)
            for line in self._wrap(draw, strip_internal_markers(subtitle), subtitle_font, max_width)[:3]:
                draw.text((x, y), line, font=subtitle_font, fill=fg)
                y += 44
        draw.rounded_rectangle((x, min(y + 24, height - 90), x + 136, min(y + 34, height - 80)), radius=5, fill=theme.accent)
        canvas.save(path, format="PNG", optimize=True)

    @staticmethod
    def _extract_emphasis(value: str) -> str:
        match = re.search(r"\d+(?:\.\d+)?\s*(?:倍|%|秒|万|亿)", value)
        return match.group(0).replace(" ", "") if match else ""

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
