from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.domain.models import DraftRevision, PublishTask, SourceItem, SourceRelation
from app.services.publisher import PublishError, PublishService
from app.services.source_graph import connected_sources


def test_connected_sources_walks_entire_thread() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        first = SourceItem(external_id="1", canonical_url="https://x.com/a/status/1")
        second = SourceItem(external_id="2", canonical_url="https://x.com/a/status/2")
        third = SourceItem(external_id="3", canonical_url="https://x.com/a/status/3")
        db.add_all([first, second, third])
        db.flush()
        db.add_all(
            [
                SourceRelation(
                    from_source_id=first.id,
                    to_source_id=second.id,
                    relation_type="thread_next",
                    position=1,
                ),
                SourceRelation(
                    from_source_id=second.id,
                    to_source_id=third.id,
                    relation_type="thread_next",
                    position=2,
                ),
            ]
        )
        db.commit()
        assert {item.external_id for item in connected_sources(db, first.id)} == {"1", "2", "3"}


def test_mark_published_requires_xiaohongshu_url(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = Settings(
        database_url="sqlite:///:memory:",
        media_dir=tmp_path / "assets",
        raw_dir=tmp_path / "raw",
        export_dir=tmp_path / "exports",
        browser_profile_dir=tmp_path / "profile",
    )
    service = PublishService(settings)
    with Session(engine) as db:
        source = SourceItem(external_id="1", canonical_url="https://x.com/a/status/1")
        db.add(source)
        db.flush()
        draft = DraftRevision(source_id=source.id, version=1, title="title", body="body")
        db.add(draft)
        db.flush()
        task = PublishTask(
            draft_id=draft.id,
            state="awaiting_user_confirmation",
            title="title",
            body="body",
        )
        db.add(task)
        db.commit()

        with pytest.raises(PublishError):
            service.mark_published(db, task, "https://example.com/not-xhs")

        result = service.mark_published(
            db,
            task,
            "https://www.xiaohongshu.com/explore/test-note",
        )
        assert result.state == "published"
        assert result.result_url.endswith("test-note")
