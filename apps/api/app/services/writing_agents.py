from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.domain.studio import WritingArtifact, WritingProject
from app.domain.writing_agent_schemas import (
    FinalClaimsOutput,
    TitleCandidatesOutput,
    WritingAgentContractError,
)
from app.services.claim_checker import ClaimChecker
from app.services.platform_studio import PlatformStudioService
from app.services.retrieval import bounded_json
from app.services.title_tournament import TitleTournamentResult, TitleTournamentService


class WritingAgentsMixin:
    @staticmethod
    def _evidence_refs(*payloads: object) -> list[str]:
        refs: set[str] = set()

        def visit(value: object) -> None:
            if isinstance(value, dict):
                evidence_ref = value.get("evidence_ref")
                text = value.get("text")
                if isinstance(evidence_ref, str) and evidence_ref and isinstance(text, str) and text:
                    refs.add(evidence_ref)
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        for payload in payloads:
            visit(payload)
        return sorted(refs)

    @staticmethod
    def _longform_completion_issues(
        payload: dict,
        *,
        minimum_chars: int = 1200,
        reference_body: str = "",
    ) -> list[str]:
        completion = payload.get("_completion")
        if not isinstance(completion, dict):
            # Deterministic fallbacks and older cached artifacts do not expose a
            # provider finish reason. Keep them readable, but only model-backed
            # longform can pass the strict completion gate below.
            return []
        issues = PlatformStudioService._article_completion_issues(
            {
                "body_markdown": str(payload.get("body") or ""),
                "illustration_plan": [],
            },
            response_meta=completion,
        )
        body_chars = len("".join(str(payload.get("body") or "").split()))
        if body_chars < minimum_chars:
            issues.append(f"正文只有 {body_chars} 字符，未达到深度长文最低 {minimum_chars} 字符")
        reference_chars = len("".join(reference_body.split()))
        retention_floor = int(reference_chars * 0.7)
        if reference_chars >= minimum_chars and body_chars < retention_floor:
            issues.append(f"终稿仅保留初稿约 {body_chars}/{reference_chars} 字符，疑似过度压缩")
        return list(dict.fromkeys(issues))

    async def _run_complete_longform(
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
        reference_body: str = "",
        schema_context: dict[str, Any] | None = None,
    ) -> WritingArtifact:
        artifact = await self._run_agent(
            db,
            project=project,
            role=role,
            stage=stage,
            artifact_type=artifact_type,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=12000,
            capture_response_meta=True,
            request_timeout_seconds=360,
            schema_context=schema_context,
        )
        first = self._json(artifact.content_json, {})
        issues = self._longform_completion_issues(first, reference_body=reference_body)
        if not issues:
            return artifact

        repair_prompt = f"""
上一轮公众号长文未通过完整度检查。禁止只续写尾部，请根据原任务从开头到结尾重新交付完整文章。

检测到的问题：{json.dumps(issues, ensure_ascii=False)}
原任务：{user_prompt}
上一轮输出：{bounded_json(first, 50000)}

保持所有有证据支持的事实和已批准结构，正文使用 Markdown，包含 3—6 个完整 H2，
所有代码围栏和句子必须闭合，结尾落在清晰判断。只输出 JSON：title、body、tags、claims；
终稿修订阶段可额外输出 applied_changes。
""".strip()
        repaired = await self._run_agent(
            db,
            project=project,
            role=role,
            stage=f"{stage}_repair",
            artifact_type=artifact_type,
            system_prompt="你是公众号长文修复总编。必须整篇重写并交付完整正文，不能把截断内容当作成稿。",
            user_prompt=repair_prompt,
            temperature=0.25,
            max_tokens=12000,
            capture_response_meta=True,
            request_timeout_seconds=360,
            schema_context=schema_context,
        )
        remaining = self._longform_completion_issues(
            self._json(repaired.content_json, {}),
            reference_body=reference_body,
        )
        if remaining:
            raise ValueError(f"模型连续两次返回不完整长文：{'；'.join(remaining)}")
        return repaired

    async def _run_editor_brief(self, db: Session, project: WritingProject) -> WritingArtifact:
        evidence_bundle = self._compile_evidence(db, project, purpose="editorial_brief")
        source = evidence_bundle.prompt_payload()
        prompt = f"""
你是写作总编辑。围绕来源建立一份可审批的写作任务单，不写正文。
作者预设读者：{project.reader or "未指定"}
作者预设承诺：{project.promise or "未指定"}
作者预设主张：{project.main_thesis or "未指定"}
来源（按任务章节检索的 evidence chunks）：{json.dumps(source, ensure_ascii=False)}

输出 JSON：reader、article_promise、main_thesis、reader_hook、must_use、must_not_claim、
article_type、tone、open_questions、success_criteria。
要求：只选一条主线；明确不能写成什么；技术内容必须先回答“做成了什么、为什么重要”。
selection_role=primary/supporting 都是作者明确选入本项目的事实来源；需要比较时必须同时使用，
不得只查 primary 后就把 supporting 中已有的材料误报为缺失。
selection_role=written_version 是作者明确选入的已写版本：必须读取并决定保留、合并或续写哪些内容，
但其中事实仍需回到关联的 primary/supporting 来源核对，不能把历史稿本身当作新证据。
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
        return self._attach_evidence_trace(artifact, evidence_bundle)

    async def _run_research(self, db: Session, project: WritingProject) -> WritingArtifact:
        evidence_bundle = self._compile_evidence(db, project, purpose="evidence_pack")
        source = evidence_bundle.prompt_payload()
        brief = self._artifact_content(db, project, "editorial_brief")
        prompt = f"""
