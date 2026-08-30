from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class StyleProfileTrainRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    original_samples: list[str] = Field(min_length=3, max_length=20)
    held_out_samples: list[str] = Field(default_factory=list, max_length=10)
    author_feedback: list[str] = Field(default_factory=list, max_length=50)
    confirm_original_or_authorized: Literal[True]

    @field_validator("name", "description")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("original_samples", "held_out_samples", "author_feedback")
    @classmethod
    def clean_samples(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]

    @field_validator("original_samples")
    @classmethod
    def require_three_non_empty_originals(cls, values: list[str]) -> list[str]:
        if len(values) < 3:
            raise ValueError("至少需要 3 篇非空原创样本")
        return values
