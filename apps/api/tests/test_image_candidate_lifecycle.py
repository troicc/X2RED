from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app.core.config import Settings
from app.domain.image_candidate_schemas import ProviderCapabilities
from app.domain.platforms import PlatformVariant
from app.services.image_candidate_service import ImageCandidateError, ImageCandidateService
from app.services.minimal_zine_native import MinimalZineNativeService
from app.services.model_client import (
    CandidateCountUnsupported,
    GeneratedImage,
    ImageGenerationResult,
    ModelClient,
)


def settings(tmp_path: Path, **values: object) -> Settings:
    return Settings(
        export_dir=tmp_path / "exports",
        media_dir=tmp_path / "assets",
        raw_dir=tmp_path / "raw",
        browser_profile_dir=tmp_path / "profile",
        native_skill_dir=tmp_path / "skills",
        scheduler_enabled=False,
        **values,
    )


def candidate_image(*, accent: str = "#c91f2c", offset: int = 0) -> bytes:
    image = Image.new("RGB", (1024, 1536), "#e6dcc8")
    draw = ImageDraw.Draw(image)
    draw.rectangle((250 + offset, 300, 650 + offset, 720), fill="#55514d")
    draw.ellipse((570, 470 + offset, 735, 635 + offset), fill=accent)
    output = io.BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def blank_image() -> bytes:
    image = Image.new("RGB", (1024, 1536), "#e6dcc8")
    output = io.BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


def brief() -> dict:
    return {
        "concrete_subject": "钉在纸面的首张证据照片",
        "action_or_relation": "照片边缘压住一条时间刻度",
        "evidence_refs": ["source:test:1"],
    }


class FakeModel:
    def __init__(
        self,
        batches: list[list[bytes]],
        *,
        edit: bool = False,
        candidate_count: bool = True,
    ) -> None:
        self.batches = list(batches)
        self.calls: list[dict] = []
        self.capabilities = ProviderCapabilities(
            provider="fake-provider",
            model="fake-image-v1",
            candidate_count=candidate_count,
            max_candidate_count=4 if candidate_count else 1,
            image_reference=edit,
            image_edit=edit,
            multi_turn=False,
            usage=True,
            detection_mode="known-provider",
        )

    def image_capabilities(self) -> ProviderCapabilities:
        return self.capabilities

    def generate_images(
        self,
        *,
        prompt: str,
        count: int,
        reference_image: bytes | None = None,
        edit: bool = False,
    ) -> ImageGenerationResult:
        self.calls.append(
            {
                "prompt": prompt,
                "count": count,
                "reference": bool(reference_image),
                "edit": edit,
            }
        )
        values = self.batches.pop(0)
        return ImageGenerationResult(
            images=[
                GeneratedImage(image_bytes=value, latency_ms=125, cost_usd=0.12)
                for value in values
            ],
            capabilities=self.capabilities,
            request_strategy="edit" if edit else ("single-call" if self.capabilities.candidate_count else "sequential"),
            call_count=1 if self.capabilities.candidate_count or edit else len(values),
            usage={"images": len(values)},
            cost_usd=0.12 * len(values),
            latency_ms=125 * len(values),
            requested_count=count,
        )


def test_provider_capability_detection_is_conservative(tmp_path: Path) -> None:
    openai = ModelClient(
        settings(
            tmp_path,
            image_base_url="https://api.openai.com/v1",
            image_api_key="test-key",
            image_model="gpt-image-1",
        )
    ).image_capabilities()
    assert openai.candidate_count is True
    assert openai.max_candidate_count == 4
    assert openai.image_reference is True
    assert openai.image_edit is True
    assert openai.usage is True

    glm = ModelClient(
        settings(
            tmp_path,
            image_base_url="https://open.bigmodel.cn/api/paas/v4",
            image_api_key="test-key",
            image_model="glm-image",
        )
    ).image_capabilities()
    assert glm.candidate_count is False
    assert glm.image_edit is False

    unknown = ModelClient(
        settings(
            tmp_path,
            image_base_url="https://images.example.invalid/v1",
            image_api_key="test-key",
            image_model="private-model",
        )
    ).image_capabilities()
    assert unknown.detection_mode == "conservative-default"
    assert unknown.max_candidate_count == 1
    assert unknown.image_reference is False


