from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Engine

ROOT = Path(__file__).resolve().parents[4]


class SchemaRevisionError(RuntimeError):
    """The connected database is not at the repository's Alembic head."""


@dataclass(frozen=True)
class SchemaRevisionStatus:
    current: tuple[str, ...]
    expected: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return set(self.current) == set(self.expected)


def alembic_config(*, database_url: str | None = None) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("prepend_sys_path", str(ROOT / "apps/api"))
    if database_url is not None:
        config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
        config.attributes["x2red_database_url_explicit"] = True
    return config


def schema_revision_status(engine: Engine) -> SchemaRevisionStatus:
    config = alembic_config()
    expected = tuple(sorted(ScriptDirectory.from_config(config).get_heads()))
    with engine.connect() as connection:
        current = tuple(sorted(MigrationContext.configure(connection).get_current_heads()))
    return SchemaRevisionStatus(current=current, expected=expected)


def assert_schema_current(engine: Engine) -> SchemaRevisionStatus:
    status = schema_revision_status(engine)
    if status.ready:
        return status
    current = ",".join(status.current) if status.current else "<unversioned>"
    expected = ",".join(status.expected) if status.expected else "<missing-head>"
    raise SchemaRevisionError(
        f"database schema revision mismatch: current={current}, expected={expected}; "
        "run `x2red migrate` before startup"
    )


def upgrade_database(database_url: str) -> SchemaRevisionStatus:
    command.upgrade(alembic_config(database_url=database_url), "head")
    from sqlalchemy import create_engine

    connect_args = (
        {"check_same_thread": False, "timeout": 30}
        if database_url.startswith("sqlite")
        else {}
    )
    verification_engine = create_engine(database_url, connect_args=connect_args, future=True)
    try:
        return assert_schema_current(verification_engine)
    finally:
        verification_engine.dispose()
