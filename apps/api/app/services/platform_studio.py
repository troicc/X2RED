from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import DraftRevision, SourceItem, new_id
from app.domain.platforms import PlatformVariant, PlatformVariantState
from app.services.editorial import EditorialService
from app.services.pool_memory import PoolMemoryService
from app.services.skills import binding_for
from app.services.source_graph import connected_sources
from app.services.wechat_cover_renderer import WeChatCoverRenderer
from app.services.wechat_renderer import WeChatHtmlRenderer, WeChatValidation
from app.services.wechat_themes import auto_theme, get_theme


class PlatformStudioError(RuntimeError):
    pass


class PlatformStudioService:
    def __init__(self, settings: Settings, editorial: EditorialService) -> None:
        self.settings = settings
        self.editorial = editorial
        self.renderer = WeChatHtmlRenderer()
        self.cover_renderer = WeChatCoverRenderer()

    async def create_wechat_variant(
        self,
        db: Session,
        *,
        source: SourceItem,
        draft: DraftRevision | None,
        theme: str,
        mode: str,
        include_citations: bool,
        include_illustration_plan: bool,
        author: str,
    ) -> PlatformVariant:
        variant_id = new_id("variant")
        selected_theme = theme if theme != "auto" else auto_theme(
            draft.title if draft else "",
            draft.body if draft else source.text_original,
        )
        bindings = {
            name: binding_for(db, name, self.settings.model_name)
            for name in (
                "wechat.adapt_longform",
                "wechat.title_summary",
                "wechat.citations",
                "article.illustration_plan",
                "wechat.format_article",
                "wechat.keyword_marking",
                "wechat.cover_pair",
                "wechat.qa",
            )
        }
        draft_provenance = self._json_object(draft.provenance_json) if draft else {}
        adapt_binding = bindings["wechat.adapt_longform"]
        model_ready = bool(
            adapt_binding.enabled
            and self.settings.model_base_url
            and (adapt_binding.model_name or self.settings.model_name)
        )
        memory_service = PoolMemoryService(self.settings, self.editorial)
        memory_snapshot = memory_service.create_snapshot(
            db,
            target_type="platform_variant",
            target_id=variant_id,
            query={
                "platform": "wechat",
                "format": "article",
                "article_type": {
                    "explain": "technical_explainer",
                    "news": "news",
                    "opinion": "commentary",
                    "studio": "technical_explainer",
                }.get(draft.style if draft else "", "technical_explainer"),
                "style_profile_id": str(draft_provenance.get("style_profile_id") or ""),
                "topics": [draft.title] if draft and draft.title else [],
                "source_text": (draft.body if draft and draft.body.strip() else source.text_original)[
                    :30000
                ],
                "limit": 6,
                "max_chars": 6500,
            },
            model_configured=model_ready,
            model_name=adapt_binding.model_name or self.settings.model_name,
        )
        memory_prompt = memory_service.prompt_payload(
            memory_snapshot,
            role="writer",
            allow_pending=True,
        )["text"]
        model_output = await self._generate_platform_copy(
            db,
            source=source,
            draft=draft,
            mode=mode,
            include_citations=include_citations and bindings["wechat.citations"].enabled,
            include_illustration_plan=(
                include_illustration_plan and bindings["article.illustration_plan"].enabled
            ),
            bindings=bindings,
            memory_prompt=memory_prompt,
        )
        if model_output is None:
            model_output = self._fallback_copy(
                db,
                source=source,
                draft=draft,
                include_citations=include_citations,
            )
            generator = "wechat-structured-fallback"
        else:
            generator = "wechat-model-skill-pack"
            memory_service.mark_snapshot_applied(
                db,
                memory_snapshot,
                roles=[
                    ("editor_in_chief", "wechat_adapt"),
                    ("outline_architect", "wechat_adapt"),
                    ("writer", "wechat_adapt"),
                ],
            )

        title = self._clean_title(str(model_output.get("title") or ""), source, draft)
        body_markdown = self._clean_markdown(str(model_output.get("body_markdown") or ""))
        if len(re.sub(r"\s+", "", body_markdown)) < 80:
            fallback = self._fallback_copy(
                db,
                source=source,
                draft=draft,
                include_citations=include_citations,
            )
            body_markdown = fallback["body_markdown"]
        short_title = str(model_output.get("short_share_title") or "").strip()
        if not short_title:
            short_title = self.cover_renderer.short_title(title)
        summary = self._summary(str(model_output.get("summary") or ""), body_markdown)
        tags = self._tags(model_output.get("tags"), draft.tags if draft else "")
        memory_summary = memory_service.snapshot_summary(memory_snapshot)
        metadata = {
            "generator": generator,
            "mode": mode,
            "author": author.strip(),
            "short_share_title": short_title[:24],
            "illustration_plan": model_output.get("illustration_plan") or [],
            "citations": model_output.get("citations") or [],
            "source_urls": [item.canonical_url for item in self._context(db, source)],
            "selected_theme": selected_theme,
            "memory_snapshot_id": memory_summary["snapshot_id"],
            "memory_snapshot_hash": memory_summary["snapshot_hash"],
            "memory_ids": memory_summary["memory_ids"],
            "memory_applied": memory_summary["applied"],
            "memory_status": memory_summary["status"],
        }
        skill_profile = {
            name: {
                "enabled": binding.enabled,
                "model": binding.model_name or self.settings.model_name,
                "reasoning_effort": binding.reasoning_effort,
                "prompt_version": binding.prompt_version,
            }
            for name, binding in bindings.items()
        }
        variant = PlatformVariant(
            id=variant_id,
            source_id=source.id,
            base_draft_id=draft.id if draft else None,
            platform="wechat",
            format="article",
            version=self._next_version(db, source.id, "wechat"),
            title=title[:160],
            subtitle=str(model_output.get("subtitle") or summary)[:240],
            summary=summary[:1000],
            body_markdown=body_markdown[:50000],
            tags=tags[:1000],
            theme=selected_theme,
            skill_profile_json=json.dumps(skill_profile, ensure_ascii=False),
            metadata_json=json.dumps(metadata, ensure_ascii=False),
            status=PlatformVariantState.draft.value,
            created_by="model" if model_output.get("_model_used") else "system",
        )
        db.add(variant)
        db.flush()
        return variant

    def revise_variant(
        self,
        db: Session,
        current: PlatformVariant,
        *,
        title: str,
        subtitle: str,
        summary: str,
        body_markdown: str,
        tags: str,
        theme: str,
    ) -> PlatformVariant:
        metadata = self._json_object(current.metadata_json)
        metadata["parent_variant_id"] = current.id
        revised = PlatformVariant(
            source_id=current.source_id,
            base_draft_id=current.base_draft_id,
            platform=current.platform,
            format=current.format,
            version=self._next_version(db, current.source_id, current.platform),
            title=title.strip()[:160],
            subtitle=subtitle.strip()[:240],
            summary=summary.strip()[:1000],
            body_markdown=self._clean_markdown(body_markdown)[:50000],
            tags=tags.strip()[:1000],
            theme=theme if theme != "auto" else auto_theme(title, body_markdown),
            skill_profile_json=current.skill_profile_json,
            metadata_json=json.dumps(metadata, ensure_ascii=False),
            status=PlatformVariantState.draft.value,
            created_by="human",
        )
        db.add(revised)
        db.flush()
        return revised

    def render_wechat_variant(
        self,
        db: Session,
        variant: PlatformVariant,
        *,
        package: bool = True,
    ) -> tuple[PlatformVariant, WeChatValidation, dict[str, str]]:
        if variant.platform != "wechat":
            raise PlatformStudioError("当前内容不是公众号版本")
        source = db.get(SourceItem, variant.source_id)
        if source is None:
            raise PlatformStudioError("公众号版本关联的来源不存在")
        theme = get_theme(variant.theme)
        metadata = self._json_object(variant.metadata_json)
        author = str(metadata.get("author") or "")
        mark_keywords = self._skill_enabled(db, "wechat.keyword_marking")
        fragment = self.renderer.render_fragment(
            title=variant.title,
            summary=variant.summary,
            markdown=variant.body_markdown,
            theme_id=theme.id,
            author=author,
            source_url=source.canonical_url,
            mark_keywords=mark_keywords,
        )
        validation = self.renderer.validate(fragment)
        variant.body_html = fragment
        if validation.errors:
            variant.status = PlatformVariantState.failed.value
            variant.error = "；".join(validation.errors)
            db.flush()
            raise PlatformStudioError(variant.error)

        output_dir = self.settings.export_dir / "wechat" / variant.id
        output_dir.mkdir(parents=True, exist_ok=True)
        article_md = output_dir / "article.md"
        article_html = output_dir / "article.html"
        preview_html = output_dir / "preview.html"
        article_md.write_text(self._frontmatter(variant, author) + variant.body_markdown, encoding="utf-8")
        article_html.write_text(fragment, encoding="utf-8")
        preview_html.write_text(
            self.renderer.preview_document(title=variant.title, fragment=fragment),
            encoding="utf-8",
        )

        covers: dict[str, str] = {}
        if self._skill_enabled(db, "wechat.cover_pair"):
            covers = self.cover_renderer.render_pair(
                output_dir,
                title=variant.title,
                short_title=str(metadata.get("short_share_title") or ""),
                subtitle=variant.subtitle or variant.summary,
                theme_id=theme.id,
                hero_image=self._hero_image(source),
            )
        manifest = {
            "variant_id": variant.id,
            "platform": variant.platform,
            "version": variant.version,
            "title": variant.title,
            "summary": variant.summary,
            "theme": variant.theme,
            "validation": {"errors": validation.errors, "warnings": validation.warnings},
            "files": {
                "markdown": article_md.name,
                "html": article_html.name,
                "preview": preview_html.name,
                "wide_cover": Path(covers.get("wide", "")).name if covers.get("wide") else "",
                "square_cover": Path(covers.get("square", "")).name if covers.get("square") else "",
            },
            "metadata": metadata,
        }
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        files = {
            "markdown": str(article_md.resolve()),
            "html": str(article_html.resolve()),
            "preview": str(preview_html.resolve()),
            "manifest": str(manifest_path.resolve()),
            **covers,
        }
        if package:
            zip_path = output_dir / f"wechat-{variant.id}.zip"
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path_value in files.values():
                    path = Path(path_value)
                    if path.is_file():
                        archive.write(path, arcname=path.name)
            files["package"] = str(zip_path.resolve())
            variant.status = PlatformVariantState.packaged.value
        else:
            variant.status = PlatformVariantState.rendered.value
        variant.error = ""
        variant.output_paths_json = json.dumps(files, ensure_ascii=False)
        variant.metadata_json = json.dumps(
            {**metadata, "validation": {"errors": [], "warnings": validation.warnings}},
            ensure_ascii=False,
        )
        db.flush()
        return variant, validation, files

    async def _generate_platform_copy(
        self,
        db: Session,
        *,
        source: SourceItem,
        draft: DraftRevision | None,
        mode: str,
        include_citations: bool,
        include_illustration_plan: bool,
        bindings: dict[str, Any],
        memory_prompt: str = "",
    ) -> dict[str, Any] | None:
        adapt = bindings["wechat.adapt_longform"]
        if not (
            adapt.enabled
            and self.settings.model_base_url
            and (adapt.model_name or self.settings.model_name)
        ):
            return None
        context = self._context(db, source)
        source_blocks = self.editorial._source_blocks(context)
        source_json = json.dumps(source_blocks, ensure_ascii=False)[:32000]
        base_copy = {
            "title": draft.title if draft else "",
            "body": draft.body if draft else source.text_original,
            "tags": draft.tags if draft else "",
        }
        mode_guide = (
            "以现有终稿为主，保留作者叙事和结构，只做公众号阅读节奏适配。"
            if mode == "preserve"
            else "回到来源证据重新组织为公众号长文，不把小红书短稿简单扩写。"
        )
        prompt = f"""
把下面来源与现有终稿制作成一篇真正适合微信公众号的中文长文。

平台目标：微信公众号文章，而不是小红书 caption、卡片脚本或审计报告。
处理模式：{mode_guide}

写作要求：
1. 标题 16-30 个汉字，具体而克制；另给一个 6-12 字的转发短标题。
2. 摘要 60-120 字，说明读者会获得什么，不写“本文将”。
3. 正文优先 1800-4500 个中文字符；来源材料不足时宁可短，不补造背景。
4. 使用 Markdown。正文不重复 H1，从自然引言开始，以 3-6 个 H2 组织长文。
5. 技术内容先解释成果、问题和意义，再引入术语；每个重要缩写首次出现必须用一句人话解释。
6. 数字要解释它意味着什么。作者自测必须保留来源归属，局部结果不能扩大成整体结论。
7. 不出现“先说结论、值得关注的3个点、阅读时注意以下边界、适用性判断、点赞收藏”。
8. 不使用营销式公众号套话，不把小红书 emoji、hashtags 和 CTA 搬进正文。
9. 文章最后落在清晰判断、启发或下一步观察，不以免责声明结束。
10. 只使用给定来源支持的事实；缺少证据的内容不要写。

当前任务检索到的个人池子记忆：
{memory_prompt}

是否整理文末来源：{include_citations}
是否给出配图规划：{include_illustration_plan}
来源材料：{source_json}
现有终稿：{json.dumps(base_copy, ensure_ascii=False)[:12000]}

只输出 JSON：
{{
  "title":"公众号标题",
  "short_share_title":"6-12字短标题",
  "subtitle":"封面副标题",
  "summary":"摘要",
  "body_markdown":"Markdown正文",
  "tags":["内部主题标签"],
  "citations":[{{"label":"来源名称","url":"https://...","purpose":"支持什么"}}],
  "illustration_plan":[{{"after_heading":"章节名","type":"infographic|flowchart|comparison|framework|scene","purpose":"为什么需要图","brief":"画面说明","use_source_asset":true}}]
}}
""".strip()
        try:
            result = await self.editorial._chat_json(
                system_prompt=(
                    "你是中文长文总编辑，擅长把复杂来源写成公众号文章。"
                    "你必须重构叙事，而不是把短内容注水。"
                ),
                user_prompt=prompt,
                temperature=0.42,
                reasoning_effort=adapt.reasoning_effort,
                model_name=adapt.model_name,
            )
            if include_citations and bindings["wechat.citations"].enabled:
                result["body_markdown"] = self._append_citations(
                    str(result.get("body_markdown") or ""),
                    result.get("citations"),
                    context,
                )
            result["_model_used"] = True
            return result
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _fallback_copy(
        self,
        db: Session,
        *,
        source: SourceItem,
        draft: DraftRevision | None,
        include_citations: bool,
    ) -> dict[str, Any]:
        title = draft.title.strip() if draft and draft.title.strip() else self._source_title(source)
        text = draft.body.strip() if draft and draft.body.strip() else source.text_original.strip()
        paragraphs = [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]
        if not paragraphs:
            paragraphs = ["当前来源没有可用正文，请回到来源页确认抓取结果。"]
        groups: list[list[str]] = []
        size = max(2, min(4, (len(paragraphs) + 2) // 3))
        for index in range(0, len(paragraphs), size):
            groups.append(paragraphs[index:index + size])
        headings = self._fallback_headings(groups, title)
        body_parts = [paragraphs[0]]
        consumed_first = False
        for heading, group in zip(headings, groups, strict=False):
            values = list(group)
            if not consumed_first and values and values[0] == paragraphs[0]:
                values = values[1:]
                consumed_first = True
            if not values:
                continue
            body_parts.append(f"## {heading}\n\n" + "\n\n".join(values))
        body = "\n\n".join(body_parts)
        context = self._context(db, source)
        citations = [
            {"label": item.author_name or item.author_handle or "X 来源", "url": item.canonical_url}
            for item in context
        ]
        if include_citations:
            body = self._append_citations(body, citations, context)
        return {
            "title": title,
            "short_share_title": self.cover_renderer.short_title(title),
            "subtitle": self._summary("", body),
            "summary": self._summary("", body),
            "body_markdown": body,
            "tags": draft.tags.split(",") if draft and draft.tags else [],
            "citations": citations,
            "illustration_plan": [],
            "_model_used": False,
        }

    @staticmethod
    def _fallback_headings(groups: list[list[str]], title: str) -> list[str]:
        defaults = ["真正发生了什么", "关键方法与证据", "这件事为什么值得看", "接下来怎么看"]
        output: list[str] = []
        for index, group in enumerate(groups):
            first = re.sub(r"\s+", " ", group[0] if group else title).strip()
            candidate = re.split(r"[。！？：:]", first, maxsplit=1)[0]
            if 4 <= len(candidate) <= 18 and candidate not in output:
                output.append(candidate)
            else:
                output.append(defaults[min(index, len(defaults) - 1)])
        return output

    def _context(self, db: Session, source: SourceItem) -> list[SourceItem]:
        related = connected_sources(db, source.id)
        return [source, *(item for item in related if item.id != source.id)]

    @staticmethod
    def _next_version(db: Session, source_id: str, platform: str) -> int:
        current = db.scalar(
            select(func.max(PlatformVariant.version)).where(
                PlatformVariant.source_id == source_id,
                PlatformVariant.platform == platform,
            )
        )
        return int(current or 0) + 1

    def _skill_enabled(self, db: Session, name: str) -> bool:
        return binding_for(db, name, self.settings.model_name).enabled

    @staticmethod
    def _json_object(value: str) -> dict[str, Any]:
        try:
            parsed = json.loads(value or "{}")
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _clean_markdown(value: str) -> str:
        text = value.replace("\r\n", "\n").replace("\r", "\n").strip()
        text = re.sub(r"^#\s+.+?\n+", "", text)
        text = re.sub(
            r"(?im)^#{1,3}\s*(?:阅读提醒|阅读时注意.*|适用边界|事实核查|仍需确认|风险提示)\s*$\n?",
            "",
            text,
        )
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _clean_title(value: str, source: SourceItem, draft: DraftRevision | None) -> str:
        title = re.sub(r"\s+", " ", value).strip(" #：:｜|")
        if title:
            return title[:160]
        if draft and draft.title.strip():
            return draft.title.strip()[:160]
        return PlatformStudioService._source_title(source)

    @staticmethod
    def _source_title(source: SourceItem) -> str:
        structured: dict[str, Any] = {}
        try:
            structured = json.loads(source.structured_content_json or "{}")
        except json.JSONDecodeError:
            pass
        title = str(structured.get("title") or "").strip()
        if title:
            return title[:160]
        first = re.sub(r"\s+", " ", source.text_original).strip()
        return (first[:48].rstrip("，。；： ") or "来自 X 的一篇文章")

    @staticmethod
    def _summary(value: str, markdown: str) -> str:
        clean = re.sub(r"\s+", " ", value).strip()
        if clean:
            return clean[:1000]
        body = re.sub(r"[#>*`\[\]()!-]", " ", markdown)
        body = re.sub(r"\s+", " ", body).strip()
        return (body[:116].rstrip("，。； ") + "…") if len(body) > 120 else body

    @staticmethod
    def _tags(value: Any, fallback: str) -> str:
        if isinstance(value, list):
            tags = [re.sub(r"^#", "", str(item)).strip() for item in value]
            return ",".join(item for item in tags if item)[:1000]
        if isinstance(value, str) and value.strip():
            return value.strip()[:1000]
        return fallback.strip()[:1000]

    @staticmethod
    def _append_citations(
        markdown: str,
        citations: Any,
        context: list[SourceItem],
    ) -> str:
        values: list[tuple[str, str]] = []
        if isinstance(citations, list):
            for item in citations:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("label") or "来源").strip()
                url = str(item.get("url") or "").strip()
                if url.startswith(("http://", "https://")) and (label, url) not in values:
                    values.append((label, url))
        for item in context:
            pair = (item.author_name or item.author_handle or "X 来源", item.canonical_url)
            if pair[1].startswith(("http://", "https://")) and pair not in values:
                values.append(pair)
        if not values or re.search(r"(?m)^##\s+(?:来源|参考|引用)", markdown):
            return markdown
        lines = ["## 来源与延伸阅读"]
        lines.extend(f"{index}. [{label}]({url})" for index, (label, url) in enumerate(values[:12], 1))
        return markdown.rstrip() + "\n\n" + "\n".join(lines)

    @staticmethod
    def _frontmatter(variant: PlatformVariant, author: str) -> str:
        values = [
            "---",
            f'title: "{variant.title.replace(chr(34), chr(39))}"',
            f'author: "{author.replace(chr(34), chr(39))}"',
            f'description: "{variant.summary.replace(chr(34), chr(39))}"',
            f"theme: {variant.theme}",
            "---",
            "",
        ]
        return "\n".join(values)

    @staticmethod
    def _hero_image(source: SourceItem) -> str:
        for asset in source.assets:
            if asset.kind == "image" and asset.local_path and Path(asset.local_path).is_file():
                return asset.local_path
        return ""
