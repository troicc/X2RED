from __future__ import annotations

import hashlib
import io
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from PIL import Image, ImageOps
from pydantic import ValidationError

from app.core.config import Settings
from app.domain.image_candidate_schemas import (
    CandidateAuditEvent,
    CandidatePageState,
    ImageCandidate,
    ImageCandidateLifecycle,
    ImagePromptRun,
    ProviderCapabilities,
    utc_timestamp,
)
from app.services.contact_sheet import ContactSheetError, ContactSheetRenderer
from app.services.image_critic import ImageCritic, ImageCriticError
from app.services.model_client import (
    GeneratedImage,
    ImageGenerationResult,
    ModelClient,
    ModelClientError,
)


class ImageCandidateError(RuntimeError):
    pass


ReviewAction = Literal["keep", "reject", "approve"]


@dataclass(frozen=True)
class CandidateBatchResult:
    lifecycle: ImageCandidateLifecycle
    page_state: CandidatePageState
    artifact_paths: dict[str, str]
    selected_candidate: ImageCandidate | None
    created_candidate_ids: tuple[str, ...] = ()


class ImageCandidateService:
    schema_version = "image-candidates-v1"

    def __init__(
        self,
        settings: Settings,
        *,
        model_client: ModelClient | None = None,
        critic: ImageCritic | None = None,
        contact_sheet: ContactSheetRenderer | None = None,
    ) -> None:
        self.settings = settings
        self.model = model_client or ModelClient(settings)
        self.critic = critic or ImageCritic()
        self.contact_sheet = contact_sheet or ContactSheetRenderer()

    @staticmethod
    def load(value: Any) -> ImageCandidateLifecycle:
        if not isinstance(value, dict) or not value:
            return ImageCandidateLifecycle()
        try:
            return ImageCandidateLifecycle.model_validate(value)
        except ValidationError as exc:
            raise ImageCandidateError("图片候选生命周期记录损坏，已拒绝静默覆盖") from exc

    def generate_candidates(
        self,
        *,
        lifecycle: ImageCandidateLifecycle,
        page: int,
        prompt: str,
        output_dir: Path,
        artifact_paths: dict[str, str],
        page_visual_brief: dict[str, Any] | None,
        invariants: list[str],
        count: int = 3,
        series_reference_bytes: list[bytes] | None = None,
        auto_repair: bool = True,
    ) -> CandidateBatchResult:
        try:
            generated = self.model.generate_images(prompt=prompt, count=count)
        except ModelClientError as exc:
            raise ImageCandidateError(str(exc)) from exc
        result = self._record_batch(
            lifecycle=lifecycle,
            page=page,
            prompt=prompt,
            output_dir=output_dir,
            artifact_paths=artifact_paths,
            page_visual_brief=page_visual_brief,
            invariants=invariants,
            generated=generated,
            operation="generation",
            origin="api_generation",
            parent_candidate_id="",
            repair_attempt=0,
            series_reference_bytes=series_reference_bytes or [],
        )
        created = [
            item
            for item in result.page_state.candidates
            if item.candidate_id in result.created_candidate_ids
        ]
        if any(item.review.passed for item in created) or not auto_repair:
            return result
        failing = (
            max(created, key=lambda item: item.review.overall_score)
            if created
            else None
        )
        if failing is None:
            return result
        try:
            return self.repair_once(
                lifecycle=result.lifecycle,
                page=page,
                candidate_id=failing.candidate_id,
                output_dir=output_dir,
                artifact_paths=result.artifact_paths,
                page_visual_brief=page_visual_brief,
                invariants=invariants,
                series_reference_bytes=series_reference_bytes or [],
            )
        except ImageCandidateError as exc:
            current = self._page(result.lifecycle, page)
            current.auto_repair_count = 1
            result.lifecycle.audit_events.append(
                CandidateAuditEvent(
                    event="repair_exhausted",
                    page=page,
                    candidate_id=failing.candidate_id,
                    detail=str(exc),
                )
            )
            return self._result(result.lifecycle, page, result.artifact_paths)

    def add_manual_candidates(
        self,
        *,
        lifecycle: ImageCandidateLifecycle,
        page: int,
        prompt: str,
        images: list[bytes],
        output_dir: Path,
        artifact_paths: dict[str, str],
        page_visual_brief: dict[str, Any] | None,
        invariants: list[str],
        provider: str = "chatgpt-web",
        model: str = "manual-web-image",
        series_reference_bytes: list[bytes] | None = None,
    ) -> CandidateBatchResult:
        if not 1 <= len(images) <= 4:
            raise ImageCandidateError("手工网页路径每页必须上传 1 到 4 张图片")
        capabilities = ProviderCapabilities(
            provider=provider,
            model=model,
            candidate_count=True,
            max_candidate_count=4,
            image_reference=True,
            image_edit=False,
            multi_turn=True,
            usage=False,
            detection_mode="known-provider",
        )
        generated = ImageGenerationResult(
            images=[
                GeneratedImage(image_bytes=value, latency_ms=0, cost_usd=0.0)
                for value in images
            ],
            capabilities=capabilities,
            request_strategy="manual-upload",
            call_count=0,
            usage={},
            cost_usd=0.0,
            latency_ms=0,
            requested_count=len(images),
        )
        return self._record_batch(
            lifecycle=lifecycle,
            page=page,
            prompt=prompt,
            output_dir=output_dir,
            artifact_paths=artifact_paths,
            page_visual_brief=page_visual_brief,
            invariants=invariants,
            generated=generated,
            operation="manual_upload",
            origin="manual_upload",
            parent_candidate_id="",
            repair_attempt=0,
            series_reference_bytes=series_reference_bytes or [],
        )

    def repair_once(
        self,
        *,
        lifecycle: ImageCandidateLifecycle,
        page: int,
        candidate_id: str,
        output_dir: Path,
        artifact_paths: dict[str, str],
        page_visual_brief: dict[str, Any] | None,
        invariants: list[str],
        series_reference_bytes: list[bytes] | None = None,
    ) -> CandidateBatchResult:
        page_state = self._page(lifecycle, page)
        if page_state.auto_repair_count >= 1:
            raise ImageCandidateError("本页自动修复次数已用完；请人工选择、替换概念或重新生成")
        candidate = self._candidate(page_state, candidate_id)
        if candidate.status == "rejected" or candidate.review.decision == "human_rejected":
            raise ImageCandidateError("已人工驳回的候选不能自动修复")
        primary_defect = candidate.review.primary_defect or "subject_clarity"
        instruction = candidate.review.repair_instruction or "只修复当前主要缺陷。"
        invariant_lines = [str(value).strip() for value in invariants if str(value).strip()]
        repair_prompt = self._repair_prompt(
            original_prompt=self._prompt_for_candidate(page_state, candidate),
            primary_defect=primary_defect,
            instruction=instruction,
            invariants=invariant_lines,
        )
        lifecycle.audit_events.append(
            CandidateAuditEvent(
                event="repair_started",
                page=page,
                candidate_id=candidate_id,
                detail=f"只修复 {primary_defect}",
            )
        )
        page_state.auto_repair_count = 1
        capabilities = self.model.image_capabilities()
        reference = self._candidate_bytes(candidate, artifact_paths)
        use_edit = capabilities.image_edit
        try:
            generated = self.model.generate_images(
                prompt=repair_prompt,
                count=1,
                reference_image=reference if use_edit else None,
                edit=use_edit,
            )
        except ModelClientError as exc:
            lifecycle.audit_events.append(
                CandidateAuditEvent(
                    event="repair_exhausted",
                    page=page,
                    candidate_id=candidate_id,
                    detail=str(exc),
                )
            )
            raise ImageCandidateError(str(exc)) from exc
        result = self._record_batch(
            lifecycle=lifecycle,
            page=page,
            prompt=repair_prompt,
            output_dir=output_dir,
            artifact_paths=artifact_paths,
            page_visual_brief=page_visual_brief,
            invariants=invariant_lines,
            generated=generated,
            operation="image_edit" if use_edit else "directed_regeneration",
            origin="image_edit" if use_edit else "directed_regeneration",
            parent_candidate_id=candidate_id,
            repair_attempt=1,
            primary_defect=primary_defect,
            series_reference_bytes=series_reference_bytes or [],
        )
        repaired = result.page_state.candidates[-1]
        if not repaired.review.passed:
            repaired.status = "repair_failed"
            result.lifecycle.audit_events.append(
                CandidateAuditEvent(
                    event="repair_exhausted",
                    page=page,
                    candidate_id=repaired.candidate_id,
                    detail="定向修复仍未通过，已转人工处理",
                )
            )
        else:
            result.lifecycle.audit_events.append(
                CandidateAuditEvent(
                    event="repair_completed",
                    page=page,
                    candidate_id=repaired.candidate_id,
                    detail=f"已通过 {primary_defect} 单缺陷修复",
                )
            )
        return self._result(
            result.lifecycle,
            page,
            result.artifact_paths,
            created_candidate_ids=result.created_candidate_ids,
        )

    def review_candidate(
        self,
        *,
        lifecycle: ImageCandidateLifecycle,
        page: int,
        candidate_id: str,
        action: ReviewAction,
        reason: str = "",
    ) -> ImageCandidateLifecycle:
        page_state = self._page(lifecycle, page)
        candidate = self._candidate(page_state, candidate_id)
        note = reason.strip()[:600]
        if action == "reject":
            if not note:
                raise ImageCandidateError("驳回候选必须填写具体理由")
            candidate.status = "rejected"
            candidate.rejection_reason = note
            candidate.review = candidate.review.model_copy(
                update={
                    "passed": False,
                    "decision": "human_rejected",
                    "reviewer_note": note,
                    "reviewed_at": utc_timestamp(),
                }
            )
            if page_state.selected_candidate_id == candidate_id:
                page_state.selected_candidate_id = ""
            event = "candidate_rejected"
        elif action == "approve":
            candidate.status = "eligible"
            candidate.rejection_reason = ""
            candidate.review = candidate.review.model_copy(
                update={
                    "passed": True,
                    "decision": "human_approved",
                    "reviewer_note": note,
                    "reviewed_at": utc_timestamp(),
                }
            )
            event = "candidate_approved"
        else:
            if candidate.status == "rejected" or candidate.review.decision == "human_rejected":
                raise ImageCandidateError("已驳回候选不能标记保留；如需恢复请执行人工批准")
            if candidate.status != "selected":
                candidate.status = "kept"
            event = "candidate_kept"
        lifecycle.audit_events.append(
            CandidateAuditEvent(
                event=event,
                page=page,
                candidate_id=candidate_id,
                detail=note,
            )
        )
        lifecycle.updated_at = utc_timestamp()
        return self._validate(lifecycle)

    def select_candidate(
        self,
        *,
        lifecycle: ImageCandidateLifecycle,
        page: int,
        candidate_id: str,
        output_dir: Path | None = None,
        artifact_paths: dict[str, str] | None = None,
    ) -> ImageCandidateLifecycle:
        page_state = self._page(lifecycle, page)
        candidate = self._candidate(page_state, candidate_id)
        if not candidate.review.passed or candidate.status == "rejected":
            raise ImageCandidateError("未通过视觉审稿的候选不能进入最终图或发布包")
        for item in page_state.candidates:
            if item.candidate_id == page_state.selected_candidate_id and item.status == "selected":
                item.status = "kept"
        candidate.status = "selected"
        page_state.selected_candidate_id = candidate_id
        lifecycle.audit_events.append(
            CandidateAuditEvent(
                event="candidate_selected",
                page=page,
                candidate_id=candidate_id,
                detail=f"候选 #{candidate.candidate_index}",
            )
        )
        lifecycle.updated_at = utc_timestamp()
        if output_dir is not None and artifact_paths is not None:
            self._render_contact_sheet(page_state, output_dir, artifact_paths)
        return self._validate(lifecycle)

    def selected_candidate(
        self,
        lifecycle: ImageCandidateLifecycle,
        page: int,
    ) -> ImageCandidate | None:
        page_state = lifecycle.pages.get(str(page))
        if page_state is None or not page_state.selected_candidate_id:
            return None
        try:
            return self._candidate(page_state, page_state.selected_candidate_id)
        except ImageCandidateError:
            return None

    def selected_bytes(
        self,
        lifecycle: ImageCandidateLifecycle,
        page: int,
        artifact_paths: dict[str, str],
    ) -> bytes:
        selected = self.selected_candidate(lifecycle, page)
        if selected is None or not selected.review.passed:
            raise ImageCandidateError("本页没有已通过审稿并选中的候选")
        return self._candidate_bytes(selected, artifact_paths)

    def publish_allowed(
        self,
        lifecycle: ImageCandidateLifecycle,
        *,
        total_pages: int,
        artifact_paths: dict[str, str] | None = None,
    ) -> bool:
        for page in range(1, total_pages + 1):
            selected = self.selected_candidate(lifecycle, page)
            if (
                selected is None
                or not selected.review.passed
                or selected.status != "selected"
            ):
                return False
            if artifact_paths is not None:
                value = artifact_paths.get(selected.artifact_key)
                if not value or not Path(value).is_file():
                    return False
        return True

    def _record_batch(
        self,
        *,
        lifecycle: ImageCandidateLifecycle,
        page: int,
        prompt: str,
        output_dir: Path,
        artifact_paths: dict[str, str],
        page_visual_brief: dict[str, Any] | None,
        invariants: list[str],
        generated: ImageGenerationResult,
        operation: str,
        origin: str,
        parent_candidate_id: str,
        repair_attempt: int,
        series_reference_bytes: list[bytes],
        primary_defect: str = "",
    ) -> CandidateBatchResult:
        page_state = self._page(lifecycle, page)
        run_token = uuid.uuid4().hex[:24]
        run_id = f"imgrun_{run_token}"
        images = generated.images
        if not 1 <= len(images) <= 4:
            raise ImageCandidateError("每次候选批次必须包含 1 到 4 张图片")
        run = ImagePromptRun(
            prompt_run_id=run_id,
            page=page,
            operation=operation,
            prompt=prompt,
            prompt_hash=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            provider=generated.capabilities.provider,
            model=generated.capabilities.model,
            requested_count=generated.requested_count,
            actual_count=len(images),
            request_strategy=generated.request_strategy,
            call_count=generated.call_count,
            capabilities=generated.capabilities,
            reference_candidate_id=parent_candidate_id,
            invariants=invariants,
            primary_defect=primary_defect,
            usage=generated.usage,
            cost_usd=generated.cost_usd,
            latency_ms=generated.latency_ms,
        )
        page_state.prompt_runs.append(run)
        next_index = max((item.candidate_index for item in page_state.candidates), default=0) + 1
        created: list[ImageCandidate] = []
        fallback_candidate_cost = (
            generated.cost_usd / len(images) if generated.cost_usd is not None else None
        )
        for offset, generated_image in enumerate(images):
            token = uuid.uuid4().hex[:24]
            candidate_id = f"imgcand_{token}"
            artifact_key = f"candidate_{page:02d}_{token}"
            normalized, width, height = self._normalize(generated_image.image_bytes)
            target = output_dir / f"candidate-page-{page:02d}-{token}.png"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(normalized)
            artifact_paths[artifact_key] = str(target.resolve())
            try:
                review = self.critic.review(
                    normalized,
                    prompt=prompt,
                    page_visual_brief=page_visual_brief,
                    invariants=invariants,
                    series_reference_bytes=series_reference_bytes,
                )
            except ImageCriticError as exc:
                raise ImageCandidateError(str(exc)) from exc
            candidate = ImageCandidate(
                candidate_id=candidate_id,
                page=page,
                candidate_index=next_index + offset,
                prompt_run_id=run_id,
                origin=origin,
                parent_candidate_id=parent_candidate_id,
                provider=generated.capabilities.provider,
                model=generated.capabilities.model,
                artifact_key=artifact_key,
                image_hash=hashlib.sha256(normalized).hexdigest(),
                width=width,
                height=height,
                cost_usd=(
                    round(generated_image.cost_usd, 8)
                    if generated_image.cost_usd is not None
                    else round(fallback_candidate_cost, 8)
                    if fallback_candidate_cost is not None
                    else None
                ),
                latency_ms=generated_image.latency_ms,
                status="eligible" if review.passed else "pending_review",
                review=review,
                repair_attempt=repair_attempt,
            )
            page_state.candidates.append(candidate)
            created.append(candidate)
        page_state.generation_count += 1
        lifecycle.total_api_calls += generated.call_count
        if generated.cost_usd is not None:
            lifecycle.total_cost_usd = round(
                (lifecycle.total_cost_usd or 0.0) + generated.cost_usd,
                8,
            )
        lifecycle.audit_events.append(
            CandidateAuditEvent(
                event="candidates_added",
                page=page,
                candidate_id=created[0].candidate_id,
                detail=f"新增 {len(created)} 张；策略 {generated.request_strategy}",
            )
        )
        passing = [item for item in created if item.review.passed]
        if passing:
            best = max(passing, key=lambda item: item.review.overall_score)
            self.select_candidate(
                lifecycle=lifecycle,
                page=page,
                candidate_id=best.candidate_id,
            )
        self._render_contact_sheet(page_state, output_dir, artifact_paths)
        lifecycle.updated_at = utc_timestamp()
        return self._result(
            lifecycle,
            page,
            artifact_paths,
            created_candidate_ids=tuple(item.candidate_id for item in created),
        )

    def _render_contact_sheet(
        self,
        page_state: CandidatePageState,
        output_dir: Path,
        artifact_paths: dict[str, str],
    ) -> None:
        candidates = page_state.candidates[-4:]
        numbered: list[tuple[int, bytes]] = []
        for item in candidates:
            numbered.append((item.candidate_index, self._candidate_bytes(item, artifact_paths)))
        if not numbered:
            return
        key = f"contact_sheet_{page_state.page:02d}"
        target = output_dir / f"contact-sheet-page-{page_state.page:02d}.png"
        selected = self.selected_candidate_id_index(page_state)
        try:
            self.contact_sheet.render(numbered, target, selected_index=selected)
        except ContactSheetError as exc:
            raise ImageCandidateError(str(exc)) from exc
        artifact_paths[key] = str(target.resolve())
        page_state.contact_sheet_key = key

    @staticmethod
    def selected_candidate_id_index(page_state: CandidatePageState) -> int | None:
        for item in page_state.candidates:
            if item.candidate_id == page_state.selected_candidate_id:
                return item.candidate_index
        return None

    @staticmethod
    def _normalize(image_bytes: bytes) -> tuple[bytes, int, int]:
        try:
            with Image.open(io.BytesIO(image_bytes)) as opened:
                image = ImageOps.exif_transpose(opened)
                image.load()
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise ImageCandidateError("只能使用可读取的 PNG、JPEG 或 WebP 图片") from exc
        if image.width < 240 or image.height < 240:
            raise ImageCandidateError("候选图片宽高都至少需要 240 像素")
        if image.width * image.height > 50_000_000:
            raise ImageCandidateError("候选图片像素过大，请先缩小到 5000 万像素以内")
        if max(image.size) > 2560:
            image.thumbnail((2560, 2560), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.convert("RGB").save(output, format="PNG", optimize=True)
        return output.getvalue(), image.width, image.height

    @staticmethod
    def _candidate_bytes(
        candidate: ImageCandidate,
        artifact_paths: dict[str, str],
    ) -> bytes:
        value = artifact_paths.get(candidate.artifact_key)
        path = Path(value).resolve() if value else None
        if path is None or not path.is_file():
            raise ImageCandidateError("候选图片文件不存在")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != candidate.image_hash:
            raise ImageCandidateError("候选图片哈希与冻结记录不一致")
        return content

    @staticmethod
    def _repair_prompt(
        *,
        original_prompt: str,
        primary_defect: str,
        instruction: str,
        invariants: list[str],
    ) -> str:
        repeated = "\n".join(f"- {item}" for item in invariants) or "- keep the frozen page brief unchanged"
        return (
            f"{original_prompt.rstrip()}\n\n"
            "DIRECTED REPAIR — ONE ATTEMPT ONLY\n"
            f"PRIMARY DEFECT: {primary_defect}\n"
            f"CHANGE ONLY THIS: {instruction}\n"
            "REPEAT AND PRESERVE EVERY INVARIANT:\n"
            f"{repeated}\n"
            "Keep the same concrete subject, evidence scope, viewpoint, crop, paper, palette, and texture "
            "unless the one repair instruction explicitly names that field. NO TEXT, NO LETTERS, NO LOGOS, NO WATERMARKS."
        )

    @staticmethod
    def _prompt_for_candidate(
        page_state: CandidatePageState,
        candidate: ImageCandidate,
    ) -> str:
        for run in page_state.prompt_runs:
            if run.prompt_run_id == candidate.prompt_run_id:
                return run.prompt
        raise ImageCandidateError("候选缺少可追溯 Prompt run")

    @staticmethod
    def _candidate(page_state: CandidatePageState, candidate_id: str) -> ImageCandidate:
        for candidate in page_state.candidates:
            if candidate.candidate_id == candidate_id:
                return candidate
        raise ImageCandidateError("候选不存在或不属于当前页")

    @staticmethod
    def _best_candidate(
        page_state: CandidatePageState,
        *,
        include_failed: bool,
    ) -> ImageCandidate | None:
        candidates = [
            item
            for item in page_state.candidates
            if item.status != "rejected" and (include_failed or item.review.passed)
        ]
        return max(candidates, key=lambda item: item.review.overall_score) if candidates else None

    @staticmethod
    def _page(
        lifecycle: ImageCandidateLifecycle,
        page: int,
    ) -> CandidatePageState:
        if not 1 <= page <= 6:
            raise ImageCandidateError("页码必须是 1 到 6")
        key = str(page)
        if key not in lifecycle.pages:
            lifecycle.pages[key] = CandidatePageState(page=page)
        return lifecycle.pages[key]

    def _result(
        self,
        lifecycle: ImageCandidateLifecycle,
        page: int,
        artifact_paths: dict[str, str],
        *,
        created_candidate_ids: tuple[str, ...] = (),
    ) -> CandidateBatchResult:
        validated = self._validate(lifecycle)
        return CandidateBatchResult(
            lifecycle=validated,
            page_state=validated.pages[str(page)],
            artifact_paths=dict(artifact_paths),
            selected_candidate=self.selected_candidate(validated, page),
            created_candidate_ids=created_candidate_ids,
        )

    @staticmethod
    def _validate(lifecycle: ImageCandidateLifecycle) -> ImageCandidateLifecycle:
        lifecycle.updated_at = utc_timestamp()
        try:
            return ImageCandidateLifecycle.model_validate(
                json.loads(lifecycle.model_dump_json())
            )
        except ValidationError as exc:
            raise ImageCandidateError("图片候选生命周期没有通过 schema 校验") from exc
