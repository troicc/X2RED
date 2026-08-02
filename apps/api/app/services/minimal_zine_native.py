from __future__ import annotations

import base64
import html
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.platforms import PlatformVariant, PlatformVariantState
from app.services.light_visual_renderer import LightVisualRenderer
from app.services.model_client import ModelClient, ModelClientError
from app.services.native_skill_manager import NativeSkillError, NativeSkillManager


class MinimalZineNativeService:
    skill_name = "gc-minimal-zine-poster-v0-1"
    compositor_version = "minimal-zine-local-type-v2"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.manager = NativeSkillManager(settings)
        self.model = ModelClient(settings)
        self.local_renderer = LightVisualRenderer()

    @property
    def image_configured(self) -> bool:
        return bool(
            (self.settings.image_base_url or self.settings.model_base_url)
            and (self.settings.image_api_key or self.settings.model_api_key)
            and self.settings.image_model
        )

    def render_variant(
        self,
        db: Session,
        variant: PlatformVariant,
        *,
        regenerate: bool = False,
    ) -> tuple[PlatformVariant, list[dict[str, Any]]]:
        if variant.platform != "wechat" or variant.format != "light_series":
            raise NativeSkillError("Minimal Zine 原生生图只支持公众号轻内容图组")
        if not self.image_configured:
            raise NativeSkillError(
                "尚未配置图片模型。请设置 X2RED_IMAGE_MODEL，以及图片接口的 BASE_URL/API_KEY；"
                "智谱兼容接口可填写 glm-image。"
            )
        metadata = self._object(variant.metadata_json)
        raw_specs = metadata.get("poster_specs")
        specs = (
            [dict(item) for item in raw_specs if isinstance(item, dict)]
            if isinstance(raw_specs, list)
            else []
        )
        if not specs:
            raise NativeSkillError("当前轻内容版本没有可生图的页面规格")

        skill_dir = self.manager.ensure_installed(self.skill_name, install_runtime=False)
        skill_text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        output_dir = self.settings.export_dir / "wechat" / variant.id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_paths = self._object(variant.output_paths_json)
        previous_native = metadata.get("native_zine")
        previous_version = (
            str(previous_native.get("compositor_version") or "")
            if isinstance(previous_native, dict)
            else ""
        )
        results: list[dict[str, Any]] = []
        recent_recipes: list[str] = []

        for index, spec in enumerate(specs, start=1):
            key = f"poster_{index:02d}"
            path = output_dir / f"poster-{index:02d}.png"
            old_path = Path(str(output_paths.get(key) or ""))
            cache_valid = (
                path.is_file()
                and not regenerate
                and previous_version == self.compositor_version
            )
            if cache_valid:
                result = {
                    "page": index,
                    "path": str(path.resolve()),
                    "cached": True,
                    "recomposed": False,
                    "final_prompt": str(spec.get("final_prompt") or ""),
                    "recipe": spec.get("native_zine_recipe") or {},
                    "interpretation": str(
                        spec.get("native_zine_interpretation") or ""
                    ),
                }
            else:
                compiled = self._compile_prompt(
                    skill_text=skill_text,
                    variant=variant,
                    spec=spec,
                    page=index,
                    total=len(specs),
                    recent_recipes=recent_recipes,
                )
                reused_existing = bool(
                    old_path.is_file()
                    and not regenerate
                    and previous_version != self.compositor_version
                )
                image_bytes = (
                    old_path.read_bytes()
                    if reused_existing
                    else self._generate_image(str(compiled["final_prompt"]))
                )
                recipe = (
                    compiled.get("recipe")
                    if isinstance(compiled.get("recipe"), dict)
                    else {}
                )
                self._compose_poster(
                    image_bytes,
                    path,
                    spec=spec,
                    recipe=recipe,
                    page=index,
                    total=len(specs),
                )
                recent_recipes.append(
                    json.dumps(recipe, ensure_ascii=False, sort_keys=True)
                )
                spec["final_prompt"] = str(compiled["final_prompt"])
                spec["native_zine_recipe"] = recipe
                spec["native_zine_interpretation"] = str(
                    compiled.get("interpretation") or ""
                )
                spec["visual_style"] = "minimal_zine_native"
                spec["text_rendering"] = "x2red-local-cjk"
                spec["model_text_forbidden"] = True
                result = {
                    "page": index,
                    "path": str(path.resolve()),
                    "cached": False,
                    "recomposed": reused_existing,
                    "final_prompt": spec["final_prompt"],
                    "recipe": recipe,
                    "interpretation": spec["native_zine_interpretation"],
                }
            output_paths[key] = str(path.resolve())
            results.append(result)

        metadata["poster_specs"] = specs
        metadata["render_engine"] = "gc-minimal-zine-local-compositor-v2"
        metadata["native_zine"] = {
            "repository": "https://github.com/LiamGvchi/gc-minimal-zine-poster",
            "commit": self.manager.definition(self.skill_name).commit,
            "license": "MIT",
            "image_model": self.settings.image_model,
            "image_size_requested": self.settings.image_size,
            "generated_pages": len(results),
            "compositor_version": self.compositor_version,
            "model_role": "visual-anchor-only",
            "local_typography": True,
            "watermark_policy": "model-edge-crop-plus-local-final-canvas",
        }
        output_paths = self._rebuild_artifacts(
            variant=variant,
            metadata=metadata,
            specs=specs,
            output_dir=output_dir,
            output_paths=output_paths,
        )
        variant.metadata_json = json.dumps(metadata, ensure_ascii=False)
        variant.output_paths_json = json.dumps(output_paths, ensure_ascii=False)
        variant.status = PlatformVariantState.packaged.value
        variant.error = ""
        db.flush()
        return variant, results

    def _compile_prompt(
        self,
        *,
        skill_text: str,
        variant: PlatformVariant,
        spec: dict[str, Any],
        page: int,
        total: int,
        recent_recipes: list[str],
    ) -> dict[str, Any]:
        phrase = self._clean(str(spec.get("phrase") or variant.title), 80)
        metaphor = self._clean(str(spec.get("visual_metaphor") or ""), 240)
        mood = self._clean(str(spec.get("mood") or "quiet"), 80)
        prompt = f"""
按照下面上游 Skill 的视觉判断，为一张 Minimal Zine 页面编译“无字视觉锚点”生图 Prompt。
不要解释规则，不要输出 Markdown。

上游 SKILL.md：
{skill_text[:30000]}

本页语义：
- 页码：{page}/{total}
- 中文短句仅用于理解含义，不得画进图片：{phrase}
- 内容隐喻：{metaphor or '从短句中提炼一个单一可成像物件'}
- 情绪：{mood}
- 整组主题：{self._clean(variant.title, 120)}
- 最近页面配方：{json.dumps(recent_recipes[-3:], ensure_ascii=False)}

严格执行：
1. 从 layout / anchor / typography / accent / texture / mood 六轴选择配方，但模型只负责视觉物件和纸张纹理，中文由 X2RED 本地排版。
2. 画面为竖版 3:5，大面积旧纸留白，一个清晰视觉簇，避免全幅复杂场景。
3. 只允许一个高饱和强调色，其余以黑、灰、米白为主。
4. 图片中禁止出现任何中文、英文、数字、字母、标题、说明文字、签名、印章文字、品牌、Logo、水印、角标、按钮、胶囊标签、UI 或“AI生成”标识。
5. 禁止商业广告、3D 渲染、霓虹、可爱卡通、密集拼贴、通用图库海报和廉价心灵鸡汤视觉。
6. 视觉主体放在画面上方或中部，底部至少 28% 保持纯净留白，便于本地中文排版。

只输出 JSON：
{{
  "final_prompt":"最终英文生图 Prompt，必须明确 NO TEXT / NO LETTERS / NO LOGO / NO WATERMARK / NO BADGE / NO UI",
  "recipe":{{"layout":"","anchor":"","typography":"local-cjk","accent":"","texture":"","mood":""}},
  "interpretation":"一句说明如何把内容变成单一视觉隐喻"
}}
""".strip()
        result = self.model.chat_json(
            system_prompt=(
                "你执行 gc-minimal-zine-poster-v0-1 的视觉配方编译。"
                "最终图片绝不生成文字；所有中文由本地排版器完成。"
            ),
            user_prompt=prompt,
            temperature=0.36,
            reasoning_effort="high",
            max_tokens=5000,
        )
        final_prompt = str(result.get("final_prompt") or "").strip()
        if len(final_prompt) < 180:
            raise ModelClientError("Minimal Zine 视觉 Prompt 编译结果过短")
        constraints = (
            " Tall vertical 3:5 editorial art plate. Large quiet negative space. "
            "NO TEXT, NO CHINESE CHARACTERS, NO LATIN LETTERS, NO NUMBERS, "
            "NO LOGO, NO WATERMARK, NO SIGNATURE, NO BADGE, NO UI, NO LABEL. "
            "Keep the bottom 30 percent blank aged paper."
        )
        result["final_prompt"] = final_prompt + constraints
        return result

    def _compose_poster(
        self,
        image_bytes: bytes,
        path: Path,
        *,
        spec: dict[str, Any],
        recipe: dict[str, Any],
        page: int,
        total: int,
    ) -> None:
        try:
            with Image.open(io.BytesIO(image_bytes)) as source:
                source = ImageOps.exif_transpose(source).convert("RGB")
                width, height = source.size
                # Drop the model's outer and lower-right regions. Provider marks and
                # accidental generated typography overwhelmingly occur there.
                crop = source.crop(
                    (
                        int(width * 0.06),
                        int(height * 0.04),
                        int(width * 0.90),
                        int(height * 0.70),
                    )
                )
                crop = ImageEnhance.Color(crop).enhance(0.10)
                crop = ImageEnhance.Contrast(crop).enhance(1.18)
                crop = ImageOps.colorize(
                    crop.convert("L"),
                    black="#161616",
                    white="#d8d1c4",
                )
        except (OSError, ValueError) as exc:
            raise NativeSkillError("图片模型返回的文件无法解析") from exc

        canvas = self.local_renderer._paper("#e8ddc8", noise=16, blend=0.07)
        draw = ImageDraw.Draw(canvas)
        layout = str(recipe.get("layout") or "").lower()
        if "right" in layout or page % 3 == 2:
            box = (430, 220, 1110, 1020)
            text_box = (90, 1060, 1080)
        elif "left" in layout or page % 3 == 0:
            box = (90, 300, 790, 1110)
            text_box = (700, 430, 430)
        else:
            box = (120, 240, 1080, 1120)
            text_box = (120, 1260, 960)

        target_size = (box[2] - box[0], box[3] - box[1])
        visual = ImageOps.fit(
            crop,
            target_size,
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.46),
        )
        mask = Image.new("L", target_size, 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle(
            (8, 8, target_size[0] - 8, target_size[1] - 8),
            radius=12,
            fill=245,
        )
        mask = mask.filter(ImageFilter.GaussianBlur(2.2))
        canvas.paste(visual, (box[0], box[1]), mask)
        draw.rectangle(box, outline="#35322d", width=3)

        accent = self._accent(str(spec.get("accent") or recipe.get("accent") or ""))
        if page % 2:
            radius = 108
            cx = min(box[2] - 70, box[0] + int(target_size[0] * 0.64))
            cy = min(box[3] - 60, box[1] + int(target_size[1] * 0.68))
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=accent)
        else:
            draw.rectangle((box[0] - 12, box[1] + 70, box[0] + 30, box[3] - 70), fill=accent)

        phrase = self._clean(str(spec.get("phrase") or ""), 70)
        note = self._clean(str(spec.get("note") or ""), 130)
        text_x, text_y, text_width = text_box
        title_size = 62 if len(phrase) <= 18 else 52
        title_font = self.local_renderer._font(title_size, bold=True, serif=False)
        note_font = self.local_renderer._font(27, serif=True)
        lines = self.local_renderer._wrap(draw, phrase, title_font, text_width)[:4]
        line_height = int(title_size * 1.42)
        for offset, line in enumerate(lines):
            draw.text(
                (text_x, text_y + offset * line_height),
                line,
                font=title_font,
                fill="#171614",
            )
        note_y = text_y + len(lines) * line_height + 34
        if note:
            for offset, line in enumerate(
                self.local_renderer._wrap(draw, note, note_font, text_width)[:3]
            ):
                draw.text(
                    (text_x, note_y + offset * 42),
                    line,
                    font=note_font,
                    fill="#625d54",
                )
        draw.line((90, 1870, 1110, 1870), fill="#575047", width=2)
        footer_font = self.local_renderer._font(20, serif=True)
        draw.text((90, 1900), "X2RED · MINIMAL ZINE", font=footer_font, fill="#575047")
        page_text = f"{page:02d} / {total:02d}"
        page_width = draw.textlength(page_text, font=footer_font)
        draw.text((1110 - page_width, 1900), page_text, font=footer_font, fill="#575047")
        canvas.save(path, "PNG", optimize=True)

    def _rebuild_artifacts(
        self,
        *,
        variant: PlatformVariant,
        metadata: dict[str, Any],
        specs: list[dict[str, Any]],
        output_dir: Path,
        output_paths: dict[str, Any],
    ) -> dict[str, str]:
        files = {
            key: str(Path(str(value)).resolve())
            for key, value in output_paths.items()
            if key.startswith("poster_") and Path(str(value)).is_file()
        }
        article = output_dir / "article.md"
        article.write_text(variant.body_markdown, encoding="utf-8")
        files["markdown"] = str(article.resolve())

        manifest = output_dir / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "variant_id": variant.id,
                    "platform": variant.platform,
                    "format": variant.format,
                    "title": variant.title,
                    "summary": variant.summary,
                    "render_engine": metadata.get("render_engine"),
                    "native_zine": metadata.get("native_zine"),
                    "posters": [
                        Path(value).name
                        for key, value in sorted(files.items())
                        if key.startswith("poster_")
                    ],
                    "poster_specs": specs,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        files["manifest"] = str(manifest.resolve())

        preview = output_dir / "preview.html"
        cards = []
        for index, spec in enumerate(specs, start=1):
            key = f"poster_{index:02d}"
            if key not in files:
                continue
            cards.append(
                "<figure><img src='{}' alt='{}'><figcaption>{}</figcaption></figure>".format(
                    html.escape(Path(files[key]).name),
                    html.escape(str(spec.get("phrase") or f"第 {index} 页")),
                    html.escape(str(spec.get("phrase") or f"第 {index} 页")),
                )
            )
        preview.write_text(
            """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{title}</title><style>
body{{margin:0;background:#181818;color:#eee;font-family:system-ui,-apple-system,sans-serif}}
main{{max-width:1120px;margin:auto;padding:32px}}h1{{font-size:24px}}p{{color:#aaa}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:20px}}
figure{{margin:0;background:#242424;padding:10px;border-radius:14px}}img{{display:block;width:100%;border-radius:8px}}
figcaption{{padding:10px 4px 2px;font-size:13px;color:#bbb}}
</style></head><body><main><h1>{title}</h1><p>{summary}</p><section class='grid'>{cards}</section></main></body></html>""".format(
                title=html.escape(variant.title),
                summary=html.escape(variant.summary),
                cards="".join(cards),
            ),
            encoding="utf-8",
        )
        files["preview"] = str(preview.resolve())

        archive_path = output_dir / f"wechat-light-series-{variant.id}.zip"
        with zipfile.ZipFile(
            archive_path,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for value in files.values():
                file_path = Path(value)
                if file_path.is_file():
                    archive.write(file_path, arcname=file_path.name)
        files["package"] = str(archive_path.resolve())
        return files

    def _generate_image(self, prompt: str) -> bytes:
        base_url = (self.settings.image_base_url or self.settings.model_base_url).rstrip("/")
        endpoint = base_url + "/images/generations"
        api_key = self.settings.image_api_key or self.settings.model_api_key
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        bodies = [
            {
                "model": self.settings.image_model,
                "prompt": prompt,
                "size": self.settings.image_size,
                "n": 1,
            },
            {"model": self.settings.image_model, "prompt": prompt, "n": 1},
        ]
        last_error = ""
        with httpx.Client(timeout=300, follow_redirects=True) as client:
            for index, body in enumerate(bodies):
                try:
                    response = client.post(endpoint, headers=headers, json=body)
                    if response.status_code in {400, 404, 422} and index == 0:
                        last_error = response.text[:1000]
                        continue
                    response.raise_for_status()
                    data = response.json()
                    items = data.get("data") if isinstance(data, dict) else None
                    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
                        raise NativeSkillError("图片模型响应缺少 data")
                    item = items[0]
                    b64 = str(item.get("b64_json") or item.get("base64") or "")
                    if b64:
                        return base64.b64decode(b64)
                    url = str(item.get("url") or "")
                    if not url:
                        raise NativeSkillError("图片模型没有返回 URL 或 base64")
                    image_response = client.get(url)
                    image_response.raise_for_status()
                    return image_response.content
                except (
                    httpx.HTTPError,
                    ValueError,
                    KeyError,
                    base64.binascii.Error,
                ) as exc:
                    last_error = str(exc)
                    if index == len(bodies) - 1:
                        break
        raise NativeSkillError(f"图片生成失败：{last_error[:1000]}")

    @staticmethod
    def _accent(value: str) -> str:
        cleaned = value.strip()
        if re.fullmatch(r"#[0-9a-fA-F]{6}", cleaned):
            return cleaned
        names = {
            "red": "#c91f2c",
            "vermilion": "#c91f2c",
            "blue": "#1646d8",
            "yellow": "#d89b19",
            "green": "#19734b",
        }
        for name, color in names.items():
            if name in cleaned.lower():
                return color
        return "#c91f2c"

    @staticmethod
    def _object(value: str) -> dict[str, Any]:
        try:
            parsed = json.loads(value or "{}")
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _clean(value: str, limit: int) -> str:
        return re.sub(r"\s+", " ", value).strip()[:limit]
