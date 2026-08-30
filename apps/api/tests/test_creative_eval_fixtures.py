from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from collections import Counter
from pathlib import Path

from app.core.config import Settings
from app.domain.creative_eval_schemas import (
    CreativeBaselineExport,
    RubricDocument,
    VisualEvalSuite,
    WritingEvalSuite,
    prompt_fingerprint,
    writing_output_fingerprint,
)
from app.services.minimal_zine_native import (
    MinimalZineNativeService,
    _model_input_fingerprint,
    _storyboard_controls,
)


ROOT = Path(__file__).resolve().parents[3]
EVAL_ROOT = Path(__file__).resolve().parent / "evals"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'fixture.db'}",
        media_dir=tmp_path / "assets",
        raw_dir=tmp_path / "raw",
        export_dir=tmp_path / "exports",
        browser_profile_dir=tmp_path / "profile",
        native_skill_dir=tmp_path / "native-skills",
        scheduler_enabled=False,
    )


def test_writing_fixtures_validate_and_keep_required_distribution() -> None:
    suite = WritingEvalSuite.model_validate(_json(EVAL_ROOT / "writing_cases.json"))

    assert len(suite.cases) == 12
    assert len({case.id for case in suite.cases}) == 12
    assert Counter(case.category for case in suite.cases) == {
        "technical_explanation": 4,
        "news_explanation": 2,
        "opinion_commentary": 2,
        "light_content": 2,
        "wechat_longform": 2,
    }
    assert all(
        case.baseline_output_fingerprint == writing_output_fingerprint(case.baseline_output)
        for case in suite.cases
    )
    serialized = json.dumps(suite.model_dump(mode="json"), ensure_ascii=False)
    assert "/Users/" not in serialized
    assert "sk-" not in serialized


def test_rubrics_freeze_all_required_dimensions() -> None:
    writing = RubricDocument.model_validate(_json(EVAL_ROOT / "rubrics" / "writing_rubric.json"))
    visual = RubricDocument.model_validate(_json(EVAL_ROOT / "rubrics" / "visual_rubric.json"))

    assert writing.kind == "writing"
    assert {item.id for item in writing.dimensions} == {
        "evidence",
        "clarity",
        "specificity",
        "structure",
        "hook",
        "title",
        "style",
        "ai_cliches",
        "usefulness",
    }
    assert visual.kind == "visual"
    assert {item.id for item in visual.dimensions} == {
        "semantic_match",
        "imageability",
        "composition",
        "thumbnail",
        "distinctness",
        "series_consistency",
        "texture",
        "color_anchor",
        "typography",
        "artifacts",
    }


def test_visual_fixtures_replay_the_current_legacy_prompt(tmp_path: Path) -> None:
    suite = VisualEvalSuite.model_validate(_json(EVAL_ROOT / "visual_cases.json"))
    service = MinimalZineNativeService(_settings(tmp_path))

    assert len(suite.cases) == 20
    assert len({case.id for case in suite.cases}) == 20
    for case in suite.cases:
        spec = case.storyboard.model_dump(mode="json")
        spec.pop("total_pages")
        controls = _storyboard_controls(spec)
        raw_prompt = (
            "Create one sparse, non-literal editorial visual symbol for this idea: "
            f"{controls['visual_metaphor']}. Express it as one {controls['anchor']} "
            f"with a {controls['texture']} material treatment and a {controls['mood']} mood. "
            "Render only the visual object and paper texture; do not render the idea as words."
        )
        replayed = service._four_paragraph_prompt(
            controls=controls,
            raw_prompt=raw_prompt,
            safe_zone=service._safe_zone(controls["layout"]),
        )

        assert case.raw_prompt == raw_prompt
        assert case.final_prompt == replayed
        assert case.model_input_fingerprint == _model_input_fingerprint(spec)
        assert case.prompt_fingerprint == prompt_fingerprint(replayed)
        assert case.compiler.skill_commit == ("4cb0396ad4e834019f753b37e1c4f415f5e02026")


def test_visual_baseline_exposes_the_known_semantic_fingerprint_gap() -> None:
    suite = VisualEvalSuite.model_validate(_json(EVAL_ROOT / "visual_cases.json"))
    by_id = {case.id: case for case in suite.cases}
    comparison = by_id["visual-firewall-03-comparison"]
    conclusion = by_id["visual-firewall-04-conclusion"]

    assert comparison.phrase != conclusion.phrase
    assert comparison.note != conclusion.note
    assert comparison.page_visual_role != conclusion.page_visual_role
    assert comparison.evidence_summary != conclusion.evidence_summary
    assert comparison.model_input_fingerprint == conclusion.model_input_fingerprint
    assert comparison.final_prompt == conclusion.final_prompt
    assert len({case.final_prompt for case in suite.cases}) == 19


