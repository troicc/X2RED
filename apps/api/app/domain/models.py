from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class SourceState(str, enum.Enum):
    available = "available"
    unavailable = "unavailable"
    deleted = "deleted"
    private = "private"


class WorkspaceState(str, enum.Enum):
    active = "active"
    archived = "archived"


class SourceWorkbench(str, enum.Enum):
    xhs = "xhs"
    wechat_long = "wechat_long"
    wechat_light = "wechat_light"
    deep_writing = "deep_writing"


class AssetState(str, enum.Enum):
    discovered = "discovered"
    downloading = "downloading"
    ready = "ready"
    failed = "failed"


class RightsStatus(str, enum.Enum):
    owned = "owned"
    licensed = "licensed"
    open_license = "open_license"
    limited_quote = "limited_quote"
    needs_review = "needs_review"
    do_not_publish = "do_not_publish"


class ReviewState(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class PublishState(str, enum.Enum):
    draft = "draft"
    approved = "approved"
    packaged = "packaged"
    awaiting_user_confirmation = "awaiting_user_confirmation"
    published = "published"
    failed = "failed"


class RawSnapshot(Base):
    __tablename__ = "raw_snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("raw"))
    provider: Mapped[str] = mapped_column(String(40), index=True)
    endpoint: Mapped[str] = mapped_column(String(255))
    external_id: Mapped[str] = mapped_column(String(64), index=True)
    payload_path: Mapped[str] = mapped_column(Text)
    payload_sha256: Mapped[str] = mapped_column(String(64), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SourceItem(Base):
    __tablename__ = "source_items"
    __table_args__ = (UniqueConstraint("platform", "external_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("src"))
    provider: Mapped[str] = mapped_column(String(40), default="fxtwitter")
    platform: Mapped[str] = mapped_column(String(20), default="x", index=True)
    external_id: Mapped[str] = mapped_column(String(64), index=True)
    canonical_url: Mapped[str] = mapped_column(Text)
    author_id: Mapped[str] = mapped_column(String(64), default="")
    author_handle: Mapped[str] = mapped_column(String(80), default="", index=True)
    author_name: Mapped[str] = mapped_column(String(160), default="")
    author_avatar_url: Mapped[str] = mapped_column(Text, default="")
    text_original: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(20), default="")
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    state: Mapped[str] = mapped_column(String(32), default=SourceState.available.value)
    workspace_state: Mapped[str] = mapped_column(
        String(20), default=WorkspaceState.active.value, index=True
    )
    content_kind: Mapped[str] = mapped_column(String(30), default="post", index=True)
    structured_content_json: Mapped[str] = mapped_column(Text, default="{}")
    editor_note: Mapped[str] = mapped_column(Text, default="")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_count: Mapped[int] = mapped_column(Integer, default=0)
    possibly_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    rights_status: Mapped[str] = mapped_column(
        String(32), default=RightsStatus.needs_review.value, index=True
    )
    rights_note: Mapped[str] = mapped_column(Text, default="")

    assets: Mapped[list[Asset]] = relationship(back_populates="source", cascade="all, delete-orphan")
    drafts: Mapped[list[DraftRevision]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class SourceWorkbenchState(Base):
    __tablename__ = "source_workbench_states"
    __table_args__ = (UniqueConstraint("source_id", "workbench"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("sws"))
    source_id: Mapped[str] = mapped_column(
        ForeignKey("source_items.id", ondelete="CASCADE"), index=True
    )
    workbench: Mapped[str] = mapped_column(String(40), index=True)
    state: Mapped[str] = mapped_column(
        String(20), default=WorkspaceState.active.value, index=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SourceRelation(Base):
    __tablename__ = "source_relations"
    __table_args__ = (UniqueConstraint("from_source_id", "to_source_id", "relation_type"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("rel"))
    from_source_id: Mapped[str] = mapped_column(ForeignKey("source_items.id", ondelete="CASCADE"))
    to_source_id: Mapped[str] = mapped_column(ForeignKey("source_items.id", ondelete="CASCADE"))
    relation_type: Mapped[str] = mapped_column(String(40), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)


class CorpusPool(Base):
    __tablename__ = "corpus_pools"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("pool"))
    name: Mapped[str] = mapped_column(String(160), default="正在整理")
    name_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[str] = mapped_column(String(20), default="active", index=True)
    batch_size: Mapped[int] = mapped_column(Integer, default=6)
    topic_keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    profile_text: Mapped[str] = mapped_column(Text, default="")
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    total_chars: Mapped[int] = mapped_column(Integer, default=0)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    last_compiled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    members: Mapped[list[CorpusPoolSource]] = relationship(
        back_populates="pool", cascade="all, delete-orphan"
    )
    batches: Mapped[list[CorpusBatch]] = relationship(
        back_populates="pool", cascade="all, delete-orphan"
    )


class CorpusPoolSource(Base):
    __tablename__ = "corpus_pool_sources"
    __table_args__ = (UniqueConstraint("pool_id", "source_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("member"))
    pool_id: Mapped[str] = mapped_column(
        ForeignKey("corpus_pools.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("source_items.id", ondelete="CASCADE"), index=True
    )
    normalized_text: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    pool: Mapped[CorpusPool] = relationship(back_populates="members")
    source: Mapped[SourceItem] = relationship()


class CorpusBatch(Base):
    __tablename__ = "corpus_batches"
    __table_args__ = (UniqueConstraint("pool_id", "sequence"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("batch"))
    pool_id: Mapped[str] = mapped_column(
        ForeignKey("corpus_pools.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    focus: Mapped[str] = mapped_column(Text, default="")
    source_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    source_fingerprint: Mapped[str] = mapped_column(String(64), default="", index=True)
    profile_revision: Mapped[int] = mapped_column(Integer, default=0)
    anchor_source_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    draft_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    pool: Mapped[CorpusPool] = relationship(back_populates="batches")
    anchor_source: Mapped[SourceItem | None] = relationship(foreign_keys=[anchor_source_id])


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("asset"))
    source_id: Mapped[str] = mapped_column(ForeignKey("source_items.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(30))
    role: Mapped[str] = mapped_column(String(30), default="original")
    remote_url: Mapped[str] = mapped_column(Text)
    local_path: Mapped[str] = mapped_column(Text, default="")
    sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    mime_type: Mapped[str] = mapped_column(String(100), default="")
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    alt_text: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[str] = mapped_column(String(30), default=AssetState.discovered.value)
    error: Mapped[str] = mapped_column(Text, default="")
    rights_status: Mapped[str] = mapped_column(
        String(32), default=RightsStatus.needs_review.value, index=True
    )
    rights_note: Mapped[str] = mapped_column(Text, default="")

    source: Mapped[SourceItem] = relationship(back_populates="assets")
    variants: Mapped[list[AssetVariant]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )


class AssetVariant(Base):
    __tablename__ = "asset_variants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("var"))
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))
    remote_url: Mapped[str] = mapped_column(Text)
    container: Mapped[str] = mapped_column(String(20), default="")
    codec: Mapped[str] = mapped_column(String(20), default="")
    bitrate: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)

    asset: Mapped[Asset] = relationship(back_populates="variants")


class DraftRevision(Base):
    __tablename__ = "draft_revisions"
    __table_args__ = (UniqueConstraint("source_id", "version"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("draft"))
    source_id: Mapped[str] = mapped_column(ForeignKey("source_items.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    style: Mapped[str] = mapped_column(String(30), default="explain")
    title: Mapped[str] = mapped_column(String(80), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(Text, default="")
    claims_json: Mapped[str] = mapped_column(Text, default="[]")
    provenance_json: Mapped[str] = mapped_column(Text, default="{}")
    created_by: Mapped[str] = mapped_column(String(30), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    source: Mapped[SourceItem] = relationship(back_populates="drafts")
    reviews: Mapped[list[ReviewDecision]] = relationship(
        back_populates="draft", cascade="all, delete-orphan"
    )
    card_renders: Mapped[list[CardRender]] = relationship(
        back_populates="draft", cascade="all, delete-orphan"
    )


class CardRender(Base):
    __tablename__ = "card_renders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("cards"))
    draft_id: Mapped[str] = mapped_column(ForeignKey("draft_revisions.id", ondelete="CASCADE"))
    template: Mapped[str] = mapped_column(String(40), default="warm_editorial")
    spec_json: Mapped[str] = mapped_column(Text, default="{}")
    output_paths_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(30), default="rendered", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    draft: Mapped[DraftRevision] = relationship(back_populates="card_renders")


class ReviewDecision(Base):
    __tablename__ = "review_decisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("review"))
    draft_id: Mapped[str] = mapped_column(ForeignKey("draft_revisions.id", ondelete="CASCADE"))
    decision: Mapped[str] = mapped_column(String(30), default=ReviewState.pending.value)
    reason: Mapped[str] = mapped_column(Text, default="")
    reviewer: Mapped[str] = mapped_column(String(80), default="local-user")
    facts_checked: Mapped[bool] = mapped_column(Boolean, default=False)
    rights_checked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    draft: Mapped[DraftRevision] = relationship(back_populates="reviews")


class PublishTask(Base):
    __tablename__ = "publish_tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("pub"))
    draft_id: Mapped[str] = mapped_column(ForeignKey("draft_revisions.id", ondelete="CASCADE"))
    state: Mapped[str] = mapped_column(String(40), default=PublishState.draft.value, index=True)
    title: Mapped[str] = mapped_column(String(80))
    body: Mapped[str] = mapped_column(Text)
    tags: Mapped[str] = mapped_column(Text, default="")
    asset_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    payload_sha256: Mapped[str] = mapped_column(String(64), default="")
    package_path: Mapped[str] = mapped_column(Text, default="")
    result_url: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SkillBinding(Base):
    __tablename__ = "skill_bindings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("skill"))
    skill_name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    model_name: Mapped[str] = mapped_column(String(120), default="")
    reasoning_effort: Mapped[str] = mapped_column(String(20), default="medium")
    prompt_version: Mapped[str] = mapped_column(String(40), default="v1")
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
