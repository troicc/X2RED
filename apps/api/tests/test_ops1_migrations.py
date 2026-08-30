from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import command

from app.db.schema import alembic_config, upgrade_database


def test_ops1_migrates_prior_snapshot_and_matches_metadata(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'prior.db'}"
    config = alembic_config(database_url=database_url)
    command.upgrade(config, "0012")
    engine = sa.create_engine(database_url)
    # Early project migrations used live SQLAlchemy metadata. Reconstruct the
    # actual 0012 boundary explicitly so this test remains a frozen snapshot
    # even as current model classes gain OPS1 fields.
    with engine.begin() as connection:
        for statement in (
            "DROP INDEX IF EXISTS uq_jobs_active_dedupe",
            "DROP INDEX IF EXISTS ix_jobs_dead_lettered_at",
            "DROP INDEX IF EXISTS ix_jobs_lease_expires_at",
            "DROP TABLE IF EXISTS publish_audit_events",
            "ALTER TABLE jobs DROP COLUMN dead_lettered_at",
            "ALTER TABLE jobs DROP COLUMN last_error_code",
            "ALTER TABLE jobs DROP COLUMN last_worker_id",
            "ALTER TABLE jobs DROP COLUMN heartbeat_at",
            "ALTER TABLE jobs DROP COLUMN lease_expires_at",
            "ALTER TABLE writing_projects DROP COLUMN spent_cost_usd",
        ):
            connection.execute(sa.text(statement))
    inspector = sa.inspect(engine)
    assert "spent_cost_usd" not in {
        str(item["name"]) for item in inspector.get_columns("writing_projects")
    }
    assert "publish_audit_events" not in inspector.get_table_names()
    engine.dispose()

    status = upgrade_database(database_url)
    assert status.current == ("0013",)
    engine = sa.create_engine(database_url)
    inspector = sa.inspect(engine)
    job_columns = {str(item["name"]) for item in inspector.get_columns("jobs")}
    assert {
        "lease_expires_at",
        "heartbeat_at",
        "last_worker_id",
        "last_error_code",
        "dead_lettered_at",
    } <= job_columns
    assert "spent_cost_usd" in {
        str(item["name"]) for item in inspector.get_columns("writing_projects")
    }
    assert "publish_audit_events" in inspector.get_table_names()
    assert "uq_jobs_active_dedupe" in {
        str(item.get("name") or "") for item in inspector.get_indexes("jobs")
    }
    engine.dispose()

    # Equivalent to the PR migration-empty gate: model metadata must not produce
    # a new Alembic operation after upgrading an empty database to repository head.
    config = alembic_config(database_url=database_url)
    command.check(config)

    command.downgrade(config, "0012")
    engine = sa.create_engine(database_url)
    inspector = sa.inspect(engine)
    assert "spent_cost_usd" not in {
        str(item["name"]) for item in inspector.get_columns("writing_projects")
    }
    assert "publish_audit_events" not in inspector.get_table_names()
    assert "lease_expires_at" not in {
        str(item["name"]) for item in inspector.get_columns("jobs")
    }
    engine.dispose()

    command.upgrade(config, "head")
    status = upgrade_database(database_url)
    assert status.current == ("0013",)