你是证据研究员。根据任务单整理证据包，不写正文，不补充来源之外的事实。
任务单：{bounded_json(brief, 10000)}
来源（按事实、机制、数字、案例和限制分别召回）：{json.dumps(source, ensure_ascii=False)}

输出 JSON：facts、author_claims、unknowns、numbers、terms、source_map、material_gaps、
usable_examples、claims_for_draft。
每条 facts/numbers/claims_for_draft 必须包含 source_index、evidence_ref 和 evidence_quote；
evidence_ref 必须逐字使用输入中的 source_id:chunk_id，不得自造或只写来源级 ID；
把局部测试、作者判断和客观事实明确区分。术语给出不超过40字的人话解释。
必须逐一检查 selection_role=primary/supporting 的来源；connected 仅作关联上下文。
written_version 是需要整合的已写材料，请列出可复用结构、已有论述和未完成部分；其事实只有在原始来源支持时才能进入 claims_for_draft。
""".strip()
        artifact = await self._run_agent(
            db,
            project=project,
            role="evidence_researcher",
            stage="evidence_pack",
            artifact_type="evidence_pack",
            system_prompt="你是严谨的材料研究员。只整理证据和材料缺口，不写文章。",
            user_prompt=prompt,
            temperature=0.1,
            schema_context={"allowed_evidence_refs": self._evidence_refs(source)},
        )
        return self._attach_evidence_trace(artifact, evidence_bundle)

    async def _run_outline(self, db: Session, project: WritingProject) -> WritingArtifact:
        brief = self._artifact_content(db, project, "editorial_brief")
        evidence = self._artifact_content(db, project, "evidence_pack")
        style = self._style_payload(db, project)
        prompt = f"""
你是技术解释与文章结构设计师。制作一份作者可审批的大纲，不写完整正文。
任务单：{bounded_json(brief, 10000)}
证据包：{bounded_json(evidence, 18000)}
风格规则：{bounded_json(style, 8000)}

输出 JSON：opening、sections、ending、cognitive_load_plan、terms_first_use、evidence_allocation、
transitions、forbidden_moves。
每一节包含 section_id、heading、purpose、reader_question、key_point、evidence_refs、
terms_allowed、target_length；evidence_refs 只能逐字引用证据包中的 source_id:chunk_id。
顺序必须是：先让读者知道发生了什么和为什么值得看，再引入复杂术语；一节只承担一个认知任务。
""".strip()
        artifact = await self._run_agent(
            db,
            project=project,
            role="outline_architect",
            stage="outline",
            artifact_type="outline",
            system_prompt="你擅长控制读者认知负荷，让复杂内容按最自然的顺序被理解。",
            user_prompt=prompt,
            temperature=0.25,
            schema_context={
                "allowed_evidence_refs": self._evidence_refs(
                    evidence.get("evidence_retrieval") or {}
                )
            },
        )
        if self.settings.writing_quality_mode == "production":
            await self._run_title_tournament(db, project, artifact)
        return artifact

    async def _run_title_tournament(
        self,
        db: Session,
        project: WritingProject,
        outline_artifact: WritingArtifact,
    ) -> WritingArtifact:
        brief = self._artifact_content(db, project, "editorial_brief")
        evidence = self._artifact_content(db, project, "evidence_pack")
        outline = self._json(outline_artifact.content_json, {})
        evidence_retrieval = evidence.get("evidence_retrieval") or {}
        prompt = f"""
