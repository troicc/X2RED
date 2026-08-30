from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, ClassVar, Self

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.core.config import Settings
from app.core.http_security import LocalSecurityMiddleware
from app.core.paths import UnsafePathError, resolved_file_within
from app.core.security import redact_sensitive, redact_url
from app.db.schema import SchemaRevisionError, assert_schema_current, upgrade_database
from app.services.model_client import (
    GeneratedImage,
    ModelClient,
    ModelClientError,
    StructuredOutputError,
)
from app.services.writing_durable import DurableAgentRunnerMixin


class _SequenceClient:
    responses: ClassVar[list[httpx.Response]] = []
    requests: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, **_kwargs: Any) -> None:
        pass

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self.requests.append({"url": url, **kwargs})
        return self.responses.pop(0)


def _response(status: int, payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        status,
        json=payload,
        request=httpx.Request("POST", "https://model.example/v1/chat/completions"),
    )


def test_model_retry_is_idempotent_and_records_priced_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _SequenceClient.requests = []
    _SequenceClient.responses = [
        _response(429, {"error": {"message": "slow down"}}),
        _response(
            200,
            {
                "choices": [
                    {
                        "message": {"content": json.dumps({"ok": True})},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
            },
        ),
    ]
    monkeypatch.setattr(httpx, "Client", _SequenceClient)
    client = ModelClient(
        Settings(
            model_base_url="https://model.example/v1",
            model_api_key="test-only-key",
            model_name="test-model",
            model_max_retries=2,
            model_retry_base_seconds=0,
            model_retry_max_seconds=0,
            model_retry_jitter_seconds=0,
            model_input_cost_per_million_usd=2,
            model_output_cost_per_million_usd=8,
        )
    )

    assert client.chat_json(system_prompt="system", user_prompt="user") == {"ok": True}
    assert len(_SequenceClient.requests) == 2
    first_key = _SequenceClient.requests[0]["headers"]["Idempotency-Key"]
    assert first_key
    assert _SequenceClient.requests[1]["headers"]["Idempotency-Key"] == first_key
    assert client.last_usage is not None
    assert client.last_usage.input_tokens == 1000
    assert client.last_usage.output_tokens == 500
    assert client.last_usage.retries == 1
    assert client.last_usage.attempts == 2
    assert client.last_usage.cost_usd == 0.006
    assert client.last_usage.cost_kind == "catalog_estimate"


def test_model_retry_jitter_never_exceeds_configured_delay_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.services.model_client.random.uniform", lambda *_args: 10.0)
    client = ModelClient(
        Settings(
            model_retry_base_seconds=8,
            model_retry_max_seconds=8,
            model_retry_jitter_seconds=10,
        )
    )

    assert client._retry_delay(3, None) == 8


def test_portability_fallback_uses_a_new_idempotency_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _SequenceClient.requests = []
    _SequenceClient.responses = [
        _response(400, {"error": {"message": "response_format unsupported"}}),
        _response(
            200,
            {
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1},
            },
        ),
    ]
    monkeypatch.setattr(httpx, "Client", _SequenceClient)
    client = ModelClient(
        Settings(
            model_base_url="https://model.example/v1",
            model_name="test-model",
            model_max_retries=0,
        )
    )

    assert client.chat_json(system_prompt="system", user_prompt="user") == {"ok": True}
    first = _SequenceClient.requests[0]["headers"]
    second = _SequenceClient.requests[1]["headers"]
    assert first["X-Request-ID"] == second["X-Request-ID"]
    assert first["Idempotency-Key"] != second["Idempotency-Key"]


def test_model_error_is_structured_and_redacts_provider_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "ops1-super-secret"
    _SequenceClient.requests = []
    _SequenceClient.responses = [
        _response(500, {"error": f"api_key={secret}"}),
        _response(500, {"error": f"Bearer {secret}"}),
    ]
    monkeypatch.setattr(httpx, "Client", _SequenceClient)
    client = ModelClient(
        Settings(
            model_base_url="https://model.example/v1",
            model_api_key=secret,
            model_name="test-model",
            model_max_retries=1,
            model_retry_base_seconds=0,
            model_retry_max_seconds=0,
            model_retry_jitter_seconds=0,
        )
    )

    with pytest.raises(ModelClientError) as raised:
        client.chat_text(system_prompt="system", user_prompt="user")
    error = raised.value
    assert error.code == "provider_server_error"
    assert error.retryable is True
    assert error.status_code == 500
    assert error.attempts == 2
    assert secret not in str(error)
    assert secret not in json.dumps(error.as_dict())


def test_provider_estimate_is_not_labeled_as_reported_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _SequenceClient.requests = []
    _SequenceClient.responses = [
        _response(
            200,
            {
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 10,
                    "estimated_cost_usd": 0.0012,
                },
            },
        )
    ]
    monkeypatch.setattr(httpx, "Client", _SequenceClient)
    client = ModelClient(
        Settings(
            model_base_url="https://model.example/v1",
            model_name="test-model",
        )
    )

    assert client.chat_json(system_prompt="system", user_prompt="user") == {"ok": True}
    assert client.last_usage is not None
    assert client.last_usage.cost_usd == 0.0012
    assert client.last_usage.cost_kind == "provider_estimate"


