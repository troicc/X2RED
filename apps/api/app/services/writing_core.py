from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
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

    def _source_payload(self, db: Session, project: WritingProject) -> list[dict[str, Any]]:
        source = db.get(SourceItem, project.source_id)
        if source is None:
            raise ValueError("来源不存在")
        context = self.editorial._context(db, source)
        return self.editorial._source_blocks(context)

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
        sanitized = self.editorial._sanitize_generated(
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
            body=sanitized["body"][:4000],
            tags=sanitized["tags"][:500],
            claims_json=json.dumps(sanitized["claims"], ensure_ascii=False),
            provenance_json=json.dumps(
                {
                    "generator": "multi-agent-writing-studio",
                    "writing_project_id": project.id,
                    "final_artifact_id": artifact.id,
                    "roles": list(ROLE_SKILLS),
                    "style_profile_id": project.style_profile_id,
                },
                ensure_ascii=False,
            ),
            created_by="multi-agent",
        )
        db.add(draft)
        db.flush()
        return draft

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
