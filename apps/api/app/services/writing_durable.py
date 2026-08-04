from __future__ import annotations

import hashlib
import json

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.domain.models import utcnow
from app.domain.studio import AgentRun, AgentRunStatus, WritingArtifact, WritingProject
from app.services.skills import binding_for
from app.services.writing_core import ROLE_SKILLS

_AUTHOR_CONTEXT_ROLES = {
    "editor_in_chief",
    "evidence_researcher",
    "outline_architect",
    "writer",
    "chief_editor",
    "final_reviser",
}


class DurableAgentRunnerMixin:
    async def _run_agent(
        self,
        db: Session,
        *,
        project: WritingProject,
        role: str,
        stage: str,
        artifact_type: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> WritingArtifact:
        skill_name = ROLE_SKILLS[role]
        binding = binding_for(db, skill_name, self.settings.model_name)
        if not binding.enabled:
            raise ValueError(f"Skill {skill_name} 已关闭")

        memory = self._memory_payload(
            db,
            project,
            role=role,
            allow_pending=True,
        )
        user_prompt = (
            f"{user_prompt}\n\n当前任务冻结的池子记忆：\n{memory['text']}\n"
            "长期风格宪法与任务记忆必须分开理解；任务记忆只决定怎么写，不能补充事实。"
        )

        if role in _AUTHOR_CONTEXT_ROLES:
            decision = self.latest_artifact(db, project.id, "author_decision")
            if decision is not None:
                decision_payload = self._json(decision.content_json, {})
                user_prompt = (
                    f"{user_prompt}\n\n作者最近一次阶段决定："
                    f"{json.dumps(decision_payload, ensure_ascii=False)[:5000]}\n"
                    "必须优先执行作者明确写出的调整要求；不要把已否决版本原样返回。"
                )

        input_hash = hashlib.sha256(
            (
                f"{role}\n{system_prompt}\n{user_prompt}\n"
                f"{binding.model_name}\n{binding.prompt_version}"
            ).encode()
        ).hexdigest()
        cached_run = db.scalar(
            select(AgentRun)
            .where(
                AgentRun.project_id == project.id,
                AgentRun.role == role,
                AgentRun.input_hash == input_hash,
                AgentRun.status.in_(
                    [AgentRunStatus.succeeded.value, AgentRunStatus.cached.value]
                ),
                AgentRun.output_artifact_id.is_not(None),
            )
            .order_by(desc(AgentRun.finished_at))
            .limit(1)
        )
        if cached_run and cached_run.output_artifact_id:
            cached = db.get(WritingArtifact, cached_run.output_artifact_id)
            if cached is not None:
                return cached

        if project.spent_estimate_cents >= project.budget_limit_cents:
            raise ValueError("写作项目已达到模型预算上限")

        run = AgentRun(
            project_id=project.id,
            role=role,
            stage=stage,
            status=AgentRunStatus.running.value,
            model_name=binding.model_name or self.settings.model_name,
            reasoning_effort=binding.reasoning_effort,
            input_hash=input_hash,
            attempts=1,
            started_at=utcnow(),
        )
        db.add(run)
        db.flush()
        try:
            if self.settings.model_base_url and self.settings.model_name:
                result = await self.editorial._chat_json(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=temperature,
                    reasoning_effort=binding.reasoning_effort,
                    model_name=binding.model_name,
                )
                self._mark_memory_applied(
                    db,
                    project,
                    role=role,
                    stage=stage,
                )
            else:
                result = self._fallback_agent(role, project)
            artifact = self._store_artifact(
                db,
                project=project,
                artifact_type=artifact_type,
                content=result,
                role=role,
                approved=False,
            )
            run.status = AgentRunStatus.succeeded.value
            run.output_artifact_id = artifact.id
            run.finished_at = utcnow()
            run.usage_json = json.dumps({"estimated_cost_cents": 1}, ensure_ascii=False)
            project.spent_estimate_cents += 1
            project.error = ""
            db.flush()
            return artifact
        except Exception as exc:
            # Preserve the failed attempt while leaving the project at the same
            # stage. The durable job can retry, and all prior role handoffs remain.
            run.status = AgentRunStatus.failed.value
            run.error = str(exc)[:2000]
            run.finished_at = utcnow()
            project.error = run.error
            db.commit()
            raise
