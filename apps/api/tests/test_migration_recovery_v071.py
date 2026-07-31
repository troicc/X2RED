from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[3]


def _config() -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("prepend_sys_path", str(ROOT / "apps/api"))
    return config


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
    jobs = sa.Table("jobs", sa.MetaData(), autoload_with=engine)
    created_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    with engine.begin() as connection:
        connection.execute(
            jobs.insert().values(
                id="job_existing",
                kind="intake.x",
                state="pending",
                payload_json="{}",
                result_json="{}",
                error="",
                attempts=0,
                created_at=created_at,
                updated_at=created_at,
                started_at=None,
                finished_at=None,
            )
        )
        if partially_applied:
            # Reproduce the exact state left by the original migration: SQLite
            # committed the first three ALTER TABLE statements, then rejected
            # available_at because CURRENT_TIMESTAMP is not a constant default.
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
        revision = connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()

    assert row["id"] == "job_existing"
    assert row["max_attempts"] == 3
    assert row["priority"] == 100
    assert row["dedupe_key"] == ""
    assert row["locked_by"] == ""
    assert row["available_at"] is not None
    assert str(row["available_at"]).startswith("2026-01-02 03:04:05")
    assert str(row["created_at"]).startswith("2026-01-02 03:04:05")
    assert revision == "0007"

    # A second startup must be a no-op rather than repeating ALTER TABLE.
    get_settings.cache_clear()
    command.upgrade(config, "head")