def _fixture_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE draft_revisions (
                id TEXT PRIMARY KEY, source_id TEXT, version INTEGER, style TEXT,
                title TEXT, body TEXT, tags TEXT, claims_json TEXT,
                provenance_json TEXT, created_by TEXT, created_at TEXT
            );
            CREATE TABLE platform_variants (
                id TEXT PRIMARY KEY, source_id TEXT, base_draft_id TEXT,
                platform TEXT, format TEXT, version INTEGER, title TEXT,
                subtitle TEXT, summary TEXT, body_markdown TEXT, tags TEXT,
                theme TEXT, skill_profile_json TEXT, metadata_json TEXT,
                output_paths_json TEXT, status TEXT, error TEXT,
                created_by TEXT, created_at TEXT, updated_at TEXT
            );
            CREATE TABLE writing_artifacts (
                id TEXT PRIMARY KEY, project_id TEXT, artifact_type TEXT,
                version INTEGER, content_json TEXT, content_hash TEXT,
                created_by_role TEXT, approved INTEGER, created_at TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO draft_revisions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "draft_private",
                "source_private",
                1,
                "explain",
                "脱敏导出测试",
                "正文包含 sk-1234567890abcdefghijkl、/Users/alice/private/note.md，"
                "以及 https://example.test/embed?token=embedded-private-token",
                "测试",
                json.dumps([{"text": "合成主张", "source_id": "source_private"}]),
                json.dumps(
                    {
                        "api_key": "sk-private-value-1234567890",
                        "model_api_key": "model-provider-private-key",
                        "source_ids": ["source_private"],
                        "source_url": "https://example.test/a?token=private-token",
                    }
                ),
                "system",
                "2026-08-09T00:00:00Z",
            ),
        )
        connection.execute(
            "INSERT INTO platform_variants VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "variant_private",
                "source_private",
                "draft_private",
                "wechat",
                "light_series",
                1,
                "视觉测试",
                "",
                "合成摘要",
                "合成正文",
                "测试",
                "zen",
                "{}",
                json.dumps(
                    {
                        "poster_specs": [
                            {
                                "page": 1,
                                "phrase": "合成短句",
                                "note": "合成说明",
                                "visual_metaphor": "one paper object",
                                "final_prompt": "Bearer abcdefghijklmnopqrstuvwxyz visual prompt",
                            }
                        ],
                        "session_id": "private-session",
                    }
                ),
                json.dumps({"poster_01": "/Users/alice/private/poster.png"}),
                "rendered",
                "",
                "system",
                "2026-08-09T00:00:01Z",
                "2026-08-09T00:00:01Z",
            ),
        )
        connection.execute(
            "INSERT INTO writing_artifacts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "artifact_private",
                "project_private",
                "draft",
                1,
                json.dumps(
                    {
                        "system_prompt": "Use sk-abcdefghijklmnop123456 safely",
                        "body": "合成工件",
                    }
                ),
                "stored-hash",
                "writer",
                0,
                "2026-08-09T00:00:02Z",
            ),
        )


def test_export_script_is_read_only_replayable_and_redacts_sensitive_values(
    tmp_path: Path,
) -> None:
    database = tmp_path / "private-fixture.db"
    output = tmp_path / "creative-export.json"
    _fixture_database(database)
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    script = ROOT / "scripts" / "export-creative-baseline.py"
    environment = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "apps" / "api"),
        "X2RED_MODEL_API_KEY": "sk-environment-must-not-be-read-1234",
    }

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--database",
            str(database),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    export = CreativeBaselineExport.model_validate(_json(output))
    assert len(export.records) == 3
    assert len(export.visual_pages) == 1
    assert export.source_database == database.name
    assert export.redaction.secret_values >= 4
    assert export.redaction.local_paths >= 2
    assert export.redaction.sensitive_url_parameters >= 1
    assert export.redaction.identifiers_hashed >= 6
    serialized = output.read_text(encoding="utf-8")
    assert "sk-1234567890abcdefghijkl" not in serialized
    assert "private-session" not in serialized
    assert "/Users/alice" not in serialized
    assert "private-token" not in serialized
    assert "model-provider-private-key" not in serialized
    assert "embedded-private-token" not in serialized
    assert "<redacted" in serialized
    assert "<local-path>" in serialized
    assert "ModelClient" not in script.read_text(encoding="utf-8")
    assert "httpx" not in script.read_text(encoding="utf-8")
