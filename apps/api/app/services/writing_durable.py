from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import ValidationError
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.domain.models import utcnow
from app.domain.studio import AgentRun, AgentRunStatus, WritingArtifact, WritingProject
from app.domain.writing_agent_schemas import (
    StructuredOutputTrace,
    WritingAgentContractError,
    schema_for_artifact,
    validate_agent_payload,
)
from app.services.model_client import StructuredOutputError
from app.services.retrieval import bounded_json
from app.services.skills import binding_for
from app.services.writing_core import ROLE_SKILLS

_AUTHOR_CONTEXT_ROLES = {
    "editor_in_chief",
    "evidence_researcher",
    "outline_architect",
    "title_strategist",
    "writer",
    "chief_editor",
    "final_reviser",
}

_SCHEMA_REPAIR_ERRORS = (
    StructuredOutputError,
    ValidationError,
    WritingAgentContractError,
    TypeError,
)


class DurableAgentRunnerMixin:
    @staticmethod
    def _validation_message(exc: Exception) -> str:
        if isinstance(exc, ValidationError):
            parts = []
            for item in exc.errors(include_url=False)[:10]:
                location = ".".join(str(value) for value in item.get("loc") or [])
                parts.append(f"{location or '<root>'}: {item.get('msg') or 'invalid'}")
            return "; ".join(parts)[:4000]
        return str(exc)[:4000]

    @staticmethod
    def _payload_hash(payload: dict[str, Any]) -> str:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(serialized.encode()).hexdigest()

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
        max_tokens: int | None = None,
        capture_response_meta: bool = False,
        request_timeout_seconds: float | None = None,
        schema_context: dict[str, Any] | None = None,
    ) -> WritingArtifact:
        skill_name = ROLE_SKILLS[role]
        binding = binding_for(db, skill_name, self.settings.model_name)
        if not binding.enabled:
            raise ValueError(f"Skill {skill_name} 已关闭")

        mode = self.settings.writing_schema_mode
        schema = schema_for_artifact(artifact_type) if mode == "production" else None
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

        if (
            self.settings.writing_quality_mode == "production"
            and role in {"title_strategist", "writer", "final_reviser"}
        ):
            exemplars = self._style_exemplar_payload(db, project)
            exemplar_prompt = str(exemplars.get("prompt_text") or "").strip()
            if exemplar_prompt:
                user_prompt = f"{user_prompt}\n\n{exemplar_prompt}"
            style = self._style_payload(db, project)
            author_overrides = style.get("author_overrides")
            if isinstance(author_overrides, list) and author_overrides:
                user_prompt = (
                    f"{user_prompt}\n\n作者明确覆盖规则（优先级高于模型推断与范例）：\n"
                    f"{bounded_json(author_overrides, 8000)}"
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

        if schema is not None:
            contract = bounded_json(schema.model_json_schema(), 24000)
            user_prompt = (
                f"{user_prompt}\n\n结构化输出契约（必须严格遵守；禁止额外字段）：\n"
                f"{contract}\n只返回一个符合该 Schema 的 JSON 对象。"
            )

        model_configured = bool(self.settings.model_base_url and self.settings.model_name)
        input_hash = hashlib.sha256(
            (
                f"{role}\n{system_prompt}\n{user_prompt}\n"
                f"{binding.model_name}\n{binding.prompt_version}\n"
                f"mode={mode}\nmodel_configured={model_configured}\n"
                f"schema_context={bounded_json(schema_context or {}, 8000)}\n"
                f"max_tokens={max_tokens}\nrequest_timeout_seconds={request_timeout_seconds}"
            ).encode()
        ).hexdigest()
        cached_run = db.scalar(
            select(AgentRun)
            .where(
                AgentRun.project_id == project.id,
                AgentRun.role == role,
                AgentRun.input_hash == input_hash,
                AgentRun.status.in_(
                    [
                        AgentRunStatus.succeeded.value,
                        AgentRunStatus.cached.value,
                        AgentRunStatus.degraded.value,
                    ]
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

        validation_errors: list[str] = []
        repair_attempted = False
        response_meta: dict[str, Any] | None = None
        initial_structured_error: StructuredOutputError | None = None
        structured_status = "degraded"
        warning = ""
        try:
            if model_configured:
                try:
                    raw_result = await self.editorial._chat_json(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        temperature=temperature,
                        reasoning_effort=binding.reasoning_effort,
                        model_name=binding.model_name,
                        max_tokens=max_tokens,
                        capture_response_meta=capture_response_meta,
                        request_timeout_seconds=request_timeout_seconds,
                    )
                except StructuredOutputError as exc:
                    if schema is None:
                        raise
                    initial_structured_error = exc
                    result = {}
                else:
                    result = dict(raw_result)
                    raw_meta = result.pop("_x2red_response_meta", None)
                    response_meta = raw_meta if isinstance(raw_meta, dict) else None
            else:
                result = self._fallback_agent(role, project)
                required_title = str((schema_context or {}).get("required_title") or "")
                if required_title and role in {"writer", "final_reviser"}:
                    result["title"] = required_title

            if schema is not None:
                try:
                    if initial_structured_error is not None:
                        raise initial_structured_error
                    validated = validate_agent_payload(
                        artifact_type,
                        result,
                        context=schema_context,
                    )
                    result = validated.model_dump(mode="json")
                    structured_status = "valid" if model_configured else "degraded"
                    if not model_configured:
                        warning = "未配置文本模型；当前产物为确定性降级输出，不代表模型已执行"
                except _SCHEMA_REPAIR_ERRORS as initial_exc:
                    if not model_configured:
                        raise
                    repair_attempted = True
                    run.attempts = 2
                    initial_error = self._validation_message(initial_exc)
                    validation_errors.append(initial_error)
                    raw_content = (
                        initial_exc.raw_content
                        if isinstance(initial_exc, StructuredOutputError)
                        else bounded_json(result, 30000)
                    )
                    repair_prompt = (
                        "上一轮输出未通过结构化契约。只修复 JSON 结构和字段映射，"
                        "不得扩展事实、观点、审稿 issue 或修改范围。\n"
                        f"错误：{initial_error}\n"
                        f"原始输出：{raw_content[:30000]}\n"
                        f"目标 Schema：{bounded_json(schema.model_json_schema(), 24000)}\n"
                        "只返回一个符合 Schema 的 JSON 对象。"
                    )
                    repaired_raw = await self.editorial._chat_json(
                        system_prompt="你是结构化输出修复器，只修复格式与字段，不创造内容。",
                        user_prompt=repair_prompt,
                        temperature=0,
                        reasoning_effort=binding.reasoning_effort,
                        model_name=binding.model_name,
                        max_tokens=max_tokens,
                        capture_response_meta=capture_response_meta,
                        request_timeout_seconds=request_timeout_seconds,
                    )
                    repaired = dict(repaired_raw)
                    repaired_meta = repaired.pop("_x2red_response_meta", None)
                    if isinstance(repaired_meta, dict):
                        response_meta = repaired_meta
                    validated = validate_agent_payload(
                        artifact_type,
                        repaired,
                        context=schema_context,
                    )
                    result = validated.model_dump(mode="json")
                    structured_status = "repaired"
            else:
                warning = (
                    "legacy 模式未执行 W2 Schema 校验；产物可读但必须按降级结果处理"
                    if model_configured
                    else "legacy 模式且未配置文本模型；当前产物为确定性降级输出"
                )

            payload_sha256 = self._payload_hash(result)
            if capture_response_meta and response_meta is not None:
                result["_completion"] = {
                    "finish_reason": str(response_meta.get("finish_reason") or ""),
                    "completion_tokens": response_meta.get("completion_tokens"),
                }
            trace = StructuredOutputTrace(
                mode=mode,
                status=structured_status,
                schema_name=schema.__name__ if schema is not None else "legacy-unvalidated",
                repair_attempted=repair_attempted,
                validation_errors=validation_errors,
                payload_sha256=payload_sha256,
                warning=warning,
            )
            result["_structured_output"] = trace.model_dump(mode="json")

            artifact = self._store_artifact(
                db,
                project=project,
                artifact_type=artifact_type,
                content=result,
                role=role,
                approved=False,
            )
            run.status = (
                AgentRunStatus.degraded.value
                if structured_status == "degraded"
                else AgentRunStatus.succeeded.value
            )
            run.output_artifact_id = artifact.id
            run.finished_at = utcnow()
            estimated_cost = run.attempts if model_configured else 0
            run.usage_json = json.dumps(
                {
                    "estimated_cost_cents": estimated_cost,
                    "structured_output": trace.model_dump(mode="json"),
                },
                ensure_ascii=False,
            )
            project.spent_estimate_cents += estimated_cost
            if model_configured and schema is not None and memory.get("memory_ids"):
                self._mark_memory_applied(
                    db,
                    project,
                    role=role,
                    stage=stage,
                )
            project.error = ""
            db.flush()
            return artifact
        except Exception as exc:
            # Keep the stage unchanged. Durable retries may resume from this exact
            # checkpoint, while failed schema attempts remain replayable in AgentRun.
            if repair_attempted and isinstance(exc, _SCHEMA_REPAIR_ERRORS):
                final_error = self._validation_message(exc)
                validation_errors.append(final_error)
            run.status = AgentRunStatus.failed.value
            run.error = str(exc)[:2000]
            run.finished_at = utcnow()
            run.usage_json = json.dumps(
                {
                    "estimated_cost_cents": run.attempts if model_configured else 0,
                    "structured_output": {
                        "mode": mode,
                        "status": "failed",
                        "repair_attempted": repair_attempted,
                        "validation_errors": validation_errors,
                    },
                },
                ensure_ascii=False,
            )
            if model_configured:
                project.spent_estimate_cents += run.attempts
            project.error = run.error
            db.commit()
            raise
