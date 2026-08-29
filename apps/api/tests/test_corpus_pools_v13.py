from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.domain.models import (
    CorpusBatch,
    CorpusPoolSource,
    DraftRevision,
    SourceItem,
    SourceRelation,
)
from app.domain.schemas import CorpusPoolDetail
from app.services.corpus_pools import CorpusPoolService
from app.services.source_graph import connected_source_ids


def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'pool.db'}",
        media_dir=tmp_path / "assets",
        raw_dir=tmp_path / "raw",
        export_dir=tmp_path / "exports",
        browser_profile_dir=tmp_path / "profile",
        native_skill_dir=tmp_path / "native-skills",
        scheduler_enabled=False,
    )


def source(
    index: int,
    *,
    platform: str,
    title: str,
    text: str,
    keyword: str,
) -> SourceItem:
    return SourceItem(
        provider="mediacrawler",
        platform=platform,
        external_id=f"item-{index}",
        canonical_url=f"https://example.com/{platform}/{index}",
        author_name=f"作者{index}",
        text_original=text,
        language="zh-CN",
        content_kind="post",
        structured_content_json=json.dumps(
            {"title": title, "discovery_keyword": keyword},
            ensure_ascii=False,
        ),
    )


def populate(db: Session) -> list[SourceItem]:
    values = [
        source(
            1,
            platform="xhs",
            title="长期焦虑不是突然出现的",
            keyword="职场焦虑",
            text="长期焦虑往往来自持续高压、过度思考和缺少恢复时间。识别身体信号比强行忍耐更重要。",
        ),
        source(
            2,
            platform="zhihu",
            title="高压工作中的情绪恢复",
            keyword="压力管理",
            text="高压工作会压缩休息和社交空间。稳定睡眠、划定边界和恢复节奏有助于减少慢性消耗。",
        ),
        source(
            3,
            platform="bili",
            title="独处和社交并不矛盾",
            keyword="独处社交",
            text="有人通过独处恢复精力，也有人从稳定关系中获得支持。关键是看见自己的真实需要。",
        ),
        source(
            4,
            platform="wb",
            title="年轻人的工作边界",
            keyword="职场边界",
            text="工作边界不是逃避责任，而是区分紧急任务、长期目标和可以延后的要求。",
        ),
        source(
            5,
            platform="tieba",
            title="失眠背后的反复思考",
            keyword="失眠焦虑",
            text="睡前反复回想未完成任务，会让大脑保持警觉。记录问题和安排处理时间可以减少循环思考。",
        ),
        source(
            6,
            platform="dy",
            title="周末如何真正恢复",
            keyword="周末恢复",
            text="真正的恢复不只是停止工作，还包括降低信息刺激、恢复身体活动和重新建立生活节奏。",
        ),
    ]
    db.add_all(values)
    db.flush()
    return values


def test_corpus_pool_compiles_members_and_auto_names(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'corpus.db'}")
    Base.metadata.create_all(engine)
    service = CorpusPoolService(settings(tmp_path))

    with Session(engine) as db:
        sources = populate(db)
        pool = service.create_pool(
            db,
            source_ids=[item.id for item in sources],
            description="面向职场人的长期情绪与恢复栏目",
            batch_size=3,
        )
        db.commit()

        detail = service.detail(db, pool.id)
        validated = CorpusPoolDetail.model_validate(detail)
        assert validated.source_count == 6
        assert validated.total_chars > 100
        assert validated.name not in {"", "正在整理", "未命名语料池"}
        assert validated.revision == 1
        assert validated.topic_keywords
        assert "全池语义记忆" in validated.profile_text
        assert "来源数：6" in validated.profile_text
        assert "章节检索候选" in validated.profile_text
        assert ":c" in validated.profile_text
        assert len(validated.members) == 6
        assert all(member.summary for member in validated.members)
        assert any(member.keywords for member in validated.members)
        assert {member.source.platform for member in validated.members} == {
            "xhs",
            "zhihu",
            "bili",
            "wb",
            "tieba",
            "dy",
        }


