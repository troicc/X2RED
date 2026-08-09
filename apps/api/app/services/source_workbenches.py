from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import (
    SourceWorkbench,
    SourceWorkbenchState,
    WorkspaceState,
    utcnow,
)


def get_source_workbench_state(
    db: Session,
    source_id: str,
    workbench: SourceWorkbench,
) -> SourceWorkbenchState | None:
    return db.scalar(
        select(SourceWorkbenchState).where(
            SourceWorkbenchState.source_id == source_id,
            SourceWorkbenchState.workbench == workbench.value,
        )
    )


def source_workbench_state_value(
    db: Session,
    source_id: str,
    workbench: SourceWorkbench | None,
) -> str:
    if workbench is None:
        return WorkspaceState.active.value
    record = get_source_workbench_state(db, source_id, workbench)
    return record.state if record is not None else WorkspaceState.active.value


def set_source_workbench_state(
    db: Session,
    source_id: str,
    workbench: SourceWorkbench,
    state: WorkspaceState,
    *,
    at: datetime | None = None,
) -> SourceWorkbenchState:
    now = at or utcnow()
    record = get_source_workbench_state(db, source_id, workbench)
    if record is None:
        record = SourceWorkbenchState(
            source_id=source_id,
            workbench=workbench.value,
            created_at=now,
        )
        db.add(record)
    record.state = state.value
    record.archived_at = now if state is WorkspaceState.archived else None
    record.updated_at = now
    return record
