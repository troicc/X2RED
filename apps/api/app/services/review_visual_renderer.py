from __future__ import annotations

import html
import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import CardRender, DraftRevision
from app.services.card_html_renderer import HtmlCardRenderer
from app.services.cards import CardService
from app.services.publication_safety import public_card_spec, strip_internal_markers


class ReviewVisualRenderer(HtmlCardRenderer):
    """High-contrast semantic renderer for human-approved storyboards."""

    palettes = {
        "electric_blue": ("#08111f", "#0f1c31", "#f7fbff", "#5ee7ff", "#1c3350", "#8ea8c4"),
        "signal_red": ("#f4efe8", "#fffaf4", "#1b1714", "#ef3e55", "#f3dedb", "#756962"),
        "acid_green": ("#0d100d", "#161c16", "#f7fff4", "#b8ff4a", "#2a3725", "#a7b79d"),
        "ink": ("#e9e7e1", "#fbfaf6", "#11110f", "#11110f", "#dedbd2", "#6f6c65"),
        "violet": ("#100d22", "#1b1733", "#fbf9ff", "#a991ff", "#31295a", "#a69bc3"),
    }

    def _document(self, raw_spec: dict[str, Any], template: str) -> str:
        spec = public_card_spec(raw_spec)
        palette_name = str(spec.get("palette") or "electric_blue")
        bg, panel, fg, accent, soft, muted = self.palettes.get(
            palette_name,
            self.palettes["electric_blue"],
        )
        kind = str(spec.get("kind") or "key_takeaways")
        title = html.escape(str(spec.get("title") or "").strip())
        body = html.escape(str(spec.get("body") or "").strip()).replace("\n", "<br>")
        kicker = html.escape(strip_internal_markers(str(spec.get("kicker") or "").strip()))
        items = [
            html.escape(str(item).strip())
            for item in (spec.get("items") or [])[:4]
            if str(item).strip()
        ]
        page = int(spec.get("page") or 1)
        total = int(spec.get("total") or 1)
        hero = self._image_src(str(spec.get("hero_image") or ""))
        style = str(spec.get("visual_style") or "technical_blueprint")
        composition = self._composition(
            kind=kind,
            title=title,
            body=body,
            items=items,
            hero=hero,
            accent=accent,
        )
        texture = self._texture(style, accent, soft)
        dark = palette_name in {"electric_blue", "acid_green", "violet"}
        contrast = "#071019" if dark else "#ffffff"
        return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{box-sizing:border-box}}html,body{{margin:0;width:{self.width}px;height:{self.height}px;overflow:hidden}}
