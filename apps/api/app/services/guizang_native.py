from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import CardRender, DraftRevision
from app.services.cards import CardRenderError
from app.services.model_client import ModelClient, ModelClientError
from app.services.native_deck_renderer import NativeDeckRenderer
from app.services.native_skill_manager import NativeSkillError, NativeSkillManager
from app.services.publication_safety import strip_internal_markers


class GuizangNativeService:
    skill_name = "guizang-social-card-skill"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.manager = NativeSkillManager(settings)
        self.model = ModelClient(settings)
        self.renderer = NativeDeckRenderer()

    def render(
        self,
        db: Session,
        draft: DraftRevision,
        *,
        style_mode: str,
        palette: str,
        material_strategy: str,
        max_cards: int,
    ) -> CardRender:
        if style_mode not in {"editorial", "swiss"}:
            raise CardRenderError("Guizang 原生引擎只支持 Editorial 或 Swiss")
        render = CardRender(
            draft_id=draft.id,
            template=f"guizang_native_{style_mode}",
            status="rendering",
        )
        db.add(render)
        db.flush()
        task_dir = self.settings.media_dir / "cards" / render.id
        task_dir.mkdir(parents=True, exist_ok=True)
        try:
            skill_dir = self.manager.ensure_installed(self.skill_name, install_runtime=True)
            input_assets = self._copy_input_assets(draft, task_dir)
            source_brief = self._source_brief(draft, input_assets)
            references = self._reference_bundle(skill_dir, style_mode)
            plan = self._plan(
                draft=draft,
                source_brief=source_brief,
                references=references,
                style_mode=style_mode,
                palette=palette,
                material_strategy=material_strategy,
                max_cards=max_cards,
            )
            posters_html = self._compose_posters(
                draft=draft,
                source_brief=source_brief,
                references=references,
                plan=plan,
                style_mode=style_mode,
                max_cards=max_cards,
            )
            template_name = (
                "assets/template-editorial-card.html"
                if style_mode == "editorial"
                else "assets/template-swiss-card.html"
            )
            seed = self.manager.read_text(self.skill_name, template_name, max_chars=350_000)
            document = self._assemble_document(seed, posters_html, max_cards=max_cards)
            html_path = task_dir / "index.html"
            html_path.write_text(document, encoding="utf-8")
            (task_dir / "plan.json").write_text(
                json.dumps(plan, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (task_dir / "SOURCES.md").write_text(
                self._sources_markdown(draft, input_assets),
                encoding="utf-8",
            )
            output_paths = self.renderer.render(html_path, task_dir / "output")
            validator = self.renderer.run_upstream_validator(skill_dir, task_dir)
            repair_summary = ""
            if validator.get("ran") and not validator.get("passed"):
                repaired = self._repair_posters(
                    draft=draft,
                    source_brief=source_brief,
                    references=references,
                    plan=plan,
                    posters_html=posters_html,
                    validator_output=str(validator.get("output") or ""),
                    max_cards=max_cards,
                )
                if repaired and repaired != posters_html:
                    posters_html = repaired
                    document = self._assemble_document(seed, posters_html, max_cards=max_cards)
                    html_path.write_text(document, encoding="utf-8")
                    shutil.rmtree(task_dir / "output", ignore_errors=True)
                    output_paths = self.renderer.render(html_path, task_dir / "output")
                    validator = self.renderer.run_upstream_validator(skill_dir, task_dir)
                    repair_summary = "根据上游 validator 做过一轮受限修复"
            status = self.manager.status(self.skill_name)
            spec = {
                "renderer": "guizang-native-upstream-seed-playwright",
                "style_mode": style_mode,
                "palette": palette,
                "material_strategy": material_strategy,
                "plan": plan,
                "input_assets": input_assets,
                "validator": validator,
                "repair_summary": repair_summary,
                "upstream": {
                    "repository": status["source_offer"],
                    "commit": status["commit"],
                    "license": status["license"],
                    "checkout_path": status["path"],
                    "source_available": True,
                },
                "task_files": {
                    "html": str(html_path.resolve()),
                    "sources": str((task_dir / "SOURCES.md").resolve()),
                    "plan": str((task_dir / "plan.json").resolve()),
                },
            }
            render.spec_json = json.dumps(spec, ensure_ascii=False)
            render.output_paths_json = json.dumps(output_paths, ensure_ascii=False)
            render.status = "rendered"
            render.error = ""
        except (NativeSkillError, ModelClientError, CardRenderError, OSError, ValueError) as exc:
            render.status = "failed"
            render.error = str(exc)[:2000]
            db.flush()
            raise CardRenderError(str(exc)) from exc
        db.flush()
        return render

    def _plan(
        self,
        *,
        draft: DraftRevision,
        source_brief: str,
        references: str,
        style_mode: str,
        palette: str,
        material_strategy: str,
        max_cards: int,
    ) -> dict[str, Any]:
        prompt = f"""
你正在运行完整的 guizang-social-card-skill 工作流。先做页面计划，不写 HTML。

目标：小红书 3:4 图文，{max_cards} 张。
视觉系统：{style_mode}
用户配色选择：{palette}
素材策略：{material_strategy}
标题：{strip_internal_markers(draft.title)}
正文：
{strip_internal_markers(draft.body)[:12000]}

来源与可用素材：
{source_brief}

上游 Skill 规则与参考：
{references[:150000]}

严格遵守：
1. 每页只有一个视觉论点，封面兑现正文，不得把制作术语写给读者。
2. 必须从上游 28 个 layout recipe 中选择，不得所有页重复标题+卡片。
3. Editorial 只用六套预设之一；Swiss 只用四套预设之一，不自创颜色。
4. 有真实来源图时优先使用；没有图时选择不依赖伪照片的排版骨架。
5. 中文大标题必须压缩到手机可读，正文不能把整篇文章塞进图片。

只输出 JSON：
{{
  "style_mode":"editorial|swiss",
  "theme":"上游 data-theme 值",
  "story_thesis":"整组一句话视觉论点",
  "pages":[{{
    "page":1,
    "layout_id":"M01-M16 或 S01-S12",
    "role":"cover|evidence|comparison|process|takeaway|closing",
    "headline":"读者可见标题",
    "supporting_copy":["最多四条短文案"],
    "asset":"可用素材相对路径或 none",
    "visual_intent":"构图理由"
  }}]
}}
""".strip()
        plan = self.model.chat_json(
            system_prompt=(
                "你是 Guizang 社交图文的内容策划与版式导演。只使用上游 Skill 定义的"
                "视觉系统、主题和版式骨架。"
            ),
            user_prompt=prompt,
            temperature=0.25,
            reasoning_effort="high",
            max_tokens=10000,
        )
        pages = plan.get("pages")
        if not isinstance(pages, list) or len(pages) < 2:
            raise CardRenderError("Guizang 页面计划无效")
        plan["pages"] = [item for item in pages[:max_cards] if isinstance(item, dict)]
        if len(plan["pages"]) < 2:
            raise CardRenderError("Guizang 页面计划不足两页")
        return plan

    def _compose_posters(
        self,
        *,
        draft: DraftRevision,
        source_brief: str,
        references: str,
        plan: dict[str, Any],
        style_mode: str,
        max_cards: int,
    ) -> str:
        prompt = f"""
按照上游 guizang-social-card-skill 的种子模板组件和 layout recipe，生成可直接插入
`<!-- POSTERS_HERE -->` 的 HTML 片段。不要输出完整 html/head/body，不要输出 Markdown。

视觉系统：{style_mode}
页面计划：
{json.dumps(plan, ensure_ascii=False, indent=2)}

原文：
标题：{strip_internal_markers(draft.title)}
正文：{strip_internal_markers(draft.body)[:12000]}

可用素材：
{source_brief}

上游组件、版式和生产规则：
{references[:170000]}

硬性要求：
- 恰好输出 {len(plan['pages'])} 个 `<section class="poster xhs" ...>`。
- 使用计划中的上游主题 data-theme 和 M/S 版式语法；不得自己另起一套 CSS 系统。
- 只引用任务目录内的相对素材路径，不得引用 file://、localhost 或未知网络图。
- 不写来源说明、AI 提示、制作要求、免责声明到卡片主视觉。
- 所有标签闭合；无横向溢出；正文使用上游可读字号；页码/footer 不碰撞。

只输出 JSON：{{"posters_html":"完整 section 片段"}}
""".strip()
        result = self.model.chat_json(
            system_prompt=(
                "你是 Guizang 原生 HTML 制作 Agent。你的输出会直接进入上游 seed template，"
                "必须复用其 CSS 类、组件和版式，不得用简化卡片替代。"
            ),
            user_prompt=prompt,
            temperature=0.2,
            reasoning_effort="high",
            max_tokens=30000,
        )
        posters_html = self._clean_html(str(result.get("posters_html") or ""))
        count = self.renderer.poster_count(posters_html)
        if count != len(plan["pages"]) or count > max_cards:
            raise CardRenderError(
                f"Guizang HTML 页数不正确：计划 {len(plan['pages'])}，实际 {count}"
            )
        return posters_html

    def _repair_posters(
        self,
        *,
        draft: DraftRevision,
        source_brief: str,
        references: str,
        plan: dict[str, Any],
        posters_html: str,
        validator_output: str,
        max_cards: int,
    ) -> str:
        prompt = f"""
上游 validate-social-deck.mjs 报告了版式问题。只修复报告指出的问题，不换视觉系统，
不把所有页面退化成相同的卡片列表，不增加无意义装饰。

Validator 报告：
{validator_output[-8000:]}

页面计划：{json.dumps(plan, ensure_ascii=False)}
当前 section HTML：
{posters_html[:50000]}

上游 QA 与组件规则：
{references[-60000:]}

只输出 JSON：{{"posters_html":"修复后的完整 section 片段","summary":"修了什么"}}
""".strip()
        result = self.model.chat_json(
            system_prompt="你是 Guizang 版式 QA 修复 Agent，只做一次最小修复。",
            user_prompt=prompt,
            temperature=0.1,
            reasoning_effort="high",
            max_tokens=30000,
        )
        repaired = self._clean_html(str(result.get("posters_html") or ""))
        count = self.renderer.poster_count(repaired)
        if count != len(plan["pages"]) or count > max_cards:
            return posters_html
        return repaired

    def _reference_bundle(self, skill_dir: Path, style_mode: str) -> str:
        paths = [
            "SKILL.md",
            "references/content-planning.md",
            "references/layout-recipes.md",
            "references/components.md",
            "references/portrait-fill.md",
            "references/production-workflow.md",
            "references/theme-presets.md",
            "references/qa-checklist.md",
        ]
        if style_mode == "editorial":
            paths.extend(
                [
                    "references/style-system.md",
                    "references/background-systems.md",
                    "references/image-overlay.md",
                ]
            )
        else:
            paths.extend(["references/style-system.md", "references/screenshot-treatment.md"])
        chunks: list[str] = []
        for relative in paths:
            path = skill_dir / relative
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                chunks.append(f"\n\n===== {relative} =====\n{text}")
        bundle = "".join(chunks)
        if not bundle:
            raise NativeSkillError("Guizang 上游 references 不完整")
        return bundle[:220000]

    def _copy_input_assets(self, draft: DraftRevision, task_dir: Path) -> list[dict[str, str]]:
        destination = task_dir / "input-assets"
        destination.mkdir(parents=True, exist_ok=True)
        copied: list[dict[str, str]] = []
        for index, asset in enumerate(draft.source.assets[:12], start=1):
            local = Path(asset.local_path) if asset.local_path else None
            if local is None or not local.is_file() or asset.kind not in {"photo", "image"}:
                continue
            suffix = local.suffix.lower() if local.suffix else ".jpg"
            target = destination / f"source-{index:02d}{suffix}"
            shutil.copy2(local, target)
            copied.append(
                {
                    "relative_path": target.relative_to(task_dir).as_posix(),
                    "source_url": asset.remote_url,
                    "rights_status": asset.rights_status,
                    "alt_text": asset.alt_text,
                }
            )
        return copied

    @staticmethod
    def _source_brief(draft: DraftRevision, assets: list[dict[str, str]]) -> str:
        source = draft.source
        asset_lines = [
            f"- {item['relative_path']} | rights={item['rights_status']} | {item['alt_text']}"
            for item in assets
        ]
        return "\n".join(
            [
                f"来源 URL：{source.canonical_url}",
                f"来源作者：{source.author_name or source.author_handle or '未知'}",
                f"来源权利状态：{source.rights_status}",
                "可用本地图片：",
                *(asset_lines or ["- 无；必须采用不依赖伪照片的版式"]),
            ]
        )

    @staticmethod
    def _sources_markdown(draft: DraftRevision, assets: list[dict[str, str]]) -> str:
        lines = [
            "# Sources",
            "",
            f"- Article/source: {draft.source.canonical_url}",
            f"- Source rights status in X2RED: {draft.source.rights_status}",
            "",
            "## Local visual assets",
        ]
        if not assets:
            lines.append("- None. The deck uses typography and layout-only recipes.")
        for item in assets:
            lines.append(
                f"- `{item['relative_path']}` — {item['source_url']} — rights: {item['rights_status']}"
            )
        lines.extend(
            [
                "",
                "This file records provenance only. Publication rights still require human review.",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _assemble_document(seed: str, posters_html: str, *, max_cards: int) -> str:
        if "<!-- POSTERS_HERE -->" not in seed:
            raise CardRenderError("Guizang 种子模板缺少 POSTERS_HERE 占位符")
        document = seed.replace("<!-- POSTERS_HERE -->", posters_html, 1)
        count = NativeDeckRenderer.poster_count(document)
        if count < 2 or count > max_cards:
            raise CardRenderError(f"组装后的 Guizang 页面数量异常：{count}")
        return document

    @staticmethod
    def _clean_html(value: str) -> str:
        cleaned = value.strip()
        cleaned = re.sub(r"^```(?:html)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.replace("file://", "")
        return cleaned.strip()
