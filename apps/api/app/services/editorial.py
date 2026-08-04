from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import datetime

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.models import DraftRevision, SkillBinding, SourceItem, new_id
from app.services.pool_memory import PoolMemoryService
from app.services.skills import binding_for
from app.services.source_graph import connected_sources

_STYLE_LABELS = {"news": "资讯速览", "explain": "解释拆解", "opinion": "编辑观察"}
_STYLE_GUIDES = {
    "news": "写成克制、清楚的资讯笔记。依次包含：发生了什么、核心信息、为什么值得关注、仍需确认。",
    "explain": "写成容易读懂的解释型笔记。依次包含：先说结论、值得关注的3个点、这对读者有什么用、阅读提醒。",
    "opinion": "写成有依据的编辑观察。依次包含：我的判断、判断依据、需要警惕的地方、给读者的判断框架。",
}
_TRANSFORM_GUIDES = {
    "de_translate": "只改中文表达，不改事实、数字、来源和判断边界。打散英文语序，删除模板句和机械过渡。",
    "stronger_insight": "保留事实边界，明确最重要的变化、影响对象、讨论价值和仍不能下的结论。",
    "concise": "压缩约三分之一，删除重复和空泛过渡，保留结论、证据、读者价值和不确定性。",
    "rewrite_title": "只重写标题，12到22个汉字，具体、有信息增量、不过度承诺。",
}
_TRANSFORM_SKILLS = {
    "de_translate": "writing.de_translate",
    "stronger_insight": "writing.stronger_insight",
    "concise": "writing.concise",
    "rewrite_title": "writing.rewrite_title",
}
_KEYWORD_TAGS = {
    "openai": "OpenAI",
    "chatgpt": "ChatGPT",
    "agent": "AI智能体",
    "model": "大模型",
    "llm": "大模型",
    "artificial intelligence": "人工智能",
    " ai ": "人工智能",
    "workflow": "效率工具",
    "local-first": "本地优先",
    "xiaohongshu": "小红书",
    "小红书": "小红书",
    "python": "Python",
    "product": "产品观察",
    "startup": "创业观察",
    "design": "设计思考",
    "creator": "内容创作",
    "content": "内容创作",
    "interface": "界面设计",
    "navigation": "交互设计",
    "ux": "UX设计",
    "ui": "UI设计",
}
_ANALYSIS_FIELDS = (
    "topic",
    "one_sentence_summary",
    "verified_facts",
    "author_claims",
    "uncertainties",
    "audience_value",
    "angles",
    "recommended_angle",
    "title_candidates",
    "outline",
    "avoid",
)


