from __future__ import annotations

import html
import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import CardRender, DraftRevision
from app.services.card_html_renderer import HtmlCardRenderer
from app.services.cards import CardRenderError, CardService
from app.services.skills import binding_for


_TEMPLATE_ALIASES = {
    "warm_editorial": "editorial_minimal",
    "dark_tech": "tech_minimal",
    "editorial_minimal": "editorial_minimal",
    "tech_minimal": "tech_minimal",
    "clean_news": "clean_news",
    "warm_note": "warm_note",
}


class RichHtmlCardRenderer(HtmlCardRenderer):
    _palette_map = {
        "neutral": ("#F2F3F5", "#FFFFFF", "#171A21", "#5364F2", "#E8EAF1"),
        "macaron": ("#F7F1E8", "#FFFDF8", "#282430", "#E8655A", "#E8DCEB"),
        "warm": ("#F8EADB", "#FFF9F1", "#30231E", "#C85D35", "#F0D5BF"),
        "neon": ("#120D1B", "#1D1428", "#F8F7FF", "#39FFB6", "#342541"),
        "monochrome": ("#ECECEA", "#FAFAF7", "#111111", "#111111", "#D9D9D4"),
    }

    def _document(self, spec: dict, template: str) -> str:
        visual_style = str(spec.get("visual_style") or "editorial")
        layout = str(spec.get("layout") or "balanced")
        palette_name = str(spec.get("palette") or "neutral")
        bg, panel, fg, accent, soft = self._palette_map.get(
            palette_name,
            self._palette_map["neutral"],
        )
        if palette_name == "auto":
            bg, panel, fg, accent, soft = self._palette_map["neutral"]
        dark = palette_name == "neon" or template == "tech_minimal"
        if template == "tech_minimal" and palette_name in {"auto", "neutral"}:
            bg, panel, fg, accent, soft = "#070A11", "#111827", "#F8FAFC", "#7DD3FC", "#1E293B"
            dark = True
        elif template == "warm_note" and palette_name in {"auto", "neutral"}:
            bg, panel, fg, accent, soft = "#F7F0E8", "#FFFAF4", "#2A211D", "#E86D4C", "#F1E1D5"
        elif template == "clean_news" and palette_name in {"auto", "neutral"}:
            bg, panel, fg, accent, soft = "#EEF2F7", "#FFFFFF", "#10213B", "#316FF6", "#E4EBF5"

        kind = html.escape(str(spec.get("kind") or "content"))
        title = html.escape(str(spec.get("title") or ""))
        body = html.escape(str(spec.get("body") or "")).replace("\n", "<br>")
        kicker = html.escape(str(spec.get("kicker") or "X2RED EDITORIAL"))
        source = html.escape(str(spec.get("source") or ""))
        footer = html.escape(str(spec.get("footer") or ""))
        page = int(spec.get("page") or 1)
        total = int(spec.get("total") or 1)
        items = spec.get("items") if isinstance(spec.get("items"), list) else []
        hero = self._image_src(str(spec.get("hero_image") or ""))
        marker_color = "#071018" if dark else "#FFFFFF"

        style_values = {
            "editorial": ("44px", "0", "none", "serif"),
            "swiss": ("22px", ".08em", "uppercase", "sans"),
            "knowledge": ("30px", ".02em", "none", "sans"),
            "poster": ("8px", "-.02em", "uppercase", "sans"),
            "notebook": ("34px", ".01em", "none", "sans"),
            "bold": ("18px", "-.01em", "uppercase", "sans"),
            "minimal": ("42px", ".04em", "uppercase", "sans"),
        }
        radius, tracking, transform, family = style_values.get(visual_style, style_values["editorial"])
        font_family = "Georgia,'Songti SC','Noto Serif CJK SC',serif" if family == "serif" else "Inter,-apple-system,BlinkMacSystemFont,'PingFang SC','Noto Sans CJK SC',sans-serif"
        layout_values = {
            "sparse": (104, 46, 2, 104),
            "balanced": (82, 38, 4, 76),
            "dense": (66, 31, 6, 52),
            "list": (76, 33, 7, 60),
            "comparison": (72, 30, 6, 54),
            "flow": (74, 31, 6, 56),
            "quadrant": (70, 29, 4, 52),
        }
        title_size, body_size, item_limit, title_margin = layout_values.get(
            layout,
            layout_values["balanced"],
        )
        if kind == "cover":
            title_size = max(title_size, 92)
            title_margin = 118
        visible_items = items[:item_limit]
        list_class = f"items {layout}"
        items_html = "".join(
            f'<li><span>{index:02d}</span><p>{html.escape(str(item))}</p></li>'
            for index, item in enumerate(visible_items, start=1)
        )
        content_html = (
            f'<ul class="{list_class}">{items_html}</ul>'
            if items_html
            else f'<div class="body">{body}</div>'
        )
        hero_html = (
            f'<div class="hero"><img src="{hero}" alt=""><i></i></div>'
            if hero
            else ""
        )
        decorative = {
            "poster": "repeating-linear-gradient(90deg,transparent 0 22px," + accent + "18 22px 24px)",
            "notebook": "repeating-linear-gradient(0deg,transparent 0 62px," + accent + "18 62px 64px)",
            "swiss": "linear-gradient(115deg," + accent + "16,transparent 46%)",
        }.get(visual_style, "radial-gradient(circle at 92% 4%," + accent + "22,transparent 28%)")
        return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}}html,body{{margin:0;width:{self.width}px;height:{self.height}px;overflow:hidden}}body{{font-family:{font_family};background:{bg};color:{fg}}}
