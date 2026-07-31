from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.studio import WritingArtifact, WritingProject, WritingState


class AuthorGateMixin:
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
        supported = {"editorial_brief", "outline", "revision_plan"}
        if artifact.artifact_type not in supported:
            raise ValueError("这个阶段产物不需要审批")

        artifact.approved = approved
        self._store_artifact(
            db,
            project=project,
            artifact_type="author_decision",
            content={
                "artifact_id": artifact.id,
                "artifact_type": artifact.artifact_type,
                "artifact_version": artifact.version,
                "approved": approved,
                "note": note.strip() or ("作者确认" if approved else "作者要求调整"),
            },
            role="author",
            approved=True,
        )

        if artifact.artifact_type == "editorial_brief":
            project.state = WritingState.researching.value if approved else WritingState.clarifying.value
            project.current_stage = "evidence_pack" if approved else "editorial_brief"
        elif artifact.artifact_type == "outline":
            project.state = WritingState.drafting.value if approved else WritingState.outlining.value
            project.current_stage = "draft" if approved else "outline"
        else:
            project.state = WritingState.revising.value if approved else WritingState.reviewing.value
            project.current_stage = "final_revision" if approved else "parallel_reviews"

        project.error = "" if approved else (note.strip() or f"作者要求调整：{artifact.artifact_type}")
        return project
