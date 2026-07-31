from __future__ import annotations

from collections import deque

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domain.models import SourceItem, SourceRelation


def connected_source_ids(db: Session, source_id: str, *, max_nodes: int = 500) -> list[str]:
    """Return a bounded connected source graph in stable breadth-first order."""
    ordered = [source_id]
    seen = {source_id}
    queue: deque[str] = deque([source_id])

    while queue and len(ordered) < max_nodes:
        current = queue.popleft()
        relations = db.scalars(
            select(SourceRelation)
            .where(
                or_(
                    SourceRelation.from_source_id == current,
                    SourceRelation.to_source_id == current,
                )
            )
            .order_by(SourceRelation.position, SourceRelation.id)
        ).all()
        for relation in relations:
            neighbor = (
                relation.to_source_id
                if relation.from_source_id == current
                else relation.from_source_id
            )
            if neighbor in seen:
                continue
            seen.add(neighbor)
            ordered.append(neighbor)
            queue.append(neighbor)
            if len(ordered) >= max_nodes:
                break
    return ordered


def connected_sources(db: Session, source_id: str, *, max_nodes: int = 500) -> list[SourceItem]:
    ids = connected_source_ids(db, source_id, max_nodes=max_nodes)
    items = list(db.scalars(select(SourceItem).where(SourceItem.id.in_(ids))).all())
    rank = {item_id: index for index, item_id in enumerate(ids)}
    items.sort(
        key=lambda item: (
            item.created_at.timestamp() if item.created_at else 0,
            rank.get(item.id, len(rank)),
        )
    )
    return items
