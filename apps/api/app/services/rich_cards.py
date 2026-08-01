from __future__ import annotations

import html
import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import CardRender, DraftRevision
from app.services.card_html_renderer import HtmlCardRenderer
from app.services.cards import CardRenderError, CardService
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


class RichHtmlCardRenderer(HtmlCardRenderer):
    """Render semantic publish-ready cards instead of decorated prose pages."""

    _palette_map = {
        "neutral": ("#EDF1F7", "#FFFFFF", "#131722", "#4F63F5", "#E9ECF6", "#6B7280"),
        "macaron": ("#F5EFE8", "#FFFDF8", "#282430", "#E8655A", "#F3E2DE", "#756D78"),
        "warm": ("#F6EDE3", "#FFFAF4", "#2B211D", "#D96845", "#F2DED1", "#786A64"),
        "neon": ("#080A10", "#111827", "#F8FAFC", "#6EE7F9", "#1C2A3A", "#9CA3AF"),
        "monochrome": ("#ECECEA", "#FAFAF7", "#111111", "#111111", "#DEDED8", "#6A6A66"),
    }

    def _document(self, spec: dict[str, Any], template: str) -> str:
        spec = public_card_spec(spec)
        visual_style = str(spec.get("visual_style") or "editorial")
        layout = str(spec.get("layout") or "balanced")
        palette_name = str(spec.get("palette") or "neutral")
        bg, panel, fg, accent, soft, muted = self._palette_map.get(
            palette_name,
            self._palette_map["neutral"],
        )
        if template == "tech_minimal" and palette_name in {"auto", "neutral"}:
            bg, panel, fg, accent, soft, muted = self._palette_map["neon"]
        elif template == "warm_note" and palette_name in {"auto", "neutral"}:
            bg, panel, fg, accent, soft, muted = self._palette_map["warm"]
        elif template == "clean_news" and palette_name in {"auto", "neutral"}:
            bg, panel, fg, accent, soft, muted = (
                "#EDF2F8",
                "#FFFFFF",
                "#10213B",
                "#316FF6",
                "#E6EDF7",
                "#68758A",
            )

        kind = str(spec.get("kind") or "key_takeaways")
        title = html.escape(str(spec.get("title") or ""))
        body = html.escape(str(spec.get("body") or "")).replace("\n", "<br>")
        kicker = html.escape(strip_internal_markers(str(spec.get("kicker") or "")))
        page = int(spec.get("page") or 1)
        total = int(spec.get("total") or 1)
        items = spec.get("items") if isinstance(spec.get("items"), list) else []
        items = [html.escape(str(item)) for item in items[:4] if str(item).strip()]
        hero = self._image_src(str(spec.get("hero_image") or ""))
        content_type = html.escape(str(spec.get("content_type") or ""))

        dark = template == "tech_minimal" or palette_name == "neon"
        contrast = "#071018" if dark else "#FFFFFF"
        radius = {
            "poster": "8px",
            "swiss": "22px",
            "minimal": "34px",
            "notebook": "42px",
        }.get(visual_style, "38px")
        family = (
            "Georgia,'Songti SC','Noto Serif CJK SC',serif"
            if visual_style == "editorial"
            else "Inter,-apple-system,BlinkMacSystemFont,'PingFang SC','Noto Sans CJK SC',sans-serif"
        )
        composition = self._composition(
            kind=kind,
            title=title,
            body=body,
            kicker=kicker,
            items=items,
            hero=hero,
            accent=accent,
            layout=layout,
        )
        texture = {
            "poster": f"linear-gradient(135deg,{accent}18 0 20%,transparent 20% 100%)",
            "swiss": f"linear-gradient(112deg,{accent}16,transparent 48%)",
            "notebook": f"repeating-linear-gradient(0deg,transparent 0 64px,{accent}12 64px 66px)",
            "minimal": f"radial-gradient(circle at 88% 8%,{accent}18,transparent 30%)",
        }.get(visual_style, f"radial-gradient(circle at 90% 5%,{accent}1f,transparent 31%)")
        shared_css = self._shared_css(fg, accent, soft, muted, contrast)
        return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}}html,body{{margin:0;width:{self.width}px;height:{self.height}px;overflow:hidden}}