def test_runtime_n_rejection_falls_back_to_three_sequential_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = ModelClient(
        settings(
            tmp_path,
            image_base_url="https://api.openai.com/v1",
            image_api_key="test-key",
            image_model="gpt-image-1",
        )
    )
    requested: list[int] = []

    def fake_post(*_: object, count: int, **__: object) -> tuple[object, int]:
        requested.append(count)
        if count > 1:
            raise CandidateCountUnsupported("provider rejected n")
        return object(), 10

    monkeypatch.setattr(client, "_post_image_generation", fake_post)
    monkeypatch.setattr(
        client,
        "_decode_image_response",
        lambda *_: ([GeneratedImage(image_bytes=candidate_image(), latency_ms=10)], {}, None),
    )
    result = client.generate_images(prompt="NO TEXT", count=3)

    assert requested == [3, 1, 1, 1]
    assert result.request_strategy == "sequential"
    assert result.call_count == 4
    assert result.capabilities.detection_mode == "runtime-fallback"
    assert len(result.images) == 3


def test_api_batch_records_three_candidates_prompt_cost_latency_and_contact_sheet(
    tmp_path: Path,
) -> None:
    fake = FakeModel(
        [[candidate_image(offset=0), candidate_image(offset=20), candidate_image(offset=40)]],
        candidate_count=False,
    )
    service = ImageCandidateService(settings(tmp_path), model_client=fake)  # type: ignore[arg-type]
    lifecycle = service.load({})
    artifacts: dict[str, str] = {}
    result = service.generate_candidates(
        lifecycle=lifecycle,
        page=1,
        prompt="NO TEXT. Evidence photograph on paper.",
        output_dir=tmp_path / "variant",
        artifact_paths=artifacts,
        page_visual_brief=brief(),
        invariants=["aged paper", "vermilion accent"],
        count=3,
        auto_repair=False,
    )

    assert len(result.page_state.candidates) == 3
    assert len(result.page_state.prompt_runs) == 1
    run = result.page_state.prompt_runs[0]
    assert run.request_strategy == "sequential"
    assert run.requested_count == 3
    assert run.call_count == 3
    assert run.prompt_hash
    assert run.cost_usd == pytest.approx(0.36)
    assert all(item.latency_ms == 125 for item in result.page_state.candidates)
    assert all(item.cost_usd == pytest.approx(0.12) for item in result.page_state.candidates)
    assert all(Path(result.artifact_paths[item.artifact_key]).is_file() for item in result.page_state.candidates)
    assert Path(result.artifact_paths[result.page_state.contact_sheet_key]).is_file()
    assert result.selected_candidate is not None
    assert result.selected_candidate.status == "selected"
    assert result.lifecycle.total_api_calls == 3


def test_manual_upload_uses_same_model_and_selection_preserves_every_candidate(
    tmp_path: Path,
) -> None:
    service = ImageCandidateService(settings(tmp_path))
    output_dir = tmp_path / "variant"
    result = service.add_manual_candidates(
        lifecycle=service.load({}),
        page=2,
        prompt="NO TEXT. A concrete evidence strip.",
        images=[candidate_image(accent="#1646d8"), candidate_image(accent="#c91f2c", offset=30)],
        output_dir=output_dir,
        artifact_paths={},
        page_visual_brief=brief(),
        invariants=["paper", "single subject"],
    )
    ids = [item.candidate_id for item in result.page_state.candidates]
    files = [Path(result.artifact_paths[item.artifact_key]) for item in result.page_state.candidates]
    first = result.page_state.candidates[0]
    lifecycle = service.select_candidate(
        lifecycle=result.lifecycle,
        page=2,
        candidate_id=first.candidate_id,
        output_dir=output_dir,
        artifact_paths=result.artifact_paths,
    )

    page = lifecycle.pages["2"]
    assert page.selected_candidate_id == first.candidate_id
    assert [item.candidate_id for item in page.candidates] == ids
    assert all(path.is_file() for path in files)
    assert {item.status for item in page.candidates} <= {"selected", "kept", "eligible"}
    assert page.prompt_runs[0].operation == "manual_upload"
    assert page.prompt_runs[0].call_count == 0


