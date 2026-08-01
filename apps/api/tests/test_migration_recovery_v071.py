from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[3]
_CREATED_AT = "2026-01-02 03:04:05.000000"


def _config() -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("prepend_sys_path", str(ROOT / "apps/api"))
    return config


def _restore_historical_0005_jobs_schema(engine: sa.Engine) -> None:
    """Replace the mutable-model replay with the schema users actually had."""

    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE jobs")
        connection.exec_driver_sql(
            """
            CREATE TABLE jobs (
                id VARCHAR(64) NOT NULL PRIMARY KEY,
                kind VARCHAR(80) NOT NULL,
                state VARCHAR(30) NOT NULL,
                payload_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                error TEXT NOT NULL,
                attempts INTEGER NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                started_at DATETIME,
                finished_at DATETIME
            )
            """
        )
        connection.exec_driver_sql("CREATE INDEX ix_jobs_kind ON jobs (kind)")
        connection.exec_driver_sql("CREATE INDEX ix_jobs_state ON jobs (state)")


def _insert_existing_job(connection: sa.Connection) -> None:
    connection.execute(
        sa.text(
            """
            INSERT INTO jobs (
                id, kind, state, payload_json, result_json, error, attempts,
                created_at, updated_at, started_at, finished_at
            ) VALUES (
                :id, :kind, :state, :payload_json, :result_json, :error,
                :attempts, :created_at, :updated_at, NULL, NULL
            )
            """
        ),
        {
            "id": "job_existing",
            "kind": "intake.x",
            "state": "pending",
            "payload_json": "{}",
            "result_json": "{}",
            "error": "",
            "attempts": 0,
            "created_at": _CREATED_AT,
            "updated_at": _CREATED_AT,
        },
    )


@pytest.mark.parametrize("partially_applied", [False, True])
def test_sqlite_0006_upgrade_recovers_without_losing_jobs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    partially_applied: bool,
) -> None:
    database_path = tmp_path / ("partial.db" if partially_applied else "clean.db")
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("X2RED_DATABASE_URL", database_url)

    from app.core.config import get_settings

    get_settings.cache_clear()
    config = _config()
    command.upgrade(config, "0005")

    engine = sa.create_engine(database_url)
    _restore_historical_0005_jobs_schema(engine)
    with engine.begin() as connection:
        _insert_existing_job(connection)
        if partially_applied:
            connection.exec_driver_sql(
                "ALTER TABLE jobs ADD COLUMN max_attempts INTEGER DEFAULT 3 NOT NULL"
            )
            connection.exec_driver_sql(
                "ALTER TABLE jobs ADD COLUMN priority INTEGER DEFAULT 100 NOT NULL"
            )
            connection.exec_driver_sql(
                "ALTER TABLE jobs ADD COLUMN dedupe_key VARCHAR(255) DEFAULT '' NOT NULL"
            )

    get_settings.cache_clear()
    command.upgrade(config, "head")

    inspector = sa.inspect(engine)
    column_names = {column["name"] for column in inspector.get_columns("jobs")}
    assert {
        "max_attempts",
        "priority",
        "dedupe_key",
        "available_at",
        "locked_by",
    }.issubset(column_names)
    assert "platform_variants" in inspector.get_table_names()
    assert "review_artifacts" in inspector.get_table_names()

    index_names = {index["name"] for index in inspector.get_indexes("jobs")}
    assert {
        "ix_jobs_priority",
        "ix_jobs_dedupe_key",
        "ix_jobs_available_at",
    }.issubset(index_names)

    with engine.connect() as connection:
        row = connection.execute(
            sa.text(
                "SELECT id, max_attempts, priority, dedupe_key, available_at, "
                "locked_by, created_at FROM jobs WHERE id = 'job_existing'"
            )
        ).mappings().one()
        revision = connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one()

    assert row["id"] == "job_existing"
    assert row["max_attempts"] == 3
    assert row["priority"] == 100
    assert row["dedupe_key"] == ""
    assert row["locked_by"] == ""
    assert row["available_at"] is not None
    assert str(row["available_at"]).startswith("2026-01-02 03:04:05")
    assert str(row["created_at"]).startswith("2026-01-02 03:04:05")
    assert revision == "0009"

    get_settings.cache_clear()
    command.upgrade(config, "head")
