from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.evidence_schemas import EvidenceBundle, EvidenceSectionRequest
from app.domain.models import DraftRevision, SourceItem
from app.domain.studio import (
    AgentRun,
    StyleProfile,
    WritingArtifact,
    WritingFeedback,
    WritingProject,
    WritingState,
)
from app.services.editorial import EditorialService
from app.services.evidence_compiler import EvidenceCompiler
from app.services.pool_memory import PoolMemoryService

ROLE_SKILLS = {
    "editor_in_chief": "writing.editor",
    "evidence_researcher": "writing.research",
    "outline_architect": "writing.outline",
    "writer": "writing.writer",
    "reader_reviewer": "review.reader",
    "fact_reviewer": "review.fact",
    "style_reviewer": "review.style",
    "chief_editor": "writing.chief_editor",
    "final_reviser": "writing.final_revision",
}


class WritingCore:
    def __init__(self, settings: Settings, editorial: EditorialService) -> None:
        self.settings = settings
        self.editorial = editorial

    @staticmethod
    def _json(value: str, fallback: Any) -> Any:
        try:
            parsed = json.loads(value or "")
        except (TypeError, json.JSONDecodeError):
            return fallback
        return parsed

    def create_project(
        self,
        db: Session,
        *,
        source: SourceItem,
        mode: str,
        reader: str,
        promise: str,
        main_thesis: str,
        style_profile_id: str | None,
        budget_limit_cents: int,
        supporting_sources: list[SourceItem] | None = None,
        input_materials: list[dict[str, Any]] | None = None,
    ) -> WritingProject:
        if style_profile_id and db.get(StyleProfile, style_profile_id) is None:
            raise ValueError("风格档案不存在")
        project = WritingProject(
            source_id=source.id,
            mode=mode,
            state=WritingState.clarifying.value,
            current_stage="editorial_brief",
            reader=reader.strip(),
            promise=promise.strip(),
            main_thesis=main_thesis.strip(),
            style_profile_id=style_profile_id,
            budget_limit_cents=budget_limit_cents,
        )
        db.add(project)
        db.flush()
        selected = [source, *(supporting_sources or [])]
        materials = input_materials or [
            {
                "ref": f"source:{item.id}",
                "kind": "source",
                "id": item.id,
                "source_id": item.id,
                "title": self._source_title(item),
            }
            for item in selected
        ]
        self._store_artifact(
            db,
            project=project,
            artifact_type="source_selection",
            content={
                "primary_source_id": source.id,
                "supporting_source_ids": [item.id for item in selected[1:]],
                "source_ids": [item.id for item in selected],
                "material_refs": [str(item.get("ref") or "") for item in materials],
                "materials": materials,
                "contract": "mixed-input-materials-v2",
                "fact_contract": (
                    "source materials are factual evidence; written versions are derivative writing material "
                    "whose factual claims must still trace to their underlying sources"
                ),
            },
            role="author",
            approved=True,
        )
        return project

    def artifacts(self, db: Session, project_id: str) -> list[WritingArtifact]:
        return list(
            db.scalars(
                select(WritingArtifact)
                .where(WritingArtifact.project_id == project_id)
                .order_by(WritingArtifact.created_at, WritingArtifact.version)
            ).all()
        )

    def runs(self, db: Session, project_id: str) -> list[AgentRun]:
        return list(
            db.scalars(
                select(AgentRun)
                .where(AgentRun.project_id == project_id)
                .order_by(AgentRun.started_at, AgentRun.id)
            ).all()
        )

    def latest_artifact(
        self,
        db: Session,
        project_id: str,
        artifact_type: str,
        *,
        approved_only: bool = False,
    ) -> WritingArtifact | None:
        query = select(WritingArtifact).where(
            WritingArtifact.project_id == project_id,
            WritingArtifact.artifact_type == artifact_type,
        )
        if approved_only:
            query = query.where(WritingArtifact.approved.is_(True))
        return db.scalar(query.order_by(desc(WritingArtifact.version)).limit(1))

    def approve_artifact(
        self,
        db: Session,
        *,
        project: WritingProject,
        artifact: WritingArtifact,
        approved: bool,
        note: str,
    ) -> WritingProject:
        if artifact.project_id != project.id:
            raise ValueError("阶段产物不属于当前写作项目")
        artifact.approved = approved
        if note.strip():
            review = self._store_artifact(
                db,
                project=project,
                artifact_type="author_decision",
                content={
                    "artifact_id": artifact.id,
                    "artifact_type": artifact.artifact_type,
                    "approved": approved,
                    "note": note.strip(),
                },
                role="author",
                approved=True,
            )
            review.approved = True

        if not approved:
            project.state = WritingState.failed.value
            project.error = f"作者退回阶段产物：{artifact.artifact_type}"
            return project

        if artifact.artifact_type == "editorial_brief":
            project.state = WritingState.researching.value
            project.current_stage = "evidence_pack"
        elif artifact.artifact_type == "outline":
            project.state = WritingState.drafting.value
            project.current_stage = "draft"
        elif artifact.artifact_type == "revision_plan":
            project.state = WritingState.revising.value
            project.current_stage = "final_revision"
        else:
            raise ValueError("这个阶段产物不需要审批")
        project.error = ""
        return project

    def selected_sources(self, db: Session, project: WritingProject) -> list[SourceItem]:
        selection = self.latest_artifact(
            db,
            project.id,
            "source_selection",
            approved_only=True,
        )
        payload = self._json(selection.content_json, {}) if selection else {}
        source_ids = payload.get("source_ids") if isinstance(payload, dict) else None
        if not isinstance(source_ids, list) or not source_ids:
            source_ids = [project.source_id]
        ordered_ids = list(dict.fromkeys(str(value) for value in source_ids if value))
        values = {
            item.id: item
            for item in db.scalars(select(SourceItem).where(SourceItem.id.in_(ordered_ids))).all()
        }
        sources = [values[source_id] for source_id in ordered_ids if source_id in values]
        if not sources or sources[0].id != project.source_id:
            primary = db.get(SourceItem, project.source_id)
            if primary is None:
                raise ValueError("来源不存在")
            sources = [primary, *(item for item in sources if item.id != primary.id)]
        return sources

    def source_summaries(self, db: Session, project: WritingProject) -> list[dict[str, Any]]:
        return [
            {
                "id": source.id,
                "role": "primary" if index == 0 else "supporting",
                "author": source.author_name or source.author_handle,
                "title": self._source_title(source),
                "url": source.canonical_url,
            }
            for index, source in enumerate(self.selected_sources(db, project))
        ]

    def material_summaries(self, db: Session, project: WritingProject) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        source_map = {item.id: item for item in self.selected_sources(db, project)}
        for index, material in enumerate(self._selected_materials(db, project)):
            kind = str(material.get("kind") or "source")
            source_id = str(material.get("source_id") or material.get("id") or "")
            source = source_map.get(source_id)
            title = str(material.get("title") or (self._source_title(source) if source else "输入材料"))
            output.append(
                {
                    "ref": str(material.get("ref") or ""),
                    "id": str(material.get("id") or ""),
                    "source_id": source_id,
                    "kind": kind,
                    "role": "primary_input" if index == 0 else "supporting_input",
                    "title": title,
                    "author": (source.author_name or source.author_handle) if source else "",
                    "platform": str(material.get("platform") or (source.platform if source else "")),
                    "version": material.get("version"),
                    "status": str(material.get("status") or ""),
                }
            )
        return output

    def _selected_materials(self, db: Session, project: WritingProject) -> list[dict[str, Any]]:
        selection = self.latest_artifact(
            db,
            project.id,
            "source_selection",
            approved_only=True,
        )
        payload = self._json(selection.content_json, {}) if selection else {}
        materials = payload.get("materials") if isinstance(payload, dict) else None
        if isinstance(materials, list) and materials:
            return [item for item in materials if isinstance(item, dict)]
        return [
            {
                "ref": f"source:{source.id}",
                "kind": "source",
                "id": source.id,
                "source_id": source.id,
                "title": self._source_title(source),
            }
            for source in self.selected_sources(db, project)
        ]

    @staticmethod
    def _source_title(source: SourceItem) -> str:
        structured: dict[str, Any] = {}
        try:
            value = json.loads(source.structured_content_json or "{}")
            if isinstance(value, dict):
                structured = value
        except json.JSONDecodeError:
            pass
        title = str(structured.get("title") or "").strip()
        if title:
            return title[:160]
        return re.sub(r"\s+", " ", source.text_original or "").strip()[:80]

    @staticmethod
    def _evidence_section_role(value: str, *, fallback: str = "overview") -> str:
        lowered = str(value or "").lower()
        if any(term in lowered for term in ("限制", "边界", "风险", "未知", "不能", "局限")):
            return "limitations"
        if any(term in lowered for term in ("对比", "比较", "差异", "取舍", "另一")):
            return "comparison"
        if any(term in lowered for term in ("证据", "数据", "数字", "测试", "结果")):
            return "evidence"
        if any(term in lowered for term in ("机制", "方法", "过程", "步骤", "原理", "实现")):
            return "mechanism"
        if any(term in lowered for term in ("案例", "例子", "场景")):
            return "example"
        if any(term in lowered for term in ("结论", "判断", "下一步", "意味着")):
            return "conclusion"
        return fallback

    def _evidence_sections(
        self,
        project: WritingProject,
        *,
        purpose: str,
        outline: dict[str, Any] | None = None,
    ) -> list[EvidenceSectionRequest]:
        thesis = " ".join(
            value.strip()
            for value in (project.main_thesis, project.promise, project.reader)
            if str(value or "").strip()
        ) or "来源中的核心事实、方法、证据和限制"
        outline_sections = outline.get("sections") if isinstance(outline, dict) else None
        if isinstance(outline_sections, list) and outline_sections:
            requests: list[EvidenceSectionRequest] = []
            for index, raw in enumerate(outline_sections[:12], start=1):
                if not isinstance(raw, dict):
                    continue
                heading = str(raw.get("heading") or raw.get("title") or f"第 {index} 节")
                details = " ".join(
                    str(raw.get(key) or "")
                    for key in ("purpose", "reader_question", "key_point")
                ).strip()
                requests.append(
                    EvidenceSectionRequest(
                        section_id=f"outline-{index:02d}",
                        heading=heading,
                        query=f"{thesis} {heading} {details}".strip(),
                        role=self._evidence_section_role(f"{heading} {details}"),
                        max_chunks=5,
                        max_chars=4200,
                    )
                )
            if requests:
                return requests

        if purpose == "evidence_pack":
            specs = (
                ("facts", "已确认事实", "事实 来源 发生了什么", "overview"),
                ("mechanism", "方法与机制", "方法 机制 过程 如何实现", "mechanism"),
                ("numbers", "数字与测试", "数字 数据 测试 样本 局部结果", "evidence"),
                ("examples", "案例与可用细节", "案例 例子 具体 场景", "example"),
                ("limits", "限制与未知", "限制 条件 反例 风险 未知 不能扩大", "limitations"),
            )
        elif purpose in {"draft", "final_revision"}:
            specs = (
                ("opening", "开头与阅读价值", "做成了什么 为什么重要", "opening"),
                ("mechanism", "核心机制", "方法 过程 原理 实现", "mechanism"),
                ("evidence", "关键证据", "数据 测试 结果 来源归属", "evidence"),
                ("limits", "限制与取舍", "限制 边界 反例 条件 风险", "limitations"),
                ("ending", "结论与下一步", "意味着什么 判断 下一步", "conclusion"),
            )
        else:
            specs = (
                ("overview", "主线与事实", "核心事实 主线 发生了什么", "overview"),
                ("evidence", "证据与细节", "数字 测试 例子 来源", "evidence"),
                ("limits", "边界与缺口", "限制 未知 风险 不能写什么", "limitations"),
            )
        return [
            EvidenceSectionRequest(
                section_id=section_id,
                heading=heading,
                query=f"{thesis} {query}",
                role=role,
                max_chunks=5,
                max_chars=4200,
            )
            for section_id, heading, query, role in specs
        ]

    def _compile_evidence(
        self,
        db: Session,
        project: WritingProject,
        *,
        purpose: str,
        outline: dict[str, Any] | None = None,
    ) -> EvidenceBundle:
        roots = self.selected_sources(db, project)
        context: list[SourceItem] = []
        seen: set[str] = set()
        for root in roots:
            for item in self.editorial._context(db, root):
                if item.id in seen:
                    continue
                seen.add(item.id)
                context.append(item)
        return EvidenceCompiler(self.settings).compile_sources(
            context,
            self._evidence_sections(project, purpose=purpose, outline=outline),
            primary_source_id=roots[0].id,
            selected_source_ids=[item.id for item in roots],
            materials=self._selected_materials(db, project),
        )

    def _source_payload(
        self,
        db: Session,
        project: WritingProject,
        *,
        purpose: str = "overview",
        outline: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        return self._compile_evidence(
            db,
            project,
            purpose=purpose,
            outline=outline,
        ).prompt_payload()

    @staticmethod
    def _attach_evidence_trace(
        artifact: WritingArtifact,
        bundle: EvidenceBundle,
    ) -> WritingArtifact:
        try:
            payload = json.loads(artifact.content_json or "{}")
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload["evidence_retrieval"] = bundle.prompt_payload()
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        artifact.content_json = serialized
        artifact.content_hash = hashlib.sha256(serialized.encode()).hexdigest()
        return artifact

    def _style_payload(self, db: Session, project: WritingProject) -> dict[str, Any]:
        if not project.style_profile_id:
            return {
                "identity": "专业但不端着的中文内容创作者",
                "reader_relationship": "把复杂问题讲给聪明但不熟悉细节的读者",
                "rhythm": "短段落；先建立画面，再解释术语；判断落在具体证据上",
                "forbidden": [
                    "阅读时注意以下边界",
                    "本文基于已归档来源整理",
                    "值得关注的3个点",
                    "不难发现",
                    "总的来说",
                ],
            }
        profile = db.get(StyleProfile, project.style_profile_id)
        if profile is None:
            return {}
        return {
            "name": profile.name,
            "description": profile.description,
            "rules": self._json(profile.rules_json, {}),
            "forbidden": self._json(profile.forbidden_json, []),
            "samples": self._json(profile.samples_json, [])[:8],
            "version": profile.version,
        }

    def _artifact_payloads(self, db: Session, project: WritingProject) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for artifact in self.artifacts(db, project.id):
            result[artifact.artifact_type] = self._json(artifact.content_json, {})
        return result

    def _memory_snapshot(self, db: Session, project: WritingProject):
        return PoolMemoryService(self.settings, self.editorial).snapshot_for_target(
            db,
            target_type="writing_project",
            target_id=project.id,
        )

    def _memory_payload(
        self,
        db: Session,
        project: WritingProject,
        *,
        role: str,
        allow_pending: bool = True,
    ) -> dict[str, Any]:
        service = PoolMemoryService(self.settings, self.editorial)
        return service.prompt_payload(
            self._memory_snapshot(db, project),
            role=role,
            allow_pending=allow_pending,
        )

    def _mark_memory_applied(
        self,
        db: Session,
        project: WritingProject,
        *,
        role: str,
        stage: str,
    ) -> None:
        snapshot = self._memory_snapshot(db, project)
        if snapshot is None:
            return
        PoolMemoryService(self.settings, self.editorial).mark_snapshot_applied(
            db,
            snapshot,
            roles=[(role, stage)],
        )

    def _store_artifact(
        self,
        db: Session,
        *,
        project: WritingProject,
        artifact_type: str,
        content: dict[str, Any],
        role: str,
        approved: bool,
    ) -> WritingArtifact:
        current = db.scalar(
            select(func.max(WritingArtifact.version)).where(
                WritingArtifact.project_id == project.id,
                WritingArtifact.artifact_type == artifact_type,
            )
        )
        serialized = json.dumps(content, ensure_ascii=False, sort_keys=True)
        artifact = WritingArtifact(
            project_id=project.id,
            artifact_type=artifact_type,
            version=int(current or 0) + 1,
            content_json=serialized,
            content_hash=hashlib.sha256(serialized.encode()).hexdigest(),
            created_by_role=role,
            approved=approved,
        )
        db.add(artifact)
        db.flush()
        return artifact

    def _artifact_content(
        self,
        db: Session,
        project: WritingProject,
        artifact_type: str,
    ) -> dict[str, Any]:
        artifact = self.latest_artifact(db, project.id, artifact_type)
        if artifact is None:
            raise ValueError(f"缺少阶段产物：{artifact_type}")
        return self._json(artifact.content_json, {})

    def _create_draft_revision(
        self,
        db: Session,
        project: WritingProject,
        artifact: WritingArtifact,
    ) -> DraftRevision:
        source = db.get(SourceItem, project.source_id)
        if source is None:
            raise ValueError("来源不存在")
        content = self._json(artifact.content_json, {})
        context = self.editorial._context(db, source)
        # The default editorial service is specialized for the 4,000-character
        # short-draft editor. Deep writing feeds the 50,000-character WeChat
        # workbench, so reuse only the base normalization and keep the full body.
        sanitized = EditorialService._sanitize_generated(
            self.editorial,
            {
                "title": content.get("title"),
                "body": content.get("body"),
                "tags": content.get("tags"),
                "claims": content.get("claims") or [],
            },
            context,
            "explain",
        )
        draft = DraftRevision(
            source_id=source.id,
            version=self.editorial._next_version(db, source.id),
            style="studio",
            title=sanitized["title"][:80],
            # Deep writing is now a WeChat longform sub-flow. Preserve the full
            # reviewed article so the platform handoff cannot silently collapse
            # a 4,000+ character draft before the final WeChat stage.
            body=sanitized["body"][:50000],
            tags=sanitized["tags"][:500],
            claims_json=json.dumps(sanitized["claims"], ensure_ascii=False),
            provenance_json=json.dumps(
                {
                    "generator": "multi-agent-writing-studio",
                    "writing_project_id": project.id,
                    "final_artifact_id": artifact.id,
                    "roles": list(ROLE_SKILLS),
                    "style_profile_id": project.style_profile_id,
                    "input_material_refs": [
                        str(item.get("ref") or "") for item in self._selected_materials(db, project)
                    ],
                    "evidence_retrieval": content.get("evidence_retrieval") or {},
                    **self._memory_provenance(db, project),
                },
                ensure_ascii=False,
            ),
            created_by="multi-agent",
        )
        db.add(draft)
        db.flush()
        return draft

    def _memory_provenance(self, db: Session, project: WritingProject) -> dict[str, Any]:
        summary = PoolMemoryService(self.settings, self.editorial).snapshot_summary(
            self._memory_snapshot(db, project)
        )
        return {
            "memory_snapshot_id": summary["snapshot_id"],
            "memory_snapshot_hash": summary["snapshot_hash"],
            "memory_ids": summary["memory_ids"],
            "memory_applied": summary["applied"],
            "memory_status": summary["status"],
        }

    def add_feedback(
        self,
        db: Session,
        *,
        project: WritingProject,
        draft_before_id: str | None,
        draft_after_id: str | None,
        diff: dict[str, Any],
        feedback_reason: str,
        affected_rules: list[str],
    ) -> WritingFeedback:
        feedback = WritingFeedback(
            project_id=project.id,
            draft_before_id=draft_before_id,
            draft_after_id=draft_after_id,
            diff_json=json.dumps(diff, ensure_ascii=False),
            feedback_reason=feedback_reason.strip(),
            affected_rules_json=json.dumps(affected_rules, ensure_ascii=False),
        )
        db.add(feedback)
        db.flush()
        return feedback

    @staticmethod
    def _fallback_agent(role: str, project: WritingProject) -> dict[str, Any]:
        if role == "editor_in_chief":
            return {
                "reader": project.reader or "对主题感兴趣但不熟悉细节的读者",
                "article_promise": project.promise or "把来源中的核心进展讲清楚",
                "main_thesis": project.main_thesis or "来源提供了值得进一步拆解的一手线索",
                "reader_hook": "先解释发生了什么",
                "must_use": [],
                "must_not_claim": ["来源未支持的数字、因果和行业结论"],
                "article_type": "explain",
                "tone": "专业、直接、无报告腔",
                "open_questions": ["未配置模型，需要作者补充主线"],
                "success_criteria": ["读者看懂核心进展"],
            }
        if role == "evidence_researcher":
            return {
                "facts": [],
                "author_claims": [],
                "unknowns": ["未配置模型，无法自动构建证据包"],
                "numbers": [],
                "terms": [],
                "source_map": [],
                "material_gaps": [],
                "usable_examples": [],
                "claims_for_draft": [],
            }
        if role == "outline_architect":
            return {
                "opening": {"purpose": "讲清发生了什么"},
                "sections": [],
                "ending": {"purpose": "给出判断"},
                "cognitive_load_plan": [],
                "terms_first_use": [],
                "evidence_allocation": [],
                "transitions": [],
                "forbidden_moves": ["逐段翻译", "审计式边界清单"],
            }
        if role in {"writer", "final_reviser"}:
            return {
                "title": "需要配置模型后生成终稿",
                "body": "当前写作项目已经建立，但多 Agent 成稿需要配置兼容模型。",
                "tags": ["内容创作", "X平台观察", "AI写作", "本地工具"],
                "claims": [],
                "applied_changes": [],
            }
        if role.endswith("reviewer"):
            return {"verdict": "needs_human_review", "minimal_fixes": ["未配置模型"]}
        return {
            "must_fix": ["未配置模型，不能自动完成主编审稿"],
            "should_fix": [],
            "reject_suggestions": [],
            "author_decisions": [],
            "revision_instructions": [],
            "release_readiness": "blocked",
        }
