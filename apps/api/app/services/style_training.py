from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.studio import StyleProfile
from app.services.skills import binding_for


class StyleTrainingMixin:
    async def train_style(
        self,
        db: Session,
        *,
        name: str,
        description: str,
        original_samples: list[str],
        held_out_samples: list[str],
        author_feedback: list[str],
    ) -> StyleProfile:
        originals = [sample.strip() for sample in original_samples if sample.strip()]
        held_out = [sample.strip() for sample in held_out_samples if sample.strip()]
        feedback = [item.strip() for item in author_feedback if item.strip()]
        if len(originals) < 3:
            raise ValueError("至少需要 3 篇明确授权的原创样本")
        if not (self.settings.model_base_url and self.settings.model_name):
            raise ValueError("训练个人风格需要先配置模型")

        binding = binding_for(db, "writing.style_train", self.settings.model_name)
        if not binding.enabled:
            raise ValueError("Skill writing.style_train 已关闭")

        sample_payload = [
            {"sample_id": index + 1, "text": sample[:12000]}
            for index, sample in enumerate(originals[:20])
        ]
        initial_prompt = f"""
你是个人风格训练师。只分析作者明确授权的原创文章，不模仿他人的经历和立场。
档案名称：{name}
说明：{description}
原创样本：{json.dumps(sample_payload, ensure_ascii=False)[:60000]}

输出 JSON：
identity、reader_relationship、fact_boundaries、language_rhythm、paragraph_habits、
judgment_style、article_type_patterns、forbidden_expressions、positive_examples、
negative_examples、confidence_notes。

要求：
- 提炼跨样本稳定出现的特征，不把单篇偶然写法升级为规则；
- 正反例必须来自样本的短片段或抽象结构，不编造作者经历；
- 禁用表达应包含样本明确回避的 AI 味、讲课味和身份错位；
- 不输出“风格匹配分数”，保留作者最终判断权。
""".strip()
        initial = await self.editorial._chat_json(
            system_prompt=(
                "你负责从原创样本提炼可执行的个人风格规则。"
                "区分稳定规则、文章类型差异和证据不足，不做人格臆测。"
            ),
            user_prompt=initial_prompt,
            temperature=0.15,
            reasoning_effort=binding.reasoning_effort,
            model_name=binding.model_name,
        )

        validation = {
            "held_out_differences": [],
            "feedback_adjustments": [],
            "rules_to_keep": [],
            "rules_to_remove": [],
        }
        final_rules: dict[str, Any] = dict(initial)
        if held_out or feedback:
            validation_prompt = f"""
你是独立风格验证员。不要重新自由总结作者风格，而是验证规则初稿。
规则初稿：{json.dumps(initial, ensure_ascii=False)[:24000]}
留出样本：{json.dumps(held_out[:10], ensure_ascii=False)[:40000]}
作者真实改稿反馈：{json.dumps(feedback[:50], ensure_ascii=False)[:16000]}

输出 JSON：held_out_differences、feedback_adjustments、rules_to_keep、rules_to_remove、
final_rules、remaining_uncertainties。
要求：逐项说明哪条规则被留出样本支持或反驳；作者反馈优先于模型推断；
final_rules 必须保留初稿字段结构，并只做有证据的修改。
""".strip()
            validation = await self.editorial._chat_json(
                system_prompt=(
                    "你是风格规则验证员。用留出样本和作者反馈找差异，"
                    "不为了显得完整而制造规则。"
                ),
                user_prompt=validation_prompt,
                temperature=0.1,
                reasoning_effort=binding.reasoning_effort,
                model_name=binding.model_name,
            )
            candidate = validation.get("final_rules")
            if isinstance(candidate, dict) and candidate:
                final_rules = candidate

        forbidden = final_rules.get("forbidden_expressions")
        forbidden_list = forbidden if isinstance(forbidden, list) else []
        stored_samples = {
            "original_samples": originals,
            "held_out_samples": held_out,
            "author_feedback": feedback,
            "validation": validation,
        }
        profile = db.scalar(select(StyleProfile).where(StyleProfile.name == name.strip()))
        if profile is None:
            profile = StyleProfile(name=name.strip())
            db.add(profile)
        else:
            profile.version += 1
        profile.description = description.strip()
        profile.rules_json = json.dumps(final_rules, ensure_ascii=False)
        profile.forbidden_json = json.dumps(forbidden_list, ensure_ascii=False)
        profile.samples_json = json.dumps(stored_samples, ensure_ascii=False)
        profile.active = True
        db.flush()
        return profile
