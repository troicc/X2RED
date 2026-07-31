from __future__ import annotations

import base64
import html
import importlib.util
import mimetypes
from pathlib import Path


class HtmlCardRenderer:
    width = 1242
    height = 1656

    def available(self) -> bool:
        return importlib.util.find_spec("playwright") is not None

    def render_many(self, output_dir: Path, specs: list[dict], template: str) -> list[str]:
        if not self.available():
            return []
        try:
            from playwright.sync_api import sync_playwright

            paths: list[str] = []
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(
                    viewport={"width": self.width, "height": self.height},
                    device_scale_factor=1,
                )
                for index, spec in enumerate(specs, start=1):
                    page.set_content(self._document(spec, template), wait_until="load")
                    page.evaluate("document.fonts && document.fonts.ready")
                    path = output_dir / f"{index:02d}.png"
                    page.screenshot(path=str(path), full_page=False)
                    paths.append(str(path.resolve()))
                browser.close()
            return paths
        except Exception:
            return []

    def _document(self, spec: dict, template: str) -> str:
        theme = {
            "editorial_minimal": ("#f4f1ed", "#fffdf9", "#171719", "#ff375f", "#efe8e1"),
            "tech_minimal": ("#070a11", "#111827", "#f8fafc", "#7dd3fc", "#1e293b"),
            "clean_news": ("#eef2f7", "#ffffff", "#10213b", "#316ff6", "#e4ebf5"),
            "warm_note": ("#f7f0e8", "#fffaf4", "#2a211d", "#e86d4c", "#f1e1d5"),
        }.get(template, ("#f4f1ed", "#fffdf9", "#171719", "#ff375f", "#efe8e1"))
        bg, panel, fg, accent, soft = theme
        kind = html.escape(str(spec.get("kind") or "content"))
        title = html.escape(str(spec.get("title") or ""))
        body = html.escape(str(spec.get("body") or "")).replace("\n", "<br>")
        kicker = html.escape(str(spec.get("kicker") or "X2RED EDITORIAL"))
        source = html.escape(str(spec.get("source") or ""))
        footer = html.escape(str(spec.get("footer") or ""))
        page = int(spec.get("page") or 1)
        total = int(spec.get("total") or 1)
        items = spec.get("items") if isinstance(spec.get("items"), list) else []
        items_html = "".join(
            f'<li><span>{index:02d}</span><p>{html.escape(str(item))}</p></li>'
            for index, item in enumerate(items[:5], start=1)
        )
        hero = self._image_src(str(spec.get("hero_image") or ""))
        hero_html = (
            f'<div class="hero" style="background-image:url(&quot;{hero}&quot;)"></div>'
            if hero
            else ""
        )
        is_dark = template == "tech_minimal"
        marker_color = "#071018" if is_dark else "#fff"
        title_size = "74" if kind != "cover" else "92"
        title_margin = "160" if kind == "cover" else "125"
        content_html = f"<ul>{items_html}</ul>" if items_html else f'<div class="body">{body}</div>'
        return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}}html,body{{margin:0;width:{self.width}px;height:{self.height}px;overflow:hidden}}
body{{font-family:Inter,-apple-system,BlinkMacSystemFont,'PingFang SC','Noto Sans CJK SC',sans-serif;background:{bg};color:{fg}}}
.card{{position:relative;width:100%;height:100%;padding:72px;background:radial-gradient(circle at 92% 4%,{accent}22,transparent 28%),{bg}}}
.frame{{position:relative;height:100%;padding:76px 72px 64px;background:{panel};border:1px solid {soft};border-radius:44px;overflow:hidden;box-shadow:0 26px 70px #00000018}}
.frame:before{{content:'';position:absolute;left:0;top:0;width:16px;height:100%;background:{accent}}}
.top{{display:flex;align-items:center;justify-content:space-between;position:relative;z-index:2}}
.kicker{{font-size:25px;font-weight:800;letter-spacing:.18em;color:{accent}}}.counter{{font-size:24px;font-weight:750;color:{fg}88}}
h1{{font-size:{title_size}px;line-height:1.12;letter-spacing:-.045em;margin:{title_margin}px 0 34px;max-width:980px}}
.rule{{width:112px;height:10px;border-radius:8px;background:{accent};margin-bottom:42px}}
.body{{font-size:39px;line-height:1.72;letter-spacing:-.012em;max-width:960px;color:{fg}e6}}
.hero{{position:absolute;left:72px;right:72px;bottom:240px;height:510px;border-radius:34px;background-size:cover;background-position:center;box-shadow:0 18px 48px #0003}}
ul{{list-style:none;padding:0;margin:36px 0 0;display:grid;gap:25px}}li{{display:grid;grid-template-columns:72px 1fr;gap:24px;align-items:start;padding:26px 28px;border-radius:26px;background:{soft}}}li span{{width:58px;height:58px;border-radius:18px;display:grid;place-items:center;background:{accent};color:{marker_color};font-size:23px;font-weight:800}}li p{{margin:2px 0 0;font-size:34px;line-height:1.55}}
.quote{{font-size:61px;line-height:1.38;font-weight:720;letter-spacing:-.035em;padding:55px;border-radius:34px;background:{soft};border-left:12px solid {accent}}}.source{{position:absolute;left:72px;right:72px;bottom:105px;padding-top:30px;border-top:2px solid {soft};display:flex;justify-content:space-between;align-items:end;color:{fg}88;font-size:22px}}.source strong{{color:{fg};font-size:25px}}.source small{{max-width:650px;text-align:right;line-height:1.45}}
.badge{{display:inline-flex;padding:13px 20px;border-radius:999px;background:{soft};color:{accent};font-size:22px;font-weight:800;margin-top:25px}}
</style></head><body><main class="card"><article class="frame {kind}"><div class="top"><div class="kicker">{kicker}</div><div class="counter">{page:02d} / {total:02d}</div></div><h1>{title}</h1><div class="rule"></div>{hero_html}{content_html}<div class="source"><strong>{source or 'X2RED'}</strong><small>{footer}</small></div></article></main></body></html>"""

    @staticmethod
    def _image_src(value: str) -> str:
        if not value:
            return ""
        path = Path(value)
        if path.is_file():
            mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            return f"data:{mime};base64,{encoded}"
        if value.startswith("https://pbs.twimg.com/"):
            return value
        return ""