body{{font-family:Inter,-apple-system,BlinkMacSystemFont,'PingFang SC','Noto Sans CJK SC',sans-serif;background:{bg};color:{fg}}}
.canvas{{position:relative;width:100%;height:100%;padding:42px;background:{texture},{bg};overflow:hidden}}
.sheet{{position:relative;width:100%;height:100%;overflow:hidden;border:1px solid {soft};border-radius:42px;background:{panel};box-shadow:0 32px 90px #00000030}}
.sheet:before{{content:'';position:absolute;inset:0;pointer-events:none;background:linear-gradient(115deg,transparent 0 70%,{accent}14 100%)}}
.chrome{{position:absolute;z-index:20;left:50px;right:50px;top:42px;display:flex;align-items:center;justify-content:space-between}}
.kicker{{display:inline-flex;align-items:center;min-height:42px;padding:0 15px;border:1px solid {accent}70;border-radius:999px;color:{accent};font-size:18px;font-weight:850;letter-spacing:.08em}}
.counter{{color:{muted};font-size:19px;font-weight:760}}.counter strong{{color:{accent}}}
.stage{{position:absolute;inset:0;padding:124px 64px 64px}}h1{{margin:0;color:{fg};font-size:86px;line-height:1.06;letter-spacing:-.052em;font-weight:900}}
.lead{{margin:28px 0 0;color:{muted};font-size:34px;line-height:1.56;letter-spacing:-.018em}}
.hero{{position:absolute;overflow:hidden;margin:0}}.hero img{{width:100%;height:100%;display:block;object-fit:cover}}.hero i{{position:absolute;inset:0}}
.big-stat{{display:flex;align-items:flex-end;gap:18px;margin-top:46px;color:{accent};font-size:170px;line-height:.9;font-weight:950;letter-spacing:-.08em}}.big-stat small{{padding-bottom:18px;color:{muted};font-size:28px;letter-spacing:0;font-weight:720}}
.tiles{{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:34px}}.tile{{min-height:195px;padding:27px;border-radius:28px;background:{soft};border:1px solid {accent}25}}.tile b{{display:block;margin-bottom:13px;color:{accent};font-size:19px}}.tile span{{font-size:29px;line-height:1.42;font-weight:720}}
.diagram{{position:relative;height:900px;margin-top:16px}}.core{{position:absolute;left:50%;top:50%;width:320px;height:320px;transform:translate(-50%,-50%);display:grid;place-items:center;padding:34px;border-radius:50%;background:{accent};color:{contrast};font-size:40px;line-height:1.2;text-align:center;font-weight:900;box-shadow:0 28px 80px #0004}}.node{{position:absolute;width:325px;min-height:175px;padding:27px;border:1px solid {accent}45;border-radius:28px;background:{soft};font-size:27px;line-height:1.45;font-weight:690}}.node:after{{content:'';position:absolute;width:74px;height:2px;background:{accent}75}}.n1{{left:0;top:35px}}.n1:after{{right:-74px;bottom:42px}}.n2{{right:0;top:35px}}.n2:after{{left:-74px;bottom:42px}}.n3{{left:0;bottom:35px}}.n3:after{{right:-74px;top:42px}}.n4{{right:0;bottom:35px}}.n4:after{{left:-74px;top:42px}}
.compare{{display:grid;grid-template-columns:1fr 82px 1fr;gap:16px;align-items:stretch;margin-top:46px}}.compare-panel{{min-height:740px;padding:33px;border-radius:32px;background:{soft};border:1px solid {accent}28}}.compare-panel h2{{margin:0 0 28px;color:{accent};font-size:31px}}.compare-panel p{{margin:0 0 24px;font-size:30px;line-height:1.46;font-weight:700}}.compare-arrow{{display:grid;place-items:center;color:{accent};font-size:60px;font-weight:900}}
.flow{{display:grid;gap:18px;margin-top:40px}}.step{{position:relative;display:grid;grid-template-columns:90px 1fr;gap:23px;align-items:center;min-height:160px;padding:25px 29px;border-radius:29px;background:{soft};border:1px solid {accent}24}}.step b{{display:grid;width:70px;height:70px;place-items:center;border-radius:23px;background:{accent};color:{contrast};font-size:24px}}.step span{{font-size:31px;line-height:1.42;font-weight:720}}.step:not(:last-child):after{{content:'↓';position:absolute;left:52px;bottom:-31px;color:{accent};font-size:34px;font-weight:900}}
.list{{display:grid;gap:18px;margin-top:42px}}.row{{display:grid;grid-template-columns:72px 1fr;gap:21px;align-items:start;padding:25px 27px;border-radius:28px;background:{soft};border:1px solid {accent}25}}.row b{{display:grid;width:57px;height:57px;place-items:center;border-radius:19px;background:{accent};color:{contrast};font-size:22px}}.row span{{font-size:31px;line-height:1.47;font-weight:700}}
.close{{position:absolute;left:70px;right:70px;top:50%;transform:translateY(-48%);padding:72px 66px;border-radius:40px;background:{soft};border:1px solid {accent}38}}.close:before{{content:'“';position:absolute;left:28px;top:-52px;color:{accent};font:170px/1 Georgia,serif}}.close h1{{font-size:76px}}.close p{{margin:42px 0 0;font-size:39px;line-height:1.58;font-weight:650}}
</style></head><body><main class="canvas"><article class="sheet"><header class="chrome"><span class="kicker">{kicker}</span><span class="counter"><strong>{page:02d}</strong> / {total:02d}</span></header>{composition}</article></main></body></html>"""

    @staticmethod
    def _texture(style: str, accent: str, soft: str) -> str:
        if style == "data_poster":
            return f"linear-gradient(145deg,{accent}22 0 18%,transparent 18% 100%),radial-gradient(circle at 92% 8%,{accent}40,transparent 30%)"
        if style == "editorial_collage":
            return f"linear-gradient(112deg,{soft} 0 22%,transparent 22% 100%),radial-gradient(circle at 80% 20%,{accent}26,transparent 28%)"
        if style == "paper_cut":
            return f"repeating-linear-gradient(0deg,transparent 0 60px,{accent}12 60px 62px)"
        return f"linear-gradient({accent}10 1px,transparent 1px),linear-gradient(90deg,{accent}10 1px,transparent 1px),radial-gradient(circle at 88% 6%,{accent}32,transparent 30%)"

    def _composition(
        self,
        *,
        kind: str,
        title: str,
        body: str,
        items: list[str],
        hero: str,
        accent: str,
    ) -> str:
        if kind == "hero_cover":
            if hero:
                return (
                    f'<figure class="hero" style="inset:0"><img src="{hero}" alt=""><i style="background:linear-gradient(180deg,#0000 0%,#0004 35%,#000e 100%)"></i></figure>'
                    f'<section class="stage" style="display:flex;flex-direction:column;justify-content:flex-end;padding-bottom:104px"><h1 style="max-width:1030px;color:#fff;text-shadow:0 5px 36px #000a">{title}</h1><p class="lead" style="max-width:900px;color:#ffffffe5">{body}</p></section>'
                )
            return f'<section class="stage" style="display:flex;flex-direction:column;justify-content:center"><span style="display:block;width:120px;height:12px;margin-bottom:38px;border-radius:99px;background:{accent}"></span><h1 style="font-size:102px;max-width:1050px">{title}</h1><p class="lead" style="max-width:920px">{body}</p></section>'
        if kind == "key_result":
            stat = self._extract_stat(title + " " + body + " " + " ".join(items))
            tiles = "".join(
                f'<div class="tile"><b>{index:02d}</b><span>{item}</span></div>'
                for index, item in enumerate(items[:4], start=1)
            )
            stat_html = f'<div class="big-stat">{html.escape(stat)}<small>核心结果</small></div>' if stat else ""
            return f'<section class="stage"><h1 style="font-size:70px">{title}</h1>{stat_html}<p class="lead">{body}</p><div class="tiles">{tiles}</div></section>'
        if kind == "concept_diagram":
            nodes = "".join(
                f'<div class="node n{index}">{item}</div>'
                for index, item in enumerate(items[:4], start=1)
            )
            core = title if len(title) <= 12 else "核心机制"
            return f'<section class="stage"><h1 style="font-size:68px">{title}</h1><div class="diagram"><div class="core">{html.escape(core)}</div>{nodes}</div></section>'
        if kind == "before_after":
            midpoint = max(1, len(items) // 2)
            left = items[:midpoint]
            right = items[midpoint:] or items[-1:]
            left_html = "".join(f"<p>{item}</p>" for item in left)
            right_html = "".join(f"<p>{item}</p>" for item in right)
            return f'<section class="stage"><h1 style="font-size:68px">{title}</h1><div class="compare"><div class="compare-panel"><h2>过去</h2>{left_html}</div><div class="compare-arrow">→</div><div class="compare-panel"><h2>现在</h2>{right_html}</div></div></section>'
        if kind == "workflow_flow":
            steps = "".join(
                f'<div class="step"><b>{index:02d}</b><span>{item}</span></div>'
                for index, item in enumerate(items[:4], start=1)
            )
            return f'<section class="stage"><h1 style="font-size:68px">{title}</h1><div class="flow">{steps}</div></section>'
        if kind == "opinion_close":
            return f'<section class="stage"><div class="close"><h1>{title}</h1><p>{body}</p><span style="display:block;width:136px;height:10px;margin-top:44px;border-radius:99px;background:{accent}"></span></div></section>'
        rows = "".join(
            f'<div class="row"><b>{index:02d}</b><span>{item}</span></div>'
            for index, item in enumerate(items[:4], start=1)
        )
        lead = f'<p class="lead">{body}</p>' if body else ""
        return f'<section class="stage"><h1 style="font-size:72px">{title}</h1>{lead}<div class="list">{rows}</div></section>'

    @staticmethod
    def _extract_stat(value: str) -> str:
        match = re.search(
            r"(?:\d+(?:\.\d+)?\s*(?:倍|%|ms|s|秒|分钟|万|亿))",
            value,
            flags=re.I,
        )
        return match.group(0).replace(" ", "") if match else ""


class ReviewVisualService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.renderer = ReviewVisualRenderer()
        self.fallback = CardService(settings)

    def render(
        self,
        db: Session,
        *,
        draft: DraftRevision,
        pages: list[dict[str, Any]],
        art_direction: dict[str, Any],
        template: str,
        artifact_id: str,
    ) -> CardRender:
        render = CardRender(
            draft_id=draft.id,
            template=template,
            status="rendering",
        )
        db.add(render)
        db.flush()
        output_dir = self.settings.media_dir / "cards" / render.id
        output_dir.mkdir(parents=True, exist_ok=True)
        specs: list[dict[str, Any]] = []
        total = len(pages)
        for index, raw in enumerate(pages, start=1):
            spec = public_card_spec(raw)
            spec["page"] = index
            spec["total"] = total
            spec["visual_style"] = str(
                art_direction.get("style") or "technical_blueprint"
            )
            spec["palette"] = str(
                art_direction.get("palette") or "electric_blue"
            )
            spec["review_artifact_id"] = artifact_id
            specs.append(spec)
        output_paths = self.renderer.render_many(output_dir, specs, template)
        renderer_name = "reviewed-semantic-playwright"
        if len(output_paths) != len(specs):
            output_paths = []
            renderer_name = "reviewed-pillow-fallback"
            for index, spec in enumerate(specs, start=1):
                path = output_dir / f"{index:02d}.png"
                self.fallback._draw_fallback(path, spec, template)
                output_paths.append(str(path.resolve()))
        for spec in specs:
            spec["renderer"] = renderer_name
        render.spec_json = json.dumps(specs, ensure_ascii=False)
        render.output_paths_json = json.dumps(output_paths, ensure_ascii=False)
        render.status = "rendered"
        render.error = ""
        db.flush()
        return render
