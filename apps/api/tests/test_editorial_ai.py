from __future__ import annotations

import pytest

from app.core.config import Settings
from app.domain.models import SourceItem
from app.services.editorial import EditorialService


@pytest.mark.asyncio
async def test_model_generation_runs_analysis_before_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = EditorialService(
        Settings(
            model_base_url="https://open.bigmodel.cn/api/paas/v4",
            model_name="glm-5.2",
        )
    )
    source = SourceItem(
        id="src_test",
        external_id="123",
        canonical_url="https://x.com/test/status/123",
        author_handle="test",
        author_name="Test Author",
        text_original="We launched a new feature. Early users report faster review cycles.",
        metrics_json="{}",
    )

    responses = [
        {
            "topic": "新功能发布",
            "one_sentence_summary": "作者发布了一项新功能，并分享了早期使用反馈。",
            "verified_facts": [{"statement": "作者发布新功能", "source_index": 1}],
            "author_claims": [{"statement": "审核更快", "source_index": 1}],
            "uncertainties": ["缺少独立测试数据"],
            "audience_value": ["帮助读者判断是否值得试用"],
            "angles": [
                {"name": "产品变化", "thesis": "功能变化比宣传口号更值得看", "why": "可核查"},
                {"name": "效率提升", "thesis": "关注真实工作流影响", "why": "与用户相关"},
                {"name": "验证边界", "thesis": "早期反馈不等于普遍效果", "why": "避免夸大"},
            ],
            "recommended_angle": {"name": "验证边界", "reason": "信息价值和事实边界兼具"},
            "title_candidates": ["这项新功能真正改变了什么"],
            "outline": [{"heading": "先说结论", "purpose": "交代变化", "source_indices": [1]}],
            "avoid": ["把早期反馈写成普遍结论"],
        },
        {
            "title": "这项新功能真正改变了什么",
            "body": "先说结论\n\n作者发布了一项新功能，但目前能确认的是发布事实，效率提升仍主要来自作者描述。",
            "tags": ["产品观察", "效率工具", "信息拆解", "事实核查"],
            "claims": [
                {"statement": "作者发布了一项新功能", "source_index": 1, "verification": "source_only"},
                {"statement": "审核周期更快", "source_index": 1, "verification": "needs_external_check"},
            ],
        },
        {
            "title": "这项新功能真正改变了什么",
            "body": "先说结论\n\n能确认的是作者发布了新功能；审核提速目前仍只是早期反馈，不能直接当作普遍效果。",
            "tags": ["产品观察", "效率工具", "信息拆解", "事实核查"],
        },
    ]
    calls: list[dict] = []

    async def fake_chat_json(**kwargs):
        calls.append(kwargs)
        return responses.pop(0)

    monkeypatch.setattr(service, "_chat_json", fake_chat_json)

    result = await service._model_generate([source], "explain")

    assert result is not None
    assert result["analysis"]["recommended_angle"]["name"] == "验证边界"
    assert result["draft"]["title"] == "这项新功能真正改变了什么"
    assert result["draft"]["claims"][1]["verification"] == "needs_external_check"
    assert result["quality_passes"] == ["analysis", "draft", "de_translation"]
    assert len(calls) == 3
    assert calls[0]["reasoning_effort"] == "high"
    assert calls[1]["reasoning_effort"] == "medium"
    assert calls[2]["reasoning_effort"] == "low"
    assert "不要直接写小红书正文" in calls[0]["user_prompt"]
    assert "编辑分析" in calls[1]["user_prompt"]
    assert "去掉 AI 翻译味" in calls[2]["user_prompt"]


def test_glm_reasoning_options_are_enabled() -> None:
    service = EditorialService(
        Settings(
            model_base_url="https://open.bigmodel.cn/api/paas/v4",
            model_name="glm-5.2",
        )
    )

    assert service._reasoning_options("high") == {
        "thinking": {"type": "enabled"},
        "reasoning_effort": "high",
    }
