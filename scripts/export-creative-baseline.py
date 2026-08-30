#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from app.domain.creative_eval_schemas import (
    CreativeBaselineExport,
    ExportedCreativeRecord,
    ExportedVisualPage,
    RedactionReport,
    canonical_fingerprint,
)


SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "cookies",
    "password",
    "secret",
    "sec_uid",
    "session",
    "session_id",
    "xsec_token",
    "access_token",
    "refresh_token",
}
SENSITIVE_URL_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "cookie",
    "password",
    "secret",
    "session",
    "token",
    "xsec_token",
}
SECRET_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
)
LOCAL_PATH_PATTERNS = (
    re.compile(r"file://(?:/[A-Za-z]:)?/[^\s\"'<>]+", re.IGNORECASE),
    re.compile(r"/Users/[^/\s\"'<>]+(?:/[^\s\"'<>]*)?"),
    re.compile(r"/home/[^/\s\"'<>]+(?:/[^\s\"'<>]*)?"),
    re.compile(r"[A-Za-z]:\\Users\\[^\\\s\"'<>]+(?:\\[^\s\"'<>]*)?"),
)
URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
PROMPT_KEY = re.compile(r"(?:^|_)(?:prompt|system_prompt|user_prompt)(?:$|_)", re.IGNORECASE)


@dataclass
class RedactionCounts:
    secret_values: int = 0
    local_paths: int = 0
    sensitive_url_parameters: int = 0
    identifiers_hashed: int = 0


class ExportRedactor:
    def __init__(self) -> None:
        self.counts = RedactionCounts()
        self._identifier_cache: dict[str, str] = {}

    def record_ref(self, kind: str, value: Any) -> str:
        raw = str(value or "")
        cache_key = f"{kind}:{raw}"
        if cache_key not in self._identifier_cache:
            digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()[:24]
            self._identifier_cache[cache_key] = f"{kind}:sha256:{digest}"
            self.counts.identifiers_hashed += 1
        return self._identifier_cache[cache_key]

    def redact(self, value: Any, *, key: str = "") -> Any:
        normalized_key = key.strip().lower().replace("-", "_")
        if self._is_sensitive_key(normalized_key):
            if value not in (None, "", [], {}):
                self.counts.secret_values += 1
            return "<redacted>"
        if self._is_identifier_key(normalized_key):
            return self._redact_identifier(value, normalized_key)
        if isinstance(value, dict):
            return {
                str(child_key): self.redact(child_value, key=str(child_key))
                for child_key, child_value in value.items()
            }
        if isinstance(value, list):
            return [self.redact(item, key=key) for item in value]
        if isinstance(value, tuple):
            return [self.redact(item, key=key) for item in value]
        if isinstance(value, str):
            return self._redact_text(value)
        return value

    @staticmethod
    def _is_sensitive_key(key: str) -> bool:
        return key in SENSITIVE_KEYS or key.endswith(
            (
                "_api_key",
                "_access_token",
                "_refresh_token",
                "_password",
                "_secret",
                "_cookie",
            )
        )

    @staticmethod
    def _is_identifier_key(key: str) -> bool:
        return key == "id" or key.endswith("_id") or key.endswith("_ids")

    def _redact_identifier(self, value: Any, key: str) -> Any:
        if value in (None, ""):
            return value
        kind = key.removesuffix("_ids").removesuffix("_id") or "id"
        if isinstance(value, list):
            return [self.record_ref(kind, item) for item in value]
        if isinstance(value, str) and value.lstrip().startswith("["):
            parsed = _json_value(value, value)
            if isinstance(parsed, list):
                return [self.record_ref(kind, item) for item in parsed]
        return self.record_ref(kind, value)

    def _redact_text(self, value: str) -> str:
        redacted = value
        for pattern in SECRET_PATTERNS:
            redacted, replacements = pattern.subn("<redacted-secret>", redacted)
            self.counts.secret_values += replacements
        redacted = URL_PATTERN.sub(
            lambda match: self._redact_url(match.group(0)),
            redacted,
        )
        for pattern in LOCAL_PATH_PATTERNS:
            redacted, replacements = pattern.subn("<local-path>", redacted)
            self.counts.local_paths += replacements
        return redacted

    def _redact_url(self, value: str) -> str:
        if not value.lower().startswith(("http://", "https://")):
            return value
        try:
            parts = urlsplit(value)
        except ValueError:
            return value
        if not parts.netloc:
            return value
        hostname = parts.hostname or ""
        try:
            port_value = parts.port
        except ValueError:
            return value
        port = f":{port_value}" if port_value else ""
        netloc = f"{hostname}{port}"
        if parts.username or parts.password:
            self.counts.secret_values += 1
        query: list[tuple[str, str]] = []
        for query_key, query_value in parse_qsl(parts.query, keep_blank_values=True):
            if query_key.strip().lower() in SENSITIVE_URL_KEYS:
                query.append((query_key, "<redacted>"))
                self.counts.sensitive_url_parameters += 1
            else:
                query.append((query_key, query_value))
        return urlunsplit(
            (parts.scheme, netloc, parts.path, urlencode(query, doseq=True), parts.fragment)
        )


