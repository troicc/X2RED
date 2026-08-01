from __future__ import annotations

import asyncio
import html
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import DraftRevision, SourceItem
from app.domain.platforms import PlatformVariant, PlatformVariantState
from app.domain.review_artifacts import ReviewArtifact, ReviewArtifactState
from app.services.editorial import EditorialService
from app.services.light_content import (
    LightContentError,
    LightContentService,
    LightRenderValidation,
    RECIPE_GUIDES,
    RECIPE_LABELS,
)
from app.services.light_visual_renderer import (
    LightVisualRenderer,
    VISUAL_STYLE_LABELS,
)
from app.services.publication_safety import strip_internal_markers
from app.services.skills import binding_for


class LightContentLabService:
    """Bounded multi-agent generation, review, corpus learning, and visual rendering.

    The loop is intentionally not autonomous. Agents can generate and revise once,
    but only human-approved outputs enter the private corpus.
    """

    def __init__(self, settings: Settings, editorial: EditorialService) -> None:
        self.settings = settings
        self.editorial = editorial
        self.legacy = LightContentService(settings, editorial)
        self.renderer = LightVisualRenderer()

    async def create_variant(
        self,
        db: Session,
        *,
        source: SourceItem,
        draft: DraftRevision | None,
        recipe: str,
        image_count: int,
        seasonal_topic: str,
        audience: str,
        tone: str,
        theme: str,
        author: str,
        visual_style: str = "auto",
        quality_mode: str = "studio",
        feedback: str = "",
        previous_variant: PlatformVariant | None = None,
    ) -> PlatformVariant:
        if recipe not in RECIPE_LABELS:
            raise LightContentError("不支持的轻内容配方")
        if quality_mode not in {"fast", "studio"}:
            raise LightContentError("质量模式必须是 fast 或 studio")
        count = min(max(int(image_count), 3), 6)
        resolved_style = self.renderer.resolve_style(visual_style, recipe)
        corpus = self.list_corpus(db, recipe=recipe, limit=8)
        source_text = draft.body if draft and draft.body.strip() else source.text_original
        title_binding = binding_for(db, "wechat.title_summary", self.settings.model_name)
        visual_binding = binding_for(db, "visual.art_direction", self.settings.model_name)
        model_ready = bool(
            title_binding.enabled
            and visual_binding.enabled
            and self.settings.model_base_url
            and (title_binding.model_name or self.settings.model_name)
        )

        pipeline: dict[str, Any] | None = None
        if model_ready:
            pipeline = await self._run_agent_pipeline(
                source_text=source_text,
                recipe=recipe,
                image_count=count,
                seasonal_topic=seasonal_topic,
                audience=audience,
                tone=tone,
                visual_style=resolved_style,
                quality_mode=quality_mode,
                feedback=feedback,
                corpus=corpus,
                previous_variant=previous_variant,
                model_name=title_binding.model_name or self.settings.model_name,
                reasoning_effort=title_binding.reasoning_effort,
            )
        if pipeline is None:
            pipeline = self._fallback_pipeline(
                source=source,
                draft=draft,
                recipe=recipe,
                image_count=count,
                seasonal_topic=seasonal_topic,
                audience=audience,
                visual_style=resolved_style,
                feedback=feedback,
            )
            generator = "light-lab-multi-agent-fallback"
        else:
            generator = "light-lab-multi-agent-model"

        final = self.legacy._normalize_output(
            pipeline["final"],
            source=source,
            recipe=recipe,
            image_count=count,
            seasonal_topic=seasonal_topic,
        )
        final["posters"] = self._apply_visual_direction(
            final["posters"],
            pipeline.get("visual_direction") or {},
            resolved_style,
        )
        iteration_round = 1
        if previous_variant is not None:
            previous_meta = self._json_object(previous_variant.metadata_json)
            iteration_round = int(previous_meta.get("iteration_round") or 1) + 1
        metadata = {
            "generator": generator,
            "content_mode": "light_series",
            "pipeline_version": "light-lab-v12",
            "recipe": recipe,
            "recipe_label": RECIPE_LABELS[recipe],
            "audience": audience.strip(),
            "tone": tone.strip(),
            "seasonal_topic": seasonal_topic.strip(),
            "author": author.strip(),
            "visual_style": resolved_style,
            "visual_style_label": VISUAL_STYLE_LABELS[resolved_style],
            "quality_mode": quality_mode,
            "iteration_round": iteration_round,
            "feedback": feedback.strip()[:3000],
            "strategy": pipeline.get("strategy") or {},
            "candidates": pipeline.get("candidates") or [],
            "reviews": pipeline.get("reviews") or {},
            "quality_score": float(pipeline.get("quality_score") or 0),
            "selected_candidate_index": int(pipeline.get("selected_candidate_index") or 0),
            "chief_editor_note": str(pipeline.get("chief_editor_note") or ""),
            "revision_summary": str(pipeline.get("revision_summary") or ""),
            "auto_revision_triggered": bool(pipeline.get("auto_revision_triggered")),
            "poster_specs": final["posters"],
            "corpus_item_ids": [str(item.get("id") or "") for item in corpus if item.get("id")],
            "human_approved": False,
            "source_skill": {
                "repository": "LiamGvchi/gc-minimal-zine-poster",
                "skill_name": "gc-minimal-zine-poster-v0-1",
                "license": "MIT",
                "integration_mode": "native-adaptation",
            },
            "safety": {
                "medical_claims_forbidden": recipe in {"mature_life", "seasonal"},
                "human_review_required": True,
                "corpus_learning_requires_approval": True,
            },
        }
        variant = PlatformVariant(
            source_id=source.id,
            base_draft_id=draft.id if draft else None,
            platform="wechat",
            format="light_series",
            version=self._next_version(db, source.id),
            title=final["title"][:160],
            subtitle=final["subtitle"][:240],
            summary=final["summary"][:1000],
            body_markdown=final["body_markdown"][:50000],
            tags=final["tags"][:1000],
            theme=theme,
            skill_profile_json=json.dumps(
                {
                    "wechat.title_summary": {
                        "enabled": title_binding.enabled,
                        "model": title_binding.model_name or self.settings.model_name,
                        "reasoning_effort": title_binding.reasoning_effort,
                    },
                    "visual.art_direction": {
                        "enabled": visual_binding.enabled,
                        "model": visual_binding.model_name or self.settings.model_name,
                        "reasoning_effort": visual_binding.reasoning_effort,
                    },
                    "gc-minimal-zine-poster-v0-1": {
                        "enabled": True,
                        "integration_mode": "native-adaptation",
                    },
                },
                ensure_ascii=False,
            ),
            metadata_json=json.dumps(metadata, ensure_ascii=False),
            status=PlatformVariantState.draft.value,
            created_by="model" if generator.endswith("model") else "system",
        )
        db.add(variant)
        db.flush()
        self._save_trace(db, variant, metadata)
        return variant

    async def iterate_variant(
        self,
        db: Session,
        variant: PlatformVariant,
        *,
        feedback: str,
        quality_mode: str = "studio",
    ) -> PlatformVariant:
        if variant.platform != "wechat" or variant.format != "light_series":
            raise LightContentError("当前版本不是轻内容图组")
        metadata = self._json_object(variant.metadata_json)
        source = db.get(SourceItem, variant.source_id)
        if source is None:
            raise LightContentError("轻内容关联来源不存在")
        draft = db.get(DraftRevision, variant.base_draft_id) if variant.base_draft_id else None
        return await self.create_variant(
            db,
            source=source,
            draft=draft,
            recipe=str(metadata.get("recipe") or "comfort"),
            image_count=len(metadata.get("poster_specs") or []) or 4,
            seasonal_topic=str(metadata.get("seasonal_topic") or ""),
            audience=str(metadata.get("audience") or ""),
            tone=str(metadata.get("tone") or ""),
            theme=variant.theme,
            author=str(metadata.get("author") or ""),
            visual_style=str(metadata.get("visual_style") or "auto"),
            quality_mode=quality_mode,
            feedback=feedback,
            previous_variant=variant,
        )

    def select_candidate(
        self,
        db: Session,
        variant: PlatformVariant,
        *,
        candidate_index: int,
    ) -> PlatformVariant:
        if variant.platform != "wechat" or variant.format != "light_series":
            raise LightContentError("当前版本不是轻内容图组")
        metadata = self._json_object(variant.metadata_json)
        candidates = metadata.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise LightContentError("当前版本没有候选稿")
        if candidate_index < 0 or candidate_index >= len(candidates):
            raise LightContentError("候选序号无效")
        source = db.get(SourceItem, variant.source_id)
        if source is None:
            raise LightContentError("轻内容关联来源不存在")
        raw = candidates[candidate_index]
        if not isinstance(raw, dict):
            raise LightContentError("候选稿内容损坏")
        normalized = self.legacy._normalize_output(
            raw,
            source=source,
            recipe=str(metadata.get("recipe") or "comfort"),
            image_count=len(metadata.get("poster_specs") or []) or 4,
            seasonal_topic=str(metadata.get("seasonal_topic") or ""),
        )
        normalized["posters"] = self._apply_visual_direction(
            normalized["posters"],
            raw.get("visual_direction") if isinstance(raw.get("visual_direction"), dict) else {},
            str(metadata.get("visual_style") or "minimal_zine"),
        )
        revised_meta = dict(metadata)
        revised_meta.update(
            {
                "selected_candidate_index": candidate_index,
                "poster_specs": normalized["posters"],
                "human_approved": False,
                "selection_changed_by": "human",
            }
        )
        revised = PlatformVariant(
            source_id=variant.source_id,
            base_draft_id=variant.base_draft_id,
            platform="wechat",
            format="light_series",
            version=self._next_version(db, variant.source_id),
            title=normalized["title"],
            subtitle=normalized["subtitle"],
            summary=normalized["summary"],
            body_markdown=normalized["body_markdown"],
            tags=normalized["tags"],
            theme=variant.theme,
            skill_profile_json=variant.skill_profile_json,
            metadata_json=json.dumps(revised_meta, ensure_ascii=False),
            created_by="human",
            status=PlatformVariantState.draft.value,
        )
        db.add(revised)
        db.flush()
        return revised

    def approve_to_corpus(
        self,
        db: Session,
        variant: PlatformVariant,
        *,
        note: str = "",
    ) -> ReviewArtifact:
        if variant.platform != "wechat" or variant.format != "light_series":
            raise LightContentError("只有轻内容版本可以进入轻内容语料")
        metadata = self._json_object(variant.metadata_json)
        recipe = str(metadata.get("recipe") or "comfort")
        metadata["human_approved"] = True
        metadata["approved_for_corpus_at"] = datetime.now(UTC).isoformat()
        variant.metadata_json = json.dumps(metadata, ensure_ascii=False)
        payload = {
            "variant_id": variant.id,
            "title": variant.title,
            "subtitle": variant.subtitle,
            "summary": variant.summary,
            "body_markdown": variant.body_markdown,
            "tags": variant.tags,
            "recipe": recipe,
            "visual_style": metadata.get("visual_style"),
            "poster_specs": metadata.get("poster_specs") or [],
            "quality_score": metadata.get("quality_score") or 0,
            "note": note.strip()[:3000],
            "source_kind": "approved_output",
        }
        artifact = ReviewArtifact(
            scope_type="light_corpus",
            scope_id=recipe,
            artifact_type="light_corpus_item",
            version=self._next_artifact_version(db, "light_corpus", recipe, "light_corpus_item"),
            payload_json=json.dumps(payload, ensure_ascii=False),
            state=ReviewArtifactState.approved.value,
            review_note=note.strip()[:3000],
            created_by="human",
            applied_to_id=variant.id,
            approved_at=datetime.now(UTC),
        )
        db.add(artifact)
        db.flush()
        return artifact

    def add_corpus_item(
        self,
        db: Session,
        *,
        recipe: str,
        title: str,
        body_markdown: str,
        visual_style: str,
        note: str,
    ) -> ReviewArtifact:
        if recipe not in RECIPE_LABELS:
            raise LightContentError("不支持的语料配方")
        if not title.strip() and not body_markdown.strip():
            raise LightContentError("语料标题和正文不能同时为空")
        payload = {
            "title": strip_internal_markers(title).strip()[:160],
            "body_markdown": strip_internal_markers(body_markdown).strip()[:8000],
            "recipe": recipe,
            "visual_style": self.renderer.resolve_style(visual_style, recipe),
            "note": note.strip()[:3000],
            "source_kind": "authorized_sample",
        }
        artifact = ReviewArtifact(
            scope_type="light_corpus",
            scope_id=recipe,
            artifact_type="light_corpus_item",
            version=self._next_artifact_version(db, "light_corpus", recipe, "light_corpus_item"),
            payload_json=json.dumps(payload, ensure_ascii=False),
            state=ReviewArtifactState.approved.value,
            review_note=note.strip()[:3000],
            created_by="human",
            approved_at=datetime.now(UTC),
        )
        db.add(artifact)
        db.flush()
        return artifact

    def list_corpus(self, db: Session, *, recipe: str = "", limit: int = 50) -> list[dict[str, Any]]:
        query = select(ReviewArtifact).where(
            ReviewArtifact.scope_type == "light_corpus",
            ReviewArtifact.artifact_type == "light_corpus_item",
            ReviewArtifact.state == ReviewArtifactState.approved.value,
        )
        if recipe:
            query = query.where(ReviewArtifact.scope_id == recipe)
        artifacts = list(db.scalars(query.order_by(desc(ReviewArtifact.created_at)).limit(limit)).all())
        output: list[dict[str, Any]] = []
        for artifact in artifacts:
            payload = self._json_object(artifact.payload_json)
            output.append(
                {
                    "id": artifact.id,
                    "recipe": artifact.scope_id,
                    "version": artifact.version,
                    "created_at": artifact.created_at,
                    **payload,
                }
            )
        return output

    def render_variant(
        self,
        db: Session,
        variant: PlatformVariant,
        *,
        package: bool = True,
    ) -> tuple[PlatformVariant, LightRenderValidation, dict[str, str]]:
        if variant.platform != "wechat" or variant.format != "light_series":
            raise LightContentError("当前版本不是公众号轻内容图组")
        source = db.get(SourceItem, variant.source_id)
        if source is None:
            raise LightContentError("轻内容版本关联来源不存在")
        metadata = self._json_object(variant.metadata_json)
        specs = metadata.get("poster_specs")
        if not isinstance(specs, list) or not specs:
            raise LightContentError("图组故事板不存在")
        recipe = str(metadata.get("recipe") or "comfort")
        visual_style = str(metadata.get("visual_style") or "auto")
        output_dir = self.settings.export_dir / "wechat" / variant.id
        output_dir.mkdir(parents=True, exist_ok=True)
        hero_image = self.legacy._hero_image(source)
        files: dict[str, str] = {}
        rendered_specs: list[dict[str, Any]] = []
        for index, raw in enumerate(specs[:6], start=1):
            spec = raw if isinstance(raw, dict) else {}
            page_style = str(spec.get("visual_style") or visual_style)
            path = output_dir / f"poster-{index:02d}.png"
            prompt = self.renderer.compile_prompt(
                spec,
                visual_style=page_style,
                recipe=recipe,
                index=index,
                total=len(specs),
            )
            resolved = self.renderer.render(
                path,
                spec=spec,
                visual_style=page_style,
                hero_image=hero_image,
                recipe=recipe,
                index=index,
                total=len(specs),
            )
            rendered = {**spec, "visual_style": resolved, "final_prompt": prompt}
            files[f"poster_{index:02d}"] = str(path.resolve())
            rendered_specs.append(rendered)
        metadata["poster_specs"] = rendered_specs
        metadata["render_engine"] = "x2red-distinct-light-visual-v12"
        warnings = []
        if recipe in {"seasonal", "mature_life"}:
            warnings.append("时令、饮食和生活建议仍需人工核对，不得替代医疗意见。")
        if not metadata.get("human_approved"):
            warnings.append("当前版本尚未批准进入优质语料；发布前请完成最终人工审阅。")
        metadata["validation"] = {"errors": [], "warnings": warnings}
        variant.metadata_json = json.dumps(metadata, ensure_ascii=False)
        article_md = output_dir / "article.md"
        article_md.write_text(variant.body_markdown, encoding="utf-8")
        files["markdown"] = str(article_md.resolve())
        manifest = output_dir / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "variant_id": variant.id,
                    "platform": "wechat",
                    "format": "light_series",
                    "title": variant.title,
                    "summary": variant.summary,
                    "recipe": recipe,
                    "visual_style": visual_style,
                    "quality_score": metadata.get("quality_score"),
                    "iteration_round": metadata.get("iteration_round"),
                    "posters": [Path(value).name for key, value in files.items() if key.startswith("poster_")],
                    "poster_specs": rendered_specs,
                    "source_skill": metadata.get("source_skill"),
                    "agent_reviews": metadata.get("reviews"),
                    "safety": metadata.get("safety"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        files["manifest"] = str(manifest.resolve())
        preview = output_dir / "preview.html"
        preview.write_text(self._preview_document(variant, rendered_specs, metadata), encoding="utf-8")
        files["preview"] = str(preview.resolve())
        variant.body_html = self.legacy._body_fragment(variant)
        if package:
            archive_path = output_dir / f"wechat-light-series-{variant.id}.zip"
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for value in files.values():
                    path = Path(value)
                    if path.is_file():
                        archive.write(path, arcname=path.name)
            files["package"] = str(archive_path.resolve())
            variant.status = PlatformVariantState.packaged.value
        else:
            variant.status = PlatformVariantState.rendered.value
        variant.output_paths_json = json.dumps(files, ensure_ascii=False)
        variant.error = ""
        db.flush()
        return variant, LightRenderValidation(errors=[], warnings=warnings), files

    async def _run_agent_pipeline(
        self,
        *,
        source_text: str,
        recipe: str,
        image_count: int,
        seasonal_topic: str,
        audience: str,
        tone: str,
        visual_style: str,
        quality_mode: str,
        feedback: str,
        corpus: list[dict[str, Any]],
        previous_variant: PlatformVariant | None,
        model_name: str,
        reasoning_effort: str,
    ) -> dict[str, Any] | None:
        corpus_text = self._corpus_prompt(corpus)
        previous_text = ""
        if previous_variant is not None:
            previous_text = (
                f"\n上一版标题：{previous_variant.title}\n"
                f"上一版正文：{previous_variant.body_markdown[:2200]}\n"
            )
        common = f"""
内容配方：{RECIPE_LABELS[recipe]}
配方边界：{RECIPE_GUIDES[recipe]}
目标读者：{audience or '普通中文读者'}
语气：{tone or '自然、具体、克制'}
节气/时令：{seasonal_topic or '无指定'}
图片数量：{image_count}
视觉方向：{VISUAL_STYLE_LABELS[visual_style]}
用户修改意见：{feedback or '无'}
{previous_text}
来源材料：
{source_text[:12000]}

授权或人工批准语料（只学习节奏、结构和判断方式，禁止照抄句子）：
{corpus_text}
""".strip()
        try:
            strategy = await self._agent(
                role="轻内容选题策划",
                system=(
                    "你是中文公众号轻内容策划。先判断来源与配方是否匹配，再决定一个明确的情绪任务、"
                    "现实矛盾、事实边界和三种不同角度。拒绝空泛鸡汤、标题党和对中老年读者的俯视。"
                ),
                prompt=f"""{common}\n\n只输出 JSON：
{{"content_thesis":"一句核心判断","emotional_job":"读者读完获得什么",
"source_fit":"为什么适合/不适合这个配方","taboos":["禁区"],
"evidence_boundaries":["不能超出来源的结论"],
"angles":[{{"name":"角度名","promise":"承诺","opening":"开头方式"}}]}}""",
                model_name=model_name,
                reasoning_effort=reasoning_effort,
                temperature=0.35,
            )
            candidate_result = await self._agent(
                role="轻内容主笔",
                system=(
                    "你是中文轻内容主笔。一次写三份明显不同的候选，不要同义改写。每份必须具体、"
                    "像真实作者说话，并且标题、正文和图上短句属于同一个主题。"
                ),
                prompt=f"""{common}\n\n策划结果：
{json.dumps(strategy, ensure_ascii=False)}

生成 3 个候选。正文 120-500 字，2-5 个短段；每张图一句 6-24 字主句和最多 36 字小注。
只输出 JSON：
{{"candidates":[{{"angle":"候选角度","title":"12-28字","subtitle":"一句副标题",
"summary":"60-120字","body_markdown":"短正文","tags":["标签"],
"posters":[{{"phrase":"短句","note":"小注","visual_metaphor":"可画物件或场景",
"photo_direction":"照片/画面要求","layout":"构图提示","accent":"#RRGGBB","mood":"情绪"}}]}}]}}""",
                model_name=model_name,
                reasoning_effort=reasoning_effort,
                temperature=0.68,
            )
            candidates = candidate_result.get("candidates")
            if not isinstance(candidates, list) or len(candidates) < 2:
                return None
            candidates = [item for item in candidates[:3] if isinstance(item, dict)]
            review_tasks = [
                self._agent(
                    role="目标读者审稿",
                    system=(
                        "你只做目标读者审稿，不改稿。逐份检查是否有真实共鸣、是否说人话、是否尊重读者、"
                        "是否值得转发；识别鸡汤、说教、空话和驴头不对马嘴。"
                    ),
                    prompt=self._review_prompt(common, strategy, candidates, "audience"),
                    model_name=model_name,
                    reasoning_effort=reasoning_effort,
                    temperature=0.15,
                ),
                self._agent(
                    role="文化事实审校",
                    system=(
                        "你只做事实、文化与时令审校，不改稿。检查来源一致性、节气和饮食表述、医学承诺、"
                        "刻板印象、虚构细节和廉价古风。"
                    ),
                    prompt=self._review_prompt(common, strategy, candidates, "culture"),
                    model_name=model_name,
                    reasoning_effort=reasoning_effort,
                    temperature=0.1,
                ),
            ]
            if quality_mode == "studio":
                review_tasks.append(
                    self._agent(
                        role="视觉导演",
                        system=(
                            "你是视觉导演。让三份候选真正形成不同图组，不要所有页面都是米色纸、小方块和同一构图。"
                            "为每个候选指定风格、照片策略、物件、版式、色彩和页间节奏。"
                        ),
                        prompt=f"""{common}\n\n候选：{json.dumps(candidates, ensure_ascii=False)}
只输出 JSON：{{"candidate_directions":[{{"candidate_index":0,
"visual_style":"minimal_zine|photo_editorial|classical_ink|dark_contemplative|seasonal_folk|old_newspaper",
"why":"为什么适配","poster_directions":[{{"page":1,"layout":"","visual_metaphor":"","photo_direction":"","accent":"#RRGGBB"}}]}}]}}""",
                        model_name=model_name,
                        reasoning_effort=reasoning_effort,
                        temperature=0.35,
                    )
                )
            reviews_raw = await asyncio.gather(*review_tasks)
            audience_review = reviews_raw[0]
            culture_review = reviews_raw[1]
            visual_review = reviews_raw[2] if len(reviews_raw) > 2 else {
                "candidate_directions": [
                    {"candidate_index": index, "visual_style": visual_style, "poster_directions": []}
                    for index in range(len(candidates))
                ]
            }
            scores = self._aggregate_scores(candidates, audience_review, culture_review)
            best_index = max(range(len(candidates)), key=lambda index: scores[index])
            selected_score = scores[best_index]
            chief = await self._agent(
                role="轻内容总编",
                system=(
                    "你是最终总编。依据两路独立审稿选择最合适的候选，并只做一次必要修订。"
                    "不能把三份候选拼成一篇；不能为了金句牺牲来源一致性。"
                ),
                prompt=f"""{common}\n\n策划：{json.dumps(strategy, ensure_ascii=False)}
候选：{json.dumps(candidates, ensure_ascii=False)}
读者审稿：{json.dumps(audience_review, ensure_ascii=False)}
文化事实审校：{json.dumps(culture_review, ensure_ascii=False)}
机器汇总分：{json.dumps(scores, ensure_ascii=False)}，建议候选：{best_index}
视觉导演：{json.dumps(visual_review, ensure_ascii=False)}

输出最终稿。若候选已经足够好只做轻微修订；分数低于 7.5 必须修复关键问题。
只输出 JSON：{{"selected_index":0,"chief_editor_note":"选择原因",
"revision_summary":"改了什么","final":{{"title":"","subtitle":"","summary":"",
"body_markdown":"","tags":[""],"posters":[{{"phrase":"","note":"","visual_metaphor":"",
"photo_direction":"","layout":"","accent":"#RRGGBB","mood":""}}]}}}}""",
                model_name=model_name,
                reasoning_effort=reasoning_effort,
                temperature=0.28,
            )
            selected_index = int(chief.get("selected_index") if isinstance(chief.get("selected_index"), int) else best_index)
            selected_index = min(max(selected_index, 0), len(candidates) - 1)
            final = chief.get("final") if isinstance(chief.get("final"), dict) else candidates[selected_index]
            visual_direction = self._visual_for_candidate(visual_review, selected_index, visual_style)
            return {
                "strategy": strategy,
                "candidates": candidates,
                "reviews": {
                    "audience": audience_review,
                    "culture": culture_review,
                    "visual": visual_review,
                },
                "quality_score": round(float(scores[selected_index]), 2),
                "selected_candidate_index": selected_index,
                "chief_editor_note": chief.get("chief_editor_note") or "",
                "revision_summary": chief.get("revision_summary") or "",
                "auto_revision_triggered": selected_score < 7.5,
                "visual_direction": visual_direction,
                "final": final,
            }
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    async def _agent(
        self,
        *,
        role: str,
        system: str,
        prompt: str,
        model_name: str,
        reasoning_effort: str,
        temperature: float,
    ) -> dict[str, Any]:
        result = await self.editorial._chat_json(
            system_prompt=f"你的唯一角色是：{role}。{system}",
            user_prompt=prompt,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            model_name=model_name,
        )
        return result if isinstance(result, dict) else {}

    def _fallback_pipeline(
        self,
        *,
        source: SourceItem,
        draft: DraftRevision | None,
        recipe: str,
        image_count: int,
        seasonal_topic: str,
        audience: str,
        visual_style: str,
        feedback: str,
    ) -> dict[str, Any]:
        base = self.legacy._fallback_copy(
            source=source,
            draft=draft,
            recipe=recipe,
            image_count=image_count,
            seasonal_topic=seasonal_topic,
            audience=audience,
        )
        candidates = [base]
        for index, label in enumerate(("更具体的生活现场", "更克制的现实判断"), start=1):
            candidate = json.loads(json.dumps(base, ensure_ascii=False))
            candidate["angle"] = label
            candidate["title"] = self._fallback_title(recipe, seasonal_topic, index)
            candidate["body_markdown"] = self._fallback_body(
                base["body_markdown"],
                recipe=recipe,
                feedback=feedback,
                index=index,
            )
            for page_index, poster in enumerate(candidate["posters"]):
                poster["phrase"] = self._fallback_phrase(
                    str(poster.get("phrase") or ""),
                    page_index=page_index,
                    candidate_index=index,
                )
                poster["visual_style"] = visual_style
            candidates.append(candidate)
        scores = [6.4, 7.1, 7.4]
        selected_index = 2 if recipe in {"comfort", "short_commentary"} else 1
        return {
            "strategy": {
                "content_thesis": str(candidates[selected_index]["title"]),
                "emotional_job": "给读者一个具体、可理解的停顿，而不是空泛安慰",
                "taboos": ["鸡汤口号", "医学承诺", "俯视读者"],
                "evidence_boundaries": ["不超出来源和人工指定主题"],
                "angles": [{"name": item.get("angle", "基础角度")} for item in candidates],
            },
            "candidates": candidates,
            "reviews": {
                "audience": {"scores": scores, "note": "结构化回退审稿"},
                "culture": {"scores": [7.0, 7.2, 7.3], "note": "未发现确定性医学承诺"},
                "visual": {
                    "candidate_directions": [
                        {"candidate_index": index, "visual_style": visual_style, "poster_directions": []}
                        for index in range(3)
                    ]
                },
            },
            "quality_score": scores[selected_index],
            "selected_candidate_index": selected_index,
            "chief_editor_note": "在无模型模式下选择更具体、边界更清楚的版本。",
            "revision_summary": "使用确定性规则减少空话，并让标题与正文围绕同一主题。",
            "auto_revision_triggered": True,
            "visual_direction": {"visual_style": visual_style, "poster_directions": []},
            "final": candidates[selected_index],
        }

    @staticmethod
    def _review_prompt(common: str, strategy: dict[str, Any], candidates: list[dict[str, Any]], kind: str) -> str:
        dimension = (
            "共鸣、清晰、自然、尊重、可转发性"
            if kind == "audience"
            else "来源一致性、文化准确、时令安全、无医学承诺、无刻板印象"
        )
        return f"""{common}\n\n策划：{json.dumps(strategy, ensure_ascii=False)}
候选：{json.dumps(candidates, ensure_ascii=False)}
按以下维度逐份 0-10 分：{dimension}。
只输出 JSON：{{"candidate_reviews":[{{"candidate_index":0,"scores":{{"dimension":8}},
"average":8.0,"must_fix":["必须修改"],"strengths":["优点"]}}]}}"""

    @staticmethod
    def _aggregate_scores(
        candidates: list[dict[str, Any]],
        audience: dict[str, Any],
        culture: dict[str, Any],
    ) -> list[float]:
        def values(payload: dict[str, Any]) -> dict[int, float]:
            output: dict[int, float] = {}
            reviews = payload.get("candidate_reviews")
            if isinstance(reviews, list):
                for item in reviews:
                    if not isinstance(item, dict):
                        continue
                    try:
                        index = int(item.get("candidate_index"))
                        average = float(item.get("average"))
                    except (TypeError, ValueError):
                        continue
                    output[index] = min(max(average, 0), 10)
            return output
        audience_values = values(audience)
        culture_values = values(culture)
        return [
            round(audience_values.get(index, 6.0) * 0.58 + culture_values.get(index, 6.0) * 0.42, 2)
            for index in range(len(candidates))
        ]

    @staticmethod
    def _visual_for_candidate(payload: dict[str, Any], index: int, fallback: str) -> dict[str, Any]:
        values = payload.get("candidate_directions")
        if isinstance(values, list):
            for item in values:
                if not isinstance(item, dict):
                    continue
                try:
                    candidate_index = int(item.get("candidate_index"))
                except (TypeError, ValueError):
                    continue
                if candidate_index == index:
                    return item
        return {"visual_style": fallback, "poster_directions": []}

    def _apply_visual_direction(
        self,
        posters: list[dict[str, Any]],
        direction: dict[str, Any],
        fallback_style: str,
    ) -> list[dict[str, Any]]:
        style = self.renderer.resolve_style(str(direction.get("visual_style") or fallback_style), "comfort")
        page_directions = direction.get("poster_directions")
        page_map: dict[int, dict[str, Any]] = {}
        if isinstance(page_directions, list):
            for item in page_directions:
                if not isinstance(item, dict):
                    continue
                try:
                    page_map[int(item.get("page")) - 1] = item
                except (TypeError, ValueError):
                    continue
        output: list[dict[str, Any]] = []
        for index, poster in enumerate(posters):
            addition = page_map.get(index, {})
            merged = {**poster}
            for key in ("layout", "visual_metaphor", "photo_direction", "accent", "mood"):
                if addition.get(key):
                    merged[key] = addition[key]
            merged["visual_style"] = str(addition.get("visual_style") or style)
            output.append(merged)
        return output

    @staticmethod
    def _corpus_prompt(corpus: list[dict[str, Any]]) -> str:
        if not corpus:
            return "暂无人工批准语料。不要假装存在个人风格。"
        lines = []
        for index, item in enumerate(corpus[:8], start=1):
            lines.append(
                f"样本{index}｜{item.get('title', '')}\n"
                f"风格：{item.get('visual_style', '')}｜备注：{item.get('note', '')}\n"
                f"正文：{str(item.get('body_markdown') or '')[:650]}"
            )
        return "\n\n".join(lines)

    def _save_trace(self, db: Session, variant: PlatformVariant, metadata: dict[str, Any]) -> None:
        artifact = ReviewArtifact(
            scope_type="platform_variant",
            scope_id=variant.id,
            artifact_type="light_generation_trace",
            version=1,
            payload_json=json.dumps(
                {
                    "pipeline_version": metadata.get("pipeline_version"),
                    "strategy": metadata.get("strategy"),
                    "candidates": metadata.get("candidates"),
                    "reviews": metadata.get("reviews"),
                    "selected_candidate_index": metadata.get("selected_candidate_index"),
                    "quality_score": metadata.get("quality_score"),
                    "chief_editor_note": metadata.get("chief_editor_note"),
                    "revision_summary": metadata.get("revision_summary"),
                    "corpus_item_ids": metadata.get("corpus_item_ids"),
                },
                ensure_ascii=False,
            ),
            state=ReviewArtifactState.draft.value,
            created_by="system",
            applied_to_id=variant.id,
        )
        db.add(artifact)
        db.flush()

    @staticmethod
    def _fallback_title(recipe: str, seasonal_topic: str, index: int) -> str:
        values = {
            "comfort": ["别急着把每一天都过成答案", "真正的松弛，是允许自己有余地"],
            "mature_life": ["人到后来，先把自己的日子照顾好", "年岁增长，不等于把自己排在最后"],
            "seasonal": [f"{seasonal_topic or '顺着时令'}，先听天气也听自己", "节气是提醒，不是生活命令"],
            "photo_quote": ["照片没有说话，日子却慢了下来", "普通的一天，也值得留下一页"],
            "short_commentary": ["一句话能传播，判断仍要有边界", "越是着急的时代，越要慢一点下结论"],
        }
        return values[recipe][min(index - 1, 1)]

    @staticmethod
    def _fallback_body(base: str, *, recipe: str, feedback: str, index: int) -> str:
        prefix = {
            "comfort": "人累的时候，最先需要的往往不是另一条命令，而是一点可以喘气的余地。",
            "mature_life": "日子走到后来，重要的不是证明自己还能扛多少，而是知道什么值得留力气。",
            "seasonal": "时令提醒人观察天气、食物和身体感受，但它不是一套人人相同的命令。",
            "photo_quote": "一张照片能留下的，不只是景物，也是当时没有说出口的心情。",
            "short_commentary": "短评不负责替复杂问题盖棺定论，它只需要指出真正值得继续追问的地方。",
        }[recipe]
        suffix = f"\n\n人工修改重点：{feedback[:180]}" if feedback else ""
        return f"{prefix}\n\n{base.strip()}{suffix}"[:1200]

    @staticmethod
    def _fallback_phrase(phrase: str, *, page_index: int, candidate_index: int) -> str:
        if candidate_index == 1:
            replacements = ["先把今天过稳", "给自己留一点余地", "不必时时证明自己", "慢一点再判断"]
        else:
            replacements = ["很多累，不是休息少", "真正稀缺的是余地", "把力气留给重要的事", "边界比金句重要"]
        return replacements[page_index % len(replacements)] if phrase else replacements[page_index % len(replacements)]

    def _preview_document(
        self,
        variant: PlatformVariant,
        specs: list[dict[str, Any]],
        metadata: dict[str, Any],
    ) -> str:
        cards = "".join(
            f'<figure><img src="/api/platforms/variants/{variant.id}/files/poster_{index:02d}" '
            f'alt="{html.escape(str(spec.get("phrase") or "轻内容海报"))}">'
            f'<figcaption><strong>{html.escape(str(spec.get("phrase") or ""))}</strong>'
            f'<span>{html.escape(VISUAL_STYLE_LABELS.get(str(spec.get("visual_style") or ""), ""))}</span></figcaption></figure>'
            for index, spec in enumerate(specs, start=1)
        )
        return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(variant.title)}</title><style>
