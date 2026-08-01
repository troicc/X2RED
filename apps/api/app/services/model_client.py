from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.core.config import Settings


class ModelClientError(RuntimeError):
    pass


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
            raise ModelClientError("模型没有返回有效 JSON") from exc
        if not isinstance(parsed, dict):
            raise ModelClientError("模型返回值不是 JSON 对象")
        return parsed