def test_one_directed_repair_prefers_edit_and_repeats_invariants(tmp_path: Path) -> None:
    fake = FakeModel(
        [
            [blank_image(), blank_image(), blank_image()],
            [candidate_image()],
        ],
        edit=True,
    )
    service = ImageCandidateService(settings(tmp_path), model_client=fake)  # type: ignore[arg-type]
    result = service.generate_candidates(
        lifecycle=service.load({}),
        page=1,
        prompt="NO TEXT. Evidence photograph on paper.",
        output_dir=tmp_path / "variant",
        artifact_paths={},
        page_visual_brief=brief(),
        invariants=["aged paper", "vermilion accent", "same crop"],
        count=3,
        auto_repair=True,
    )

    page = result.page_state
    assert page.auto_repair_count == 1
    assert len(page.candidates) == 4
    repaired = page.candidates[-1]
    assert repaired.origin == "image_edit"
    assert repaired.repair_attempt == 1
    assert repaired.parent_candidate_id
    assert repaired.review.passed is True
    assert page.selected_candidate_id == repaired.candidate_id
    assert len(fake.calls) == 2
    assert fake.calls[1]["edit"] is True
    assert fake.calls[1]["reference"] is True
    assert "aged paper" in fake.calls[1]["prompt"]
    assert "vermilion accent" in fake.calls[1]["prompt"]
    assert "same crop" in fake.calls[1]["prompt"]
    assert "CHANGE ONLY THIS" in fake.calls[1]["prompt"]
    assert page.prompt_runs[-1].primary_defect

    with pytest.raises(ImageCandidateError, match="次数已用完"):
        service.repair_once(
            lifecycle=result.lifecycle,
            page=1,
            candidate_id=repaired.candidate_id,
            output_dir=tmp_path / "variant",
            artifact_paths=result.artifact_paths,
            page_visual_brief=brief(),
            invariants=["aged paper"],
        )


def test_failed_or_rejected_candidate_cannot_enter_publish_gate(tmp_path: Path) -> None:
    service = ImageCandidateService(settings(tmp_path))
    result = service.add_manual_candidates(
        lifecycle=service.load({}),
        page=1,
        prompt="NO TEXT.",
        images=[blank_image()],
        output_dir=tmp_path / "variant",
        artifact_paths={},
        page_visual_brief=brief(),
        invariants=["paper"],
    )
    candidate = result.page_state.candidates[0]
    assert candidate.review.passed is False
    assert service.publish_allowed(result.lifecycle, total_pages=1) is False
    with pytest.raises(ImageCandidateError, match="未通过视觉审稿"):
        service.select_candidate(
            lifecycle=result.lifecycle,
            page=1,
            candidate_id=candidate.candidate_id,
        )
    with pytest.raises(ImageCandidateError, match="具体理由"):
        service.review_candidate(
            lifecycle=result.lifecycle,
            page=1,
            candidate_id=candidate.candidate_id,
            action="reject",
        )

    approved = service.review_candidate(
        lifecycle=result.lifecycle,
        page=1,
        candidate_id=candidate.candidate_id,
        action="approve",
        reason="人工核对主体和边缘后批准",
    )
    selected = service.select_candidate(
        lifecycle=approved,
        page=1,
        candidate_id=candidate.candidate_id,
    )
    assert service.publish_allowed(
        selected,
        total_pages=1,
        artifact_paths=result.artifact_paths,
    ) is True

    rejected = service.review_candidate(
        lifecycle=selected,
        page=1,
        candidate_id=candidate.candidate_id,
        action="reject",
        reason="发现角标风险",
    )
    assert rejected.pages["1"].selected_candidate_id == ""
    assert service.publish_allowed(rejected, total_pages=1) is False