def test_preview_does_not_consume_and_batches_rotate(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'rotation.db'}")
    Base.metadata.create_all(engine)
    service = CorpusPoolService(settings(tmp_path))

    with Session(engine) as db:
        sources = populate(db)
        pool = service.create_pool(
            db,
            source_ids=[item.id for item in sources],
            batch_size=2,
        )
        db.flush()

        preview = service.preview_batch(db, pool, batch_size=2, focus="职场焦虑")
        assert len(preview["source_ids"]) == 2
        assert db.scalar(
            select(func.sum(CorpusPoolSource.used_count)).where(
                CorpusPoolSource.pool_id == pool.id
            )
        ) == 0
        assert db.scalar(select(func.count(CorpusBatch.id))) == 0

        first_batch, first_anchor, first_sources = service.create_generation_batch(
            db,
            pool,
            batch_size=2,
            focus="职场焦虑",
        )
        second_batch, second_anchor, second_sources = service.create_generation_batch(
            db,
            pool,
            batch_size=2,
            focus="",
        )
        db.flush()

        first_ids = {item.id for item in first_sources}
        second_ids = {item.id for item in second_sources}
        assert first_batch.sequence == 1
        assert second_batch.sequence == 2
        assert first_ids.isdisjoint(second_ids)
        assert first_anchor.provider == "corpus_pool"
        assert first_anchor.state == "private"
        assert first_anchor.content_kind == "corpus_batch"
        assert "全池语义记忆" in first_anchor.text_original
        assert "本批次来源索引" in first_anchor.text_original
        assert second_anchor.id != first_anchor.id
        assert db.scalar(
            select(func.count(SourceRelation.id)).where(
                SourceRelation.from_source_id == first_anchor.id,
                SourceRelation.relation_type == "corpus_batch",
            )
        ) == 2

        first_context = connected_source_ids(db, first_anchor.id)
        second_context = connected_source_ids(db, second_anchor.id)
        assert set(first_context) == {first_anchor.id, *first_ids}
        assert set(second_context) == {second_anchor.id, *second_ids}
        assert second_anchor.id not in first_context
        assert first_anchor.id not in second_context
        assert connected_source_ids(db, first_sources[0].id) == [first_sources[0].id]


def test_batch_draft_keeps_pool_provenance_and_frozen_context(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'provenance.db'}")
    Base.metadata.create_all(engine)
    service = CorpusPoolService(settings(tmp_path))

    with Session(engine) as db:
        sources = populate(db)
        pool = service.create_pool(
            db,
            source_ids=[item.id for item in sources],
            name="职场焦虑与恢复",
            batch_size=3,
        )
        batch, anchor, selected = service.create_generation_batch(
            db,
            pool,
            batch_size=3,
            focus="睡眠和反复思考",
        )
        draft = DraftRevision(
            source_id=anchor.id,
            version=1,
            style="explain",
            title="测试草稿",
            body="测试正文",
            tags="职场焦虑,情绪恢复",
            claims_json="[]",
            provenance_json=json.dumps(
                {"source_ids": [anchor.id, *[item.id for item in selected]]},
                ensure_ascii=False,
            ),
        )
        db.add(draft)
        db.flush()
        service.finalize_batch(db, pool=pool, batch=batch, draft=draft)
        db.commit()

        payload = json.loads(draft.provenance_json)
        corpus = payload["corpus_pool"]
        assert corpus["pool_id"] == pool.id
        assert corpus["pool_name"] == "职场焦虑与恢复"
        assert corpus["batch_id"] == batch.id
        assert corpus["batch_sequence"] == 1
        assert corpus["batch_source_ids"] == [item.id for item in selected]
        assert corpus["memory_mode"] == (
            "compiled-global-memory-plus-detailed-batch"
        )
        assert batch.draft_id == draft.id
        assert batch.anchor_source_id == anchor.id