你是公众号标题策略师。基于已经确认的任务单、证据包和大纲，生成一组用于竞赛的标题候选，不写正文。
任务单：{bounded_json(brief, 10000)}
证据包：{bounded_json(evidence, 20000)}
文章大纲：{bounded_json(outline, 14000)}
可引用证据块：{bounded_json(evidence_retrieval, 20000)}

输出 JSON：candidates，共 12—20 个。每项必须包含 candidate_id、title、mechanism、
reader_promise、evidence_refs。mechanism 只能是 result、conflict、counterintuitive、scene、
question、number、judgment；至少覆盖五种机制，并尽量覆盖全部七种。
要求：
- 每个标题必须说明读者会看到什么，不能写“一文读懂”“值得关注”等空泛承诺；
- 数字、结果、比较和强判断必须由 evidence_refs 支持，引用只能逐字使用输入中的 source_id:chunk_id；
- 禁止震惊体、过度悬念、套路词和同义改写式凑数；
- 标题之间要有真实角度差异，不得复制历史短范例中的事实。
""".strip()
        candidates_artifact = await self._run_agent(
            db,
            project=project,
            role="title_strategist",
            stage="title_candidates",
            artifact_type="title_candidates",
            system_prompt="你只提出有当前证据支持、读者第一眼能理解的中文标题候选。",
            user_prompt=prompt,
            temperature=0.6,
            schema_context={
                "allowed_evidence_refs": self._evidence_refs(evidence_retrieval),
            },
        )
        raw = self._json(candidates_artifact.content_json, {})
        candidates = TitleCandidatesOutput.model_validate(
            {"candidates": raw.get("candidates") or []}
        )
        tournament = TitleTournamentService().evaluate(
            candidates,
            evidence_payload=evidence_retrieval,
            audience=str(brief.get("reader") or project.reader or "目标读者"),
            promise=str(brief.get("article_promise") or project.promise),
            thesis=str(brief.get("main_thesis") or project.main_thesis),
            source_artifact_id=candidates_artifact.id,
        )
        return self._store_artifact(
            db,
            project=project,
            artifact_type="title_tournament",
            content=tournament.model_dump(mode="json"),
            role="reader_simulator",
            approved=False,
        )

    def select_title_preference(
        self,
        db: Session,
        *,
        project: WritingProject,
        tournament_artifact_id: str,
        candidate_id: str,
        note: str,
    ) -> WritingArtifact:
        tournament_artifact = db.get(WritingArtifact, tournament_artifact_id)
        if (
            tournament_artifact is None
            or tournament_artifact.project_id != project.id
            or tournament_artifact.artifact_type != "title_tournament"
        ):
            raise ValueError("标题竞赛产物不存在或不属于当前项目")
        latest = self.latest_artifact(db, project.id, "title_tournament")
        if latest is None or latest.id != tournament_artifact.id:
            raise ValueError("标题竞赛已经更新，请从最新 top 5 重新选择")
        tournament = TitleTournamentResult.model_validate(
            self._json(tournament_artifact.content_json, {})
        )
        selected = TitleTournamentService.selected_candidate(tournament, candidate_id)
        candidate = selected.candidate
        preference = self._store_artifact(
            db,
            project=project,
            artifact_type="title_preference",
            content={
                "schema_version": 1,
                "tournament_artifact_id": tournament_artifact.id,
                "candidate_id": candidate.candidate_id,
                "title": candidate.title,
                "mechanism": candidate.mechanism,
                "reader_promise": candidate.reader_promise,
                "selection_source": "human",
                "note": note.strip(),
            },
            role="author",
            approved=True,
        )
        tournament_artifact.approved = True
        return preference

    def _selected_title_payload(
        self,
        db: Session,
        project: WritingProject,
    ) -> dict[str, Any]:
        if self.settings.writing_quality_mode != "production":
            return {}
        tournament_artifact = self.latest_artifact(db, project.id, "title_tournament")
        if tournament_artifact is None:
            return {}
        preference = self.latest_artifact(db, project.id, "title_preference")
        if preference is not None:
            payload = self._json(preference.content_json, {})
            if payload.get("tournament_artifact_id") == tournament_artifact.id:
                return payload
        tournament = TitleTournamentResult.model_validate(
            self._json(tournament_artifact.content_json, {})
        )
        if not tournament.quality_gate_passed:
            return {}
        candidate = tournament.top_five[0].candidate
        return {
            "schema_version": 1,
            "tournament_artifact_id": tournament_artifact.id,
            "candidate_id": candidate.candidate_id,
            "title": candidate.title,
            "mechanism": candidate.mechanism,
            "reader_promise": candidate.reader_promise,
            "selection_source": "deterministic_top_one_fallback",
            "note": "作者尚未选择；使用当前锦标赛第一名作为可回滚默认值",
        }

    async def _run_writer(self, db: Session, project: WritingProject) -> WritingArtifact:
        brief = self._artifact_content(db, project, "editorial_brief")
        evidence = self._artifact_content(db, project, "evidence_pack")
        outline = self._artifact_content(db, project, "outline")
        evidence_bundle = self._compile_evidence(
            db,
            project,
            purpose="draft",
            outline=outline,
        )
        source = evidence_bundle.prompt_payload()
        style = self._style_payload(db, project)
        selected_title = self._selected_title_payload(db, project)
        prompt = f"""
