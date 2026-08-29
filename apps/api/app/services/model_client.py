from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import Settings
from app.domain.image_candidate_schemas import ProviderCapabilities


class ModelClientError(RuntimeError):
    pass


class StructuredOutputError(ModelClientError, ValueError):
    """A model response was returned but could not be decoded as an object."""

    def __init__(
        self,
        message: str,
        *,
        raw_content: str = "",
        phase: str = "parse",
    ) -> None:
        super().__init__(message)
        self.raw_content = raw_content
        self.phase = phase


class CandidateCountUnsupported(ModelClientError):
    """The provider accepted image generation but rejected a multi-image count."""


@dataclass(frozen=True)
class GeneratedImage:
    image_bytes: bytes
    latency_ms: int
    cost_usd: float | None = None


@dataclass(frozen=True)
class ImageGenerationResult:
    images: list[GeneratedImage]
    capabilities: ProviderCapabilities
    request_strategy: str
    call_count: int
    usage: dict[str, Any]
    cost_usd: float | None
    latency_ms: int
    requested_count: int


class ModelClient:
    """Small synchronous client for long-form native Skill composition.

    Existing editorial services remain asynchronous. Native visual rendering is
    invoked from the synchronous card API, so this client deliberately exposes a
    synchronous, provider-portable interface with the same GLM reasoning options.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(self.settings.model_base_url and self.settings.model_name)

    def chat_text(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        reasoning_effort: str = "medium",
        model_name: str = "",
        max_tokens: int | None = None,
    ) -> str:
        if not self.configured:
            raise ModelClientError("尚未配置文本模型，无法运行原生视觉 Skill")
        body = self._request_body(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            model_name=model_name,
            max_tokens=max_tokens,
        )
        response = self._post_variants([body])
        content = str(response["choices"][0]["message"].get("content") or "").strip()
        if not content:
            raise ModelClientError("模型返回了空内容")
        return content

    def chat_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        reasoning_effort: str = "medium",
        model_name: str = "",
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        if not self.configured:
            raise ModelClientError("尚未配置文本模型，无法运行原生视觉 Skill")
        body = self._request_body(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            model_name=model_name,
            max_tokens=max_tokens,
        )
        with_format = dict(body)
        with_format["response_format"] = {"type": "json_object"}
        portable = dict(body)
        portable.pop("thinking", None)
        portable.pop("reasoning_effort", None)
        response = self._post_variants([with_format, body, portable])
        content = str(response["choices"][0]["message"].get("content") or "")
        return self.parse_json_object(content)

    def image_capabilities(self) -> ProviderCapabilities:
        """Detect only documented/common capabilities; unknown providers fail closed."""

        base_url = (self.settings.image_base_url or self.settings.model_base_url).lower()
        model = self.settings.image_model.strip()
        lowered = model.lower()
        provider = self._image_provider_name(base_url, lowered)
        if provider == "openai":
            is_gpt_image = lowered.startswith("gpt-image")
            is_dalle_two = lowered.startswith("dall-e-2")
            supports_many = is_gpt_image or is_dalle_two
            return ProviderCapabilities(
                provider=provider,
                model=model or "unconfigured",
                candidate_count=supports_many,
                max_candidate_count=4 if supports_many else 1,
                image_reference=is_gpt_image or is_dalle_two,
                image_edit=is_gpt_image or is_dalle_two,
                multi_turn=False,
                usage=is_gpt_image,
                detection_mode="known-provider",
            )
        if provider == "zhipu":
            return ProviderCapabilities(
                provider=provider,
                model=model or "unconfigured",
                candidate_count=False,
                max_candidate_count=1,
                image_reference=False,
                image_edit=False,
                multi_turn=False,
                usage=False,
                detection_mode="known-provider",
            )
        return ProviderCapabilities(
            provider=provider,
            model=model or "unconfigured",
            candidate_count=False,
            max_candidate_count=1,
            image_reference=False,
            image_edit=False,
            multi_turn=False,
            usage=False,
            detection_mode="conservative-default",
        )

    def generate_images(
        self,
        *,
        prompt: str,
        count: int = 3,
        reference_image: bytes | None = None,
        edit: bool = False,
    ) -> ImageGenerationResult:
        """Generate 1–4 images with an auditable single-call/sequential fallback."""

        if not 1 <= count <= 4:
            raise ModelClientError("图片候选数量必须是 1 到 4")
        base_url = (self.settings.image_base_url or self.settings.model_base_url).rstrip("/")
        api_key = self.settings.image_api_key or self.settings.model_api_key
        if not base_url or not api_key or not self.settings.image_model:
            raise ModelClientError("尚未配置图片模型")
        capabilities = self.image_capabilities()
        if edit and (not reference_image or not capabilities.image_edit):
            raise ModelClientError("当前图片 provider 不支持带参考图的编辑")

        started = time.perf_counter()
        images: list[GeneratedImage] = []
        usages: list[dict[str, Any]] = []
        costs: list[float] = []
        call_count = 0
        strategy = "edit" if edit else "single-call"
        headers = {"Authorization": f"Bearer {api_key}"}
        timeout = max(float(self.settings.request_timeout_seconds), 300.0)
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            if edit:
                response, elapsed = self._post_image_edit(
                    client,
                    endpoint=base_url + "/images/edits",
                    headers=headers,
                    prompt=prompt,
                    reference_image=reference_image or b"",
                )
                call_count = 1
                parsed, usage, cost = self._decode_image_response(client, response, elapsed)
                images.extend(parsed[:1])
                if usage:
                    usages.append(usage)
                if cost is not None:
                    costs.append(cost)
            elif capabilities.candidate_count and count > 1:
                try:
                    response, elapsed = self._post_image_generation(
                        client,
                        endpoint=base_url + "/images/generations",
                        headers=headers,
                        prompt=prompt,
                        count=count,
                    )
                    call_count = 1
                    parsed, usage, cost = self._decode_image_response(client, response, elapsed)
                    images.extend(parsed)
                    if usage:
                        usages.append(usage)
                    if cost is not None:
                        costs.append(cost)
                except CandidateCountUnsupported:
                    call_count = 1
                    capabilities = capabilities.model_copy(
                        update={
                            "candidate_count": False,
                            "max_candidate_count": 1,
                            "detection_mode": "runtime-fallback",
                        }
                    )
                    images = []
                if len(images) < count:
                    strategy = "sequential"
                    missing = count - len(images)
                    for _ in range(missing):
                        response, elapsed = self._post_image_generation(
                            client,
                            endpoint=base_url + "/images/generations",
                            headers=headers,
                            prompt=prompt,
                            count=1,
                        )
                        call_count += 1
                        parsed, usage, cost = self._decode_image_response(client, response, elapsed)
                        images.extend(parsed[:1])
                        if usage:
                            usages.append(usage)
                        if cost is not None:
                            costs.append(cost)
            else:
                strategy = "sequential" if count > 1 else "single-call"
                for _ in range(count):
                    response, elapsed = self._post_image_generation(
                        client,
                        endpoint=base_url + "/images/generations",
                        headers=headers,
                        prompt=prompt,
                        count=1,
                    )
                    call_count += 1
                    parsed, usage, cost = self._decode_image_response(client, response, elapsed)
                    images.extend(parsed[:1])
                    if usage:
                        usages.append(usage)
                    if cost is not None:
                        costs.append(cost)

        if len(images) < count:
            raise ModelClientError(
                f"图片模型只返回 {len(images)} 张候选，少于请求的 {count} 张"
            )
        latency_ms = max(0, round((time.perf_counter() - started) * 1000))
        usage = {"responses": usages} if usages else {}
        return ImageGenerationResult(
            images=images[:count],
            capabilities=capabilities,
            request_strategy=strategy,
            call_count=call_count,
            usage=usage,
            cost_usd=round(sum(costs), 8) if costs else None,
            latency_ms=latency_ms,
            requested_count=count,
        )

    @staticmethod
    def _image_provider_name(base_url: str, model: str) -> str:
        if "openai.com" in base_url or model.startswith(("gpt-image", "dall-e")):
            return "openai"
        if "bigmodel.cn" in base_url or model.startswith("glm"):
            return "zhipu"
        host = urlparse(base_url).hostname or "compatible-api"
        return host[:80]

    def _post_image_generation(
        self,
        client: httpx.Client,
        *,
        endpoint: str,
        headers: dict[str, str],
        prompt: str,
        count: int,
    ) -> tuple[httpx.Response, int]:
        payload: dict[str, Any] = {
            "model": self.settings.image_model,
            "prompt": prompt,
            "n": count,
        }
        if self.settings.image_size:
            payload["size"] = self.settings.image_size
        started = time.perf_counter()
        try:
            response = client.post(
                endpoint,
                headers={**headers, "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            error_response = getattr(exc, "response", None)
            detail = (
                str(getattr(error_response, "text", ""))[:500]
                if error_response is not None
                else str(exc)
            )
            status = int(getattr(error_response, "status_code", 0) or 0)
            if (
                count > 1
                and status in {400, 404, 405, 422}
                and re.search(
                    r"(?:\bn\b|candidate|image\s*count|number\s+of\s+images|must\s+be\s+1|not\s+support|unsupported)",
                    detail,
                    flags=re.IGNORECASE,
                )
            ):
                raise CandidateCountUnsupported(
                    f"图片 provider 不支持单次多候选：{detail}"
                ) from exc
            raise ModelClientError(f"图片生成失败：{detail}") from exc
        except httpx.HTTPError as exc:
            raise ModelClientError(f"图片生成失败：{exc}") from exc
        return response, max(0, round((time.perf_counter() - started) * 1000))

    def _post_image_edit(
        self,
        client: httpx.Client,
        *,
        endpoint: str,
        headers: dict[str, str],
        prompt: str,
        reference_image: bytes,
    ) -> tuple[httpx.Response, int]:
        data = {"model": self.settings.image_model, "prompt": prompt, "n": "1"}
        if self.settings.image_size:
            data["size"] = self.settings.image_size
        started = time.perf_counter()
        try:
            response = client.post(
                endpoint,
                headers=headers,
                data=data,
                files={"image": ("reference.png", reference_image, "image/png")},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            error_response = getattr(exc, "response", None)
            detail = (
                str(getattr(error_response, "text", ""))[:500]
                if error_response is not None
                else str(exc)
            )
            raise ModelClientError(f"图片编辑失败：{detail}") from exc
        return response, max(0, round((time.perf_counter() - started) * 1000))

    @staticmethod
    def _decode_image_response(
        client: httpx.Client,
        response: httpx.Response,
        latency_ms: int,
    ) -> tuple[list[GeneratedImage], dict[str, Any], float | None]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ModelClientError("图片模型没有返回 JSON") from exc
        items = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(items, list) or not items:
            raise ModelClientError("图片模型响应缺少 data")
        decoded: list[GeneratedImage] = []
        per_image_latency = max(0, round(latency_ms / max(len(items), 1)))
        for item in items:
            if not isinstance(item, dict):
                continue
            encoded = str(item.get("b64_json") or item.get("base64") or "")
            if encoded:
                try:
                    content = base64.b64decode(encoded, validate=True)
                except (ValueError, base64.binascii.Error) as exc:
                    raise ModelClientError("图片模型返回了无效 base64") from exc
            else:
                url = str(item.get("url") or "")
                if not url:
                    continue
                try:
                    fetched = client.get(url)
                    fetched.raise_for_status()
                    content = fetched.content
                except httpx.HTTPError as exc:
                    raise ModelClientError("图片 URL 下载失败") from exc
            decoded.append(GeneratedImage(image_bytes=content, latency_ms=per_image_latency))
        if not decoded:
            raise ModelClientError("图片模型没有返回可读取的图片")
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        cost = None
        for key in ("estimated_cost_usd", "total_cost_usd", "cost_usd", "cost"):
            try:
                if usage.get(key) is not None:
                    cost = max(0.0, float(usage[key]))
                    break
            except (TypeError, ValueError):
                continue
        if cost is not None:
            per_image_cost = round(cost / len(decoded), 8)
            decoded = [
                GeneratedImage(
                    image_bytes=item.image_bytes,
                    latency_ms=item.latency_ms,
                    cost_usd=per_image_cost,
                )
                for item in decoded
            ]
        return decoded, dict(usage), cost

    def _request_body(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        reasoning_effort: str,
        model_name: str,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        selected_model = model_name.strip() or self.settings.model_name
        body: dict[str, Any] = {
            "model": selected_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if max_tokens:
            body["max_tokens"] = max_tokens
        if selected_model.lower().startswith("glm-5") or "bigmodel.cn" in self.settings.model_base_url.lower():
            body["thinking"] = {"type": "enabled"}
            body["reasoning_effort"] = reasoning_effort
        return body

    def _post_variants(self, variants: list[dict[str, Any]]) -> dict[str, Any]:
        endpoint = self.settings.model_base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.settings.model_api_key:
            headers["Authorization"] = f"Bearer {self.settings.model_api_key}"
        last_error = ""
        timeout = max(float(self.settings.request_timeout_seconds), 240.0)
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            for index, payload in enumerate(variants):
                try:
                    response = client.post(endpoint, headers=headers, json=payload)
                    if response.status_code in {400, 404, 422} and index < len(variants) - 1:
                        last_error = response.text[:500]
                        continue
                    response.raise_for_status()
                    data = response.json()
                    if not isinstance(data, dict) or not data.get("choices"):
                        raise ModelClientError("模型响应缺少 choices")
                    return data
                except (httpx.HTTPError, ValueError, KeyError) as exc:
                    last_error = str(exc)
                    if index == len(variants) - 1:
                        break
        raise ModelClientError(f"模型调用失败：{last_error[:500]}")

    @staticmethod
    def parse_json_object(content: str) -> dict[str, Any]:
        cleaned = content.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        if not cleaned.startswith("{"):
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start >= 0 and end > start:
                cleaned = cleaned[start : end + 1]
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise StructuredOutputError(
                "模型没有返回有效 JSON",
                raw_content=content,
            ) from exc
        if not isinstance(parsed, dict):
            raise StructuredOutputError(
                "模型返回值不是 JSON 对象",
                raw_content=content,
            )
        return parsed
