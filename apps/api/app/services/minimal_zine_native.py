from __future__ import annotations

import base64
import io
import json
import re
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.platforms import PlatformVariant, PlatformVariantState
from app.services.model_client import ModelClient, ModelClientError
from app.services.native_skill_manager import NativeSkillError, NativeSkillManager


class MinimalZineNativeService:
    skill_name = "gc-minimal-zine-poster-v0-1"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.manager = NativeSkillManager(settings)
        self.model = ModelClient(settings)

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
        specs = [dict(item) for item in raw_specs if isinstance(item, dict)] if isinstance(raw_specs, list) else []
        if not specs:
            raise NativeSkillError("当前轻内容版本没有可生图的页面规格")
        skill_dir = self.manager.ensure_installed(self.skill_name, install_runtime=False)
        skill_text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        output_dir = self.settings.media_dir / "platforms" / variant.id / "minimal-zine-native"
        output_dir.mkdir(parents=True, exist_ok=True)
        results: list[dict[str, Any]] = []
        output_paths = self._object(variant.output_paths_json)
        recent_recipes: list[str] = []
        for index, spec in enumerate(specs, start=1):
            path = output_dir / f"poster-{index:02d}.png"
            if path.is_file() and not regenerate:
                result = {
                    "page": index,
                    "path": str(path.resolve()),
                    "cached": True,
                    "final_prompt": str(spec.get("final_prompt") or ""),
                    "recipe": spec.get("native_zine_recipe") or {},
                    "interpretation": str(spec.get("native_zine_interpretation") or ""),
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
                image_bytes = self._generate_image(str(compiled["final_prompt"]))
                self._save_as_poster(image_bytes, path)
                recipe = compiled.get("recipe") if isinstance(compiled.get("recipe"), dict) else {}
                recent_recipes.append(json.dumps(recipe, ensure_ascii=False, sort_keys=True))
                spec["final_prompt"] = str(compiled["final_prompt"])
                spec["native_zine_recipe"] = recipe
                spec["native_zine_interpretation"] = str(compiled.get("interpretation") or "")
                spec["visual_style"] = "minimal_zine_native"
                result = {
                    "page": index,
                    "path": str(path.resolve()),
                    "cached": False,
                    "final_prompt": spec["final_prompt"],
                    "recipe": recipe,
                    "interpretation": spec["native_zine_interpretation"],
                }
            output_paths[f"poster_{index:02d}"] = str(path.resolve())
            results.append(result)
        metadata["poster_specs"] = specs
        metadata["render_engine"] = "gc-minimal-zine-poster-native-image-api"
        metadata["native_zine"] = {
            "repository": "https://github.com/LiamGvchi/gc-minimal-zine-poster",
            "commit": self.manager.definition(self.skill_name).commit,
            "license": "MIT",
            "image_model": self.settings.image_model,
            "image_size_requested": self.settings.image_size,
            "generated_pages": len(results),
        }
        variant.metadata_json = json.dumps(metadata, ensure_ascii=False)
        variant.output_paths_json = json.dumps(output_paths, ensure_ascii=False)
        variant.status = PlatformVariantState.rendered.value
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
        note = self._clean(str(spec.get("note") or ""), 160)
        metaphor = self._clean(str(spec.get("visual_metaphor") or ""), 240)
        mood = self._clean(str(spec.get("mood") or "quiet"), 80)
        prompt = f"""
按照下面完整的上游 Skill 规则，为一张图片编译 Standard Mode 最终生图 Prompt。
不要解释规则，不要输出 Markdown。

上游 SKILL.md：
{skill_text[:30000]}

本页内容：
- 图组页码：{page}/{total}
- 必须表达的短句：{phrase}
- 小注：{note or '无'}
- 内容隐喻：{metaphor or '从短句中提炼一个单一可成像物件'}
- 情绪：{mood}
- 整组标题：{self._clean(variant.title, 120)}
- 整组摘要：{self._clean(variant.summary, 600)}
- 最近页面已使用配方：{json.dumps(recent_recipes[-3:], ensure_ascii=False)}

严格执行：
1. 从 layout / anchor / typography / accent / texture / mood 六轴选择具体配方；与最近页明显不同。
2. 最终 Prompt 必须是上游规定的四个紧凑段落，明确 3:5、70%-90% 留白、8%-25% 视觉簇。
3. 只保留一个高饱和主色锚点，写明颜色、材质形态和视觉占比。
4. 文字只保留短句“{phrase}”；图像模型可能无法稳定生成长中文，因此不得添加其他长文案。
5. 必须包含完整反向约束，拒绝商业广告、全幅场景、3D、霓虹、UI、可爱卡通和密集拼贴。

只输出 JSON：
{{
  "final_prompt":"四段最终英文或中英混合生图 Prompt",
  "recipe":{{"layout":"","anchor":"","typography":"","accent":"","texture":"","mood":""}},
  "interpretation":"一句说明如何把内容变成单一视觉隐喻"
}}
""".strip()
        result = self.model.chat_json(
            system_prompt=(
                "你正在原样执行 gc-minimal-zine-poster-v0-1 的 Standard Mode Prompt Compiler。"
                "不得用通用海报提示词替代。"
            ),
            user_prompt=prompt,
            temperature=0.42,
            reasoning_effort="high",
            max_tokens=6000,
        )
        final_prompt = str(result.get("final_prompt") or "").strip()
        if len(final_prompt) < 300:
            raise ModelClientError("Minimal Zine Prompt 编译结果过短")
        if "3:5" not in final_prompt:
            final_prompt = "Tall vertical 3:5 phone-poster.\n\n" + final_prompt
        result["final_prompt"] = final_prompt
        return result

    def _generate_image(self, prompt: str) -> bytes:
        base_url = (self.settings.image_base_url or self.settings.model_base_url).rstrip("/")
        endpoint = base_url + "/images/generations"
        api_key = self.settings.image_api_key or self.settings.model_api_key
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
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
                except (httpx.HTTPError, ValueError, KeyError, base64.binascii.Error) as exc:
                    last_error = str(exc)
                    if index == len(bodies) - 1:
                        break
        raise NativeSkillError(f"图片生成失败：{last_error[:1000]}")

    @staticmethod
    def _save_as_poster(image_bytes: bytes, path: Path) -> None:
        try:
            with Image.open(io.BytesIO(image_bytes)) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                poster = ImageOps.fit(
                    image,
                    (1200, 2000),
                    method=Image.Resampling.LANCZOS,
                    centering=(0.5, 0.5),
                )
                poster.save(path, "PNG", optimize=True)
        except (OSError, ValueError) as exc:
            raise NativeSkillError("图片模型返回的文件无法解析") from exc

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
