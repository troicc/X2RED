from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import (
    Asset,
    AssetState,
    DraftRevision,
    RightsStatus,
    SourceItem,
    new_id,
    utcnow,
)
from app.domain.platforms import PlatformVariant, PlatformVariantState
from app.services.editorial import EditorialService
from app.services.input_materials import (
    InputMaterialError,
    compact_material_provenance,
    resolve_input_materials,
)
from app.services.pool_memory import PoolMemoryService
from app.services.skills import binding_for
from app.services.source_graph import connected_sources
from app.services.visual_brief import VisualBriefService
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
        self.visual_briefs = VisualBriefService(settings, editorial)

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
        supporting_sources: list[SourceItem] | None = None,
        input_materials: list[dict[str, Any]] | None = None,
    ) -> PlatformVariant:
        variant_id = new_id("variant")
        selected_sources = [source, *(supporting_sources or [])]
        input_materials = input_materials or [
            {
                "ref": f"source:{item.id}",
                "kind": "source",
                "id": item.id,
                "source_id": item.id,
                "title": self._source_title(item),
            }
            for item in selected_sources
        ]
        context = self._evidence_context(db, selected_sources)
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
                "source_text": "\n\n".join(
                    ([draft.body] if draft and draft.body.strip() else [])
                    + [item.text_original for item in selected_sources]
                    + [
                        str(item.get("body") or "")
                        for item in input_materials
                        if str(item.get("kind") or "") != "source"
                    ]
                )[:30000],
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
            context=context,
            selected_source_ids=[item.id for item in selected_sources],
            input_materials=input_materials,
        )
        if model_output is None:
            model_output = self._fallback_copy(
                db,
                source=source,
                draft=draft,
                include_citations=include_citations,
                context=context,
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
                context=context,
            )
            body_markdown = fallback["body_markdown"]
        short_title = str(model_output.get("short_share_title") or "").strip()
        if not short_title:
            short_title = self.cover_renderer.short_title(title)
        summary = self._summary(str(model_output.get("summary") or ""), body_markdown)
        tags = self._tags(model_output.get("tags"), draft.tags if draft else "")
        memory_summary = memory_service.snapshot_summary(memory_snapshot)
        illustration_plan = model_output.get("illustration_plan") or []
        visual_bible = self.visual_briefs.default_bible(
            visual_style=f"wechat-{selected_theme}",
            content_recipe="longform",
        )
        visual_prompts = self._build_visual_handoff(
            title=title,
            summary=summary,
            body_markdown=body_markdown,
            theme_id=selected_theme,
            illustration_plan=illustration_plan,
            visual_bible=visual_bible.model_dump(mode="json"),
        ) if include_illustration_plan else []
        metadata = {
            "generator": generator,
            "mode": mode,
            "author": author.strip(),
            "writing_project_id": str(draft_provenance.get("writing_project_id") or ""),
            "writing_final_artifact_id": str(
                draft_provenance.get("final_artifact_id") or ""
            ),
            "short_share_title": short_title[:24],
            "illustration_plan": illustration_plan,
            "visual_prompts": visual_prompts,
            "visual_bible": visual_bible.model_dump(mode="json"),
            "visual_handoff_mode": "codex_skill_prompt_upload",
            "citations": model_output.get("citations") or [],
            "input_materials": compact_material_provenance(input_materials),
            "input_material_refs": [str(item.get("ref") or "") for item in input_materials],
            "generation_completion": model_output.get("_completion") or {
                "status": "complete",
                "source": "deterministic_fallback",
                "issues": [],
            },
            "evidence_source_ids": [item.id for item in selected_sources],
            "evidence_sources": [
                {
                    "id": item.id,
                    "role": "primary" if index == 0 else "supporting",
                    "author": item.author_name or item.author_handle,
                    "url": item.canonical_url,
                }
                for index, item in enumerate(selected_sources)
            ],
            "source_urls": [item.canonical_url for item in context],
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
        created_by: str = "human",
    ) -> PlatformVariant:
        metadata = self._json_object(current.metadata_json)
        metadata["parent_variant_id"] = current.id
        resolved_theme = theme if theme != "auto" else auto_theme(title, body_markdown)
        if current.format == "article" and metadata.get("visual_handoff_mode"):
            metadata["visual_prompts"] = self._build_visual_handoff(
                title=title.strip(),
                summary=summary.strip(),
                body_markdown=body_markdown,
                theme_id=resolved_theme,
                illustration_plan=metadata.get("illustration_plan") or [],
                previous=metadata.get("visual_prompts") or [],
                visual_bible=metadata.get("visual_bible") or {},
            )
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
            theme=resolved_theme,
            skill_profile_json=current.skill_profile_json,
            metadata_json=json.dumps(metadata, ensure_ascii=False),
            status=PlatformVariantState.draft.value,
            created_by=created_by,
        )
        db.add(revised)
        db.flush()
        return revised

    async def repair_incomplete_variant(
        self,
        db: Session,
        current: PlatformVariant,
    ) -> PlatformVariant:
        if current.platform != "wechat" or current.format != "article":
            raise PlatformStudioError("只有公众号长文支持完成度修复")
        metadata = self._json_object(current.metadata_json)
        issues = self._article_completion_issues(
            {
                "body_markdown": current.body_markdown,
                "illustration_plan": metadata.get("illustration_plan") or [],
            }
        )
        if not issues:
            raise PlatformStudioError("当前正文未检测到截断，不需要续写修复")
        normalized_current_body = self._normalize_bare_code_blocks(current.body_markdown)
        normalized_issues = self._article_completion_issues(
            {
                "body_markdown": normalized_current_body,
                "illustration_plan": metadata.get("illustration_plan") or [],
            }
        )
        if normalized_current_body != current.body_markdown and not normalized_issues:
            repaired = self.revise_variant(
                db,
                current,
                title=current.title,
                subtitle=current.subtitle,
                summary=current.summary,
                body_markdown=normalized_current_body,
                tags=current.tags,
                theme=current.theme,
                created_by="system-repair",
            )
            repaired_metadata = self._json_object(repaired.metadata_json)
            repaired_metadata.update(
                {
                    "generator": "wechat-local-code-fence-repair",
                    "generation_completion": {
                        "status": "complete_after_local_format_repair",
                        "issues_repaired": issues,
                        "finish_reason": "local",
                        "completion_tokens": 0,
                        "code_fences_normalized": True,
                    },
                }
            )
            repaired_metadata["visual_prompts"] = self._build_visual_handoff(
                title=repaired.title,
                summary=repaired.summary,
                body_markdown=repaired.body_markdown,
                theme_id=repaired.theme,
                illustration_plan=repaired_metadata.get("illustration_plan") or [],
                visual_bible=repaired_metadata.get("visual_bible") or {},
            )
            repaired.metadata_json = json.dumps(repaired_metadata, ensure_ascii=False)
            db.flush()
            return repaired
        binding = binding_for(db, "wechat.adapt_longform", self.settings.model_name)
        if not (
            binding.enabled
            and self.settings.model_base_url
            and (binding.model_name or self.settings.model_name)
        ):
            raise PlatformStudioError("未配置可用的公众号长文模型，无法续写修复")
        refs = metadata.get("input_material_refs")
        if not isinstance(refs, list) or not refs:
            evidence_ids = metadata.get("evidence_source_ids")
            refs = [
                f"source:{source_id}"
                for source_id in (evidence_ids if isinstance(evidence_ids, list) else [current.source_id])
                if source_id
            ]
        try:
            resolved = resolve_input_materials(
                db,
                [str(value) for value in refs],
                preferred_source_id=current.source_id,
            )
        except InputMaterialError as exc:
            raise PlatformStudioError(str(exc)) from exc
        context = self._evidence_context(db, resolved.sources)
        source_blocks = self.editorial._source_blocks(context)
        selected_ids = {item.id for item in resolved.sources}
        for index, block in enumerate(source_blocks):
            source_id = str(block.get("source_id") or "")
            block["selection_role"] = (
                "primary"
                if source_id == resolved.primary_source.id
                else "supporting"
                if source_id in selected_ids
                else "connected"
            )
            block["index"] = index + 1
        materials_json = json.dumps(
            self._merge_material_blocks(source_blocks, resolved.materials),
            ensure_ascii=False,
        )[:48000]
        prompt = f"""
修复下面这篇被截断的公众号文章。必须返回从开头到结尾完整的一篇文章，不是单独的续写片段。

检测到的问题：{json.dumps(issues, ensure_ascii=False)}
原始来源与已选版本：{materials_json}
当前残缺版本：{json.dumps({
    'title': current.title,
    'subtitle': current.subtitle,
    'summary': current.summary,
    'body_markdown': current.body_markdown,
    'tags': current.tags,
    'illustration_plan': metadata.get('illustration_plan') or [],
}, ensure_ascii=False)[:50000]}

要求：
1. 保留已有、有证据支持的内容，完成残缺代码和所有尚未写出的论述；
2. 代码必须放在带语言名的 Markdown 围栏中，逐行完整，围栏和括号闭合；
3. 代码之后继续写完能力边界、安全风险和最终判断，不能以代码收尾；
4. written_version 可用于结构和表达，具体事实仍须由 primary/supporting 来源支持；
5. 3—6 个 H2 全部写完，illustration_plan.after_heading 只能引用正文真实存在的 H2；
6. 正文优先 1800—4500 个中文字符，不添加来源没有支持的数字、品牌结论或人物经历。

只输出 JSON：
{{"title":"完整标题","short_share_title":"短标题","subtitle":"副标题","summary":"摘要",
"body_markdown":"完整 Markdown 正文","tags":["标签"],"citations":[{{"label":"来源","url":"https://...","purpose":"用途"}}],
"illustration_plan":[{{"after_heading":"真实 H2","type":"infographic|flowchart|comparison|framework|scene",
"purpose":"用途","brief":"画面","composition":"构图","use_source_asset":false}}]}}
""".strip()
        try:
            result = await self.editorial._chat_json(
                system_prompt="你是公众号长文修复总编。绝不交付半行代码、半句话或缺失结尾的文章。",
                user_prompt=prompt,
                temperature=0.25,
                reasoning_effort=binding.reasoning_effort,
                model_name=binding.model_name,
                max_tokens=12000,
                capture_response_meta=True,
                request_timeout_seconds=360,
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PlatformStudioError("续写修复模型调用失败，原版本保持不变") from exc
        response_meta = result.pop("_x2red_response_meta", {})
        normalized_body = self._normalize_bare_code_blocks(
            str(result.get("body_markdown") or "")
        )
        code_fences_normalized = normalized_body != str(result.get("body_markdown") or "")
        result["body_markdown"] = normalized_body
        remaining = self._article_completion_issues(result, response_meta=response_meta)
        first_attempt_issues = list(remaining)
        if remaining:
            correction_prompt = f"""
上一版修复候选仍未通过完整性校验。请根据原始来源重新输出从开头到结尾完整的一篇文章，不要只返回局部补丁。

未通过原因：{json.dumps(remaining, ensure_ascii=False)}
原始来源与已选版本：{materials_json}
原始残缺版本：{json.dumps({
    'title': current.title,
    'subtitle': current.subtitle,
    'summary': current.summary,
    'body_markdown': current.body_markdown,
    'tags': current.tags,
}, ensure_ascii=False)[:50000]}
未通过的修复候选：{json.dumps(result, ensure_ascii=False)[:50000]}

硬性要求：
1. 返回完整文章，3—6 个 H2，正文 1800—4500 个中文字符；
2. 所有代码都必须置于带语言名的三反引号 Markdown 围栏中，代码、括号、字符串与围栏完整闭合；
3. 代码块后必须继续写完能力边界、安全风险和最终判断，最后一句以中文句号结束；
4. illustration_plan.after_heading 只能引用正文实际存在的 H2；
5. 只用来源支持的事实，不补造数字、产品能力或人物经历。

只输出与第一次相同字段的 JSON 对象。
""".strip()
            try:
                result = await self.editorial._chat_json(
                    system_prompt="你是公众号长文修复总编。根据校验错误彻底重写全文，绝不交付裸代码、半行代码或缺失结尾的文章。",
                    user_prompt=correction_prompt,
                    temperature=0.15,
                    reasoning_effort=binding.reasoning_effort,
                    model_name=binding.model_name,
                    max_tokens=12000,
                    capture_response_meta=True,
                    request_timeout_seconds=360,
                )
            except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise PlatformStudioError(
                    f"修复候选未通过校验，自动重写失败：{'；'.join(remaining)}"
                ) from exc
            response_meta = result.pop("_x2red_response_meta", {})
            normalized_body = self._normalize_bare_code_blocks(
                str(result.get("body_markdown") or "")
            )
            code_fences_normalized = normalized_body != str(
                result.get("body_markdown") or ""
            )
            result["body_markdown"] = normalized_body
            remaining = self._article_completion_issues(result, response_meta=response_meta)
            if remaining:
                raise PlatformStudioError(
                    f"模型连续两次返回不完整修复，已阻止保存：{'；'.join(remaining)}"
                )
        body_markdown = self._append_citations(
            str(result.get("body_markdown") or ""),
            result.get("citations"),
            context,
        )
        title = self._clean_title(str(result.get("title") or current.title), resolved.primary_source, None)
        summary = self._summary(str(result.get("summary") or current.summary), body_markdown)
        repaired = self.revise_variant(
            db,
            current,
            title=title,
            subtitle=str(result.get("subtitle") or current.subtitle),
            summary=summary,
            body_markdown=body_markdown,
            tags=self._tags(result.get("tags"), current.tags),
            theme=current.theme,
            created_by="model-repair",
        )
        repaired_metadata = self._json_object(repaired.metadata_json)
        repaired_metadata.update(
            {
                "generator": "wechat-model-repair",
                "citations": result.get("citations") or metadata.get("citations") or [],
                "illustration_plan": result.get("illustration_plan") or [],
                "input_materials": compact_material_provenance(resolved.materials),
                "input_material_refs": resolved.refs,
                "generation_completion": {
                    "status": "complete_after_repair",
                    "issues_repaired": list(dict.fromkeys([*issues, *first_attempt_issues])),
                    "finish_reason": str(response_meta.get("finish_reason") or ""),
                    "completion_tokens": response_meta.get("completion_tokens"),
                    "code_fences_normalized": code_fences_normalized,
                },
            }
        )
        repaired_metadata["visual_prompts"] = self._build_visual_handoff(
            title=repaired.title,
            summary=repaired.summary,
            body_markdown=repaired.body_markdown,
            theme_id=repaired.theme,
            illustration_plan=repaired_metadata["illustration_plan"],
            visual_bible=repaired_metadata.get("visual_bible") or {},
        )
        repaired.metadata_json = json.dumps(repaired_metadata, ensure_ascii=False)
        db.flush()
        return repaired

    def attach_visual_asset(
        self,
        db: Session,
        variant: PlatformVariant,
        *,
        slot_id: str,
        payload: bytes,
    ) -> Asset:
        if variant.platform != "wechat" or variant.format != "article":
            raise PlatformStudioError("只有公众号长文支持逐段配图回传")
        if not payload:
            raise PlatformStudioError("上传图片为空")
        if len(payload) > 12 * 1024 * 1024:
            raise PlatformStudioError("单张图片不能超过 12 MB")

        metadata = self._json_object(variant.metadata_json)
        prompts = metadata.get("visual_prompts")
        if not isinstance(prompts, list):
            raise PlatformStudioError("当前版本没有可回传的生图 Prompt")
        slot = next(
            (
                item
                for item in prompts
                if isinstance(item, dict) and str(item.get("slot_id") or "") == slot_id
            ),
            None,
        )
        if slot is None:
            raise PlatformStudioError("配图位置不存在或已随文章修改而失效")

        try:
            with Image.open(io.BytesIO(payload)) as opened:
                image = ImageOps.exif_transpose(opened)
                image.load()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise PlatformStudioError("只能上传可读取的 PNG、JPEG 或 WebP 图片") from exc
        if image.width < 240 or image.height < 240:
            raise PlatformStudioError("图片尺寸过小，宽高都至少需要 240 像素")
        if image.width * image.height > 50_000_000:
            raise PlatformStudioError("图片像素过大，请先缩小到 5000 万像素以内")
        if max(image.size) > 2560:
            image.thumbnail((2560, 2560), Image.Resampling.LANCZOS)

        has_alpha = image.mode in {"RGBA", "LA"} or (
            image.mode == "P" and "transparency" in image.info
        )
        normalized = io.BytesIO()
        if has_alpha:
            image = image.convert("RGBA")
            extension = ".png"
            mime_type = "image/png"
            image.save(normalized, format="PNG", optimize=True)
        else:
            image = image.convert("RGB")
            extension = ".jpg"
            mime_type = "image/jpeg"
            image.save(normalized, format="JPEG", quality=92, optimize=True, progressive=True)
        normalized_bytes = normalized.getvalue()
        sha256 = hashlib.sha256(normalized_bytes).hexdigest()
        upload_dir = self.settings.media_dir / "user-uploads" / "wechat"
        upload_dir.mkdir(parents=True, exist_ok=True)
        target = upload_dir / f"{sha256}{extension}"
        if not target.is_file():
            staging = upload_dir / f".{sha256}{extension}.tmp"
            staging.write_bytes(normalized_bytes)
            staging.replace(target)

        asset = db.scalar(
            select(Asset).where(
                Asset.source_id == variant.source_id,
                Asset.sha256 == sha256,
                Asset.role == "wechat_visual",
            )
        )
        if asset is None:
            asset = Asset(
                source_id=variant.source_id,
                kind="image",
                role="wechat_visual",
                remote_url="",
                local_path=str(target.resolve()),
                sha256=sha256,
                mime_type=mime_type,
                width=image.width,
                height=image.height,
                alt_text=str(slot.get("alt_text") or slot.get("label") or "公众号配图")[:1000],
                state=AssetState.ready.value,
                rights_status=RightsStatus.needs_review.value,
                rights_note="由用户从外部 Codex/生图 Skill 回传；发布前需人工确认模型、参考素材和版权。",
            )
            db.add(asset)
            db.flush()

        slot.update(
            {
                "asset_id": asset.id,
                "asset_sha256": asset.sha256,
                "asset_width": asset.width,
                "asset_height": asset.height,
                "asset_mime_type": asset.mime_type,
                "asset_uploaded_at": utcnow().isoformat(),
            }
        )
        metadata["visual_prompts"] = prompts
        metadata["visual_assets_need_render"] = True
        variant.metadata_json = json.dumps(metadata, ensure_ascii=False)
        variant.output_paths_json = "{}"
        variant.status = PlatformVariantState.draft.value
        variant.error = ""
        db.flush()
        return asset

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
        visual_records = self._visual_asset_records(db, metadata)
        package_markdown = self._markdown_with_visuals(
            variant.body_markdown,
            visual_records,
            source_for=lambda record: f"illustrations/{record['filename']}",
        )
        preview_markdown = self._markdown_with_visuals(
            variant.body_markdown,
            visual_records,
            source_for=lambda record: f"/api/assets/{record['asset'].id}/file",
        )
        fragment = self.renderer.render_fragment(
            title=variant.title,
            summary=variant.summary,
            markdown=package_markdown,
            theme_id=theme.id,
            author=author,
            source_url=source.canonical_url,
            mark_keywords=mark_keywords,
        )
        preview_fragment = self.renderer.render_fragment(
            title=variant.title,
            summary=variant.summary,
            markdown=preview_markdown,
            theme_id=theme.id,
            author=author,
            source_url=source.canonical_url,
            mark_keywords=mark_keywords,
        )
        validation = self.renderer.validate(fragment)
        completion_errors = (
            self._article_completion_issues(
                {
                    "body_markdown": variant.body_markdown,
                    "illustration_plan": metadata.get("illustration_plan") or [],
                }
            )
            if variant.created_by.startswith("model")
            else []
        )
        if metadata.get("generator") == "wechat-structured-fallback":
            completion_errors = [
                message for message in completion_errors if message != "正文少于三个完整章节"
            ]
        validation = WeChatValidation(
            errors=list(dict.fromkeys([*validation.errors, *completion_errors])),
            warnings=validation.warnings,
        )
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
        handoff_md = output_dir / "visual-handoff.md"
        visual_files: dict[str, str] = {}
        visual_manifest: list[dict[str, Any]] = []
        if visual_records:
            illustration_dir = output_dir / "illustrations"
            illustration_dir.mkdir(parents=True, exist_ok=True)
            for record in visual_records:
                destination = illustration_dir / str(record["filename"])
                shutil.copy2(record["source_path"], destination)
                visual_files[f"visual_{record['slot']['slot_id']}"] = str(destination.resolve())
                visual_manifest.append(
                    {
                        "slot_id": record["slot"]["slot_id"],
                        "kind": record["slot"].get("kind"),
                        "label": record["slot"].get("label"),
                        "placement": record["slot"].get("placement"),
                        "asset_id": record["asset"].id,
                        "file": f"illustrations/{destination.name}",
                        "rights_status": record["asset"].rights_status,
                    }
                )
        handoff_md.write_text(
            self._visual_handoff_markdown(metadata, visual_manifest),
            encoding="utf-8",
        )
        article_md.write_text(self._frontmatter(variant, author) + package_markdown, encoding="utf-8")
        article_html.write_text(fragment, encoding="utf-8")
        preview_html.write_text(
            self.renderer.preview_document(title=variant.title, fragment=preview_fragment),
            encoding="utf-8",
        )

        covers: dict[str, str] = {}
        if self._skill_enabled(db, "wechat.cover_pair"):
            uploaded_cover = next(
                (
                    str(record["source_path"])
                    for record in visual_records
                    if record["slot"].get("kind") == "cover"
                ),
                "",
            )
            covers = self.cover_renderer.render_pair(
                output_dir,
                title=variant.title,
                short_title=str(metadata.get("short_share_title") or ""),
                subtitle=variant.subtitle or variant.summary,
                theme_id=theme.id,
                hero_image=uploaded_cover or self._hero_image(source),
            )
        metadata["visual_assets_need_render"] = False
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
                "visual_handoff": handoff_md.name,
                "wide_cover": Path(covers.get("wide", "")).name if covers.get("wide") else "",
                "square_cover": Path(covers.get("square", "")).name if covers.get("square") else "",
            },
            "visuals": visual_manifest,
            "metadata": metadata,
        }
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        files = {
            "markdown": str(article_md.resolve()),
            "html": str(article_html.resolve()),
            "preview": str(preview_html.resolve()),
            "visual_handoff": str(handoff_md.resolve()),
            "manifest": str(manifest_path.resolve()),
            **covers,
            **visual_files,
        }
        if package:
            zip_path = output_dir / f"wechat-{variant.id}.zip"
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for key, path_value in files.items():
                    path = Path(path_value)
                    if path.is_file():
                        arcname = (
                            f"illustrations/{path.name}"
                            if key.startswith("visual_") and key != "visual_handoff"
                            else path.name
                        )
                        archive.write(path, arcname=arcname)
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
        context: list[SourceItem] | None = None,
        selected_source_ids: list[str] | None = None,
        input_materials: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        adapt = bindings["wechat.adapt_longform"]
        if not (
            adapt.enabled
            and self.settings.model_base_url
            and (adapt.model_name or self.settings.model_name)
        ):
            return None
        context = context or self._context(db, source)
        source_blocks = self.editorial._source_blocks(context)
        selected_source_ids = selected_source_ids or [source.id]
        selected_roles = {
            source_id: "primary" if index == 0 else "supporting"
            for index, source_id in enumerate(selected_source_ids)
        }
        for block in source_blocks:
            block["evidence_contract"] = "selected-or-connected-source"
            block["selection_role"] = selected_roles.get(block["source_id"], "connected")
        material_blocks = self._merge_material_blocks(
            source_blocks,
            input_materials or [],
        )
        source_json = json.dumps(material_blocks, ensure_ascii=False)[:48000]
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
11. selection_role=primary/supporting 的来源均是作者明确选择的事实材料；有多个时按任务需要对照，
    不得因为某项事实不在主来源里，就忽略 supporting 来源并声称“缺乏资料”。