你是微信公众号中文长文写手。严格根据已确认任务单、证据包、大纲、原始材料和风格规则写完整初稿。
任务单：{bounded_json(brief, 9000)}
证据包：{bounded_json(evidence, 18000)}
大纲：{bounded_json(outline, 16000)}
逐节证据材料：{json.dumps(source, ensure_ascii=False)}
风格：{bounded_json(style, 9000)}
已冻结标题选择：{bounded_json(selected_title, 3000)}

输出 JSON：title、body、tags、claims。
要求：
- 平台目标是微信公众号长文，不是小红书 caption、卡片脚本或内部研究报告；
- 开头两三句让目标读者知道做成了什么、为什么值得看；
- 不按原文逐段翻译，不堆术语，术语首次出现时解释；
- 数字必须说明意义；作者自测必须有自然来源归属；
- 不出现内部核查清单、阅读边界、报告腔和模板标题；
- 不编造作者经历、读者对话、数字、情绪或观点；
- 正文优先 1800—4500 个中文字符，使用 Markdown，以 3—6 个 H2 组织完整文章；
- 所有代码使用带语言名的 Markdown 围栏，正文不能停在半句话或半行代码；
- 段落有快慢变化，结尾给出明确判断。
- 若“已冻结标题选择”包含 title，必须逐字使用，不能擅自改写。
""".strip()
        schema_context = {
            "allowed_evidence_refs": self._evidence_refs(
                source,
                evidence.get("evidence_retrieval") or {},
            )
        }
        if str(selected_title.get("title") or "").strip():
            schema_context["required_title"] = str(selected_title["title"])
        artifact = await self._run_complete_longform(
            db,
            project=project,
            role="writer",
            stage="draft",
            artifact_type="draft",
            system_prompt="你是中文母语写作者。只写已经被任务单与证据包允许的内容。",
            user_prompt=prompt,
            temperature=0.55,
            schema_context=schema_context,
        )
        return self._attach_evidence_trace(artifact, evidence_bundle)

    async def _run_reviews(self, db: Session, project: WritingProject) -> WritingArtifact:
        draft = self._artifact_content(db, project, "draft")
        brief = self._artifact_content(db, project, "editorial_brief")
        evidence = self._artifact_content(db, project, "evidence_pack")
        outline = self._artifact_content(db, project, "outline")
        style = self._style_payload(db, project)

        reader_prompt = f"""
你是目标读者代表。只输出审稿报告，不直接改正文。
目标与承诺：{bounded_json(brief, 7000)}
大纲：{bounded_json(outline, 9000)}
初稿：{bounded_json(draft, 16000)}
输出 JSON：verdict、issues、strong_parts。每个 issue 必须包含 issue_id、category、location、
severity、message、evidence_refs、evidence_quote、minimal_fix；issue_id 使用 reader- 前缀。
location 至少给出 section、paragraph_index 或初稿 exact quote 之一，禁止无法定位的泛泛建议。
重点判断第一屏是否看懂，以及哪里会让聪明但不熟悉细节的读者退出。
""".strip()
        fact_prompt = f"""