body{{font-family:{family};background:{bg};color:{fg}}}
.card{{position:relative;width:100%;height:100%;padding:54px;background:{texture},{bg};overflow:hidden}}
.frame{{position:relative;width:100%;height:100%;overflow:hidden;border:1px solid {soft};border-radius:{radius};background:{panel};box-shadow:0 26px 72px #00000016}}
.chrome{{position:absolute;z-index:12;top:40px;left:48px;right:48px;display:flex;align-items:center;justify-content:space-between}}
.kicker{{display:inline-flex;align-items:center;min-height:44px;padding:0 16px;border-radius:999px;background:{soft};color:{accent};font-size:20px;font-weight:850;letter-spacing:.06em}}
.counter{{font-size:20px;font-weight:800;color:{muted}}}.counter b{{color:{accent}}}
.content-type{{position:absolute;right:44px;bottom:34px;color:{muted};font-size:16px;letter-spacing:.12em;text-transform:uppercase}}
{shared_css}
</style></head><body><main class="card"><article class="frame {kind}"><header class="chrome"><span class="kicker">{kicker}</span><span class="counter"><b>{page:02d}</b> / {total:02d}</span></header>{composition}<small class="content-type">{content_type}</small></article></main></body></html>"""

    @staticmethod
    def _shared_css(fg: str, accent: str, soft: str, muted: str, contrast: str) -> str:
        return f"""
.stage{{position:absolute;inset:0;padding:132px 72px 76px}}
.eyebrow{{color:{accent};font-size:21px;font-weight:850;letter-spacing:.08em}}
h1{{margin:0;color:{fg};font-size:84px;line-height:1.08;letter-spacing:-.045em;font-weight:880}}
.lead{{margin:28px 0 0;color:{muted};font-size:34px;line-height:1.58;letter-spacing:-.012em}}
.hero{{position:absolute;overflow:hidden}}.hero img{{width:100%;height:100%;object-fit:cover;display:block}}.hero i{{position:absolute;inset:0}}
.pills{{display:grid;gap:18px;margin-top:36px}}.pill{{display:grid;grid-template-columns:58px 1fr;gap:18px;align-items:start;padding:24px 26px;border-radius:25px;background:{soft}}}.pill b{{display:grid;width:48px;height:48px;place-items:center;border-radius:16px;background:{accent};color:{contrast};font-size:20px}}.pill span{{color:{fg};font-size:31px;line-height:1.48;font-weight:680}}
.diagram{{position:relative;height:920px;margin-top:18px}}.core{{position:absolute;left:50%;top:50%;width:280px;height:280px;transform:translate(-50%,-50%);display:grid;place-items:center;padding:30px;border-radius:50%;background:{accent};color:{contrast};font-size:38px;line-height:1.25;text-align:center;font-weight:850;box-shadow:0 22px 58px #0002}}.node{{position:absolute;width:330px;min-height:170px;padding:24px;border:2px solid {soft};border-radius:26px;background:{soft};color:{fg};font-size:27px;line-height:1.46;font-weight:660}}.node.n1{{left:0;top:30px}}.node.n2{{right:0;top:30px}}.node.n3{{left:0;bottom:30px}}.node.n4{{right:0;bottom:30px}}
.compare{{display:grid;grid-template-columns:1fr 1fr;gap:22px;margin-top:42px}}.compare section{{min-height:720px;padding:32px;border-radius:30px;background:{soft}}}.compare h2{{margin:0 0 24px;color:{accent};font-size:30px}}.compare p{{margin:0 0 22px;color:{fg};font-size:30px;line-height:1.5;font-weight:660}}
.flow{{display:grid;gap:18px;margin-top:34px}}.step{{position:relative;display:grid;grid-template-columns:88px 1fr;gap:22px;align-items:center;min-height:160px;padding:24px 28px;border-radius:28px;background:{soft}}}.step b{{display:grid;width:70px;height:70px;place-items:center;border-radius:23px;background:{accent};color:{contrast};font-size:24px}}.step span{{color:{fg};font-size:31px;line-height:1.45;font-weight:680}}.step:not(:last-child):after{{content:'↓';position:absolute;left:51px;bottom:-31px;color:{accent};font-size:34px;font-weight:900}}
.quote{{position:absolute;left:78px;right:78px;top:50%;transform:translateY(-48%);padding:68px 64px;border-radius:38px;background:{soft}}}.quote:before{{content:'“';position:absolute;left:30px;top:-34px;color:{accent};font-size:150px;line-height:1;font-family:Georgia,serif}}.quote h1{{font-size:72px}}.quote p{{margin:42px 0 0;color:{fg};font-size:38px;line-height:1.65;font-weight:650}}
"""

    def _composition(
        self,
        *,
        kind: str,
        title: str,
        body: str,
        kicker: str,
        items: list[str],
        hero: str,
        accent: str,
        layout: str,
    ) -> str:
        if kind == "hero_cover":
            if hero:
                return (
                    f'<figure class="hero" style="inset:0"><img src="{hero}" alt=""><i style="background:linear-gradient(180deg,#00000012 0%,#00000048 45%,#000000d8 100%)"></i></figure>'
                    f'<section class="stage" style="display:flex;flex-direction:column;justify-content:flex-end;padding-bottom:108px"><h1 style="max-width:980px;color:#fff;text-shadow:0 4px 30px #0008">{title}</h1>'
                    f'<p class="lead" style="max-width:900px;color:#ffffffe0">{body}</p></section>'
                )
            return (
                f'<section class="stage" style="display:flex;flex-direction:column;justify-content:center"><div class="eyebrow">{kicker}</div>'
                f'<h1 style="max-width:1010px;margin-top:28px;font-size:96px">{title}</h1><p class="lead" style="max-width:900px">{body}</p>'
                f'<i style="display:block;width:150px;height:12px;margin-top:42px;border-radius:99px;background:{accent}"></i></section>'
            )
        if kind == "concept_diagram":
            nodes = "".join(
                f'<div class="node n{index}">{value}</div>'
                for index, value in enumerate(items[:4], start=1)
            )
            core = title if len(title) <= 12 else "核心机制"
            return (
                f'<section class="stage"><h1 style="font-size:68px">{title}</h1><div class="diagram">'
                f'<div class="core">{html.escape(core)}</div>{nodes}</div></section>'
            )
        if kind == "before_after":
            left = items[:2]
            right = items[2:4] if len(items) > 2 else items[1:]
            if len(items) == 2:
                left, right = items[:1], items[1:]
            left_html = "".join(f"<p>{item}</p>" for item in left)
            right_html = "".join(f"<p>{item}</p>" for item in right)
            return (
                f'<section class="stage"><h1 style="font-size:68px">{title}</h1><div class="compare">'
                f'<section><h2>过去</h2>{left_html}</section><section><h2>现在</h2>{right_html}</section>'
                f'</div></section>'
            )
        if kind == "workflow_flow":
            steps = "".join(
                f'<div class="step"><b>{index:02d}</b><span>{value}</span></div>'
                for index, value in enumerate(items[:4], start=1)
            )
            return f'<section class="stage"><h1 style="font-size:68px">{title}</h1><div class="flow">{steps}</div></section>'
        if kind == "opinion_close":
            return (
                f'<section class="stage"><div class="quote"><h1>{title}</h1><p>{body}</p>'
                f'<i style="display:block;width:130px;height:10px;margin-top:44px;border-radius:99px;background:{accent}"></i></div></section>'
            )

        cards = "".join(
            f'<div class="pill"><b>{index:02d}</b><span>{value}</span></div>'
            for index, value in enumerate(items[:4], start=1)
        )
        body_html = f'<p class="lead">{body}</p>' if body else ""
        if not cards and body:
            cards = f'<div class="pill"><span style="grid-column:1/-1">{body}</span></div>'
        title_size = 70 if len(title) > 14 else 78
        return (
            f'<section class="stage"><h1 style="font-size:{title_size}px">{title}</h1>{body_html}'
            f'<div class="pills" data-layout="{html.escape(layout)}">{cards}</div></section>'
        )


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
        resolved_palette = palette if palette != "auto" else self._palette(
            resolved_style,
            resolved_template,
        )
        resolved_material = material_strategy
        if not layout_binding.enabled:
            resolved_layout = "balanced"
        if not palette_binding.enabled:
            resolved_palette = "neutral"
        if not material_binding.enabled:
            resolved_material = "text_only"

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
        for index, raw_spec in enumerate(specs, start=1):
            spec = public_card_spec(raw_spec)
            spec["page"] = index
            spec["total"] = len(specs)
            spec["visual_style"] = resolved_style
            spec["layout"] = self._page_layout(spec, resolved_layout)
            spec["palette"] = resolved_palette
            spec["material_strategy"] = resolved_material
            if resolved_material == "text_only":
                spec["hero_image"] = ""
            elif resolved_material == "source_first" and spec.get("kind") != "hero_cover":
                spec["hero_image"] = ""
            specs[index - 1] = spec

        try:
            output_paths = self.html_renderer.render_many(
                output_dir,
                specs,
                resolved_template,
            )
            renderer = "html-playwright-semantic"
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
        text = f"{draft.title} {draft.body[:1600]}".lower()
        if any(token in text for token in ("步骤", "教程", "清单", "方法")):
            return "knowledge"
        if any(token in text for token in ("设计", "ui", "ux", "交互", "视觉")):
            return "swiss"
        if any(token in text for token in ("cuda", "gpu", "模型", "mcp", "agent", "api", "内核", "推理")):
            return "minimal"
        if any(token in text for token in ("观点", "判断", "争议", "为什么")):
            return "editorial"
        if template == "tech_minimal":
            return "minimal"
        return "editorial"

    @staticmethod
    def _layout(draft: DraftRevision) -> str:
        body = draft.body
        if any(token in body for token in ("过去", "现在", "而不是", "相比", "vs", "VS")):
            return "comparison"
        numbered = sum(
            1
            for line in body.splitlines()
            if line.strip().startswith(("1.", "2.", "3.", "- ", "•"))
        )
        if numbered >= 3:
            return "flow"
        if len(body) > 1800:
            return "dense"
        if len(body) < 420:
            return "sparse"
        return "balanced"

    @staticmethod
    def _palette(style: str, template: str) -> str:
        if template == "tech_minimal" or style == "minimal":
            return "neon"
        if template == "warm_note" or style == "notebook":
            return "warm"
        if style == "knowledge":
            return "macaron"
        if style in {"poster", "bold"}:
            return "monochrome"
        return "neutral"

    @staticmethod
    def _page_layout(spec: dict[str, Any], requested: str) -> str:
        kind = str(spec.get("kind") or "key_takeaways")
        mapping = {
            "hero_cover": "sparse",
            "key_result": "balanced",
            "concept_diagram": "quadrant",
            "before_after": "comparison",
            "workflow_flow": "flow",
            "key_takeaways": "list",
            "opinion_close": "sparse",
        }
        return mapping.get(kind, requested)
