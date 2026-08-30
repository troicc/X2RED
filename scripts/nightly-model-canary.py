#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import get_settings
from app.services.model_client import ModelClient, ModelClientError


ROOT = Path(__file__).resolve().parents[1]


def _bounded_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    try:
        value = float(os.environ.get(name, default))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be numeric") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "ci-artifacts/nightly-model-canary.json",
    )
    args = parser.parse_args()
    settings = get_settings()
    cap = _bounded_float("X2RED_CANARY_COST_CAP_USD", 0.05, minimum=0.001, maximum=0.10)
    max_output_tokens = int(
        _bounded_float("X2RED_CANARY_MAX_OUTPUT_TOKENS", 32, minimum=8, maximum=128)
    )
    input_token_budget = 256
    if not (
        settings.model_base_url
        and settings.model_name
        and settings.model_api_key
    ):
        raise RuntimeError("nightly canary model configuration is incomplete")
    if (
        settings.model_input_cost_per_million_usd <= 0
        and settings.model_output_cost_per_million_usd <= 0
    ):
        raise RuntimeError("nightly canary requires explicit model pricing")
    per_attempt_worst_case = (
        input_token_budget * settings.model_input_cost_per_million_usd / 1_000_000
        + max_output_tokens * settings.model_output_cost_per_million_usd / 1_000_000
    )
    maximum_attempts = settings.model_max_retries + 1
    worst_case = per_attempt_worst_case * maximum_attempts
    if worst_case > cap:
        raise RuntimeError(
            f"preflight worst-case cost US${worst_case:.6f} exceeds cap US${cap:.6f}"
        )

    client = ModelClient(settings)
    try:
        response = client.chat_text(
            system_prompt="Return one short health token. Do not include secrets.",
            user_prompt="Reply with exactly: X2RED_CANARY_OK",
            temperature=0,
            reasoning_effort="low",
            max_tokens=max_output_tokens,
        )
    except ModelClientError as exc:
        report = {
            "schema_version": "ops1-model-canary-v1",
            "generated_at": datetime.now(UTC).isoformat(),
            "passed": False,
            "error": exc.as_dict(),
            "cost_cap_usd": cap,
            "preflight_worst_case_usd": round(worst_case, 8),
            "preflight_maximum_attempts": maximum_attempts,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        return 1

    usage = client.last_usage.as_dict() if client.last_usage is not None else {}
    observed_cost = usage.get("cost_usd")
    passed = (
        response.strip() == "X2RED_CANARY_OK"
        and observed_cost is not None
        and float(observed_cost) <= cap
    )
    report = {
        "schema_version": "ops1-model-canary-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "passed": passed,
        "response_sha256": hashlib.sha256(response.encode("utf-8")).hexdigest(),
        "response_length": len(response),
        "usage": usage,
        "cost_cap_usd": cap,
        "preflight_worst_case_usd": round(worst_case, 8),
        "preflight_maximum_attempts": maximum_attempts,
        "raw_response_persisted": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