12. selection_role=written_version 是作者明确选入的已写版本：可以复用其结构、表达和未完成内容，
    但其中事实仍须回到关联的 primary/supporting 来源核对，不能把历史稿本身当成新的事实来源。
13. 代码示例必须使用带语言名的 Markdown 围栏，逐行完整；绝不允许停在半行代码、未闭合围栏或半句话。
14. 输出 JSON 前自行核对：正文所有 H2 已写完，代码块已闭合，最后有完整判断；配图规划的 after_heading
    必须与正文中真实存在的 H2 完全一致。

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
  "illustration_plan":[{{"after_heading":"必须与一个 H2 章节名完全一致","type":"infographic|flowchart|comparison|framework|scene","purpose":"这张图帮助读者理解什么","brief":"具体主体、场景、动作和空间关系","composition":"主体位置、层级、视线和留白","use_source_asset":true}}]
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
                max_tokens=12000,
                capture_response_meta=True,
                request_timeout_seconds=360,
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
        response_meta = result.pop("_x2red_response_meta", {})
        normalized_body = self._normalize_bare_code_blocks(
            str(result.get("body_markdown") or "")
        )
        code_fences_normalized = normalized_body != str(result.get("body_markdown") or "")
        result["body_markdown"] = normalized_body
        issues = self._article_completion_issues(result, response_meta=response_meta)
        repaired = False
        if issues:
            repair_prompt = f"""
上一轮公众号长文输出不完整，禁止只补一句或只续写尾部。请基于全部来源重新返回一份从开头到结尾都完整的 JSON 成稿。

检测到的问题：{json.dumps(issues, ensure_ascii=False)}
全部输入材料：{source_json}
上一轮输出：{json.dumps(result, ensure_ascii=False)[:50000]}

必须保留有证据支持的内容并完成所有尚未写出的章节。所有代码使用带语言名的 Markdown 围栏，
代码块和括号完整闭合，代码之后继续完成分析、能力边界、安全风险和结尾判断。
written_version 只作为待整合稿件，事实仍须由 primary/supporting 来源支持。
配图规划的 after_heading 必须逐项对应最终正文中真实存在的 H2。

只输出与上一轮相同字段的完整 JSON，不要解释修复过程。
""".strip()
            try:
                result = await self.editorial._chat_json(
                    system_prompt=(
                        "你是公众号长文修复总编。你的首要任务是交付完整文章，绝不把半行代码或半句话当成成稿。"
                    ),
                    user_prompt=repair_prompt,
                    temperature=0.25,
                    reasoning_effort=adapt.reasoning_effort,
                    model_name=adapt.model_name,
                    max_tokens=12000,
                    capture_response_meta=True,
                    request_timeout_seconds=360,
                )
            except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise PlatformStudioError(
                    f"模型返回的公众号正文不完整，自动修复失败：{'；'.join(issues)}"
                ) from exc
            response_meta = result.pop("_x2red_response_meta", {})
            normalized_body = self._normalize_bare_code_blocks(
                str(result.get("body_markdown") or "")
            )
            code_fences_normalized = normalized_body != str(
                result.get("body_markdown") or ""
            )
            result["body_markdown"] = normalized_body
            remaining = self._article_completion_issues(result, response_meta=response_meta)
            if remaining:
                raise PlatformStudioError(
                    f"模型连续两次返回不完整正文，已阻止保存：{'；'.join(remaining)}"
                )
            repaired = True
        if include_citations and bindings["wechat.citations"].enabled:
            result["body_markdown"] = self._append_citations(
                str(result.get("body_markdown") or ""),
                result.get("citations"),
                context,
            )
        result["_completion"] = {
            "status": "complete_after_repair" if repaired else "complete",
            "issues_repaired": issues,
            "finish_reason": str(response_meta.get("finish_reason") or ""),
            "completion_tokens": response_meta.get("completion_tokens"),
            "code_fences_normalized": code_fences_normalized,
        }
        result["_model_used"] = True
        return result

    @staticmethod
    def _merge_material_blocks(
        source_blocks: list[dict[str, Any]],
        materials: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not materials:
            return source_blocks
        by_source = {str(item.get("source_id") or ""): item for item in source_blocks}
        selected_budget = max(1600, min(10000, 38000 // max(1, len(materials))))
        output: list[dict[str, Any]] = []
        used_sources: set[str] = set()
        for material in materials:
            kind = str(material.get("kind") or "source")
            source_id = str(material.get("source_id") or material.get("id") or "")
            if kind == "source":
                block = by_source.get(source_id)
                if block is None or source_id in used_sources:
                    continue
                item = dict(block)
                item["material_ref"] = str(material.get("ref") or f"source:{source_id}")
                item["material_kind"] = "source"
                item["text"] = str(item.get("text") or "")[:selected_budget]
                output.append(item)
                used_sources.add(source_id)
                continue
            output.append(
                {
                    "material_ref": str(material.get("ref") or ""),
                    "material_id": str(material.get("id") or ""),
                    "material_kind": kind,
                    "source_id": source_id,
                    "selection_role": "written_version",
                    "fact_contract": "可复用结构与表达，但具体事实必须由关联原始来源支持",
                    "title": str(material.get("title") or "已写版本"),
                    "version": material.get("version"),
                    "platform": str(material.get("platform") or "draft"),
                    "text": str(material.get("body") or "")[:selected_budget],
                    "body_sha256": str(material.get("body_sha256") or ""),
                }
            )
        for block in source_blocks:
            source_id = str(block.get("source_id") or "")
            if source_id in used_sources:
                continue
            item = dict(block)
            item["text"] = str(item.get("text") or "")[:1600 if item.get("selection_role") == "connected" else selected_budget]
            output.append(item)
        for index, item in enumerate(output, start=1):
            item["index"] = index
        return output

    @staticmethod
    def _has_bare_code_marker(body: str) -> bool:
        languages = {"python", "javascript", "typescript", "bash", "shell", "json"}
        inside_fence = False
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("```"):
                inside_fence = not inside_fence
                continue
            if not inside_fence and stripped.lower() in languages:
                return True
        return False

    @staticmethod
    def _looks_like_code_line(line: str, language: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return True
        if (
            language == "python"
            and stripped.startswith("#")
            and not re.match(r"^#{2,6}\s", stripped)
        ):
            return True
        if re.match(r"^(?:#{1,6}\s|>|[-*+]\s|\d+[.)]\s)", stripped):
            return False
        if re.match(r"^[\u3400-\u9fff]", stripped):
            return False
        if line[:1].isspace():
            return True
        if re.match(
            r"^(?:import|from|def|class|async|await|if|elif|else|for|while|try|except|finally|with|return|raise|yield|break|continue|pass|const|let|var|function|export|interface|type|echo|cd|curl|pip|npm|git)\b",
            stripped,
            flags=re.IGNORECASE,
        ):
            return True
        if stripped.startswith(("@", "$", "//", "/*", "*", "}")):
            return True
        if language == "json" and stripped.startswith(('"', "{", "[", "}", "]")):
            return True
        return bool(re.search(r"(?:=|\(|\)|\[|\]|\{|\}|:|;|->)", stripped))

    @staticmethod
    def _normalize_bare_code_blocks(body: str) -> str:
        languages = {"python", "javascript", "typescript", "bash", "shell", "json"}

        lines = body.splitlines()
        output: list[str] = []
        index = 0
        inside_fence = False
        while index < len(lines):
            line = lines[index]
            stripped = line.strip()
            if stripped.startswith("```"):
                inside_fence = not inside_fence
                output.append(line)
                index += 1
                continue
            language = stripped.lower()
            if inside_fence or language not in languages:
                output.append(line)
                index += 1
                continue

            cursor = index + 1
            code_lines: list[str] = []
            while cursor < len(lines):
                candidate = lines[cursor]
                if candidate.strip():
                    if not PlatformStudioService._looks_like_code_line(candidate, language):
                        break
                    code_lines.append(candidate)
                    cursor += 1
                    continue
                lookahead = cursor + 1
                while lookahead < len(lines) and not lines[lookahead].strip():
                    lookahead += 1
                if lookahead < len(lines) and PlatformStudioService._looks_like_code_line(
                    lines[lookahead], language
                ):
                    code_lines.append(candidate)
                    cursor += 1
                    continue
                break
            if not any(value.strip() for value in code_lines):
                output.append(line)
                index += 1
                continue
            while code_lines and not code_lines[-1].strip():
                code_lines.pop()
            output.extend([f"```{language}", *code_lines, "```"])
            index = cursor
        return PlatformStudioService._extend_fenced_code_spill("\n".join(output))

    @staticmethod
    def _extend_fenced_code_spill(body: str) -> str:
        languages = {"python", "javascript", "typescript", "bash", "shell", "json"}
        lines = body.splitlines()
        output: list[str] = []
        index = 0
        inside_fence = False
        language = ""
        while index < len(lines):
            line = lines[index]
            stripped = line.strip()
            if not inside_fence and stripped.startswith("```"):
                language = stripped[3:].strip().lower()
                inside_fence = True
                output.append(line)
                index += 1
                continue
            if inside_fence and stripped == "```":
                cursor = index + 1
                while cursor < len(lines) and not lines[cursor].strip():
                    cursor += 1
                if (
                    language in languages
                    and cursor < len(lines)
                    and PlatformStudioService._looks_like_code_line(lines[cursor], language)
                ):
                    output.extend(lines[index + 1 : cursor])
                    spill_cursor = cursor
                    while spill_cursor < len(lines):
                        candidate = lines[spill_cursor]
                        if candidate.strip():
                            if not PlatformStudioService._looks_like_code_line(
                                candidate, language
                            ):
                                break
                            output.append(candidate)
                            spill_cursor += 1
                            continue
                        lookahead = spill_cursor + 1
                        while lookahead < len(lines) and not lines[lookahead].strip():
                            lookahead += 1
                        if (
                            lookahead < len(lines)
                            and PlatformStudioService._looks_like_code_line(
                                lines[lookahead], language
                            )
                        ):
                            output.append(candidate)
                            spill_cursor += 1
                            continue
                        break
                    output.append("```")
                    inside_fence = False
                    language = ""
                    index = spill_cursor
                    continue
                inside_fence = False
                language = ""
            output.append(line)
            index += 1
        return "\n".join(output)

    @staticmethod
    def _has_unfenced_code_lines(body: str) -> bool:
        inside_fence = False
        run = 0
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("```"):
                inside_fence = not inside_fence
                run = 0
                continue
            if inside_fence or not stripped:
                continue
            if re.match(r"^(?:#{1,6}\s|>|[-*+]\s|\d+[.)]\s)", stripped):
                run = 0
                continue
            if PlatformStudioService._looks_like_code_line(line, "python"):
                run += 1
                if run >= 3:
                    return True
            else:
                run = 0
        return False

    @staticmethod
    def _article_completion_issues(
        result: dict[str, Any],
        *,
        response_meta: dict[str, Any] | None = None,
    ) -> list[str]:
        issues: list[str] = []
        finish_reason = str((response_meta or {}).get("finish_reason") or "").lower()
        if finish_reason in {"length", "max_tokens", "token_limit"}:
            issues.append("模型因输出长度上限停止")
        body = str(result.get("body_markdown") or "").strip()
        if len(re.sub(r"\s+", "", body)) < 500:
            issues.append("正文过短，未形成完整长文")
        if body.count("```") % 2:
            issues.append("Markdown 代码围栏未闭合")
        if PlatformStudioService._has_bare_code_marker(body):
            issues.append("代码没有使用可验证的 Markdown 围栏")
        if PlatformStudioService._has_unfenced_code_lines(body):
            issues.append("检测到代码行位于 Markdown 围栏之外")
        if body and not re.search(r"[。！？!?…）》」』)\]]$", body):
            issues.append("正文结束在半句话或半行代码")
        headings = {
            re.sub(r"\s+", "", value).lower()
            for value in re.findall(r"(?m)^##\s+(.+?)\s*$", body)
            if not re.search(r"(?:来源|参考|引用|延伸阅读)$", value.strip())
        }
        if len(headings) < 3:
            issues.append("正文少于三个完整章节")
        plan = result.get("illustration_plan")
        if isinstance(plan, list):
            missing = [
                str(item.get("after_heading") or "").strip()
                for item in plan
                if isinstance(item, dict)
                and str(item.get("after_heading") or "").strip()
                and re.sub(r"\s+", "", str(item.get("after_heading") or "")).lower() not in headings
            ]
            if missing:
                issues.append(f"配图规划引用了正文不存在的章节：{'、'.join(missing[:4])}")
        return list(dict.fromkeys(issues))

    def _fallback_copy(
        self,
        db: Session,
        *,
        source: SourceItem,
        draft: DraftRevision | None,
        include_citations: bool,
        context: list[SourceItem] | None = None,
    ) -> dict[str, Any]:
        title = draft.title.strip() if draft and draft.title.strip() else self._source_title(source)
        context = context or self._context(db, source)
        selected_text = "\n\n".join(item.text_original.strip() for item in context if item.text_original.strip())
        text = "\n\n".join(
            value
            for value in (
                draft.body.strip() if draft and draft.body.strip() else "",
                selected_text,
            )
            if value
        )
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

    def _evidence_context(
        self,
        db: Session,
        selected_sources: list[SourceItem],
    ) -> list[SourceItem]:
        context: list[SourceItem] = []
        seen: set[str] = set()
        for source in selected_sources:
            for item in self._context(db, source):
                if item.id in seen:
                    continue
                seen.add(item.id)
                context.append(item)
        return context

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
        seen_urls: set[str] = set()
        if isinstance(citations, list):
            for item in citations:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("label") or "来源").strip()
                url = str(item.get("url") or "").strip()
                if url.startswith(("http://", "https://")) and url not in seen_urls:
                    values.append((label, url))
                    seen_urls.add(url)
        for item in context:
            pair = (item.author_name or item.author_handle or "X 来源", item.canonical_url)
            if pair[1].startswith(("http://", "https://")) and pair[1] not in seen_urls:
                values.append(pair)
                seen_urls.add(pair[1])
        if not values or re.search(r"(?m)^##\s+(?:来源|参考|引用)", markdown):
            return markdown
        lines = ["## 来源与延伸阅读"]
        lines.extend(f"{index}. [{label}]({url})" for index, (label, url) in enumerate(values[:12], 1))
        return markdown.rstrip() + "\n\n" + "\n".join(lines)

    def _build_visual_handoff(
        self,
        *,
        title: str,
        summary: str,
        body_markdown: str,
        theme_id: str,
        illustration_plan: Any,
        previous: Any = None,
        visual_bible: Any = None,
    ) -> list[dict[str, Any]]:
        theme = get_theme(theme_id)
        sections = self._markdown_sections(body_markdown)
        plans = [item for item in illustration_plan if isinstance(item, dict)] if isinstance(illustration_plan, list) else []
        previous_by_id = {
            str(item.get("slot_id") or ""): item
            for item in previous
            if isinstance(item, dict) and item.get("slot_id")
        } if isinstance(previous, list) else {}

        def finish(slot: dict[str, Any]) -> dict[str, Any]:
            prompt_hash = hashlib.sha256(str(slot["prompt"]).encode("utf-8")).hexdigest()
            slot["prompt_hash"] = prompt_hash
            old = previous_by_id.get(str(slot["slot_id"]))
            if old and old.get("prompt_hash") == prompt_hash:
                for key in (
                    "asset_id",
                    "asset_sha256",
                    "asset_width",
                    "asset_height",
                    "asset_mime_type",
                    "asset_uploaded_at",
                ):
                    if old.get(key):
                        slot[key] = old[key]
            return slot

        bible = visual_bible if isinstance(visual_bible, dict) else {}
        bible_rules = ""
        if bible:
            raw_invariants = bible.get("invariants")
            invariants = raw_invariants if isinstance(raw_invariants, list) else []
            bible_rules = (
                f"冻结 Visual Bible：纸张系统 {bible.get('paper_system') or '统一纸本'}；"
                f"强调色政策 {bible.get('accent_policy') or '单一强调色'}；"
                f"摄影处理 {bible.get('photographic_treatment') or '克制纪实'}；"
                f"插画处理 {bible.get('illustration_treatment') or '单一具体主体'}；"
                f"整组不变量 {'；'.join(str(item) for item in invariants)}。"
                "这些规则只决定怎么画，不得替代当前章节证据决定画什么。"
            )
        shared_rules = (
            f"整体视觉语言：{theme.label}，纸张底色 {theme.paper}，正文深色 {theme.text}，"
            f"只使用一个强调色 {theme.accent}；克制、编辑感、真实材质、清晰焦点。"
            f"{bible_rules}"
            "画面中不得出现中文、英文、字母、数字、Logo、水印、签名、角标、二维码、UI 或标签；"
            "不要虚构具有事实含义的数据图表、真实产品界面、机构标识或人物身份。"
            "不要套模板边框，不要廉价 3D 图标堆叠，不要赛博霓虹，不要多主体抢焦点。"
            "只输出一张完成图，不输出解释。"
        )
        cover_seed = summary.strip() or (sections[0][1] if sections else body_markdown)
        cover_seed = self._visual_excerpt(cover_seed, 360)
        cover_prompt = (
            f"为微信公众号长文《{title}》生成一张无字封面视觉母图。"
            "规格：16:9 横图，至少 1600×900；主体放在中央 55% 安全区，左右和上下保留充足延展空间，"
            "确保同一张图后续可安全裁切为 21:9 主封面和 1:1 分享封面。"
            f"文章核心：{cover_seed}。"
            "画面要求：用一个具体、可辨认的核心物件或场景表达文章判断，前景与背景层级明确，"
            "避免把整篇文章的所有概念同时塞入画面；不在图内排标题，标题由 X2RED 本地完成。"
            f"{shared_rules}"
        )
        output = [
            finish(
                {
                    "slot_id": "cover_visual",
                    "kind": "cover",
                    "label": "封面视觉母图",
                    "placement": "上传后由 X2RED 本地生成 21:9 主封面与 1:1 分享封面",
                    "aspect_ratio": "16:9（中央主体，兼容 21:9 与 1:1 裁切）",
                    "alt_text": f"{title}的封面视觉",
                    "prompt": cover_prompt,
                }
            )
        ]

        type_labels = {
            "infographic": "信息关系的编辑插画",
            "flowchart": "流程关系的编辑插画",
            "comparison": "左右对照的编辑插画",
            "framework": "层级框架的编辑插画",
            "scene": "纪实感场景插画",
        }
        for index, (heading, excerpt) in enumerate(sections, start=1):
            normalized_heading = re.sub(r"\s+", "", heading).lower()
            plan = next(
                (
                    item
                    for item in plans
                    if re.sub(r"\s+", "", str(item.get("after_heading") or "")).lower()
                    == normalized_heading
                ),
                plans[index - 1] if index - 1 < len(plans) else {},
            )
            visual_type = str(plan.get("type") or "scene").strip().lower()
            visual_type = visual_type if visual_type in type_labels else "scene"
            purpose = self._visual_excerpt(str(plan.get("purpose") or "解释本节的核心关系"), 180)
            brief = self._visual_excerpt(str(plan.get("brief") or excerpt), 420)
            composition = self._visual_excerpt(str(plan.get("composition") or ""), 220)
            if not composition:
                composition = {
                    "comparison": "左右两组主体形成明确对照，中间留出呼吸区，不使用文字标签",
                    "flowchart": "用 3 至 5 个具象节点和清晰动线表达先后关系，不使用箭头文字",
                    "framework": "用前中后景或大小层级表达结构关系，避免流程图模板",
                    "infographic": "用具象物件之间的空间关系传达信息，不绘制带刻度的数据图",
                    "scene": "单一场景、一个核心主体、少量辅助物件，光线和视线都指向主体",
                }[visual_type]
            prompt = (
                f"为微信公众号长文《{title}》的章节《{heading}》生成一张正文配图。"
                "规格：16:9 横图，至少 1600×900，适合手机阅读，单张图、无边框。"
                f"本节证据与语义锚点：{self._visual_excerpt(excerpt, 460)}。"
                f"配图目的：{purpose}。视觉类型：{type_labels[visual_type]}。"
                f"核心画面：{brief}。构图：{composition}。"
                "必须让画面含义与本节一致，但不要增加文章没有提供的数字、品牌、界面或结论。"
                f"{shared_rules}"
            )
            output.append(
                finish(
                    {
                        "slot_id": f"section_{index:02d}",
                        "kind": "section",
                        "label": f"正文配图 {index:02d} · {heading}",
                        "placement": f"置于章节《{heading}》标题之后",
                        "after_heading": heading,
                        "aspect_ratio": "16:9",
                        "alt_text": f"{heading}：{purpose}"[:240],
                        "prompt": prompt,
                    }
                )
            )
        return output

    @staticmethod
    def _markdown_sections(markdown: str) -> list[tuple[str, str]]:
        matches = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", markdown))
        sections: list[tuple[str, str]] = []
        for index, match in enumerate(matches):
            heading = match.group(1).strip()
            if re.search(r"(?:来源|参考|引用|延伸阅读)$", heading):
                continue
            end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
            excerpt = markdown[match.end():end]
            sections.append((heading, PlatformStudioService._visual_excerpt(excerpt, 700)))
        if sections:
            return sections
        fallback = PlatformStudioService._visual_excerpt(markdown, 700)
        return [("核心内容", fallback)] if fallback else []

    @staticmethod
    def _visual_excerpt(value: str, limit: int) -> str:
        text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", str(value or ""))
        text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"[#>*_`|]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip(" -：:；;")
        return text[:limit].rstrip("，。；： ")

    def _visual_asset_records(
        self,
        db: Session,
        metadata: dict[str, Any],
    ) -> list[dict[str, Any]]:
        prompts = metadata.get("visual_prompts")
        if not isinstance(prompts, list):
            return []
        media_root = self.settings.media_dir.resolve()
        records: list[dict[str, Any]] = []
        for slot in prompts:
            if not isinstance(slot, dict) or not slot.get("asset_id"):
                continue
            slot_id = str(slot.get("slot_id") or "")
            if not re.fullmatch(r"[a-z0-9_]{1,64}", slot_id):
                continue
            asset = db.get(Asset, str(slot["asset_id"]))
            if asset is None or asset.state != AssetState.ready.value or not asset.local_path:
                continue
            source_path = Path(asset.local_path).resolve()
            if media_root not in source_path.parents or not source_path.is_file():
                continue
            suffix = source_path.suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
                continue
            records.append(
                {
                    "slot": slot,
                    "asset": asset,
                    "source_path": source_path,
                    "filename": f"{slot_id}{suffix}",
                }
            )
        return records

    @staticmethod
    def _markdown_with_visuals(
        markdown: str,
        records: list[dict[str, Any]],
        *,
        source_for: Any,
    ) -> str:
        section_records = [
            record for record in records if record["slot"].get("kind") == "section"
        ]
        if not section_records:
            return markdown
        by_heading = {
            re.sub(r"\s+", "", str(record["slot"].get("after_heading") or "")).lower(): record
            for record in section_records
            if record["slot"].get("after_heading")
        }
        used: set[str] = set()
        output: list[str] = []
        for line in markdown.splitlines():
            output.append(line)
            heading = re.match(r"^##\s+(.+?)\s*$", line.strip())
            if not heading:
                continue
            key = re.sub(r"\s+", "", heading.group(1)).lower()
            record = by_heading.get(key)
            if record is None:
                continue
            alt = re.sub(r"[\]\r\n]+", " ", str(record["slot"].get("alt_text") or "公众号配图")).strip()
            output.extend(["", f"![{alt}]({source_for(record)})", ""])
            used.add(str(record["slot"]["slot_id"]))
        for record in section_records:
            if str(record["slot"]["slot_id"]) in used:
                continue
            alt = re.sub(r"[\]\r\n]+", " ", str(record["slot"].get("alt_text") or "公众号配图")).strip()
            output.extend(["", f"![{alt}]({source_for(record)})"])
        return "\n".join(output).strip()

    @staticmethod
    def _visual_handoff_markdown(
        metadata: dict[str, Any],
        visual_manifest: list[dict[str, Any]],
    ) -> str:
        prompts = metadata.get("visual_prompts")
        lines = [
            "# 公众号视觉交接清单",
            "",
            "逐项把 Prompt 粘贴到带生图 Skill 的 Codex。回传图片已放入 illustrations/；发布前仍需人工核对画面事实、异常文字和版权。",
        ]
        if not isinstance(prompts, list) or not prompts:
            lines.extend(["", "当前版本未生成视觉 Prompt。"])
            return "\n".join(lines) + "\n"
        files = {str(item.get("slot_id") or ""): str(item.get("file") or "") for item in visual_manifest}
        for item in prompts:
            if not isinstance(item, dict):
                continue
            slot_id = str(item.get("slot_id") or "")
            lines.extend(
                [
                    "",
                    f"## {item.get('label') or slot_id}",
                    "",
                    f"- 位置：{item.get('placement') or '待确认'}",
                    f"- 比例：{item.get('aspect_ratio') or '按 Prompt'}",
                    f"- 回传：{files.get(slot_id) or '尚未上传'}",
                    "",
                    "```text",
                    str(item.get("prompt") or "").strip(),
                    "```",
                ]
            )
        return "\n".join(lines) + "\n"

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
