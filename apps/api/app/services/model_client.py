from __future__ import annotations

import asyncio
import base64
import binascii
import ipaddress
import json
import random
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from app.core.config import Settings
from app.core.security import redact_sensitive
from app.domain.image_candidate_schemas import ProviderCapabilities


class ModelClientError(httpx.HTTPError):
    """A provider failure with stable fields safe for logs and API responses."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "model_error",
        retryable: bool = False,
        status_code: int | None = None,
        attempts: int = 0,
        provider: str = "",
        model: str = "",
        request_id: str = "",
        detail: str = "",
    ) -> None:
        safe_detail = redact_sensitive(detail, max_length=1000)
        rendered = message if not safe_detail else f"{message}：{safe_detail}"
        super().__init__(rendered)
        self.code = code
        self.retryable = retryable
        self.status_code = status_code
        self.attempts = attempts
        self.provider = provider
        self.model = model
        self.request_id = request_id
        self.detail = safe_detail

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "retryable": self.retryable,
            "status_code": self.status_code,
            "attempts": self.attempts,
            "provider": self.provider,
            "model": self.model,
            "request_id": self.request_id,
        }


class StructuredOutputError(ModelClientError, ValueError):
    """A model response was returned but could not be decoded as an object."""

    def __init__(
        self,
        message: str,
        *,
        raw_content: str = "",
        phase: str = "parse",
        usage: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code="structured_output_error")
        self.raw_content = raw_content
        self.phase = phase
        self.usage = dict(usage or {})


class CandidateCountUnsupported(ModelClientError):
    """The provider accepted image generation but rejected a multi-image count."""


@dataclass(frozen=True)
class ModelUsage:
    provider: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    image_count: int
    cost_usd: float | None
    cost_kind: str
    latency_ms: int
    retries: int
    attempts: int
    request_id: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "image_count": self.image_count,
            "cost_usd": self.cost_usd,
            "cost_kind": self.cost_kind,
            "latency_ms": self.latency_ms,
            "retries": self.retries,
            "attempts": self.attempts,
            "request_id": self.request_id,
        }


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
        self.last_usage: ModelUsage | None = None

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
        response, request_meta = self._post_variants([body])
        self.last_usage = self._text_usage(response, request_meta)
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
        response, request_meta = self._post_variants([with_format, body, portable])
        self.last_usage = self._text_usage(response, request_meta)
        content = str(response["choices"][0]["message"].get("content") or "")
        try:
            return self.parse_json_object(content)
        except StructuredOutputError as exc:
            exc.usage = self.last_usage.as_dict()
            raise

    async def chat_json_async(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        reasoning_effort: str = "medium",
        model_name: str = "",
        max_tokens: int | None = None,
        request_timeout_seconds: float | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Async JSON chat with the same retry and telemetry policy as native Skills."""

        if not self.configured:
            raise ModelClientError(
                "尚未配置文本模型",
                code="not_configured",
                model=model_name.strip() or self.settings.model_name,
            )
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
        without_format = dict(body)
        without_format.pop("response_format", None)
        portable = dict(without_format)
        portable.pop("thinking", None)
        portable.pop("reasoning_effort", None)
        variants = [with_format, without_format]
        if portable != without_format:
            variants.append(portable)
        response, request_meta = await self._post_variants_async(
            variants,
            request_timeout_seconds=request_timeout_seconds,
        )
        self.last_usage = self._text_usage(response, request_meta)
        choice = response["choices"][0]
        content = str(choice["message"].get("content") or "")
        try:
            parsed = self.parse_json_object(content)
        except StructuredOutputError as exc:
            exc.usage = self.last_usage.as_dict()
            exc.usage["finish_reason"] = str(choice.get("finish_reason") or "")
            raise
        usage = self.last_usage.as_dict()
        usage["finish_reason"] = str(choice.get("finish_reason") or "")
        return parsed, usage

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
        cost_kinds: list[str] = []
        request_metas: list[dict[str, Any]] = []
        call_count = 0
        strategy = "edit" if edit else "single-call"
        headers = {"Authorization": f"Bearer {api_key}"}
        timeout = max(float(self.settings.request_timeout_seconds), 300.0)
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            if edit:
                response, elapsed, request_meta = self._normalize_image_post_result(
                    self._post_image_edit(
                        client,
                        endpoint=base_url + "/images/edits",
                        headers=headers,
                        prompt=prompt,
                        reference_image=reference_image or b"",
                    )
                )
                request_metas.append(request_meta)
                call_count = 1
                parsed, usage, cost = self._decode_image_response(client, response, elapsed)
                images.extend(parsed[:1])
                if usage:
                    usages.append(usage)
                if cost is not None:
                    costs.append(cost)
                    cost_kinds.append(self._reported_cost(usage)[1])
            elif capabilities.candidate_count and count > 1:
                try:
                    response, elapsed, request_meta = self._normalize_image_post_result(
                        self._post_image_generation(
                            client,
                            endpoint=base_url + "/images/generations",
                            headers=headers,
                            prompt=prompt,
                            count=count,
                        )
                    )
                    request_metas.append(request_meta)
                    call_count = 1
                    parsed, usage, cost = self._decode_image_response(client, response, elapsed)
                    images.extend(parsed)
                    if usage:
                        usages.append(usage)
                    if cost is not None:
                        costs.append(cost)
                        cost_kinds.append(self._reported_cost(usage)[1])
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
                        response, elapsed, request_meta = self._normalize_image_post_result(
                            self._post_image_generation(
                                client,
                                endpoint=base_url + "/images/generations",
                                headers=headers,
                                prompt=prompt,
                                count=1,
                            )
                        )
                        request_metas.append(request_meta)
                        call_count += 1
                        parsed, usage, cost = self._decode_image_response(client, response, elapsed)
                        images.extend(parsed[:1])
                        if usage:
                            usages.append(usage)
                        if cost is not None:
                            costs.append(cost)
                            cost_kinds.append(self._reported_cost(usage)[1])
            else:
                strategy = "sequential" if count > 1 else "single-call"
                for _ in range(count):
                    response, elapsed, request_meta = self._normalize_image_post_result(
                        self._post_image_generation(
                            client,
                            endpoint=base_url + "/images/generations",
                            headers=headers,
                            prompt=prompt,
                            count=1,
                        )
                    )
                    request_metas.append(request_meta)
                    call_count += 1
                    parsed, usage, cost = self._decode_image_response(client, response, elapsed)
                    images.extend(parsed[:1])
                    if usage:
                        usages.append(usage)
                    if cost is not None:
                        costs.append(cost)
                        cost_kinds.append(self._reported_cost(usage)[1])

        if len(images) < count:
            raise ModelClientError(
                f"图片模型只返回 {len(images)} 张候选，少于请求的 {count} 张"
            )
        latency_ms = max(0, round((time.perf_counter() - started) * 1000))
        known_cost = round(sum(costs), 8) if costs else None
        cost_kind = "unavailable"
        if known_cost is not None:
            known_kinds = {item for item in cost_kinds if item != "unavailable"}
            if len(costs) != call_count:
                cost_kind = "partial"
            elif len(known_kinds) == 1:
                cost_kind = known_kinds.pop()
            else:
                cost_kind = "mixed_estimate"
        if known_cost is None and self.settings.image_cost_per_image_usd > 0:
            known_cost = round(count * self.settings.image_cost_per_image_usd, 8)
            cost_kind = "catalog_estimate"
            per_image_cost = round(known_cost / count, 8)
            images = [
                GeneratedImage(
                    image_bytes=item.image_bytes,
                    latency_ms=item.latency_ms,
                    cost_usd=per_image_cost,
                )
                for item in images
            ]
        usage = {
            "provider": capabilities.provider,
            "model": capabilities.model,
            "input_tokens": None,
            "output_tokens": None,
            "image_count": count,
            "cost_usd": known_cost,
            "cost_kind": cost_kind,
            "latency_ms": latency_ms,
            "retries": sum(int(item.get("retries") or 0) for item in request_metas),
            "attempts": sum(int(item.get("attempts") or 0) for item in request_metas),
            "request_ids": [str(item.get("request_id") or "") for item in request_metas],
            "responses": usages,
        }
        return ImageGenerationResult(
            images=images[:count],
            capabilities=capabilities,
            request_strategy=strategy,
            call_count=call_count,
            usage=usage,
            cost_usd=known_cost,
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

    @staticmethod
    def _normalize_image_post_result(
        value: tuple[Any, ...],
    ) -> tuple[Any, int, dict[str, Any]]:
        """Accept legacy two-item test doubles while production returns telemetry."""

        if len(value) == 3 and isinstance(value[2], dict):
            return value[0], int(value[1]), value[2]
        return value[0], int(value[1]), {
            "request_id": "",
            "attempts": 1,
            "retries": 0,
        }

    def _post_image_generation(
        self,
        client: httpx.Client,
        *,
        endpoint: str,
        headers: dict[str, str],
        prompt: str,
        count: int,
    ) -> tuple[httpx.Response, int, dict[str, Any]]:
        payload: dict[str, Any] = {
            "model": self.settings.image_model,
            "prompt": prompt,
            "n": count,
        }
        if self.settings.image_size:
            payload["size"] = self.settings.image_size
        response, elapsed, request_meta = self._post_image_request(
            client,
            endpoint=endpoint,
            headers={**headers, "Content-Type": "application/json"},
            json_payload=payload,
        )
        detail = redact_sensitive(response.text[:1000])
        if (
            count > 1
            and response.status_code in {400, 404, 405, 422}
            and re.search(
                r"(?:\bn\b|candidate|image\s*count|number\s+of\s+images|must\s+be\s+1|not\s+support|unsupported)",
                detail,
                flags=re.IGNORECASE,
            )
        ):
            raise CandidateCountUnsupported(
                "图片 provider 不支持单次多候选",
                code="candidate_count_unsupported",
                status_code=response.status_code,
                attempts=int(request_meta["attempts"]),
                provider=self.image_capabilities().provider,
                model=self.settings.image_model,
                request_id=str(request_meta["request_id"]),
                detail=detail,
            )
        if response.is_error:
            raise self._response_error(
                response,
                attempts=int(request_meta["attempts"]),
                provider=self.image_capabilities().provider,
                model=self.settings.image_model,
                request_id=str(request_meta["request_id"]),
            )
        return response, elapsed, request_meta

    def _post_image_edit(
        self,
        client: httpx.Client,
        *,
        endpoint: str,
        headers: dict[str, str],
        prompt: str,
        reference_image: bytes,
    ) -> tuple[httpx.Response, int, dict[str, Any]]:
        data = {"model": self.settings.image_model, "prompt": prompt, "n": "1"}
        if self.settings.image_size:
            data["size"] = self.settings.image_size
        response, elapsed, request_meta = self._post_image_request(
            client,
            endpoint=endpoint,
            headers=headers,
            data=data,
            files={"image": ("reference.png", reference_image, "image/png")},
        )
        if response.is_error:
            raise self._response_error(
                response,
                attempts=int(request_meta["attempts"]),
                provider=self.image_capabilities().provider,
                model=self.settings.image_model,
                request_id=str(request_meta["request_id"]),
            )
        return response, elapsed, request_meta

    def _post_image_request(
        self,
        client: httpx.Client,
        *,
        endpoint: str,
        headers: dict[str, str],
        json_payload: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> tuple[httpx.Response, int, dict[str, Any]]:
        request_id = str(uuid4())
        request_headers = {
            **headers,
            "Idempotency-Key": request_id,
            "X-Request-ID": request_id,
        }
        started = time.perf_counter()
        provider = self.image_capabilities().provider
        attempts = 0
        retries = 0
        last_error: ModelClientError | None = None
        for retry_index in range(self.settings.model_max_retries + 1):
            attempts += 1
            response: httpx.Response | None = None
            try:
                response = client.post(
                    endpoint,
                    headers=request_headers,
                    json=json_payload,
                    data=data,
                    files=files,
                )
            except httpx.TimeoutException as exc:
                last_error = self._transport_error(
                    exc,
                    code="timeout",
                    attempts=attempts,
                    provider=provider,
                    model=self.settings.image_model,
                    request_id=request_id,
                )
            except httpx.TransportError as exc:
                last_error = self._transport_error(
                    exc,
                    code="network_error",
                    attempts=attempts,
                    provider=provider,
                    model=self.settings.image_model,
                    request_id=request_id,
                )
            else:
                if not self._is_retryable_status(response.status_code):
                    return response, max(
                        0,
                        round((time.perf_counter() - started) * 1000),
                    ), {
                        "request_id": request_id,
                        "attempts": attempts,
                        "retries": retries,
                    }
                last_error = self._response_error(
                    response,
                    attempts=attempts,
                    provider=provider,
                    model=self.settings.image_model,
                    request_id=request_id,
                )
            if retry_index < self.settings.model_max_retries:
                retries += 1
                time.sleep(self._retry_delay(retry_index, response))
                continue
            break
        if last_error is not None:
            raise last_error
        raise ModelClientError(
            "图片模型调用失败",
            code="provider_error",
            attempts=attempts,
            provider=provider,
            model=self.settings.image_model,
            request_id=request_id,
        )

    def _decode_image_response(
        self,
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
                except (ValueError, binascii.Error) as exc:
                    raise ModelClientError("图片模型返回了无效 base64") from exc
            else:
                url = str(item.get("url") or "")
                if not url:
                    continue
                self._validate_generated_image_url(url)
                max_bytes = min(int(self.settings.max_media_bytes), 25 * 1024 * 1024)
                try:
                    with client.stream("GET", url) as fetched:
                        fetched.raise_for_status()
                        declared = int(fetched.headers.get("content-length") or 0)
                        if declared > max_bytes:
                            raise ModelClientError(
                                "图片 URL 内容超过 25 MB 安全上限",
                                code="image_too_large",
                            )
                        chunks: list[bytes] = []
                        total = 0
                        for chunk in fetched.iter_bytes(1024 * 1024):
                            total += len(chunk)
                            if total > max_bytes:
                                raise ModelClientError(
                                    "图片 URL 内容超过 25 MB 安全上限",
                                    code="image_too_large",
                                )
                            chunks.append(chunk)
                        content = b"".join(chunks)
                except httpx.HTTPError as exc:
                    raise ModelClientError(
                        "图片 URL 下载失败",
                        code="image_download_error",
                        detail=str(exc),
                    ) from exc
            decoded.append(GeneratedImage(image_bytes=content, latency_ms=per_image_latency))
        if not decoded:
            raise ModelClientError("图片模型没有返回可读取的图片")
        raw_usage = payload.get("usage")
        usage: dict[str, Any] = dict(raw_usage) if isinstance(raw_usage, dict) else {}
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

    def _validate_generated_image_url(self, value: str) -> None:
        try:
            parsed = urlparse(value)
        except ValueError as exc:
            raise ModelClientError("图片 URL 无效", code="unsafe_image_url") from exc
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host or parsed.username or parsed.password:
            raise ModelClientError("图片 URL 不符合 HTTPS 安全策略", code="unsafe_image_url")
        try:
            if not ipaddress.ip_address(host).is_global:
                raise ModelClientError("图片 URL 不得指向非公网地址", code="unsafe_image_url")
        except ValueError:
            pass
        base_host = (
            urlparse(self.settings.image_base_url or self.settings.model_base_url).hostname or ""
        ).lower()
        allowed_suffixes = {base_host}
        provider = self.image_capabilities().provider
        if provider == "openai":
            allowed_suffixes.update(
                {
                    "openai.com",
                    "blob.core.windows.net",
                }
            )
        elif provider == "zhipu":
            allowed_suffixes.add("bigmodel.cn")
        if not any(
            suffix and (host == suffix or host.endswith(f".{suffix}"))
            for suffix in allowed_suffixes
        ):
            raise ModelClientError(
                "图片 URL host 不在 provider 允许列表",
                code="unsafe_image_url",
            )

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

    def _post_variants(
        self,
        variants: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        endpoint = self.settings.model_base_url.rstrip("/") + "/chat/completions"
        request_id = str(uuid4())
        headers = {
            "Content-Type": "application/json",
            "X-Request-ID": request_id,
        }
        if self.settings.model_api_key:
            headers["Authorization"] = f"Bearer {self.settings.model_api_key}"
        selected_model = str(variants[0].get("model") or self.settings.model_name)
        provider = self._text_provider_name()
        started = time.perf_counter()
        attempts = 0
        retries = 0
        last_error: ModelClientError | None = None
        timeout = max(float(self.settings.request_timeout_seconds), 240.0)
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            for index, payload in enumerate(variants):
                variant_headers = {
                    **headers,
                    "Idempotency-Key": f"{request_id}-{index + 1}",
                }
                for retry_index in range(self.settings.model_max_retries + 1):
                    attempts += 1
                    try:
                        response = client.post(
                            endpoint,
                            headers=variant_headers,
                            json=payload,
                        )
                    except httpx.TimeoutException as exc:
                        last_error = self._transport_error(
                            exc,
                            code="timeout",
                            attempts=attempts,
                            provider=provider,
                            model=selected_model,
                            request_id=request_id,
                        )
                        if retry_index < self.settings.model_max_retries:
                            retries += 1
                            time.sleep(self._retry_delay(retry_index, None))
                            continue
                        break
                    except httpx.TransportError as exc:
                        last_error = self._transport_error(
                            exc,
                            code="network_error",
                            attempts=attempts,
                            provider=provider,
                            model=selected_model,
                            request_id=request_id,
                        )
                        if retry_index < self.settings.model_max_retries:
                            retries += 1
                            time.sleep(self._retry_delay(retry_index, None))
                            continue
                        break

                    if self._is_retryable_status(response.status_code):
                        last_error = self._response_error(
                            response,
                            attempts=attempts,
                            provider=provider,
                            model=selected_model,
                            request_id=request_id,
                        )
                        if retry_index < self.settings.model_max_retries:
                            retries += 1
                            time.sleep(self._retry_delay(retry_index, response))
                            continue
                        break
                    if response.status_code in {400, 404, 422} and index < len(variants) - 1:
                        last_error = self._response_error(
                            response,
                            attempts=attempts,
                            provider=provider,
                            model=selected_model,
                            request_id=request_id,
                        )
                        break
                    if response.is_error:
                        raise self._response_error(
                            response,
                            attempts=attempts,
                            provider=provider,
                            model=selected_model,
                            request_id=request_id,
                        )
                    try:
                        data = response.json()
                    except ValueError as exc:
                        raise ModelClientError(
                            "模型没有返回 JSON",
                            code="invalid_response",
                            attempts=attempts,
                            provider=provider,
                            model=selected_model,
                            request_id=request_id,
                            detail=str(exc),
                        ) from exc
                    if not isinstance(data, dict) or not data.get("choices"):
                        raise ModelClientError(
                            "模型响应缺少 choices",
                            code="invalid_response",
                            attempts=attempts,
                            provider=provider,
                            model=selected_model,
                            request_id=request_id,
                        )
                    return data, {
                        "provider": provider,
                        "model": selected_model,
                        "latency_ms": max(0, round((time.perf_counter() - started) * 1000)),
                        "retries": retries,
                        "attempts": attempts,
                        "request_id": request_id,
                    }
                else:
                    continue
                if last_error is not None and last_error.retryable:
                    raise last_error
        if last_error is not None:
            raise last_error
        raise ModelClientError(
            "模型调用失败",
            code="provider_error",
            attempts=attempts,
            provider=provider,
            model=selected_model,
            request_id=request_id,
        )

    async def _post_variants_async(
        self,
        variants: list[dict[str, Any]],
        *,
        request_timeout_seconds: float | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        endpoint = self.settings.model_base_url.rstrip("/") + "/chat/completions"
        request_id = str(uuid4())
        headers = {
            "Content-Type": "application/json",
            "X-Request-ID": request_id,
        }
        if self.settings.model_api_key:
            headers["Authorization"] = f"Bearer {self.settings.model_api_key}"
        selected_model = str(variants[0].get("model") or self.settings.model_name)
        provider = self._text_provider_name()
        started = time.perf_counter()
        attempts = 0
        retries = 0
        last_error: ModelClientError | None = None
        timeout = max(
            30.0,
            min(float(request_timeout_seconds or max(self.settings.request_timeout_seconds, 180)), 600.0),
        )
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            for index, payload in enumerate(variants):
                variant_headers = {
                    **headers,
                    "Idempotency-Key": f"{request_id}-{index + 1}",
                }
                for retry_index in range(self.settings.model_max_retries + 1):
                    attempts += 1
                    try:
                        response = await client.post(
                            endpoint,
                            headers=variant_headers,
                            json=payload,
                        )
                    except httpx.TimeoutException as exc:
                        last_error = self._transport_error(
                            exc,
                            code="timeout",
                            attempts=attempts,
                            provider=provider,
                            model=selected_model,
                            request_id=request_id,
                        )
                        if retry_index < self.settings.model_max_retries:
                            retries += 1
                            await asyncio.sleep(self._retry_delay(retry_index, None))
                            continue
                        break
                    except httpx.TransportError as exc:
                        last_error = self._transport_error(
                            exc,
                            code="network_error",
                            attempts=attempts,
                            provider=provider,
                            model=selected_model,
                            request_id=request_id,
                        )
                        if retry_index < self.settings.model_max_retries:
                            retries += 1
                            await asyncio.sleep(self._retry_delay(retry_index, None))
                            continue
                        break

                    if self._is_retryable_status(response.status_code):
                        last_error = self._response_error(
                            response,
                            attempts=attempts,
                            provider=provider,
                            model=selected_model,
                            request_id=request_id,
                        )
                        if retry_index < self.settings.model_max_retries:
                            retries += 1
                            await asyncio.sleep(self._retry_delay(retry_index, response))
                            continue
                        break
                    if response.status_code in {400, 404, 422} and index < len(variants) - 1:
                        last_error = self._response_error(
                            response,
                            attempts=attempts,
                            provider=provider,
                            model=selected_model,
                            request_id=request_id,
                        )
                        break
                    if response.is_error:
                        raise self._response_error(
                            response,
                            attempts=attempts,
                            provider=provider,
                            model=selected_model,
                            request_id=request_id,
                        )
                    try:
                        data = response.json()
                    except ValueError as exc:
                        raise ModelClientError(
                            "模型没有返回 JSON",
                            code="invalid_response",
                            attempts=attempts,
                            provider=provider,
                            model=selected_model,
                            request_id=request_id,
                            detail=str(exc),
                        ) from exc
                    if not isinstance(data, dict) or not data.get("choices"):
                        raise ModelClientError(
                            "模型响应缺少 choices",
                            code="invalid_response",
                            attempts=attempts,
                            provider=provider,
                            model=selected_model,
                            request_id=request_id,
                        )
                    return data, {
                        "provider": provider,
                        "model": selected_model,
                        "latency_ms": max(0, round((time.perf_counter() - started) * 1000)),
                        "retries": retries,
                        "attempts": attempts,
                        "request_id": request_id,
                    }
                else:
                    continue
                if last_error is not None and last_error.retryable:
                    raise last_error
        if last_error is not None:
            raise last_error
        raise ModelClientError(
            "模型调用失败",
            code="provider_error",
            attempts=attempts,
            provider=provider,
            model=selected_model,
            request_id=request_id,
        )

    def _text_provider_name(self) -> str:
        base_url = self.settings.model_base_url.lower()
        model = self.settings.model_name.lower()
        if "openai.com" in base_url or model.startswith(("gpt-", "o1", "o3", "o4")):
            return "openai"
        if "bigmodel.cn" in base_url or model.startswith("glm"):
            return "zhipu"
        return (urlparse(base_url).hostname or "compatible-api")[:80]

    def _text_usage(
        self,
        payload: dict[str, Any],
        request_meta: dict[str, Any],
    ) -> ModelUsage:
        raw_usage = payload.get("usage")
        usage: dict[str, Any] = dict(raw_usage) if isinstance(raw_usage, dict) else {}
        input_tokens = self._usage_int(usage, "prompt_tokens", "input_tokens")
        output_tokens = self._usage_int(usage, "completion_tokens", "output_tokens")
        cost, cost_kind = self._reported_cost(usage)
        if cost is None and input_tokens is not None and output_tokens is not None:
            input_rate = self.settings.model_input_cost_per_million_usd
            output_rate = self.settings.model_output_cost_per_million_usd
            if input_rate > 0 or output_rate > 0:
                cost = round(
                    input_tokens * input_rate / 1_000_000
                    + output_tokens * output_rate / 1_000_000,
                    8,
                )
                cost_kind = "catalog_estimate"
        return ModelUsage(
            provider=str(request_meta["provider"]),
            model=str(request_meta["model"]),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            image_count=0,
            cost_usd=cost,
            cost_kind=cost_kind,
            latency_ms=int(request_meta["latency_ms"]),
            retries=int(request_meta["retries"]),
            attempts=int(request_meta["attempts"]),
            request_id=str(request_meta["request_id"]),
        )

    @staticmethod
    def _usage_int(usage: dict[str, Any], *keys: str) -> int | None:
        for key in keys:
            try:
                if usage.get(key) is not None:
                    return max(0, int(usage[key]))
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _reported_cost(usage: dict[str, Any]) -> tuple[float | None, str]:
        for key in ("total_cost_usd", "cost_usd", "cost"):
            try:
                if usage.get(key) is not None:
                    return round(max(0.0, float(usage[key])), 8), "provider_reported"
            except (TypeError, ValueError):
                continue
        try:
            if usage.get("estimated_cost_usd") is not None:
                return (
                    round(max(0.0, float(usage["estimated_cost_usd"])), 8),
                    "provider_estimate",
                )
        except (TypeError, ValueError):
            pass
        return None, "unavailable"

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code in {408, 409, 425, 429} or 500 <= status_code <= 599

    def _retry_delay(
        self,
        retry_index: int,
        response: httpx.Response | None,
    ) -> float:
        if response is not None:
            raw_retry_after = response.headers.get("Retry-After", "").strip()
            if raw_retry_after:
                try:
                    retry_after = max(0.0, float(raw_retry_after))
                except ValueError:
                    try:
                        target = parsedate_to_datetime(raw_retry_after)
                        if target.tzinfo is None:
                            target = target.replace(tzinfo=UTC)
                        retry_after = max(0.0, (target - datetime.now(UTC)).total_seconds())
                    except (TypeError, ValueError, OverflowError):
                        retry_after = 0.0
                if retry_after > 0:
                    return min(retry_after, self.settings.model_retry_max_seconds)
        exponential = min(
            self.settings.model_retry_base_seconds * (2**retry_index),
            self.settings.model_retry_max_seconds,
        )
        jitter = random.uniform(0.0, self.settings.model_retry_jitter_seconds)
        return min(exponential + jitter, self.settings.model_retry_max_seconds)

    @staticmethod
    def _transport_error(
        exc: Exception,
        *,
        code: str,
        attempts: int,
        provider: str,
        model: str,
        request_id: str,
    ) -> ModelClientError:
        return ModelClientError(
            "模型请求超时" if code == "timeout" else "模型网络请求失败",
            code=code,
            retryable=True,
            attempts=attempts,
            provider=provider,
            model=model,
            request_id=request_id,
            detail=str(exc),
        )

    @staticmethod
    def _response_error(
        response: httpx.Response,
        *,
        attempts: int,
        provider: str,
        model: str,
        request_id: str,
    ) -> ModelClientError:
        status_code = response.status_code
        if status_code == 429:
            code = "rate_limited"
            message = "模型服务触发限流"
        elif status_code in {408, 409, 425}:
            code = "transient_request"
            message = "模型请求暂时不可用"
        elif 500 <= status_code <= 599:
            code = "provider_server_error"
            message = "模型服务端错误"
        elif status_code in {401, 403}:
            code = "authentication_error"
            message = "模型服务认证失败"
        else:
            code = "provider_response_error"
            message = "模型服务拒绝请求"
        return ModelClientError(
            message,
            code=code,
            retryable=ModelClient._is_retryable_status(status_code),
            status_code=status_code,
            attempts=attempts,
            provider=provider,
            model=model,
            request_id=request_id,
            detail=response.text[:1000],
        )

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