def test_manual_upload_count_is_bounded(tmp_path: Path) -> None:
    service = ImageCandidateService(settings(tmp_path))
    with pytest.raises(ImageCandidateError, match="1 到 4"):
        service.add_manual_candidates(
            lifecycle=service.load({}),
            page=1,
            prompt="NO TEXT",
            images=[candidate_image()] * 5,
            output_dir=tmp_path / "variant",
            artifact_paths={},
            page_visual_brief=brief(),
            invariants=[],
        )


def test_unreviewed_candidate_artifacts_are_excluded_from_publish_zip(
    tmp_path: Path,
) -> None:
    service = MinimalZineNativeService(settings(tmp_path))
    variant = PlatformVariant(
        id="variant_candidate_gate",
        source_id="source_candidate_gate",
        platform="wechat",
        format="light_series",
        version=1,
        title="候选门禁",
        subtitle="",
        summary="未审稿候选不能进入发布包",
        body_markdown="正文",
        tags="测试",
        theme="zen",
    )
    output_dir = tmp_path / "exports" / "wechat" / variant.id
    output_dir.mkdir(parents=True)
    paths: dict[str, str] = {}
    specs: list[dict] = []
    for page in range(1, 4):
        anchor = output_dir / f"anchor-{page:02d}.png"
        poster = output_dir / f"poster-{page:02d}.png"
        candidate = output_dir / f"candidate-page-{page:02d}-pending.png"
        anchor.write_bytes(candidate_image(offset=page * 5))
        poster.write_bytes(candidate_image(offset=page * 5))
        candidate.write_bytes(candidate_image(offset=page * 5))
        paths[f"anchor_{page:02d}"] = str(anchor)
        paths[f"poster_{page:02d}"] = str(poster)
        paths[f"candidate_{page:02d}_pending"] = str(candidate)
        specs.append({"page": page, "phrase": f"第 {page} 页"})

    files = service._rebuild_artifacts(
        variant=variant,
        metadata={"image_candidate_mode": "production"},
        specs=specs,
        output_dir=output_dir,
        output_paths=paths,
        allow_package=False,
    )

    assert "package" not in files
    assert all(key in files for key in ("candidate_01_pending", "candidate_02_pending", "candidate_03_pending"))
    manifest = json.loads(Path(files["manifest"]).read_text(encoding="utf-8"))
    assert manifest["candidate_publish_gate"]["allowed"] is False
    assert not list(output_dir.glob("*.zip"))


def test_light_ui_exposes_candidate_review_cost_and_bounded_upload() -> None:
    root = Path(__file__).resolve().parents[3]
    script = (root / "apps/api/app/static/light-content-v15.js").read_text(
        encoding="utf-8"
    )
    style = (root / "apps/api/app/static/light-content-v15.css").read_text(
        encoding="utf-8"
    )
    api = (root / "apps/api/app/api/native_skills.py").read_text(encoding="utf-8")

    assert "upload.multiple = true" in script
    assert "每页请选择 1–4 张图片" in script
    assert "Contact Sheet 仅显示原始候选与编号" in script
    assert "定向修复 1 次" in script
    assert "成本未返回" in script
    assert "替换概念" in script
    assert "light-candidate-scores" in style
    assert "candidates/{page}/review" in api
    assert "candidates/{page}/select" in api
    assert "candidates/{page}/repair" in api
