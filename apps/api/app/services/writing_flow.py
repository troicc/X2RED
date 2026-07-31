from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.studio import WritingArtifact, WritingMode, WritingProject, WritingState


class WritingFlowMixin:
    async def run_next(self, db: Session, project: WritingProject) -> WritingArtifact:
        if project.state == WritingState.clarifying.value:
            artifact = await self._run_editor_brief(db, project)
            project.state = WritingState.awaiting_brief_approval.value
            project.current_stage = "approve_brief"
            if project.mode == WritingMode.fast.value:
                artifact.approved = True
                project.state = WritingState.researching.value
                project.current_stage = "evidence_pack"
            return artifact

        if project.state == WritingState.researching.value:
            artifact = await self._run_research(db, project)
            project.state = WritingState.outlining.value
            project.current_stage = "outline"
            return artifact

        if project.state == WritingState.outlining.value:
            artifact = await self._run_outline(db, project)
            project.state = WritingState.awaiting_outline_approval.value
            project.current_stage = "approve_outline"
            if project.mode == WritingMode.fast.value:
                artifact.approved = True
                project.state = WritingState.drafting.value
                project.current_stage = "draft"
            return artifact

        if project.state == WritingState.drafting.value:
            artifact = await self._run_writer(db, project)
            project.state = WritingState.reviewing.value
            project.current_stage = "parallel_reviews"
            return artifact

        if project.state == WritingState.reviewing.value:
            artifact = await self._run_reviews(db, project)
            project.state = WritingState.awaiting_revision_approval.value
            project.current_stage = "approve_revision_plan"
            if project.mode == WritingMode.fast.value:
                artifact.approved = True
                project.state = WritingState.revising.value
                project.current_stage = "final_revision"
            return artifact

        if project.state == WritingState.revising.value:
            artifact = await self._run_final_revision(db, project)
            project.state = WritingState.completed.value
            project.current_stage = "completed"
            return artifact

        if project.state in {
            WritingState.awaiting_brief_approval.value,
            WritingState.awaiting_outline_approval.value,
            WritingState.awaiting_revision_approval.value,
        }:
            raise ValueError("当前阶段需要作者确认后才能继续")
        if project.state == WritingState.completed.value:
            raise ValueError("写作项目已经完成")
        raise ValueError(f"当前状态不能继续执行：{project.state}")

    async def run_until_gate(
        self,
        db: Session,
        project: WritingProject,
        *,
        max_steps: int = 12,
    ) -> list[WritingArtifact]:
        output: list[WritingArtifact] = []
        for _ in range(max_steps):
            if project.state in {
                WritingState.awaiting_brief_approval.value,
                WritingState.awaiting_outline_approval.value,
                WritingState.awaiting_revision_approval.value,
                WritingState.completed.value,
                WritingState.failed.value,
                WritingState.canceled.value,
            }:
                break
            artifact = await self.run_next(db, project)
            output.append(artifact)
            # Each role handoff is a durable checkpoint. A later model outage must
            # not erase an approved brief, evidence pack, outline, or completed review.
            db.commit()
            db.refresh(project)
            db.refresh(artifact)
        return output
