from __future__ import annotations

import hashlib
import json

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.domain.models import utcnow
from app.domain.studio import AgentRun, AgentRunStatus, WritingArtifact, WritingProject, WritingState
from app.services.skills import binding_for
from app.services.writing_core import ROLE_SKILLS


class WritingAgentsMixin:
    async def _run_editor_brief(self, db: Session, project: WritingProject) -> WritingArtifact:
        source = self._source_payload(db, project)
        prompt = f"""
你是写作总编辑。围绕来源建立一份可审批的写作任务单，不写正文。
作者预设读者：{project.reader or '未指定'}
作者预设承诺：{project.promise or '未指定'}
作者预设主张：{project.main_thesis or '未指定'}
来源：{json.dumps(source, ensure_ascii=False)[:30000]}

输出 JSON：reader、article_promise、main_thesis、reader_hook、must_use、must_not_claim、
article_type、tone、open_questions、success_criteria。
要求：只选一条主线；明确不能写成什么；技术内容必须先回答“做成了什么、为什么重要”。
""".strip()
        artifact = await self._run_agent(
            db,
            project=project,
            role="editor_in_chief",
            stage="editorial_brief",
            artifact_type="editorial_brief",
            system_prompt="你是总编辑，只做选题澄清和任务分配，不抢写手的工作。",
            user_prompt=prompt,
            temperature=0.2,
        )
        data = self._json(artifact.content_json, {})
        project.reader = str(data.get("reader") or project.reader)
        project.promise = str(data.get("article_promise") or project.promise)
        project.main_thesis = str(data.get("main_thesis") or project.main_thesis)
        return artifact

    async def _run_research(self, db: Session, project: WritingProject) -> WritingArtifact:
        source = self._source_payload(db, project)
        brief = self._artifact_content(db, project, "editorial_brief")
        prompt = f"""
你是证据研究员。根据任务单整理证据包，不写正文，不补充来源之外的事实。
任务单：{json.dumps(brief, ensure_ascii=False)[:10000]}
来源：{json.dumps(source, ensure_ascii=False)[:30000]}

输出 JSON：facts、author_claims、unknowns、numbers、terms、source_map、material_gaps、
usable_examples、claims_for_draft。
每条 facts/numbers/claims_for_draft 必须包含 source_index 和 evidence_quote；
把局部测试、作者判断和客观事实明确区分。术语给出不超过40字的人话解释。
""".strip()
        return await self._run_agent(
            db,
            project=project,
            role="evidence_researcher",
            stage="evidence_pack",
            artifact_type="evidence_pack",
            system_prompt="你是严谨的材料研究员。只整理证据和材料缺口，不写文章。",
            user_prompt=prompt,
            temperature=0.1,
        )

    async def _run_outline(self, db: Session, project: WritingProject) -> WritingArtifact:
        brief = self._artifact_content(db, project, "editorial_brief")
        evidence = self._artifact_content(db, project, "evidence_pack")
        style = self._style_payload(db, project)
        prompt = f"""
你是技术解释与文章结构设计师。制作一份作者可审批的大纲，不写完整正文。
任务单：{json.dumps(brief, ensure_ascii=False)[:10000]}
证据包：{json.dumps(evidence, ensure_ascii=False)[:18000]}
风格规则：{json.dumps(style, ensure_ascii=False)[:8000]}

输出 JSON：opening、sections、ending、cognitive_load_plan、terms_first_use、evidence_allocation、
transitions、forbidden_moves。
每一节包含 purpose、reader_question、key_point、evidence_ids、terms_allowed、target_length。
顺序必须是：先让读者知道发生了什么和为什么值得看，再引入复杂术语；一节只承担一个认知任务。
""".strip()
        return await self._run_agent(
            db,
            project=project,
            role="outline_architect",
            stage="outline",
            artifact_type="outline",
            system_prompt="你擅长控制读者认知负荷，让复杂内容按最自然的顺序被理解。",
            user_prompt=prompt,
            temperature=0.25,
        )

    async def _run_writer(self, db: Session, project: WritingProject) -> WritingArtifact:
        brief = self._artifact_content(db, project, "editorial_brief")
        evidence = self._artifact_content(db, project, "evidence_pack")
        outline = self._artifact_content(db, project, "outline")
        style = self._style_payload(db, project)
        prompt = f"""
你是中文写手。严格根据已确认任务单、证据包、大纲和风格规则写初稿。
任务单：{json.dumps(brief, ensure_ascii=False)[:9000]}
证据包：{json.dumps(evidence, ensure_ascii=False)[:18000]}
大纲：{json.dumps(outline, ensure_ascii=False)[:16000]}
风格：{json.dumps(style, ensure_ascii=False)[:9000]}

输出 JSON：title、body、tags、claims。
要求：
- 开头两三句让目标读者知道做成了什么、为什么值得看；
- 不按原文逐段翻译，不堆术语，术语首次出现时解释；
- 数字必须说明意义；作者自测必须有自然来源归属；
- 不出现内部核查清单、阅读边界、报告腔和模板标题；
- 不编造作者经历、读者对话、数字、情绪或观点；
- 650-1400个中文字符，段落有快慢变化，结尾给出明确判断。
""".strip()
        return await self._run_agent(
            db,
            project=project,
            role="writer",
            stage="draft",
            artifact_type="draft",
            system_prompt="你是中文母语写作者。只写已经被任务单与证据包允许的内容。",
            user_prompt=prompt,
            temperature=0.55,
        )

    async def _run_reviews(self, db: Session, project: WritingProject) -> WritingArtifact:
        draft = self._artifact_content(db, project, "draft")
        brief = self._artifact_content(db, project, "editorial_brief")
        evidence = self._artifact_content(db, project, "evidence_pack")
        outline = self._artifact_content(db, project, "outline")
        style = self._style_payload(db, project)

        reader_prompt = f"""
你是目标读者代表。只输出审稿报告，不直接改正文。
目标与承诺：{json.dumps(brief, ensure_ascii=False)[:7000]}
大纲：{json.dumps(outline, ensure_ascii=False)[:9000]}
初稿：{json.dumps(draft, ensure_ascii=False)[:16000]}
输出 JSON：verdict、exit_points、confusing_terms、unexplained_numbers、report_tone、
strong_parts、minimal_fixes。逐项标明位置、原句、原因和最小修改建议。
重点判断第一屏是否看懂，以及哪里会让聪明但不熟悉细节的读者退出。
""".strip()
        fact_prompt = f"""
你是事实核查编辑。只输出报告，不直接改正文。
证据包：{json.dumps(evidence, ensure_ascii=False)[:18000]}
初稿：{json.dumps(draft, ensure_ascii=False)[:16000]}
输出 JSON：verdict、unsupported_claims、scope_inflation、number_errors、missing_attribution、
approved_claims、minimal_fixes。每项指出原句与证据 ID；不要把写作风格偏好当成事实错误。
""".strip()
        style_prompt = f"""
你是个人风格与去 AI 味审稿人。只输出报告，不直接改正文。
风格规则：{json.dumps(style, ensure_ascii=False)[:10000]}
初稿：{json.dumps(draft, ensure_ascii=False)[:16000]}
输出 JSON：verdict、ai_phrases、rhythm_issues、template_transitions、identity_mismatch、
strong_parts、minimal_fixes。查找空话、匀速排比、伪纠偏、过度总结、讲课味和虚构真人感。
只改明确命中的问题，不把文章重写成你的风格。
""".strip()

        # Each reviewer has an independent prompt and result. Database-backed stages
        # execute sequentially because a SQLAlchemy Session is not concurrency-safe.
        reader_artifact = await self._run_agent(
            db,
            project=project,
            role="reader_reviewer",
            stage="reader_review",
            artifact_type="reader_review",
            system_prompt="你代表真实读者，检查理解阻力，而不是展示专业术语。",
            user_prompt=reader_prompt,
            temperature=0.15,
        )
        fact_artifact = await self._run_agent(
            db,
            project=project,
            role="fact_reviewer",
            stage="fact_review",
            artifact_type="fact_review",
            system_prompt="你只检查来源支持度、数字、范围和归属。",
            user_prompt=fact_prompt,
            temperature=0.05,
        )
        style_artifact = await self._run_agent(
            db,
            project=project,
            role="style_reviewer",
            stage="style_review",
            artifact_type="style_review",
            system_prompt="你只检查文章类型规则、禁用表达和作者风格，不直接改稿。",
            user_prompt=style_prompt,
            temperature=0.15,
        )
        reports = {
            "reader_review": self._json(reader_artifact.content_json, {}),
            "fact_review": self._json(fact_artifact.content_json, {}),
            "style_review": self._json(style_artifact.content_json, {}),
        }
        chief_prompt = f"""
你是资深主编。综合三份独立审稿报告，制作最小修改计划，不直接重写正文。
初稿：{json.dumps(draft, ensure_ascii=False)[:15000]}
审稿报告：{json.dumps(reports, ensure_ascii=False)[:24000]}
输出 JSON：must_fix、should_fix、reject_suggestions、author_decisions、revision_instructions、
release_readiness。事实错误优先；读者理解问题次之；风格只做最小修改；审稿人意见冲突时说明取舍。
""".strip()
        return await self._run_agent(
            db,
            project=project,
            role="chief_editor",
            stage="revision_plan",
            artifact_type="revision_plan",
            system_prompt="你是最终把关主编。你裁决审稿意见，但不擅自扩大文章主张。",
            user_prompt=chief_prompt,
            temperature=0.15,
        )

    async def _run_final_revision(self, db: Session, project: WritingProject) -> WritingArtifact:
        draft = self._artifact_content(db, project, "draft")
        plan = self._artifact_content(db, project, "revision_plan")
        evidence = self._artifact_content(db, project, "evidence_pack")
        style = self._style_payload(db, project)
        prompt = f"""
你是终稿修订者。只落实主编批准的最小修改，不自由重写。
初稿：{json.dumps(draft, ensure_ascii=False)[:16000]}
修改计划：{json.dumps(plan, ensure_ascii=False)[:14000]}
证据包：{json.dumps(evidence, ensure_ascii=False)[:16000]}
风格规则：{json.dumps(style, ensure_ascii=False)[:9000]}
输出 JSON：title、body、tags、claims、applied_changes。
不得新增证据包没有支持的事实；不要恢复被审稿删除的免责声明和模板标题。
""".strip()
        artifact = await self._run_agent(
            db,
            project=project,
            role="final_reviser",
            stage="final_revision",
            artifact_type="final_draft",
            system_prompt="你执行经批准的修订计划，保持事实、作者立场和文章主线稳定。",
            user_prompt=prompt,
            temperature=0.25,
        )
        self._create_draft_revision(db, project, artifact)
        return artifact

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
        input_hash = hashlib.sha256(
            f"{role}\n{system_prompt}\n{user_prompt}\n{binding.model_name}\n{binding.prompt_version}".encode()
        ).hexdigest()
        cached_run = db.scalar(
            select(AgentRun)
            .where(
                AgentRun.project_id == project.id,
                AgentRun.role == role,
                AgentRun.input_hash == input_hash,
                AgentRun.status.in_([AgentRunStatus.succeeded.value, AgentRunStatus.cached.value]),
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
            db.flush()
            return artifact
        except Exception as exc:
            run.status = AgentRunStatus.failed.value
            run.error = str(exc)[:2000]
            run.finished_at = utcnow()
            project.error = run.error
            project.state = WritingState.failed.value
            db.flush()
            raise