body{{margin:0;background:#111318;color:#f4f1e9;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif}}main{{max-width:1380px;margin:auto;padding:52px 28px}}header{{display:grid;grid-template-columns:1fr auto;gap:24px;align-items:end}}h1{{max-width:900px;margin:0;font-size:42px;line-height:1.18}}p{{max-width:760px;line-height:1.9;color:#aaa99f}}.score{{padding:14px 18px;border:1px solid #3b3e45;border-radius:16px;color:#d8b36a}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:24px;margin-top:34px}}figure{{margin:0;padding:10px;background:#1c1f25;border:1px solid #30343c;border-radius:16px}}img{{display:block;width:100%;aspect-ratio:3/5;object-fit:cover;border-radius:10px}}figcaption{{display:flex;justify-content:space-between;gap:12px;padding:12px 3px 4px;color:#b9b8af;font-size:13px}}figcaption strong{{color:#f3f0e7}}</style></head><body><main><header><div><h1>{html.escape(variant.title)}</h1><p>{html.escape(variant.summary)}</p></div><div class="score">质量分 {float(metadata.get('quality_score') or 0):.1f} · 第 {int(metadata.get('iteration_round') or 1)} 轮</div></header><section class="grid">{cards}</section></main></body></html>"""

    @staticmethod
    def _json_object(value: str) -> dict[str, Any]:
        try:
            parsed = json.loads(value or "{}")
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _next_version(db: Session, source_id: str) -> int:
        value = db.scalar(
            select(func.max(PlatformVariant.version)).where(
                PlatformVariant.source_id == source_id,
                PlatformVariant.platform == "wechat",
            )
        )
        return int(value or 0) + 1

    @staticmethod
    def _next_artifact_version(db: Session, scope_type: str, scope_id: str, artifact_type: str) -> int:
        value = db.scalar(
            select(func.max(ReviewArtifact.version)).where(
                ReviewArtifact.scope_type == scope_type,
                ReviewArtifact.scope_id == scope_id,
                ReviewArtifact.artifact_type == artifact_type,
            )
        )
        return int(value or 0) + 1
