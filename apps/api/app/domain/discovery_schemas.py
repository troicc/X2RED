from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DiscoverySearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    feed: Literal["latest", "top", "media"] = "latest"
    count: int = Field(default=30, ge=1, le=100)
    cursor: str | None = None
    language: str | None = Field(default=None, max_length=20)


class DiscoveryTimelineRequest(BaseModel):
    handle: str = Field(min_length=1, max_length=100)
    count: int = Field(default=20, ge=1, le=100)
    cursor: str | None = None
    since: int | None = Field(default=None, ge=0)
    media_only: bool = False


class DiscoveryQuotesRequest(BaseModel):
    post_id: str = Field(pattern=r"^\d{2,20}$")
    count: int = Field(default=20, ge=1, le=100)
    cursor: str | None = None


class DiscoveryTrendsRequest(BaseModel):
    count: int = Field(default=20, ge=1, le=50)


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    kind: str
    external_id: str
    canonical_url: str
    author_handle: str
    author_name: str
    text: str
    metadata_json: str
    state: str
    discovered_at: datetime
    updated_at: datetime


class DiscoveryResult(BaseModel):
    run_id: str
    kind: str
    query: str
    cursor: dict[str, Any] = Field(default_factory=dict)
    candidates: list[CandidateOut] = Field(default_factory=list)


class CandidateStateRequest(BaseModel):
    state: Literal["new", "saved", "dismissed"]


class CandidateImportRequest(BaseModel):
    mode: Literal["thread", "conversation"] = "thread"
    download_media: bool = True
