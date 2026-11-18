"""Structured output the LLM must produce. Anything that fails validation goes back to a human."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["stroke", "trauma", "heart_attack", "organ", "supplies", "other"]


class IntakeResult(BaseModel):
    category: Category
    origin_name: str | None = Field(None, description="Facility name as written by the requester")
    dest_name: str | None = None
    deadline_min: int | None = Field(None, ge=1, le=48 * 60)
    people: int | None = Field(None, ge=0, le=6)
    notes: str = ""
    needs_human_review: list[str] = Field(default_factory=list,
                                          description="Fields the model was not sure about")