def _json_value(value: Any, fallback: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _extract_prompts(value: Any, *, key: str = "") -> list[str]:
    prompts: list[str] = []
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            if PROMPT_KEY.search(str(child_key)) and isinstance(child_value, str):
                if child_value.strip():
                    prompts.append(child_value.strip())
            else:
                prompts.extend(_extract_prompts(child_value, key=str(child_key)))
    elif isinstance(value, list):
        for item in value:
            prompts.extend(_extract_prompts(item, key=key))
    return list(dict.fromkeys(prompts))


def _connect_read_only(database_path: Path) -> sqlite3.Connection:
    resolved = database_path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"数据库不存在：{database_path}")
    uri = f"file:{quote(str(resolved))}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=10.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def _table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {str(row["name"]) for row in rows}


def _database_fingerprint(connection: sqlite3.Connection, tables: set[str]) -> str:
    schema_rows = connection.execute(
        "SELECT name, sql FROM sqlite_master WHERE type = 'table' ORDER BY name"
    ).fetchall()
    counts: dict[str, int] = {}
    for table in sorted(tables & {"draft_revisions", "platform_variants", "writing_artifacts"}):
        counts[table] = int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    alembic = ""
    if "alembic_version" in tables:
        row = connection.execute("SELECT version_num FROM alembic_version LIMIT 1").fetchone()
        alembic = str(row[0]) if row else ""
    return canonical_fingerprint(
        {
            "schema": [(str(row["name"]), str(row["sql"] or "")) for row in schema_rows],
            "counts": counts,
            "alembic": alembic,
        }
    )


def _limited_rows(
    connection: sqlite3.Connection,
    query: str,
    *,
    limit: int,
) -> Iterable[sqlite3.Row]:
    sql = query
    parameters: tuple[int, ...] = ()
    if limit > 0:
        sql = f"{query}\nLIMIT ?"
        parameters = (limit,)
    return connection.execute(sql, parameters).fetchall()


def _record_payload(record: ExportedCreativeRecord) -> dict[str, Any]:
    return record.model_dump(mode="json", exclude={"content_fingerprint"})


def _visual_payload(record: ExportedVisualPage) -> dict[str, Any]:
    return record.model_dump(mode="json", exclude={"content_fingerprint"})


def _draft_records(
    connection: sqlite3.Connection,
    redactor: ExportRedactor,
    *,
    limit: int,
) -> list[ExportedCreativeRecord]:
    rows = _limited_rows(
        connection,
        """
        SELECT id, source_id, version, style, title, body, tags,
               claims_json, provenance_json, created_by, created_at
        FROM draft_revisions
        ORDER BY created_at, id
        """.strip(),
        limit=limit,
    )
    records: list[ExportedCreativeRecord] = []
    for row in rows:
        metadata = redactor.redact(
            {
                "source_id": row["source_id"],
                "style": row["style"],
                "claims": _json_value(row["claims_json"], []),
                "provenance": _json_value(row["provenance_json"], {}),
                "created_by": row["created_by"],
                "created_at": row["created_at"],
            }
        )
        record = ExportedCreativeRecord(
            record_ref=redactor.record_ref("draft", row["id"]),
            record_type="draft_revision",
            platform="xhs",
            format=str(row["style"] or ""),
            version=int(row["version"] or 0),
            title=redactor.redact(str(row["title"] or "")),
            body=redactor.redact(str(row["body"] or "")),
            tags=redactor.redact(str(row["tags"] or "")),
            metadata=metadata,
            prompts=_extract_prompts(metadata),
            content_fingerprint="0" * 64,
        )
        record.content_fingerprint = canonical_fingerprint(_record_payload(record))
        records.append(record)
    return records