def test_multi_call_usage_preserves_known_partial_cost_and_request_chain() -> None:
    first = DurableAgentRunnerMixin._merge_response_meta(
        None,
        {
            "provider": "test-provider",
            "model": "test-model",
            "cost_usd": 0.01,
            "cost_kind": "provider_reported",
            "request_id": "request-1",
        },
    )
    merged = DurableAgentRunnerMixin._merge_response_meta(
        first,
        {
            "provider": "test-provider",
            "model": "test-model",
            "cost_usd": None,
            "cost_kind": "unavailable",
            "request_id": "request-2",
        },
    )
    assert merged is not None
    assert merged["cost_usd"] == 0.01
    assert merged["cost_kind"] == "partial"
    assert merged["request_id"] == "request-1"
    assert merged["request_ids"] == ["request-1", "request-2"]


def test_invalid_structured_output_preserves_billable_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _SequenceClient.requests = []
    _SequenceClient.responses = [
        _response(
            200,
            {
                "choices": [{"message": {"content": "not-json"}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 25},
            },
        )
    ]
    monkeypatch.setattr(httpx, "Client", _SequenceClient)
    client = ModelClient(
        Settings(
            model_base_url="https://model.example/v1",
            model_name="test-model",
            model_input_cost_per_million_usd=2,
            model_output_cost_per_million_usd=4,
        )
    )

    with pytest.raises(StructuredOutputError) as raised:
        client.chat_json(system_prompt="system", user_prompt="user")
    assert raised.value.usage["input_tokens"] == 100
    assert raised.value.usage["output_tokens"] == 25
    assert raised.value.usage["cost_usd"] == 0.0003
    assert raised.value.usage["cost_kind"] == "catalog_estimate"


def test_image_usage_uses_explicit_catalog_estimate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = ModelClient(
        Settings(
            image_base_url="https://images.example/v1",
            image_api_key="test-key",
            image_model="image-model",
            image_cost_per_image_usd=0.03,
            media_dir=tmp_path / "media",
        )
    )
    monkeypatch.setattr(
        client,
        "_post_image_generation",
        lambda *_args, **_kwargs: (object(), 10),
    )
    monkeypatch.setattr(
        client,
        "_decode_image_response",
        lambda *_args: ([GeneratedImage(image_bytes=b"image", latency_ms=10)], {}, None),
    )

    result = client.generate_images(prompt="NO TEXT", count=2)
    assert result.cost_usd == 0.06
    assert result.usage["cost_kind"] == "catalog_estimate"
    assert result.usage["image_count"] == 2
    assert result.usage["attempts"] == 2


def test_generated_image_url_rejects_non_public_ip() -> None:
    client = ModelClient(
        Settings(
            image_base_url="https://images.example/v1",
            image_api_key="test-key",
            image_model="image-model",
        )
    )
    with pytest.raises(ModelClientError, match="非公网地址"):
        client._validate_generated_image_url("https://127.0.0.1/image.png")


def _secured_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.add_middleware(LocalSecurityMiddleware, settings=settings)

    @app.get("/api/demo")
    def read_demo() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/demo")
    def write_demo() -> dict[str, bool]:
        return {"ok": True}

    return app


def test_non_loopback_api_requires_token_and_rejects_cross_origin() -> None:
    token = "local-token"
    with TestClient(_secured_app(Settings(local_api_token=token))) as client:
        assert client.get("/api/demo", headers={"Host": "192.0.2.4"}).status_code == 401
        authorized = {"Host": "192.0.2.4", "Authorization": f"Bearer {token}"}
        response = client.get("/api/demo", headers=authorized)
        assert response.status_code == 200
        assert response.headers["x-content-type-options"] == "nosniff"
        rejected = client.post(
            "/api/demo",
            headers={**authorized, "Origin": "https://attacker.example"},
        )
        assert rejected.status_code == 403
        allowed = client.post(
            "/api/demo",
            headers={**authorized, "Origin": "http://192.0.2.4"},
        )
        assert allowed.status_code == 200

    with TestClient(_secured_app(Settings())) as client:
        response = client.get("/api/demo", headers={"Host": "192.0.2.4"})
        assert response.status_code == 403
        cross_port = client.post(
            "/api/demo",
            headers={"Host": "127.0.0.1:8787", "Origin": "http://127.0.0.1:3000"},
        )
        assert cross_port.status_code == 403


def test_cli_refuses_non_loopback_bind_without_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import cli
    from app.core.config import get_settings

    monkeypatch.setenv("X2RED_LOCAL_API_TOKEN", "")
    monkeypatch.setenv("X2RED_ALLOW_INSECURE_NON_LOOPBACK", "false")
    for name in (
        "MEDIA_DIR",
        "RAW_DIR",
        "EXPORT_DIR",
        "BROWSER_PROFILE_DIR",
        "NATIVE_SKILL_DIR",
    ):
        monkeypatch.setenv(f"X2RED_{name}", str(tmp_path / name.lower()))
    get_settings.cache_clear()
    monkeypatch.setattr(
        sys,
        "argv",
        ["x2red", "serve", "--host", "0.0.0.0", "--skip-migrate"],
    )
    try:
        assert cli.main() == 2
    finally:
        get_settings.cache_clear()


def test_schema_revision_gate_rejects_unversioned_database(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'schema.db'}"
    engine = create_engine(database_url)
    with pytest.raises(SchemaRevisionError, match="unversioned"):
        assert_schema_current(engine)
    engine.dispose()

    upgraded = upgrade_database(database_url)
    assert upgraded.ready is True
    assert upgraded.current == ("0013",)


def test_application_lifespan_blocks_unversioned_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.main as main_module

    engine = create_engine(f"sqlite:///{tmp_path / 'unversioned-startup.db'}")
    monkeypatch.setattr(main_module, "engine", engine)
    with pytest.raises(SchemaRevisionError, match="revision mismatch"), TestClient(
        main_module.app
    ):
        pass
    engine.dispose()


def test_persisted_files_must_stay_inside_approved_root(tmp_path: Path) -> None:
    root = tmp_path / "approved"
    root.mkdir()
    approved = root / "asset.png"
    approved.write_bytes(b"png")
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"png")

    assert resolved_file_within(approved, [root]) == approved.resolve()
    with pytest.raises(UnsafePathError):
        resolved_file_within(outside, [root])


def test_redaction_removes_bearer_assignment_and_url_credentials() -> None:
    secret = "secret-value"
    rendered = redact_sensitive(
        f"Bearer {secret} api_key={secret} "
        f"https://user:{secret}@example.com/path?token={secret}"
    )
    assert secret not in rendered
    redacted_url = redact_url(f"https://user:pass@example.com/path?token={secret}&page=2#fragment")
    assert "user:pass" not in redacted_url
    assert secret not in redacted_url
    assert "page=2" in redacted_url


def test_redaction_removes_json_credential_values() -> None:
    secret = "json-secret-value"
    rendered = redact_sensitive(
        f'{{"error":{{"api_key":"{secret}","message":"token: {secret}"}}}}'
    )
    assert secret not in rendered
    assert rendered.count("[REDACTED]") == 2
