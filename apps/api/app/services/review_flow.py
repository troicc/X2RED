from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import DraftRevision, SourceItem, new_id
from app.domain.platforms import PlatformVariant
from app.domain.review_artifacts import ReviewArtifact, ReviewArtifactState
from app.services.platform_studio import PlatformStudioService
from app.services.publication_safety import public_card_spec, strip_internal_markers
from app.services.review_visual_renderer import ReviewVisualService
from app.services.rich_cards import RichCardService
from app.services.wechat_cover_renderer import WeChatCoverRenderer


class ReviewFlowError(RuntimeError):
    pass


class ReviewFlowService:
    def __init__(
        self,
        settings: Settings,
        card_service: RichCardService,
        platform_service: PlatformStudioService,
    ) -> None:
        self.settings = settings
        self.card_service = card_service
        self.platform_service = platform_service
        self.visual_service = ReviewVisualService(settings)
        self.cover_renderer = WeChatCoverRenderer()

    def list_artifacts(
        self,
        db: Session,
        *,
        scope_type: str = "",
        scope_id: str = "",
        artifact_type: str = "",
    ) -> list[ReviewArtifact]:
        query = select(ReviewArtifact)
        if scope_type:
            query = query.where(ReviewArtifact.scope_type == scope_type)
        if scope_id:
            query = query.where(ReviewArtifact.scope_id == scope_id)
        if artifact_type:
            query = query.where(ReviewArtifact.artifact_type == artifact_type)
        return list(
            db.scalars(
                query.order_by(
                    ReviewArtifact.artifact_type,
                    ReviewArtifact.version.desc(),
                )
            ).all()
        )

    def create(
        self,
        db: Session,
        *,
        scope_type: str,
        scope_id: str,
        artifact_type: str,
    ) -> ReviewArtifact:
        existing = db.scalar(
            select(ReviewArtifact)
            .where(
                ReviewArtifact.scope_type == scope_type,
                ReviewArtifact.scope_id == scope_id,
                ReviewArtifact.artifact_type == artifact_type,
                ReviewArtifact.state != ReviewArtifactState.superseded.value,
            )
            .order_by(ReviewArtifact.version.desc())
        )
        if existing is not None:
            return existing
        if artifact_type == "xhs_storyboard":
            payload = self._xhs_storyboard(db, scope_type, scope_id)
        elif artifact_type == "wechat_module_tree":
            payload = self._wechat_module_tree(db, scope_type, scope_id)
        elif artifact_type == "wechat_cover_brief":
            payload = self._wechat_cover_brief(db, scope_type, scope_id)
        else:
            raise ReviewFlowError(f"不支持的审阅产物：{artifact_type}")
        artifact = ReviewArtifact(
            scope_type=scope_type,
            scope_id=scope_id,
            artifact_type=artifact_type,
            version=self._next_version(db, scope_type, scope_id, artifact_type),
            payload_json=json.dumps(payload, ensure_ascii=False),
            state=ReviewArtifactState.draft.value,
            created_by="system",
        )
        db.add(artifact)
        db.flush()
        return artifact

    def revise(
        self,
        db: Session,
        current: ReviewArtifact,
        *,
        payload: dict[str, Any],
        note: str,
    ) -> ReviewArtifact:
        normalized = self._normalize_payload(current.artifact_type, payload)
        current.state = ReviewArtifactState.superseded.value
        revised = ReviewArtifact(
            scope_type=current.scope_type,
            scope_id=current.scope_id,
            artifact_type=current.artifact_type,
            version=self._next_version(
                db,
                current.scope_type,
                current.scope_id,
                current.artifact_type,
            ),
            parent_id=current.id,
            payload_json=json.dumps(normalized, ensure_ascii=False),
            state=ReviewArtifactState.draft.value,
            review_note=note.strip()[:3000],
            created_by="human",
        )
        db.add(revised)
        db.flush()
        return revised

    def decide(
        self,
        db: Session,
        artifact: ReviewArtifact,
        *,
        decision: str,
        note: str,
    ) -> ReviewArtifact:
        if decision == "approved":
            artifact.state = ReviewArtifactState.approved.value
            artifact.approved_at = datetime.now(UTC)
            artifact.error = ""
        elif decision == "changes_requested":
            artifact.state = ReviewArtifactState.changes_requested.value
            artifact.approved_at = None
        else:
            raise ReviewFlowError("未知审阅决定")
        artifact.review_note = note.strip()[:3000]
        db.flush()
        return artifact

    def render_storyboard(
        self,
        db: Session,
        artifact: ReviewArtifact,
        *,
        template: str,
        preview: bool,
    ):
        if artifact.artifact_type != "xhs_storyboard":
            raise ReviewFlowError("当前产物不是小红书故事板")
        if artifact.state != ReviewArtifactState.approved.value and not preview:
            raise ReviewFlowError("请先批准故事板，再生成发布卡片")
        draft = db.get(DraftRevision, artifact.scope_id)
        if draft is None:
            raise ReviewFlowError("故事板关联的草稿不存在")
        payload = self._json_object(artifact.payload_json)
        pages = payload.get("pages")
        art_direction = payload.get("art_direction")
        if not isinstance(pages, list) or not pages:
            raise ReviewFlowError("故事板没有可渲染页面")
        if not isinstance(art_direction, dict):
            art_direction = {}
        render = self.visual_service.render(
            db,
            draft=draft,
            pages=[page for page in pages if isinstance(page, dict)],
            art_direction=art_direction,
            template=template,
            artifact_id=artifact.id,
        )
        artifact.applied_to_id = render.id
        artifact.state = ReviewArtifactState.applied.value
        db.flush()
        return render

    def apply_wechat_modules(
        self,
        db: Session,
        artifact: ReviewArtifact,
    ) -> PlatformVariant:
        if artifact.artifact_type != "wechat_module_tree":
            raise ReviewFlowError("当前产物不是公众号模块树")
        if artifact.state != ReviewArtifactState.approved.value:
            raise ReviewFlowError("请先批准公众号模块树")
        current = db.get(PlatformVariant, artifact.scope_id)
        if current is None:
            raise ReviewFlowError("模块树关联的公众号版本不存在")
        payload = self._json_object(artifact.payload_json)
        modules = payload.get("modules")
        if not isinstance(modules, list):
            raise ReviewFlowError("模块树内容损坏")
        markdown = self.modules_to_markdown(modules)
        revised = self.platform_service.revise_variant(
            db,
            current,
            title=str(payload.get("title") or current.title),
            subtitle=str(payload.get("subtitle") or current.subtitle),
            summary=str(payload.get("summary") or current.summary),
            body_markdown=markdown,
            tags=current.tags,
            theme=str(payload.get("theme") or current.theme),
        )
        metadata = self._json_object(revised.metadata_json)
        metadata["review_module_artifact_id"] = artifact.id
        metadata["review_module_artifact_version"] = artifact.version
        revised.metadata_json = json.dumps(metadata, ensure_ascii=False)
        artifact.applied_to_id = revised.id
        artifact.state = ReviewArtifactState.applied.value
        db.flush()
        return revised

    def render_wechat_cover(
        self,
        db: Session,
        artifact: ReviewArtifact,
    ) -> dict[str, str]:
        if artifact.artifact_type != "wechat_cover_brief":
            raise ReviewFlowError("当前产物不是公众号封面 brief")
        if artifact.state != ReviewArtifactState.approved.value:
            raise ReviewFlowError("请先批准封面 brief")
        variant = db.get(PlatformVariant, artifact.scope_id)
        if variant is None:
            raise ReviewFlowError("封面 brief 关联的公众号版本不存在")
        source = db.get(SourceItem, variant.source_id)
        if source is None:
            raise ReviewFlowError("公众号版本关联来源不存在")
        payload = self._json_object(artifact.payload_json)
        output_dir = self.settings.export_dir / "wechat" / variant.id
        output_dir.mkdir(parents=True, exist_ok=True)
        files = self.cover_renderer.render_pair(
            output_dir,
            title=strip_internal_markers(str(payload.get("title") or variant.title)),
            short_title=strip_internal_markers(
                str(payload.get("short_title") or "")
            ),
            subtitle=strip_internal_markers(
                str(payload.get("subtitle") or variant.subtitle)
            ),
            theme_id=str(payload.get("theme") or variant.theme),
            hero_image=self._hero_image(source),
            series_label=strip_internal_markers(
                str(payload.get("series_label") or "")
            ),
            cover_style=str(payload.get("cover_style") or "auto"),
            emphasis=str(payload.get("emphasis") or ""),
        )
        paths = self._json_object(variant.output_paths_json)
        paths.update(files)
        variant.output_paths_json = json.dumps(paths, ensure_ascii=False)
        metadata = self._json_object(variant.metadata_json)
        metadata["cover_review_artifact_id"] = artifact.id
        metadata["cover_style"] = str(payload.get("cover_style") or "auto")
        variant.metadata_json = json.dumps(metadata, ensure_ascii=False)
        artifact.applied_to_id = variant.id
        artifact.state = ReviewArtifactState.applied.value
        db.flush()
        return files

    def publisher_payload(self, db: Session, variant: PlatformVariant) -> dict[str, Any]:
        if variant.platform != "wechat":
            raise ReviewFlowError("只有公众号版本可以发送到发布助手")
        metadata = self._json_object(variant.metadata_json)
        files = self._json_object(variant.output_paths_json)
        warnings = metadata.get("validation", {}).get("warnings", [])
        if not isinstance(warnings, list):
            warnings = []
        return {
            "variant_id": variant.id,
            "title": variant.title,
            "author": str(metadata.get("author") or ""),
            "body_html": variant.body_html,
            "summary": variant.summary,
            "cover_wide_url": self._file_url(variant.id, files, "wide"),
            "cover_square_url": self._file_url(variant.id, files, "square"),
            "validation_warnings": [str(item) for item in warnings],
        }

    def _xhs_storyboard(
        self,
        db: Session,
        scope_type: str,
        scope_id: str,
    ) -> dict[str, Any]:
        if scope_type != "draft":
            raise ReviewFlowError("小红书故事板必须关联草稿")
        draft = db.get(DraftRevision, scope_id)
        if draft is None:
            raise ReviewFlowError("草稿不存在")
        pages = self.card_service._build_specs(
            draft,
            max_cards=7,
            use_analysis=True,
        )
        normalized_pages: list[dict[str, Any]] = []
        for raw in pages:
            page = public_card_spec(raw)
            page["id"] = str(page.get("id") or new_id("page"))
            page["title"] = str(page.get("title") or "")[:80]
            page["body"] = str(page.get("body") or "")[:500]
            page["items"] = [
                str(item)[:180]
                for item in (page.get("items") or [])[:4]
                if str(item).strip()
            ]
            normalized_pages.append(page)
        return {
            "art_direction": {
                "style": "technical_blueprint"
                if self._is_technical(draft.title + " " + draft.body)
                else "editorial_collage",
                "palette": "electric_blue"
                if self._is_technical(draft.title + " " + draft.body)
                else "signal_red",
                "density": "balanced",
                "material_strategy": "source_first",
            },
            "pages": normalized_pages,
            "review_questions": [
                "封面是否只承诺一个核心价值？",
                "每页是否只有一个认知任务？",
                "图解页是否真的降低理解成本？",
                "最后一页是否给出明确判断？",
            ],
        }

    def _wechat_module_tree(
        self,
        db: Session,
        scope_type: str,
        scope_id: str,
    ) -> dict[str, Any]:
        if scope_type != "platform_variant":
            raise ReviewFlowError("公众号模块树必须关联平台版本")
        variant = db.get(PlatformVariant, scope_id)
        if variant is None or variant.platform != "wechat":
            raise ReviewFlowError("公众号版本不存在")
        return {
            "title": variant.title,
            "subtitle": variant.subtitle,
            "summary": variant.summary,
            "theme": variant.theme,
            "modules": self.markdown_to_modules(variant.body_markdown),
        }

    def _wechat_cover_brief(
        self,
        db: Session,
        scope_type: str,
        scope_id: str,
    ) -> dict[str, Any]:
        if scope_type != "platform_variant":
            raise ReviewFlowError("公众号封面 brief 必须关联平台版本")
        variant = db.get(PlatformVariant, scope_id)
        if variant is None or variant.platform != "wechat":
            raise ReviewFlowError("公众号版本不存在")
        metadata = self._json_object(variant.metadata_json)
        return {
            "title": variant.title,
            "short_title": str(metadata.get("short_share_title") or ""),
            "subtitle": variant.subtitle or variant.summary,
            "series_label": "",
            "cover_style": "image_cinema"
            if self._hero_image(db.get(SourceItem, variant.source_id))
            else "tech_blueprint",
            "emphasis": self._extract_emphasis(variant.title + " " + variant.summary),
            "theme": variant.theme,
            "review_questions": [
                "3 秒内是否看懂主题？",
                "是否存在一个明确视觉锚点？",
                "标题是否适合 21:9 裁切？",
                "是否完全没有内部品牌或工作流信息？",
            ],
        }

    def _normalize_payload(
        self,
        artifact_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if artifact_type == "xhs_storyboard":
            pages = payload.get("pages")
            if not isinstance(pages, list) or not 3 <= len(pages) <= 9:
                raise ReviewFlowError("小红书故事板必须包含 3-9 页")
            allowed = {
                "hero_cover",
                "key_result",
                "concept_diagram",
                "before_after",
                "workflow_flow",
                "key_takeaways",
                "opinion_close",
            }
            clean_pages: list[dict[str, Any]] = []
            for raw in pages:
                if not isinstance(raw, dict):
                    continue
                kind = str(raw.get("kind") or "")
                if kind not in allowed:
                    raise ReviewFlowError(f"不支持的卡片页型：{kind}")
                clean_pages.append(
                    {
                        **public_card_spec(raw),
                        "id": str(raw.get("id") or new_id("page")),
                        "kind": kind,
                        "kicker": strip_internal_markers(
                            str(raw.get("kicker") or "")
                        )[:30],
                        "title": str(raw.get("title") or "").strip()[:80],
                        "body": str(raw.get("body") or "").strip()[:500],
                        "items": [
                            str(item).strip()[:180]
                            for item in (raw.get("items") or [])[:4]
                            if str(item).strip()
                        ],
                        "visual_brief": str(
                            raw.get("visual_brief") or ""
                        ).strip()[:300],
                    }
                )
            if not clean_pages or clean_pages[0]["kind"] != "hero_cover":
                raise ReviewFlowError("故事板第一页必须是封面")
            art_direction = payload.get("art_direction")
            return {
                "art_direction": art_direction
                if isinstance(art_direction, dict)
                else {},
                "pages": clean_pages,
                "review_questions": payload.get("review_questions") or [],
            }
        if artifact_type == "wechat_module_tree":
            modules = payload.get("modules")
            if not isinstance(modules, list) or not modules:
                raise ReviewFlowError("公众号模块树不能为空")
            return {
                "title": str(payload.get("title") or "")[:160],
                "subtitle": str(payload.get("subtitle") or "")[:240],
                "summary": str(payload.get("summary") or "")[:1000],
                "theme": str(payload.get("theme") or "auto")[:60],
                "modules": self._clean_modules(modules),
            }
        if artifact_type == "wechat_cover_brief":
            return {
                "title": strip_internal_markers(str(payload.get("title") or ""))[:160],
                "short_title": strip_internal_markers(
                    str(payload.get("short_title") or "")
                )[:30],
                "subtitle": strip_internal_markers(
                    str(payload.get("subtitle") or "")
                )[:240],
                "series_label": strip_internal_markers(
                    str(payload.get("series_label") or "")
                )[:30],
                "cover_style": str(payload.get("cover_style") or "auto")[:40],
                "emphasis": str(payload.get("emphasis") or "")[:40],
                "theme": str(payload.get("theme") or "auto")[:60],
                "review_questions": payload.get("review_questions") or [],
            }
        raise ReviewFlowError("未知审阅产物")

    @staticmethod
    def markdown_to_modules(markdown: str) -> list[dict[str, Any]]:
        lines = markdown.replace("\r\n", "\n").splitlines()
        modules: list[dict[str, Any]] = []
        paragraph: list[str] = []
        list_items: list[str] = []
        ordered = False
        in_code = False
        code_lines: list[str] = []

        def flush_paragraph() -> None:
            if paragraph:
                modules.append(
                    {
                        "id": new_id("module"),
                        "type": "paragraph",
                        "text": " ".join(paragraph).strip(),
                    }
                )
                paragraph.clear()

        def flush_list() -> None:
            nonlocal ordered
            if list_items:
                modules.append(
                    {
                        "id": new_id("module"),
                        "type": "list",
                        "ordered": ordered,
                        "items": list_items.copy(),
                    }
                )
                list_items.clear()
            ordered = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                flush_paragraph()
                flush_list()
                if in_code:
                    modules.append(
                        {
                            "id": new_id("module"),
                            "type": "code",
                            "text": "\n".join(code_lines),
                        }
                    )
                    code_lines.clear()
                in_code = not in_code
                continue
            if in_code:
                code_lines.append(line)
                continue
            if not stripped:
                flush_paragraph()
                flush_list()
                continue
            image = re.match(r"!\[(.*?)\]\((https?://[^)]+)\)", stripped)
            if image:
                flush_paragraph()
                flush_list()
                modules.append(
                    {
                        "id": new_id("module"),
                        "type": "image",
                        "alt": image.group(1),
                        "url": image.group(2),
                    }
                )
                continue
            heading = re.match(r"^(#{2,3})\s+(.+)$", stripped)
            if heading:
                flush_paragraph()
                flush_list()
                modules.append(
                    {
                        "id": new_id("module"),
                        "type": "heading",
                        "level": len(heading.group(1)),
                        "text": heading.group(2).strip(),
                    }
                )
                continue
            if stripped.startswith(">"):
                flush_paragraph()
                flush_list()
                modules.append(
                    {
                        "id": new_id("module"),
                        "type": "quote",
                        "text": stripped.lstrip(">").strip(),
                    }
                )
                continue
            match = re.match(r"^([-*+] |\d+[.)] )(.*)$", stripped)
            if match:
                flush_paragraph()
                marker = match.group(1).strip()
                current_ordered = bool(re.match(r"\d", marker))
                if list_items and current_ordered != ordered:
                    flush_list()
                ordered = current_ordered
                list_items.append(match.group(2).strip())
                continue
            flush_list()
            paragraph.append(stripped)
        flush_paragraph()
        flush_list()
        if code_lines:
            modules.append(
                {
                    "id": new_id("module"),
                    "type": "code",
                    "text": "\n".join(code_lines),
                }
            )
        return modules

    @staticmethod
    def modules_to_markdown(modules: list[dict[str, Any]]) -> str:
        output: list[str] = []
        for module in modules:
            kind = str(module.get("type") or "paragraph")
            if kind == "heading":
                level = 3 if int(module.get("level") or 2) == 3 else 2
                output.append(f"{'#' * level} {str(module.get('text') or '').strip()}")
            elif kind == "quote":
                output.append(f"> {str(module.get('text') or '').strip()}")
            elif kind == "list":
                ordered = bool(module.get("ordered"))
                rows = [
                    f"{index}. {str(item).strip()}"
                    if ordered
                    else f"- {str(item).strip()}"
                    for index, item in enumerate(module.get("items") or [], start=1)
                    if str(item).strip()
                ]
                output.append("\n".join(rows))
            elif kind == "code":
                output.append(f"```\n{str(module.get('text') or '').rstrip()}\n```")
            elif kind == "image":
                output.append(
                    f"![{str(module.get('alt') or '').strip()}]({str(module.get('url') or '').strip()})"
                )
            else:
                text = str(module.get("text") or "").strip()
                if text:
                    output.append(text)
        return "\n\n".join(item for item in output if item.strip()).strip()

    @staticmethod
    def _clean_modules(modules: list[Any]) -> list[dict[str, Any]]:
        allowed = {"paragraph", "heading", "quote", "list", "code", "image"}
        output: list[dict[str, Any]] = []
        for raw in modules[:120]:
            if not isinstance(raw, dict):
                continue
            kind = str(raw.get("type") or "paragraph")
            if kind not in allowed:
                continue
            item: dict[str, Any] = {
                "id": str(raw.get("id") or new_id("module")),
                "type": kind,
            }
            if kind == "list":
                item["ordered"] = bool(raw.get("ordered"))
                item["items"] = [
                    str(value).strip()[:1000]
                    for value in (raw.get("items") or [])[:30]
                    if str(value).strip()
                ]
            elif kind == "heading":
                item["level"] = 3 if int(raw.get("level") or 2) == 3 else 2
                item["text"] = str(raw.get("text") or "").strip()[:1000]
            elif kind == "image":
                item["alt"] = str(raw.get("alt") or "").strip()[:300]
                item["url"] = str(raw.get("url") or "").strip()[:3000]
            else:
                item["text"] = str(raw.get("text") or "").strip()[:12000]
            output.append(item)
        return output

    @staticmethod
    def _next_version(
        db: Session,
        scope_type: str,
        scope_id: str,
        artifact_type: str,
    ) -> int:
        current = db.scalar(
            select(func.max(ReviewArtifact.version)).where(
                ReviewArtifact.scope_type == scope_type,
                ReviewArtifact.scope_id == scope_id,
                ReviewArtifact.artifact_type == artifact_type,
            )
        )
        return int(current or 0) + 1

    @staticmethod
    def _json_object(value: str) -> dict[str, Any]:
        try:
            parsed = json.loads(value or "{}")
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _hero_image(source: SourceItem | None) -> str:
        if source is None:
            return ""
        for asset in source.assets:
            if asset.kind == "image" and asset.local_path and Path(asset.local_path).is_file():
                return asset.local_path
        return ""

    @staticmethod
    def _is_technical(text: str) -> bool:
        lowered = text.lower()
        return any(
            token in lowered
            for token in (
                "cuda",
                "gpu",
                "api",
                "mcp",
                "agent",
                "模型",
                "内核",
                "推理",
                "算法",
                "3d",
            )
        )

    @staticmethod
    def _extract_emphasis(value: str) -> str:
        match = re.search(r"\d+(?:\.\d+)?\s*(?:倍|%|ms|s|秒|分钟|万|亿)", value, flags=re.I)
        return match.group(0).replace(" ", "") if match else ""

    @staticmethod
    def _file_url(variant_id: str, files: dict[str, Any], key: str) -> str:
        return (
            f"/api/platforms/variants/{variant_id}/files/{key}"
            if files.get(key)
            else ""
        )
