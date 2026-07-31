from pathlib import Path

from PIL import Image

from app.core.config import Settings
from app.domain.models import DraftRevision, SourceItem
from app.services.cards import CardService
from app.services.editorial import EditorialService


def test_editorial_and_card_quality(tmp_path: Path) -> None:
    source = SourceItem(
        id="src_quality",
        provider="fxtwitter",
        platform="x",
        external_id="1234567890",
        canonical_url="https://x.com/designer/status/1234567890",
        author_handle="designer",
        author_name="Product Designer",
        text_original=(
            "一个新的本地优先内容工作流上线了。它会保存原始来源，"
            "把事实核对与人工审核放在发布之前。最终发布动作必须由本人确认。"
        ),
        metrics_json="{}",
    )
    editorial = EditorialService(Settings())
    result = editorial._fallback([source], "explain")
    assert "先说结论" in result["body"]
    assert "值得关注的 3 个点" in result["body"]
    assert len(result["tags"].split(",")) >= 4

    draft = DraftRevision(
        id="draft_quality",
        source_id=source.id,
        version=1,
        style="explain",
        title="本地内容工作流为什么值得关注",
        body=result["body"],
        tags=result["tags"],
    )
    draft.source = source
    service = CardService(
        Settings(
            media_dir=tmp_path / "assets",
            raw_dir=tmp_path / "raw",
            export_dir=tmp_path / "exports",
            browser_profile_dir=tmp_path / "profiles",
        )
    )
    specs = service._build_specs(draft, max_cards=6)
    assert specs[0]["kind"] == "cover"
    assert specs[-1]["kind"] == "source"
    assert any(spec["kind"] == "content" for spec in specs)

    for index, spec in enumerate(specs, start=1):
        spec["page"] = index
        spec["total"] = len(specs)

    html_document = service.html_renderer._document(specs[0], "editorial_minimal")
    assert "本地内容工作流为什么值得关注" in html_document
    assert "1242px" in html_document
    assert "1656px" in html_document

    output = tmp_path / "preview.png"
    service._draw_fallback(output, specs[0], "editorial_minimal")
    with Image.open(output) as image:
        assert image.size == (1242, 1656)
