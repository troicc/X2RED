from __future__ import annotations

import io
import math
import re
from typing import Any

from PIL import Image, ImageFilter, ImageOps, ImageStat

from app.domain.image_candidate_schemas import ImageCandidateReview, VisualCriticScores


class ImageCriticError(RuntimeError):
    pass


_CLICHE_TERMS = (
    "light bulb",
    "glowing brain",
    "maze",
    "puzzle piece",
    "floating geometric",
    "abstract network",
    "hand holding phone",
    "rocket launch",
    "generic silhouette",
    "箭头迷宫",
    "发光大脑",
    "拼图",
    "悬浮几何",
    "抽象网络",
)


def _clamp(value: float) -> float:
    return round(min(100.0, max(0.0, value)), 2)


class ImageCritic:
    """Deterministic local preflight for visual candidates.

    This is deliberately a conservative image preflight, not a claim that local
    heuristics understand the source facts.  Semantic credit therefore requires a
    frozen prompt plus page evidence; human review remains explicit in metadata.
    """

    version = "x2red-image-critic-v1"

    def review(
        self,
        image_bytes: bytes,
        *,
        prompt: str,
        page_visual_brief: dict[str, Any] | None = None,
        invariants: list[str] | None = None,
        series_reference_bytes: list[bytes] | None = None,
    ) -> ImageCandidateReview:
        image = self._decode(image_bytes)
        sampled = image.copy()
        sampled.thumbnail((192, 192), Image.Resampling.LANCZOS)
        rgb = sampled.convert("RGB")
        gray = rgb.convert("L")
        hsv = rgb.convert("HSV")

        gray_stats = ImageStat.Stat(gray)
        contrast = float(gray_stats.stddev[0])
        entropy = float(gray.entropy())
        edge_mean = float(ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).mean[0])
        saturation_mean = float(ImageStat.Stat(hsv).mean[1])
        high_saturation_ratio = self._high_saturation_ratio(hsv)
        near_blank_ratio = self._near_blank_ratio(gray)
        border_risk = self._border_artifact_risk(rgb)

        brief = page_visual_brief if isinstance(page_visual_brief, dict) else {}
        evidence = brief.get("evidence_refs")
        evidence_count = len([item for item in evidence if str(item).strip()]) if isinstance(evidence, list) else 0
        has_subject = bool(str(brief.get("concrete_subject") or "").strip())
        prompt_has_contract = bool(prompt.strip()) and bool(
            re.search(r"NO\s+TEXT|无字|do not render text", prompt, flags=re.IGNORECASE)
        )
        semantic_match = 48.0
        semantic_match += 18.0 if prompt.strip() else 0.0
        semantic_match += 12.0 if has_subject else 0.0
        semantic_match += min(evidence_count, 2) * 6.0
        semantic_match += 5.0 if invariants else 0.0

        subject_clarity = 32.0 + contrast * 1.15 + edge_mean * 0.42
        if near_blank_ratio > 0.96:
            subject_clarity -= 30.0
        composition = 58.0 + min(contrast, 38.0) * 0.55
        aspect = image.width / max(image.height, 1)
        if 0.52 <= aspect <= 1.9:
            composition += 10.0
        else:
            composition -= 16.0
        if near_blank_ratio < 0.25:
            composition -= 8.0
        thumbnail_hook = 28.0 + contrast * 1.25 + saturation_mean * 0.12
        texture = 18.0 + entropy * 9.2 + min(edge_mean, 25.0) * 0.35
        color_anchor = 34.0 + min(high_saturation_ratio, 0.08) * 600.0 + saturation_mean * 0.12
        series_consistency = self._series_consistency(rgb, series_reference_bytes or [])

        artifacts = 7.0 + border_risk * 75.0
        if near_blank_ratio > 0.985:
            artifacts += 35.0
        if image.width < 512 or image.height < 512:
            artifacts += 18.0
        text_safety = 91.0 if prompt_has_contract else 76.0
        text_safety -= border_risk * 28.0
        cliche_score = self._cliche_score(prompt, brief)

        scores = VisualCriticScores(
            semantic_match=_clamp(semantic_match),
            subject_clarity=_clamp(subject_clarity),
            composition=_clamp(composition),
            thumbnail_hook=_clamp(thumbnail_hook),
            series_consistency=_clamp(series_consistency),
            texture=_clamp(texture),
            color_anchor=_clamp(color_anchor),
            artifacts=_clamp(artifacts),
            text_safety=_clamp(text_safety),
            cliche_score=_clamp(cliche_score),
        )
        good_values = (
            scores.semantic_match,
            scores.subject_clarity,
            scores.composition,
            scores.thumbnail_hook,
            scores.series_consistency,
            scores.texture,
            scores.color_anchor,
            scores.text_safety,
            100.0 - scores.artifacts,
            100.0 - scores.cliche_score,
        )
        overall = _clamp(sum(good_values) / len(good_values))
        issues = self._issues(scores, overall)
        passed = not issues
        primary_defect = self._primary_defect(scores) if issues else ""
        return ImageCandidateReview(
            scores=scores,
            overall_score=overall,
            passed=passed,
            decision="automatic_pass" if passed else "automatic_fail",
            issues=issues,
            primary_defect=primary_defect,
            repair_instruction=self._repair_instruction(primary_defect),
            critic_version=self.version,
        )

    @staticmethod
    def _decode(image_bytes: bytes) -> Image.Image:
        try:
            with Image.open(io.BytesIO(image_bytes)) as opened:
                image = ImageOps.exif_transpose(opened)
                image.load()
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise ImageCriticError("候选图片无法解析") from exc
        if image.width < 240 or image.height < 240:
            raise ImageCriticError("候选图片宽高都必须至少为 240 像素")
        if image.width * image.height > 50_000_000:
            raise ImageCriticError("候选图片超过 5000 万像素")
        return image.convert("RGB")

    @staticmethod
    def _high_saturation_ratio(image: Image.Image) -> float:
        histogram = image.histogram()
        saturation = histogram[256:512]
        return sum(saturation[120:]) / max(sum(saturation), 1)

    @staticmethod
    def _near_blank_ratio(image: Image.Image) -> float:
        histogram = image.histogram()
        peak = max(histogram)
        return peak / max(sum(histogram), 1)

    @staticmethod
    def _border_artifact_risk(image: Image.Image) -> float:
        width, height = image.size
        border = max(2, min(width, height) // 16)
        strips = (
            image.crop((0, 0, width, border)),
            image.crop((0, height - border, width, height)),
            image.crop((0, 0, border, height)),
            image.crop((width - border, 0, width, height)),
        )
        values: list[float] = []
        for strip in strips:
            gray = strip.convert("L")
            # FIND_EDGES paints the crop boundary itself and made a clean flat
            # paper margin look like an artifact.  Variation inside the margin is
            # the stable signal we actually need here.
            values.append(float(ImageStat.Stat(gray).stddev[0]) / 72.0)
        return min(1.0, max(values, default=0.0))

    @staticmethod
    def _average_rgb(image: Image.Image) -> tuple[float, float, float]:
        values = ImageStat.Stat(image.resize((1, 1), Image.Resampling.BOX)).mean
        return float(values[0]), float(values[1]), float(values[2])

    def _series_consistency(self, image: Image.Image, references: list[bytes]) -> float:
        if not references:
            return 82.0
        current = self._average_rgb(image)
        distances: list[float] = []
        for raw in references[-4:]:
            try:
                reference = self._decode(raw)
            except ImageCriticError:
                continue
            ref = self._average_rgb(reference)
            distance = math.sqrt(sum((first - second) ** 2 for first, second in zip(current, ref, strict=True)))
            distances.append(distance)
        if not distances:
            return 82.0
        return _clamp(96.0 - (sum(distances) / len(distances)) * 0.22)

    @staticmethod
    def _cliche_score(prompt: str, brief: dict[str, Any]) -> float:
        haystack = " ".join(
            (
                prompt,
                str(brief.get("concrete_subject") or ""),
                str(brief.get("action_or_relation") or ""),
            )
        ).casefold()
        matches = sum(1 for term in _CLICHE_TERMS if term.casefold() in haystack)
        return min(100.0, 8.0 + matches * 32.0)

    @staticmethod
    def _issues(scores: VisualCriticScores, overall: float) -> list[str]:
        checks = (
            (scores.semantic_match < 65, "语义与冻结证据的关联不足"),
            (scores.subject_clarity < 50, "主体不够清楚"),
            (scores.composition < 55, "构图稳定性不足"),
            (scores.thumbnail_hook < 45, "缩略图识别力不足"),
            (scores.artifacts > 42, "边缘或图像伪影风险过高"),
            (scores.text_safety < 68, "无字与本地排版安全性不足"),
            (scores.cliche_score > 55, "概念过于陈词滥调"),
            (overall < 62, "综合视觉分低于发布门槛"),
        )
        return [message for failed, message in checks if failed]

    @staticmethod
    def _primary_defect(scores: VisualCriticScores) -> str:
        threshold_failures = {
            "semantic_match": scores.semantic_match if scores.semantic_match < 65 else 101.0,
            "subject_clarity": scores.subject_clarity if scores.subject_clarity < 50 else 101.0,
            "composition": scores.composition if scores.composition < 55 else 101.0,
            "thumbnail_hook": scores.thumbnail_hook if scores.thumbnail_hook < 45 else 101.0,
            "artifacts": 100.0 - scores.artifacts if scores.artifacts > 42 else 101.0,
            "text_safety": scores.text_safety if scores.text_safety < 68 else 101.0,
            "cliche_score": 100.0 - scores.cliche_score if scores.cliche_score > 55 else 101.0,
        }
        failed = {key: value for key, value in threshold_failures.items() if value <= 100}
        if failed:
            return min(failed, key=failed.get)
        goodness = {
            "semantic_match": scores.semantic_match,
            "subject_clarity": scores.subject_clarity,
            "composition": scores.composition,
            "thumbnail_hook": scores.thumbnail_hook,
            "series_consistency": scores.series_consistency,
            "texture": scores.texture,
            "color_anchor": scores.color_anchor,
            "artifacts": 100.0 - scores.artifacts,
            "text_safety": scores.text_safety,
            "cliche_score": 100.0 - scores.cliche_score,
        }
        return min(goodness, key=goodness.get)

    @staticmethod
    def _repair_instruction(primary_defect: str) -> str:
        return {
            "semantic_match": "只校正主体与冻结证据的对应关系，不改变其他构图与系列不变量。",
            "subject_clarity": "只提高单一主体的轮廓与前后景分离，不添加第二主体。",
            "composition": "只修正主体位置、视点或裁切，使构图稳定；其他内容保持不变。",
            "thumbnail_hook": "只增强缩略图下的单一识别点，不扩大文字或添加图标。",
            "series_consistency": "只校正纸张、色锚和质感以匹配整组，不改变本页主体。",
            "texture": "只恢复纸张与印刷质感，不加入新的装饰物。",
            "color_anchor": "只恢复一个受控强调色区域，不新增视觉主体。",
            "artifacts": "只清理边缘、伪影和疑似角标，保留主体、构图与质感。",
            "text_safety": "只移除图中字符、标识和水印风险，保持无字视觉锚点。",
            "cliche_score": "只把陈词滥调物件替换为证据中的具体物件，其他不变量保持。",
        }.get(primary_defect, "只修复当前主要缺陷，其他主体、构图、色锚和质感保持不变。")
