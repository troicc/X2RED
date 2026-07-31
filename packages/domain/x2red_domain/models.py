from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class RightsStatus(StrEnum):
    UNKNOWN = "unknown"
    REVIEW_REQUIRED = "review_required"
    LICENSED = "licensed"
    CLEARED = "cleared"
    BLOCKED = "blocked"


class SourceRelationType(StrEnum):
    THREAD_NEXT = "thread_next"
    REPLY_TO = "reply_to"
    QUOTE_OF = "quote_of"
    CONVERSATION_REPLY = "conversation_reply"


@dataclass(slots=True)
class SourceItem:
    id: str
    platform: str
    external_id: str
    url: str
    text_original: str
    author_handle: str | None = None
    created_at: datetime | None = None
    rights_status: RightsStatus = RightsStatus.REVIEW_REQUIRED


@dataclass(slots=True)
class SourceGraph:
    items: list[SourceItem] = field(default_factory=list)
    relations: list[tuple[str, str, SourceRelationType]] = field(default_factory=list)


@dataclass(slots=True)
class Claim:
    statement: str
    evidence_source_ids: list[str] = field(default_factory=list)
    verified: bool = False


@dataclass(slots=True)
class DraftRevision:
    source_id: str
    title: str
    body: str
    version: int = 1
