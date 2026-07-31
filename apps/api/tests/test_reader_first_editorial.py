from __future__ import annotations

import pytest

from app.core.config import Settings
from app.domain.models import SourceItem
from app.services.reader_editorial import ReaderFirstEditorialService


def _source() -> SourceItem:
    return SourceItem(
        id="src_tech",
        external_id="tech-1",
        canonical_url="https://x.com/engineer/status/1",
        author_handle="engineer",
        author_name="GPU Engineer",
        text_original=(
            "We optimized a Wan2.2 attention kernel on Blackwell GPUs. "
            "The optimized CUDA kernel reduced latency from 7444 us to 4719 us."
        ),
        metrics_json="{}",
    )


def test_reader_body_removes_internal_review_sections() -> None:
    body = """
这次优化真正厉害的地方，是作者把视频生成中最耗时的注意力计算重新写了一遍。

VSA 可以理解为只让真正有贡献的 token 参与计算，从而减少无效工作。

阅读时需注意以下边界：
1. 54 倍是注意力内核的局部结果。
2. 需要更多公开测试。

评估此方案的适用性，可关注硬件配置与业务场景。

据作者在 Blackwell GPU 上的测试，内核延迟从 7444 微秒降到 4719 微秒。
""".strip()

    cleaned = ReaderFirstEditorialService._reader_body(body)

    assert "真正厉害" in cleaned
    assert "VSA 可以理解" in cleaned
    assert "7444" in cleaned
    assert "阅读时需注意" not in cleaned
    assert "54 倍是注意力内核" not in cleaned
    assert "评估此方案" not in cleaned


def test_reader_body_strips_template_headings_without_losing_copy() -> None:
    body = """
先说结论

作者把最慢的一段计算从通用框架换成了针对 Blackwell 的 CUDA 内核。

这对读者有什么用：它说明性能差距往往不只来自模型本身，也来自底层实现。
""".strip()

    cleaned = ReaderFirstEditorialService._reader_body(body)

    assert "先说结论" not in cleaned
    assert "这对读者有什么用" not in cleaned
    assert "作者把最慢的一段计算" in cleaned
    assert "性能差距" in cleaned


@pytest.mark.asyncio
async def test_reader_first_generation_keeps_caveats_out_of_reader_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ReaderFirstEditorialService(
        Settings(
            model_base_url="https://open.bigmodel.cn/api/paas/v4",
            model_name="glm-5.2",
        )
    )
    source = _source()
    responses = [
        {
            "topic": "视频生成内核优化",
            "one_sentence_summary": "作者重写了注意力内核并显著降低延迟。",
            "verified_facts": ["作者展示了内核实现与延迟数字"],
            "author_claims": ["局部优化最高达到 54 倍"],
            "uncertainties": ["端到端提升幅度未给出"],
            "audience_value": ["理解模型速度为何受底层内核影响"],
            "angles": [{"name": "底层实现", "reason": "最有信息增量"}],
            "recommended_angle": {
                "name": "底层实现",
                "reason": "解释模型之外的性能来源",
                "reader_hook": "最快的视频内核不是换模型，而是重写最慢的计算",
                "plain_language_thesis": "模型速度也取决于底层代码如何使用 GPU",
            },
            "title_candidates": ["视频生成提速，关键可能不在模型"],
            "outline": [],
            "avoid": ["把局部 54 倍写成端到端 54 倍"],
        },
        {
            "title": "视频生成提速，关键可能不在模型",
            "body": (
                "这次优化最值得看的，不是又换了一个模型，而是作者重写了最慢的注意力计算。\n\n"
                "VSA 可以理解为只让真正有贡献的 token 参与计算。\n\n"
                "阅读提醒：端到端提升仍需验证。"
            ),
            "tags": ["CUDA", "视频生成", "GPU优化", "AI工程"],
            "claims": [
                {
                    "statement": "内核延迟从 7444 微秒降到 4719 微秒",
                    "source_index": 1,
                    "verification": "source_only",
                }
            ],
        },
        {
            "title": "视频生成提速，关键可能不在模型",
            "body": (
                "这次优化最值得看的，不是又换了一个模型，而是作者重写了最慢的注意力计算。\n\n"
                "VSA 可以理解为只让真正有贡献的 token 参与计算。\n\n"
                "据作者在 Blackwell GPU 上的测试，内核延迟从 7444 微秒降到 4719 微秒。"
            ),
            "tags": ["CUDA", "视频生成", "GPU优化", "AI工程"],
        },
    ]
    calls: list[dict] = []

    async def fake_chat_json(**kwargs):
        calls.append(kwargs)
        return responses.pop(0)

    monkeypatch.setattr(service, "_chat_json", fake_chat_json)

    result = await service._model_generate([source], "explain")

    assert result is not None
    assert "reader-first" in result["quality_passes"]
    assert "不要把事实核查流程写成面向读者的内容" in calls[0]["system_prompt"]
    assert "禁止使用以下标题或句式" in calls[1]["user_prompt"]
    assert "不要以免责声明收尾" in calls[1]["user_prompt"]
    assert "把“限制、边界、不确定性”放回内部分析" in calls[2]["user_prompt"]


def test_sanitize_generated_applies_reader_firewall() -> None:
    service = ReaderFirstEditorialService(Settings())
    source = _source()
    generated = {
        "title": "一次 CUDA 内核优化",
        "body": (
            "作者重写了最慢的注意力计算。\n\n"
            "阅读提醒\n\n"
            "实际效果仍需验证。\n\n"
            "真正有价值的是，它展示了如何让 GPU 少做无效计算。"
        ),
        "tags": ["CUDA", "GPU优化", "视频生成", "AI工程"],
        "claims": [],
    }

    result = service._sanitize_generated(generated, [source], "explain")

    assert "阅读提醒" not in result["body"]
    assert "实际效果仍需验证" not in result["body"]
    assert "GPU 少做无效计算" in result["body"]