.card{{position:relative;width:100%;height:100%;padding:72px;background:{decorative},{bg}}}
.frame{{position:relative;height:100%;padding:72px 70px 62px;background:{panel};border:1px solid {soft};border-radius:{radius};overflow:hidden;box-shadow:0 26px 70px #00000018}}
.frame:before{{content:'';position:absolute;left:0;top:0;width:{'24px' if visual_style in {'poster','bold'} else '12px'};height:100%;background:{accent}}}
.top{{display:flex;align-items:center;justify-content:space-between;position:relative;z-index:3}}.kicker{{font-size:23px;font-weight:850;letter-spacing:.17em;text-transform:{transform};color:{accent}}}.counter{{font-size:23px;font-weight:750;color:{fg}88}}
h1{{position:relative;z-index:3;margin:{title_margin}px 0 30px;max-width:990px;font-size:{title_size}px;line-height:1.11;letter-spacing:{tracking};font-weight:{'900' if visual_style in {'poster','bold'} else '780'}}}.rule{{position:relative;z-index:3;width:{'220px' if visual_style == 'swiss' else '110px'};height:{'6px' if visual_style == 'minimal' else '10px'};border-radius:8px;background:{accent};margin-bottom:36px}}
.body{{position:relative;z-index:3;max-width:980px;color:{fg}e8;font-size:{body_size}px;line-height:{'1.55' if layout == 'dense' else '1.68'};letter-spacing:-.01em}}
.hero{{position:absolute;z-index:1;left:70px;right:70px;bottom:220px;height:500px;border-radius:28px;overflow:hidden;box-shadow:0 18px 48px #0003}}.hero img{{display:block;width:100%;height:100%;object-fit:cover}}.hero i{{position:absolute;inset:0;background:linear-gradient(180deg,transparent 40%,{panel}AA)}}
ul.items{{position:relative;z-index:3;list-style:none;padding:0;margin:26px 0 0;display:grid;gap:20px}}ul.items li{{display:grid;grid-template-columns:68px 1fr;gap:20px;align-items:start;padding:23px 25px;border-radius:22px;background:{soft}}ul.items li span{{width:54px;height:54px;border-radius:16px;display:grid;place-items:center;background:{accent};color:{marker_color};font-size:21px;font-weight:850}}ul.items li p{{margin:1px 0 0;font-size:{body_size - 3}px;line-height:1.5}}
ul.items.comparison{{grid-template-columns:repeat(2,minmax(0,1fr))}}ul.items.comparison li{{grid-template-columns:1fr;min-height:210px}}ul.items.comparison li span{{margin-bottom:8px}}ul.items.quadrant{{grid-template-columns:repeat(2,minmax(0,1fr))}}ul.items.quadrant li{{grid-template-columns:1fr;min-height:205px}}ul.items.flow li{{position:relative;margin-left:18px}}ul.items.flow li:before{{content:'';position:absolute;left:-23px;top:44px;bottom:-42px;width:3px;background:{accent}55}}ul.items.flow li:last-child:before{{display:none}}
.source{{position:absolute;z-index:4;left:70px;right:70px;bottom:92px;padding-top:26px;border-top:2px solid {soft};display:flex;justify-content:space-between;align-items:end;color:{fg}88;font-size:21px}}.source strong{{color:{fg};font-size:24px}}.source small{{max-width:650px;text-align:right;line-height:1.45}}
</style></head><body><main class="card"><article class="frame {kind}"><div class="top"><div class="kicker">{kicker}</div><div class="counter">{page:02d} / {total:02d}</div></div><h1>{title}</h1><div class="rule"></div>{hero_html}{content_html}<div class="source"><strong>{source or 'X2RED'}</strong><small>{footer}</small></div></article></main></body></html>"""


class RichCardService(CardService):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.html_renderer = RichHtmlCardRenderer()

    def render(
        self,
        db: Session,
        draft: DraftRevision,
        *,
        template: str,
        visual_style: str,
        layout: str,
        palette: str,
        material_strategy: str,
        max_cards: int,
    ) -> CardRender:
        resolved_template = _TEMPLATE_ALIASES.get(template)
        if resolved_template is None:
            raise CardRenderError(f"未知卡片模板：{template}")
        storyboard = binding_for(db, "visual.storyboard", self.settings.model_name)
        art_direction = binding_for(db, "visual.art_direction", self.settings.model_name)
        layout_binding = binding_for(db, "visual.layout_selector", self.settings.model_name)
        palette_binding = binding_for(db, "visual.palette_selector", self.settings.model_name)
        material_binding = binding_for(db, "visual.material_intake", self.settings.model_name)
        if not art_direction.enabled:
            resolved_template = "clean_news"
        resolved_style = self._style(draft, visual_style, resolved_template)
        resolved_layout = layout if layout != "auto" else self._layout(draft)
        resolved_palette = palette if palette != "auto" else self._palette(resolved_style, resolved_template)
        resolved_material = material_strategy
        if not layout_binding.enabled:
            resolved_layout = "balanced"
        if not palette_binding.enabled:
            resolved_palette = "neutral"
        if not material_binding.enabled:
            resolved_material = "text_only"

        render = CardRender(draft_id=draft.id, template=resolved_template, status="rendering")
        db.add(render)
        db.flush()
        output_dir = self.settings.media_dir / "cards" / render.id
        output_dir.mkdir(parents=True, exist_ok=True)
        specs = self._build_specs(draft, max_cards=max_cards, use_analysis=storyboard.enabled)
        for index, spec in enumerate(specs, start=1):
            spec["page"] = index
            spec["total"] = len(specs)
            spec["visual_style"] = resolved_style
            spec["layout"] = self._page_layout(spec, resolved_layout)
            spec["palette"] = resolved_palette
            spec["material_strategy"] = resolved_material
            if resolved_material == "text_only":
                spec["hero_image"] = ""
            elif resolved_material == "source_first" and index != 1:
                spec["hero_image"] = ""

        try:
            output_paths = self.html_renderer.render_many(output_dir, specs, resolved_template)
            renderer = "html-playwright-rich"
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

    @staticmethod
    def _style(draft: DraftRevision, requested: str, template: str) -> str:
        if requested != "auto":
            return requested
        text = f"{draft.title} {draft.body[:1200]}".lower()
        if any(token in text for token in ("步骤", "教程", "清单", "方法")):
            return "knowledge"
        if any(token in text for token in ("设计", "ui", "ux", "产品")):
            return "swiss"
        if any(token in text for token in ("观点", "判断", "争议", "为什么")):
            return "editorial"
        if any(token in text for token in ("警告", "避坑", "错误", "千万")):
            return "bold"
        if template == "tech_minimal":
            return "minimal"
        return "editorial"

    @staticmethod
    def _layout(draft: DraftRevision) -> str:
        body = draft.body
        if len(body) < 360:
            return "sparse"
        if body.count("\n") >= 8 or len(body) > 1800:
            return "dense"
        if any(token in body for token in ("对比", "而不是", "相比", "vs", "VS")):
            return "comparison"
        if sum(1 for line in body.splitlines() if line.strip().startswith(("1.", "2.", "3.", "- "))) >= 3:
            return "list"
        return "balanced"

    @staticmethod
    def _palette(style: str, template: str) -> str:
        if template == "tech_minimal":
            return "neon"
        if template == "warm_note" or style == "notebook":
            return "warm"
        if style == "knowledge":
            return "macaron"
        if style in {"poster", "bold"}:
            return "monochrome"
        return "neutral"

    @staticmethod
    def _page_layout(spec: dict, requested: str) -> str:
        kind = str(spec.get("kind") or "content")
        items = spec.get("items") if isinstance(spec.get("items"), list) else []
        if kind == "cover":
            return "sparse"
        if kind == "facts" and len(items) >= 4:
            return "list"
        if kind == "caution":
            return "list"
        if requested == "comparison" and len(items) < 2:
            return "balanced"
        if requested == "quadrant" and len(items) < 4:
            return "balanced"
        return requested
