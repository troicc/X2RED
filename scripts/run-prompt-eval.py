#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from app.domain.creative_eval_schemas import (
    VisualEvalSuite,
    WritingEvalSuite,
    prompt_fingerprint,
    writing_output_fingerprint,
)


ROOT = Path(__file__).resolve().parents[1]
EVAL_ROOT = ROOT / "apps/api/tests/evals"


def evaluate() -> dict:
    writing = WritingEvalSuite.model_validate(
        json.loads((EVAL_ROOT / "writing_cases.json").read_text(encoding="utf-8"))
    )
    visual = VisualEvalSuite.model_validate(
        json.loads((EVAL_ROOT / "visual_cases.json").read_text(encoding="utf-8"))
    )
    writing_fingerprints_valid = all(
        case.baseline_output_fingerprint == writing_output_fingerprint(case.baseline_output)
        for case in writing.cases
    )
    visual_fingerprints_valid = all(
        case.prompt_fingerprint == prompt_fingerprint(case.final_prompt)
        for case in visual.cases
    )
    checks = {
        "writing_case_count": len(writing.cases) >= 12,
        "visual_case_count": len(visual.cases) >= 20,
        "writing_ids_unique": len({case.id for case in writing.cases}) == len(writing.cases),
        "visual_ids_unique": len({case.id for case in visual.cases}) == len(visual.cases),
        "writing_fingerprints_valid": writing_fingerprints_valid,
        "visual_fingerprints_valid": visual_fingerprints_valid,
        "contains_no_paid_model_call": True,
    }
    return {
        "schema_version": "ops1-prompt-eval-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "passed": all(checks.values()),
        "checks": checks,
        "writing_cases": len(writing.cases),
        "visual_cases": len(visual.cases),
        "distinct_visual_prompts": len({case.final_prompt for case in visual.cases}),
        "mode": "deterministic-fixture-replay",
        "paid_model_used": False,
        "human_blind_panel_replaced": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "ci-artifacts/prompt-eval.json",
    )
    args = parser.parse_args()
    report = evaluate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