class EditorialService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(self, db: Session, source: SourceItem, style: str) -> DraftRevision:
        context = self._context(db, source)
        draft_id = new_id("draft")
        bindings = {
            name: binding_for(db, name, self.settings.model_name)
            for name in ("editorial.analysis", "writing.draft", "writing.de_translate")
        }
        model_ready = bool(
            self.settings.model_base_url
            and self.settings.model_name
            and bindings["editorial.analysis"].enabled
            and bindings["writing.draft"].enabled
        )
        memory_service = PoolMemoryService(self.settings, self)
        memory_snapshot = memory_service.create_snapshot(
            db,
            target_type="draft_revision",
            target_id=draft_id,
            query={
                "platform": "xhs",
                "format": "caption",
                "article_type": {
                    "explain": "technical_explainer",
                    "news": "news",
                    "opinion": "commentary",
                }.get(style, style),
                "source_text": "\n".join(item.text_original for item in context)[:30000],
                "topics": [],
                "limit": 6,
                "max_chars": 6000,
            },
            model_configured=model_ready,
            model_name=self.settings.model_name,
        )
        memory_prompts = {
            "editor": memory_service.prompt_payload(
                memory_snapshot,
                role="editor_in_chief",
                allow_pending=True,
            )["text"],
            "writer": memory_service.prompt_payload(
                memory_snapshot,
                role="writer",
                allow_pending=True,
            )["text"],
            "polish": memory_service.prompt_payload(
                memory_snapshot,
                role="transform",
                allow_pending=True,
            )["text"],
        }
        model_result = await self._model_generate(
            context,
            style,
            bindings,
            memory_prompts=memory_prompts,
        )
        analysis: dict = {}
        quality_passes: list[str] = []
        if model_result is None:
            generated = self._fallback(context, style)
            generator = "structured-fallback"
            model_name = ""
        else:
            generated = model_result["draft"]
            analysis = self._compact_analysis(model_result["analysis"])
            quality_passes = list(model_result.get("quality_passes") or [])
            generator = "model-skill-pipeline"
            model_name = str(model_result.get("model") or self.settings.model_name)
            roles = [
                ("editor_in_chief", "editorial_analysis"),
                ("writer", "draft"),
            ]
            if "writing.de_translate" in quality_passes:
                roles.append(("transform", "de_translate"))
            memory_service.mark_snapshot_applied(db, memory_snapshot, roles=roles)
        generated = self._sanitize_generated(generated, context, style)
        memory_summary = memory_service.snapshot_summary(memory_snapshot)

        draft = DraftRevision(
            id=draft_id,
            source_id=source.id,
            version=self._next_version(db, source.id),
            style=style,
            title=generated["title"][:80],
            body=generated["body"][:4000],
            tags=generated["tags"][:500],
            claims_json=json.dumps(generated["claims"], ensure_ascii=False),
            provenance_json=json.dumps(
                {
                    "source_ids": [item.id for item in context],
                    "source_urls": [item.canonical_url for item in context],
                    "generator": generator,
                    "model": model_name,
                    "quality_passes": quality_passes,
                    "editorial_analysis": analysis,
                    "skills": {name: binding.enabled for name, binding in bindings.items()},
                    "memory_snapshot_id": memory_summary["snapshot_id"],
                    "memory_snapshot_hash": memory_summary["snapshot_hash"],
                    "memory_ids": memory_summary["memory_ids"],
                    "memory_applied": memory_summary["applied"],
                    "memory_status": memory_summary["status"],
                },
                ensure_ascii=False,
            ),
            created_by="model" if model_result is not None else "system",
        )
        db.add(draft)
        db.flush()
        return draft

    def revise(
        self, db: Session, current: DraftRevision, *, title: str, body: str, tags: str
    ) -> DraftRevision:
        revised = DraftRevision(
            source_id=current.source_id,
            version=self._next_version(db, current.source_id, current.version),
            style=current.style,
            title=title.strip(),
            body=body.strip(),
            tags=tags.strip(),
            claims_json=current.claims_json,
            provenance_json=current.provenance_json,
            created_by="human",
        )
        db.add(revised)
        db.flush()
        return revised

    async def transform(
        self, db: Session, current: DraftRevision, *, action: str, instruction: str = ""
    ) -> DraftRevision:
        if action not in _TRANSFORM_GUIDES:
            raise ValueError("未知的 AI 编辑动作")
        if not (self.settings.model_base_url and self.settings.model_name):
            raise ValueError("尚未配置 AI 模型，无法执行智能改写")
        binding = binding_for(db, _TRANSFORM_SKILLS[action], self.settings.model_name)
        if not binding.enabled:
            raise ValueError(f"Skill {_TRANSFORM_SKILLS[action]} 已在设置中关闭")

        context = self._context(db, current.source)
        source_json = json.dumps(self._source_blocks(context), ensure_ascii=False)[:24000]
        provenance = self._parse_object(current.provenance_json)
        memory_service = PoolMemoryService(self.settings, self)
        source_memory_snapshot = memory_service.snapshot(
            db,
            str(provenance.get("memory_snapshot_id") or ""),
        )
        revised_id = new_id("draft")
        memory_snapshot = (
            memory_service.clone_snapshot(
                db,
                source_memory_snapshot,
                target_type="draft_revision",
                target_id=revised_id,
                model_configured=True,
                model_name=binding.model_name or self.settings.model_name,
            )
            if source_memory_snapshot is not None
            else None
        )
        memory_prompt = memory_service.prompt_payload(
            memory_snapshot,
            role="transform",
            allow_pending=True,
        )
        analysis = provenance.get("editorial_analysis") if isinstance(provenance, dict) else {}
        claims = self._parse_list(current.claims_json)
        prompt = f"""
请对下面的中文小红书草稿执行受约束编辑。

动作：{action}
要求：{_TRANSFORM_GUIDES[action]}
用户补充：{instruction.strip() or "无"}

编辑分析：{json.dumps(analysis or {}, ensure_ascii=False)[:9000]}
原始来源：{source_json}
当前标题：{current.title}
当前标签：{current.tags}
当前正文：\n{current.body}

当前草稿冻结的个人池子记忆：
{memory_prompt["text"]}

不得新增来源没有支持的人名、数字、日期、效果、因果或行业结论；不得把作者主张写成事实；
不确定内容继续保留边界。rewrite_title 只改变 title。只输出 JSON：
{{"title":"标题","body":"正文","tags":["标签"]}}
""".strip()
        parsed = await self._chat_json(
            system_prompt="你是中文内容主编，只能在已归档来源与编辑分析允许的范围内修改。",
            user_prompt=prompt,
            temperature=0.6 if action == "rewrite_title" else 0.35,
            reasoning_effort=binding.reasoning_effort,
            model_name=binding.model_name,
        )
        title = str(parsed.get("title") or current.title)
        body = (
            current.body if action == "rewrite_title" else str(parsed.get("body") or current.body)
        )
        tags = (
            current.tags
            if action == "rewrite_title"
            else self._tags_value(parsed.get("tags")) or current.tags
        )
        generated = self._sanitize_generated(
            {"title": title, "body": body, "tags": tags, "claims": claims}, context, current.style
        )
        passes = (
            list(provenance.get("quality_passes") or []) if isinstance(provenance, dict) else []
        )
        passes.append(action)
        if memory_snapshot is not None:
            memory_service.mark_snapshot_applied(
                db,
                memory_snapshot,
                roles=[("transform", action)],
            )
        memory_summary = memory_service.snapshot_summary(memory_snapshot)
        next_provenance = {
            **(provenance if isinstance(provenance, dict) else {}),
            "generator": "model-transform",
            "model": binding.model_name or self.settings.model_name,
            "parent_draft_id": current.id,
            "transform_action": action,
            "quality_passes": passes[-12:],
            "memory_snapshot_id": memory_summary["snapshot_id"],
            "memory_snapshot_hash": memory_summary["snapshot_hash"],
            "memory_ids": memory_summary["memory_ids"],
            "memory_applied": memory_summary["applied"],
            "memory_status": memory_summary["status"],
        }
        revised = DraftRevision(
            id=revised_id,
            source_id=current.source_id,
            version=self._next_version(db, current.source_id, current.version),
            style=current.style,
            title=generated["title"][:80],
            body=generated["body"][:4000],
            tags=generated["tags"][:500],
            claims_json=json.dumps(generated["claims"], ensure_ascii=False),
            provenance_json=json.dumps(next_provenance, ensure_ascii=False),
            created_by="model-polish",
        )
        db.add(revised)
        db.flush()
        return revised

    def _context(self, db: Session, source: SourceItem) -> list[SourceItem]:
        connected = connected_sources(db, source.id)
        return [source, *(item for item in connected if item.id != source.id)]

    @staticmethod
    def _next_version(db: Session, source_id: str, fallback: int = 0) -> int:
        current = db.scalar(
            select(func.max(DraftRevision.version)).where(DraftRevision.source_id == source_id)
        )
        return int(current or fallback) + 1

    @staticmethod
    def _binding_defaults(name: str, settings: Settings) -> SkillBinding:
        effort = (
            "high"
            if name == "editorial.analysis"
            else "low"
            if name == "writing.de_translate"
            else "medium"
        )
        return SkillBinding(
            skill_name=name, enabled=True, model_name=settings.model_name, reasoning_effort=effort
        )

    async def _model_generate(
        self,
        context: list[SourceItem],
        style: str,
        bindings: dict[str, SkillBinding] | None = None,
        memory_prompts: dict[str, str] | None = None,
    ) -> dict | None:
        if not (self.settings.model_base_url and self.settings.model_name):
            return None
        active = bindings or {
            name: self._binding_defaults(name, self.settings)
            for name in ("editorial.analysis", "writing.draft", "writing.de_translate")
        }
        analysis_binding = active["editorial.analysis"]
        draft_binding = active["writing.draft"]
        polish_binding = active["writing.de_translate"]
        if not analysis_binding.enabled or not draft_binding.enabled:
            return None

        source_json = json.dumps(self._source_blocks(context), ensure_ascii=False)[:28000]
        memory = memory_prompts or {}
        style_label = _STYLE_LABELS.get(style, style)
        analysis_prompt = f"""
先分析下面的 X 原帖、Thread 或 X Article，不要直接写正文。
写作类型：{style_label}
1. 用自然中文说明真正发生了什么；长文要识别论证主线，不按段落逐句翻译。
2. 区分来源事实、作者主张和无法确认的内容。
3. 找出对中文读者的具体价值，提出 3 个不同角度并推荐一个。
4. 给出 5 个具体标题、正文提纲，以及必须避免的误读和翻译腔。
只输出 JSON，字段：topic、one_sentence_summary、verified_facts、author_claims、uncertainties、
audience_value、angles、recommended_angle、title_candidates、outline、avoid。
来源：{source_json}

当前任务相关个人记忆：
{memory.get("editor", "")}
""".strip()
        try:
            analysis = await self._chat_json(
                system_prompt="你是资深中文内容主编和事实核查编辑，先分析证据与叙事，再决定怎么写。",
                user_prompt=analysis_prompt,
                temperature=0.2,
                reasoning_effort=analysis_binding.reasoning_effort,
                model_name=analysis_binding.model_name,
            )
            writing_prompt = f"""
根据编辑分析和原始来源写一篇可发布的小红书笔记。
类型：{style_label}。{_STYLE_GUIDES.get(style, _STYLE_GUIDES["explain"])}
编辑分析：{json.dumps(analysis, ensure_ascii=False)[:14000]}
原始来源：{source_json}
当前任务相关个人记忆：
{memory.get("writer", "")}
要求：只采用 recommended_angle；标题 12-22 字；开头直接交代事实与阅读价值；正文 500-1100 字；
短段落；不逐句翻译；区分事实、作者观点和编辑判断；不增加来源没有的信息；不确定项使用保守措辞；
结尾给具体判断框架；标签 4-7 个。只输出 JSON：
{{"title":"标题","body":"正文","tags":["标签"],"claims":[{{"statement":"陈述","source_index":1,"verification":"source_only"}}]}}
""".strip()
            initial = await self._chat_json(
                system_prompt="你是严谨、有判断力、熟悉小红书阅读节奏的中文主编，不做机械翻译。",
                user_prompt=writing_prompt,
                temperature=0.5,
                reasoning_effort=draft_binding.reasoning_effort,
                model_name=draft_binding.model_name,
            )
            final = initial
            passes = ["editorial.analysis", "writing.draft"]
            if polish_binding.enabled:
                final = await self._polish_draft(
                    initial,
                    analysis,
                    source_json,
                    polish_binding,
                    memory_prompt=memory.get("polish", ""),
                )
                passes.append("writing.de_translate")
            return {
                "analysis": analysis,
                "quality_passes": passes,
                "model": draft_binding.model_name or self.settings.model_name,
                "draft": {
                    "title": str(final.get("title") or initial.get("title") or ""),
                    "body": str(final.get("body") or initial.get("body") or ""),
                    "tags": self._tags_value(final.get("tags"))
                    or self._tags_value(initial.get("tags")),
                    "claims": self._map_model_claims(initial.get("claims"), context),
                },
            }
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    async def _polish_draft(
        self,
        initial: dict,
        analysis: dict,
        source_json: str,
        binding: SkillBinding,
        *,
        memory_prompt: str = "",
    ) -> dict:
        prompt = f"""
把初稿做最后一轮中文编辑：事实、数字、来源归属和不确定性边界不变；打散英文语序；
删除机械过渡、同义反复和模板句；每段只承担一个意思；不增加背景或个人体验。
编辑分析：{json.dumps(analysis, ensure_ascii=False)[:9000]}
原始来源：{source_json}
初稿：{json.dumps(initial, ensure_ascii=False)[:14000]}
当前任务冻结的个人记忆：{memory_prompt}
只输出 JSON：{{"title":"标题","body":"正文","tags":["标签"]}}
""".strip()
        try:
            return await self._chat_json(
                system_prompt="你是中文母语内容总编，专门消除机器翻译痕迹，绝不改变事实边界。",
                user_prompt=prompt,
                temperature=0.35,
                reasoning_effort=binding.reasoning_effort,
                model_name=binding.model_name,
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return initial

    async def _chat_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        reasoning_effort: str,
        model_name: str = "",
    ) -> dict:
        selected_model = model_name.strip() or self.settings.model_name
        request_body: dict = {
            "model": selected_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        request_body.update(self._reasoning_options(reasoning_effort, selected_model))
        headers = {"Content-Type": "application/json"}
        if self.settings.model_api_key:
            headers["Authorization"] = f"Bearer {self.settings.model_api_key}"
        endpoint = self.settings.model_base_url.rstrip("/") + "/chat/completions"
        variants = [request_body]
        without_format = dict(request_body)
        without_format.pop("response_format", None)
        variants.append(without_format)
        if "thinking" in request_body or "reasoning_effort" in request_body:
            portable = dict(without_format)
            portable.pop("thinking", None)
            portable.pop("reasoning_effort", None)
            variants.append(portable)
        last_response: httpx.Response | None = None
        async with httpx.AsyncClient(timeout=180) as client:
            for index, payload in enumerate(variants):
                response = await client.post(endpoint, headers=headers, json=payload)
                last_response = response
                if response.status_code not in {400, 404, 422} or index == len(variants) - 1:
                    response.raise_for_status()
                    content = str(response.json()["choices"][0]["message"].get("content") or "")
                    return self._parse_json_object(content)
        if last_response is not None:
            last_response.raise_for_status()
        raise ValueError("model returned no response")

    def _reasoning_options(self, effort: str, model_name: str = "") -> dict:
        model = (model_name or self.settings.model_name).lower()
        if model.startswith("glm-5") or "bigmodel.cn" in self.settings.model_base_url.lower():
            return {"thinking": {"type": "enabled"}, "reasoning_effort": effort}
        return {}

    @staticmethod
    def _source_blocks(context: list[SourceItem]) -> list[dict]:
        output = []
        for index, item in enumerate(context, start=1):
            try:
                metrics = json.loads(item.metrics_json or "{}")
            except json.JSONDecodeError:
                metrics = {}
            created = item.created_at.isoformat() if isinstance(item.created_at, datetime) else ""
            output.append(
                {
                    "index": index,
                    "author": item.author_name,
                    "handle": item.author_handle,
                    "published_at": created,
                    "metrics": metrics,
                    "content_kind": item.content_kind,
                    "text": item.text_original,
                    "editor_note": item.editor_note,
                    "url": item.canonical_url,
                }
            )
        return output

    @staticmethod
    def _compact_analysis(analysis: dict) -> dict:
        compact = {key: analysis.get(key) for key in _ANALYSIS_FIELDS if key in analysis}
        if len(json.dumps(compact, ensure_ascii=False)) <= 16000:
            return compact
        return {
            "topic": str(analysis.get("topic") or "")[:300],
            "one_sentence_summary": str(analysis.get("one_sentence_summary") or "")[:600],
            "recommended_angle": analysis.get("recommended_angle") or {},
            "verified_facts": (analysis.get("verified_facts") or [])[:6],
            "author_claims": (analysis.get("author_claims") or [])[:6],
            "audience_value": (analysis.get("audience_value") or [])[:6],
            "uncertainties": (analysis.get("uncertainties") or [])[:8],
            "title_candidates": (analysis.get("title_candidates") or [])[:5],
        }

    @staticmethod
    def _parse_json_object(content: str) -> dict:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
        if not cleaned.startswith("{"):
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start >= 0 and end > start:
                cleaned = cleaned[start : end + 1]
        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise ValueError("model response is not a JSON object")
        return parsed

    @staticmethod
    def _parse_object(value: str) -> dict:
        try:
            parsed = json.loads(value or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _parse_list(value: str) -> list:
        try:
            parsed = json.loads(value or "[]")
        except (TypeError, json.JSONDecodeError):
            return []
        return parsed if isinstance(parsed, list) else []

    @staticmethod
    def _tags_value(value: object) -> str:
        return ",".join(str(tag) for tag in value) if isinstance(value, list) else str(value or "")

    @staticmethod
    def _map_model_claims(value: object, context: list[SourceItem]) -> list[dict]:
        if not isinstance(value, list):
            return []
        claims = []
        for raw in value:
            if not isinstance(raw, dict):
                continue
            try:
                source_index = max(1, int(raw.get("source_index") or 1))
            except (TypeError, ValueError):
                source_index = 1
            item = context[min(source_index - 1, len(context) - 1)]
            verification = str(raw.get("verification") or "source_only")
            if verification not in {"source_only", "needs_external_check"}:
                verification = "source_only"
            statement = str(raw.get("statement") or "").strip()
            if statement:
                claims.append(
                    {
                        "statement": statement[:300],
                        "source_id": item.id,
                        "source_url": item.canonical_url,
                        "verification": verification,
                    }
                )
        return claims

    def _fallback(self, context: Iterable[SourceItem], style: str) -> dict:
        items = list(context)
        focal = items[0]
        cleaned_pairs = [
            (item, self._clean(item.text_original)) for item in items if item.text_original.strip()
        ]
        pieces: list[tuple[SourceItem, str]] = []
        for item, text in cleaned_pairs:
            for sentence in self._sentences(text):
                if sentence and all(sentence != existing for _, existing in pieces):
                    pieces.append((item, sentence))
        first = pieces[0][1] if pieces else "这条 X 内容暂时没有可提取的正文。"
        has_chinese = bool(re.search(r"[\u4e00-\u9fff]", " ".join(text for _, text in pieces)))
        handle = focal.author_handle or focal.author_name or "原作者"
        title = self._fallback_title(first, handle, has_chinese)
        summary = self._trim_sentence(first, 110)
        supporting = [self._trim_sentence(text, 120) for _, text in pieces[1:5]]
        if style == "news":
            parts = [
                "发生了什么",
                f"@{handle} 发布的信息可概括为：{summary}",
                "核心信息",
                *[f"• {x}" for x in supporting[:3]],
                "仍需确认",
                "涉及数字、时间、效果或因果判断时，应结合公开资料核查。",
            ]
        elif style == "opinion":
            parts = [
                "我的判断",
                f"这更像一个观察信号，而不是完整结论。{summary}",
                "判断依据",
                *[f"• {x}" for x in ([summary, *supporting][:3])],
                "给读者的判断框架",
                "先确认它改变了什么具体行为，再判断是不是可复制趋势。",
            ]
        else:
            parts = ["先说结论", f"@{handle} 的核心信息是：{summary}", "值得关注的 3 个点"]
            for index, point in enumerate([summary, *supporting][:3], start=1):
                parts.append(f"{index}️⃣ {point}")
            parts.extend(
                [
                    "这对读者有什么用",
                    "它提供了一条一手线索，适用条件与实际效果仍需验证。",
                    "阅读提醒",
                    "本文基于已归档 X 来源整理。",
                ]
            )
        claims = [
            {
                "statement": text[:300],
                "source_id": item.id,
                "source_url": item.canonical_url,
                "verification": "source_only",
            }
            for item, text in pieces[:8]
        ]
        return {
            "title": title,
            "body": "\n\n".join(parts),
            "tags": ",".join(
                self._fallback_tags(focal, style, " ".join(text for _, text in pieces))
            ),
            "claims": claims,
        }

    def _sanitize_generated(self, generated: dict, context: list[SourceItem], style: str) -> dict:
        title = re.sub(
            r"\s+", " ", re.sub(r"^[#\s]+|[#\s]+$", "", str(generated.get("title") or ""))
        ).strip("，。！？；：-—")
        body = re.sub(
            r"\n{3,}", "\n\n", str(generated.get("body") or "").replace("\r\n", "\n").strip()
        )
        if not title:
            focal = context[0]
            title = self._fallback_title(
                self._clean(focal.text_original),
                focal.author_handle or focal.author_name or "原作者",
                bool(re.search(r"[\u4e00-\u9fff]", focal.text_original)),
            )
        if not body:
            body = self._fallback(context, style)["body"]
        tags = []
        for value in re.split(r"[,，#\n]+", self._tags_value(generated.get("tags"))):
            tag = re.sub(r"\s+", "", value).strip()
            if 1 < len(tag) <= 18 and tag not in tags:
                tags.append(tag)
        if len(tags) < 4:
            tags.extend(
                tag for tag in self._fallback_tags(context[0], style, body) if tag not in tags
            )
        claims = generated.get("claims") if isinstance(generated.get("claims"), list) else []
        return {"title": title[:36], "body": body, "tags": ",".join(tags[:7]), "claims": claims}

    @staticmethod
    def _fallback_title(text: str, handle: str, has_chinese: bool) -> str:
        cleaned = re.sub(
            r"\s+", " ", re.sub(r"[@#]\S+", "", re.sub(r"https?://\S+", "", text))
        ).strip("，。！？；：-— ")
        if has_chinese and cleaned:
            first = re.split(r"[。！？\n]", cleaned)[0].strip()
            if first:
                return first[:22].rstrip("，。！？；：")
        handle_text = re.sub(r"[^A-Za-z0-9_\u4e00-\u9fff]", "", handle)[:14]
        return f"来自@{handle_text}的关键信息" if handle_text else "这条X内容讲了什么"

    def _fallback_tags(self, focal: SourceItem, style: str, text: str) -> list[str]:
        normalized = f" {text.lower()} "
        tags = [{"news": "科技资讯", "opinion": "编辑观察"}.get(style, "信息拆解"), "X平台观察"]
        for needle, tag in _KEYWORD_TAGS.items():
            if needle in normalized and tag not in tags:
                tags.append(tag)
        handle_tag = re.sub(r"[^A-Za-z0-9_\u4e00-\u9fff]", "", focal.author_handle or "")
        if handle_tag and handle_tag not in tags:
            tags.append(handle_tag[:18])
        if "内容创作" not in tags:
            tags.append("内容创作")
        return tags[:7]

    @staticmethod
    def _sentences(text: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", text).strip()
        return (
            [
                part.strip()
                for part in re.split(r"(?<=[。！？!?；;])\s*|(?<=\.)\s+(?=[A-Z0-9])", normalized)
                if len(part.strip()) >= 4
            ]
            if normalized
            else []
        )

    @staticmethod
    def _trim_sentence(text: str, limit: int) -> str:
        cleaned = re.sub(r"\s+", " ", re.sub(r"https?://\S+", "", text)).strip()
        if len(cleaned) <= limit:
            return cleaned
        cut = max(cleaned.rfind(mark, 0, limit) for mark in ("。", "！", "？", "；", ",", "，"))
        cut = limit if cut < limit // 2 else cut + 1
        return cleaned[:cut].rstrip("，,；; ") + "…"

    @staticmethod
    def _clean(text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()