def _platform_records(
    connection: sqlite3.Connection,
    redactor: ExportRedactor,
    *,
    limit: int,
) -> tuple[list[ExportedCreativeRecord], list[ExportedVisualPage]]:
    rows = _limited_rows(
        connection,
        """
        SELECT id, source_id, base_draft_id, platform, format, version,
               title, subtitle, summary, body_markdown, tags, theme,
               skill_profile_json, metadata_json, output_paths_json,
               status, error, created_by, created_at, updated_at
        FROM platform_variants
        ORDER BY created_at, id
        """.strip(),
        limit=limit,
    )
    records: list[ExportedCreativeRecord] = []
    visual_pages: list[ExportedVisualPage] = []
    for row in rows:
        raw_metadata = _json_value(row["metadata_json"], {})
        raw_skill = _json_value(row["skill_profile_json"], {})
        raw_outputs = _json_value(row["output_paths_json"], {})
        metadata = redactor.redact(
            {
                "source_id": row["source_id"],
                "base_draft_id": row["base_draft_id"],
                "subtitle": row["subtitle"],
                "summary": row["summary"],
                "theme": row["theme"],
                "skill_profile": raw_skill,
                "variant_metadata": raw_metadata,
                "output_paths": raw_outputs,
                "status": row["status"],
                "error": row["error"],
                "created_by": row["created_by"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
        record = ExportedCreativeRecord(
            record_ref=redactor.record_ref("variant", row["id"]),
            record_type="platform_variant",
            platform=str(row["platform"] or ""),
            format=str(row["format"] or ""),
            version=int(row["version"] or 0),
            title=redactor.redact(str(row["title"] or "")),
            body=redactor.redact(str(row["body_markdown"] or "")),
            tags=redactor.redact(str(row["tags"] or "")),
            metadata=metadata,
            prompts=[redactor.redact(prompt) for prompt in _extract_prompts(raw_metadata)],
            content_fingerprint="0" * 64,
        )
        record.content_fingerprint = canonical_fingerprint(_record_payload(record))
        records.append(record)
        visual_pages.extend(
            _visual_pages_from_variant(
                row=row,
                raw_metadata=raw_metadata,
                parent_ref=record.record_ref,
                redactor=redactor,
            )
        )
    return records, visual_pages


def _visual_pages_from_variant(
    *,
    row: sqlite3.Row,
    raw_metadata: Any,
    parent_ref: str,
    redactor: ExportRedactor,
) -> list[ExportedVisualPage]:
    if not isinstance(raw_metadata, dict):
        return []
    candidates: list[dict[str, Any]] = []
    poster_specs = raw_metadata.get("poster_specs")
    if isinstance(poster_specs, list):
        candidates.extend(item for item in poster_specs if isinstance(item, dict))
    visual_prompts = raw_metadata.get("visual_prompts")
    if isinstance(visual_prompts, list):
        candidates.extend(item for item in visual_prompts if isinstance(item, dict))
    pages: list[ExportedVisualPage] = []
    for index, source in enumerate(candidates, start=1):
        page = _safe_positive_int(source.get("page"), fallback=index)
        final_prompt = str(
            source.get("final_prompt")
            or source.get("prompt")
            or source.get("positive_prompt")
            or ""
        )
        page_metadata = redactor.redact(
            {
                key: value
                for key, value in source.items()
                if key
                not in {
                    "phrase",
                    "note",
                    "visual_metaphor",
                    "final_prompt",
                    "prompt",
                    "positive_prompt",
                }
            }
        )
        record = ExportedVisualPage(
            record_ref=redactor.record_ref("visual", f"{row['id']}:{page}:{index}"),
            parent_record_ref=parent_ref,
            page=page,
            article_summary=redactor.redact(str(row["summary"] or "")),
            phrase=redactor.redact(str(source.get("phrase") or "")),
            note=redactor.redact(str(source.get("note") or "")),
            visual_metaphor=redactor.redact(
                str(source.get("visual_metaphor") or source.get("composition") or "")
            ),
            final_prompt=redactor.redact(final_prompt),
            metadata=page_metadata,
            content_fingerprint="0" * 64,
        )
        record.content_fingerprint = canonical_fingerprint(_visual_payload(record))
        pages.append(record)
    return pages


def _writing_artifact_records(
    connection: sqlite3.Connection,
    redactor: ExportRedactor,
    *,
    limit: int,
) -> list[ExportedCreativeRecord]:
    rows = _limited_rows(
        connection,
        """
        SELECT id, project_id, artifact_type, version, content_json,
               content_hash, created_by_role, approved, created_at
        FROM writing_artifacts
        ORDER BY created_at, id
        """.strip(),
        limit=limit,
    )
    records: list[ExportedCreativeRecord] = []
    for row in rows:
        content = redactor.redact(_json_value(row["content_json"], {}))
        body = json.dumps(content, ensure_ascii=False, sort_keys=True)
        metadata = redactor.redact(
            {
                "project_id": row["project_id"],
                "artifact_type": row["artifact_type"],
                "stored_content_hash": row["content_hash"],
                "created_by_role": row["created_by_role"],
                "approved": bool(row["approved"]),
                "created_at": row["created_at"],
            }
        )
        record = ExportedCreativeRecord(
            record_ref=redactor.record_ref("artifact", row["id"]),
            record_type="writing_artifact",
            platform="wechat",
            format=str(row["artifact_type"] or ""),
            version=int(row["version"] or 0),
            title=str(row["artifact_type"] or ""),
            body=body,
            tags="",
            metadata=metadata,
            prompts=[redactor.redact(prompt) for prompt in _extract_prompts(content)],
            content_fingerprint="0" * 64,
        )
        record.content_fingerprint = canonical_fingerprint(_record_payload(record))
        records.append(record)
    return records


def _safe_positive_int(value: Any, *, fallback: int) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return fallback


def export_database(
    database_path: Path,
    *,
    limit_writing: int = 0,
    limit_visual: int = 0,
) -> CreativeBaselineExport:
    redactor = ExportRedactor()
    warnings = [
        "这是本地私有重放导出；即使已脱敏，分享或提交前仍需人工检查来源权利与隐私。",
        "导出不会调用文本模型或图片模型，也不会修改源数据库。",
    ]
    with _connect_read_only(database_path) as connection:
        tables = _table_names(connection)
        database_fingerprint = _database_fingerprint(connection, tables)
        records: list[ExportedCreativeRecord] = []
        visual_pages: list[ExportedVisualPage] = []
        if "draft_revisions" in tables:
            records.extend(_draft_records(connection, redactor, limit=limit_writing))
        else:
            warnings.append("数据库没有 draft_revisions 表。")
        if "platform_variants" in tables:
            variants, variant_visuals = _platform_records(
                connection,
                redactor,
                # Visual pages are nested in variant metadata. Read every variant so
                # a small visual limit cannot accidentally inspect only article rows.
                limit=0,
            )
            records.extend(variants[:limit_writing] if limit_writing > 0 else variants)
            visual_pages.extend(variant_visuals)
        else:
            warnings.append("数据库没有 platform_variants 表。")
        if "writing_artifacts" in tables:
            records.extend(_writing_artifact_records(connection, redactor, limit=limit_writing))
        if limit_visual > 0:
            visual_pages = visual_pages[:limit_visual]
    counts = redactor.counts
    return CreativeBaselineExport(
        exported_at=datetime.now(UTC),
        source_database=database_path.name,
        source_database_fingerprint=database_fingerprint,
        records=records,
        visual_pages=visual_pages,
        redaction=RedactionReport(
            secret_values=counts.secret_values,
            local_paths=counts.local_paths,
            sensitive_url_parameters=counts.sensitive_url_parameters,
            identifiers_hashed=counts.identifiers_hashed,
        ),
        warnings=warnings,
    )


def _write_export(output_path: Path, export: CreativeBaselineExport) -> None:
    target = output_path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(
        json.dumps(export.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="只读导出 X2RED 当前创作工件，生成脱敏、可重放的 C0 JSON 基线。"
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/x2red.db"),
        help="SQLite 数据库路径；默认 data/x2red.db。",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="输出 JSON 路径。真实数据库导出默认不应提交到 Git。",
    )
    parser.add_argument(
        "--limit-writing",
        type=int,
        default=0,
        help="每类写作表最多导出条数；0 表示全部。",
    )
    parser.add_argument(
        "--limit-visual",
        type=int,
        default=0,
        help="最多导出的视觉页数；0 表示全部。",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.limit_writing < 0 or args.limit_visual < 0:
        raise SystemExit("limit 不能小于 0")
    export = export_database(
        args.database,
        limit_writing=args.limit_writing,
        limit_visual=args.limit_visual,
    )
    _write_export(args.output, export)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "records": len(export.records),
                "visual_pages": len(export.visual_pages),
                "redaction": export.redaction.model_dump(mode="json"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