你是事实核查编辑。只输出报告，不直接改正文。
证据包：{bounded_json(evidence, 18000)}
初稿：{bounded_json(draft, 16000)}
输出 JSON：verdict、issues、strong_parts。每个 issue 必须包含 issue_id、category、location、
severity、message、evidence_refs、evidence_quote、minimal_fix；issue_id 使用 fact- 前缀。
证据引用必须是证据包中的 source_id:chunk_id，并给出对应原文；不要把风格偏好当成事实错误。
""".strip()
        style_prompt = f"""
你是个人风格与去 AI 味审稿人。只输出报告，不直接改正文。
风格规则：{bounded_json(style, 10000)}
初稿：{bounded_json(draft, 16000)}
输出 JSON：verdict、issues、strong_parts。每个 issue 必须包含 issue_id、category、location、
severity、message、evidence_refs、evidence_quote、minimal_fix；issue_id 使用 style- 前缀。
风格问题用初稿 exact quote 作为定位证据。查找空话、匀速排比、伪纠偏、过度总结、讲课味和虚构真人感。
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
            schema_context={"issue_id_prefix": "reader-"},
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
            schema_context={
                "issue_id_prefix": "fact-",
                "allowed_evidence_refs": self._evidence_refs(
                    evidence.get("evidence_retrieval") or {}
                ),
            },
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
            schema_context={"issue_id_prefix": "style-"},
        )
        reports = {
            "reader_review": self._json(reader_artifact.content_json, {}),
            "fact_review": self._json(fact_artifact.content_json, {}),
            "style_review": self._json(style_artifact.content_json, {}),
        }
        issue_ids = [
            str(issue.get("issue_id") or "")
            for report in reports.values()
            for issue in report.get("issues", [])
            if isinstance(report, dict) and isinstance(issue, dict)
        ]
        if len(issue_ids) != len(set(issue_ids)):
            raise WritingAgentContractError("reviewers returned duplicate issue ids")
        chief_prompt = f"""
你是资深主编。综合三份独立审稿报告，制作最小修改计划，不直接重写正文。
初稿：{bounded_json(draft, 15000)}
审稿报告：{bounded_json(reports, 24000)}
输出 JSON：decisions、release_readiness、rationale。decisions 必须对每个既有 issue_id 恰好裁决一次，
只能填写 issue_id、decision（approve/reject/defer）、reason、approved_fix；禁止新建 issue 或直接改正文。
事实错误优先；读者理解问题次之；风格只做最小修改；意见冲突时在 reason 中说明取舍。
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
            schema_context={"allowed_issue_ids": issue_ids},
        )

    async def _run_final_revision(self, db: Session, project: WritingProject) -> WritingArtifact:
        draft = self._artifact_content(db, project, "draft")
        plan = self._artifact_content(db, project, "revision_plan")
        evidence = self._artifact_content(db, project, "evidence_pack")
        outline = self._artifact_content(db, project, "outline")
        evidence_bundle = self._compile_evidence(
            db,
            project,
            purpose="final_revision",
            outline=outline,
        )
        source = evidence_bundle.prompt_payload()
        style = self._style_payload(db, project)
        selected_title = self._selected_title_payload(db, project)
        decisions = plan.get("decisions") if isinstance(plan, dict) else None
        initial_claim_ids = [
            str(item.get("claim_id") or "")
            for item in (draft.get("claims") if isinstance(draft.get("claims"), list) else [])
            if isinstance(item, dict) and item.get("claim_id")
        ]
        approved_issue_ids = [
            str(item.get("issue_id") or "")
            for item in (decisions if isinstance(decisions, list) else [])
            if isinstance(item, dict)
            if item.get("decision") == "approve" and item.get("issue_id")
        ]
        prompt = f"""
