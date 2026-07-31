from __future__ import annotations

from pydantic import BaseModel, Field


class StyleProfileTrainRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    original_samples: list[str] = Field(min_length=3, max_length=20)
    held_out_samples: list[str] = Field(default_factory=list, max_length=10)
    author_feedback: list[str] = Field(default_factory=list, max_length=50)

    @classmethod
    def _clean_samples(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]
