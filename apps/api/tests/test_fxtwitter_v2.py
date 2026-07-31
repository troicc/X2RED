from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domain.models import SourceRelation
from app.services.normalizer import upsert_payload


def test_current_v2_reply_quote_and_timestamp_shape() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    payload = {
        "code": 200,
        "status": {
            "type": "status",
            "id": "100",
            "url": "https://x.com/author/status/100",
            "text": "focal",
            "created_timestamp": 1_700_000_000,
            "author": {"id": "u1", "screen_name": "author", "name": "Author"},
            "quote": {
                "type": "status",
                "id": "99",
                "url": "https://x.com/other/status/99",
                "text": "quoted",
                "created_at": "Tue Nov 14 22:00:00 +0000 2023",
                "author": {"id": "u2", "screen_name": "other", "name": "Other"},
            },
        },
        "thread": [
            {
                "type": "status",
                "id": "101",
                "url": "https://x.com/author/status/101",
                "text": "reply",
                "created_timestamp": 1_700_000_060,
                "replying_to": {"screen_name": "author", "status": "100"},
                "author": {"id": "u1", "screen_name": "author", "name": "Author"},
            }
        ],
    }

    with Session(engine) as db:
        focal, sources, _ = upsert_payload(db, payload, "100")
        db.commit()
        assert focal.created_at is not None
        assert {source.external_id for source in sources} == {"99", "100", "101"}
        relations = db.scalars(select(SourceRelation)).all()
        relation_types = {relation.relation_type for relation in relations}
        assert "reply_to" in relation_types
        assert "quote_of" in relation_types