你是微信公众号终稿修订者。落实主编批准的修改，不擅自改变主线，也不能把完整初稿压缩成短稿。
初稿：{bounded_json(draft, 30000)}
修改计划：{bounded_json(plan, 14000)}
证据包：{bounded_json(evidence, 16000)}
逐节原始证据：{json.dumps(source, ensure_ascii=False)}
风格规则：{bounded_json(style, 9000)}
已冻结标题选择：{bounded_json(selected_title, 3000)}
输出 JSON：title、body、tags、claims、applied_changes。
applied_changes 只能引用主编批准的 issue_id，并必须逐项执行：
{json.dumps(approved_issue_ids, ensure_ascii=False)}
不得新增证据包没有支持的事实；不要恢复被审稿删除的免责声明和模板标题；
保持 1800—4500 个中文字符、3—6 个完整 H2、闭合代码围栏和完整结尾。
若“已冻结标题选择”包含 title，终稿必须逐字保留，不能在修订时另起标题。
""".strip()
        schema_context = {
            "approved_issue_ids": approved_issue_ids,
            "required_issue_ids": approved_issue_ids,
            "allowed_evidence_refs": self._evidence_refs(
                source,
                evidence.get("evidence_retrieval") or {},
            ),
        }
        if str(selected_title.get("title") or "").strip():
            schema_context["required_title"] = str(selected_title["title"])
        artifact = await self._run_complete_longform(
            db,
            project=project,
            role="final_reviser",
            stage="final_revision",
            artifact_type="final_draft",
            system_prompt="你执行经批准的修订计划，保持事实、作者立场和文章主线稳定。",
            user_prompt=prompt,
            temperature=0.25,
            reference_body=str(draft.get("body") or ""),
            schema_context=schema_context,
        )
        self._attach_evidence_trace(artifact, evidence_bundle)
        if self.settings.writing_schema_mode == "legacy":
            self._create_draft_revision(db, project, artifact)
            return artifact

        evidence_scope = {
            "retrievals": [
                evidence.get("evidence_retrieval") or {},
                source,
            ]
        }
        claim_prompt = f"""
你是终稿 claim 提取器，只做事实与主张抽取，不做风格改写。
终稿：{bounded_json(self._json(artifact.content_json, {}), 36000)}
初稿 claims：{bounded_json(draft.get("claims") or [], 16000)}
已批准修订 issue_id：{json.dumps(approved_issue_ids, ensure_ascii=False)}
可用逐节证据：{json.dumps(evidence_scope, ensure_ascii=False)}

输出 JSON：claims。每条 claim 必须包含 claim_id、statement、终稿中的 exact_quote、location、
claim_type、importance、evidence_refs、evidence_quote、origin_claim_id、approved_issue_ids。
evidence_refs 只能逐字使用输入中的 source_id:chunk_id；若无法支持则保留空数组，不得伪造。
origin_claim_id 只能引用初稿 claim_id；approved_issue_ids 只能引用上方已批准 ID。
必须抽取终稿中的全部 critical/major 事实、数字、因果、比较与能力主张，禁止用空 claims 逃避核查。
""".strip()
        final_claims_artifact = await self._run_agent(
            db,
            project=project,
            role="claim_extractor",
            stage="final_claims",
            artifact_type="final_claims",
            system_prompt="你是事实 claim 提取器。历史风格记忆不能参与事实判断。",
            user_prompt=claim_prompt,
            temperature=0,
            schema_context={
                "initial_claim_ids": initial_claim_ids,
                "approved_issue_ids": approved_issue_ids,
                "allowed_evidence_refs": self._evidence_refs(evidence_scope),
            },
        )
        claims_payload = self._json(final_claims_artifact.content_json, {})
        extraction = FinalClaimsOutput.model_validate(
            {"claims": claims_payload.get("claims") or []}
        )
        matrix = ClaimChecker().evaluate(
            final_artifact_id=artifact.id,
            final_claims_artifact_id=final_claims_artifact.id,
            final_body=str(self._json(artifact.content_json, {}).get("body") or ""),
            extraction=extraction,
            evidence_retrieval=evidence_scope,
            initial_claims=draft.get("claims") or [],
            approved_issue_ids=set(approved_issue_ids),
        )
        matrix_payload = matrix.model_dump(mode="json")
        matrix_artifact = self._store_artifact(
            db,
            project=project,
            artifact_type="claim_evidence_matrix",
            content=matrix_payload,
            role="claim_checker",
            approved=True,
        )
        self._attach_claim_trace(
            artifact,
            final_claims_artifact=final_claims_artifact,
            matrix_artifact=matrix_artifact,
            matrix=matrix_payload,
        )
        if matrix.completion_allowed:
            self._create_draft_revision(db, project, artifact)
        return artifact
