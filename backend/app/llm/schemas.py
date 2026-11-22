"""Structured output for intake. Anything that fails validation goes back to a human.

Two shapes on purpose:
  IntakeDraft   what the LLM is asked to fill in. Loose types only, because the
                structured-output feature does not enforce number ranges.
  IntakeResult  what the rest of the app trusts. Built from a draft by `finalize`, which
                checks every field in code and sends anything odd to human review.
"""
from __future__ import annotations

from typing import Literal, get_args

from pydantic import BaseModel, Field

Category = Literal["stroke", "trauma", "heart_attack", "organ", "supplies", "other"]
MAX_DEADLINE_MIN = 48 * 60
MAX_PEOPLE = 6
MAX_NAME_LEN = 120
MAX_NOTES_LEN = 300


class IntakeDraft(BaseModel):
    category: str = Field(description="One of: stroke, trauma, heart_attack, organ, supplies, other")
    origin_name: str | None = Field(description="Sending facility, copied as written. null if not stated")
    dest_name: str | None = Field(description="Receiving facility, copied as written. null if not stated")
    deadline_min: int | None = Field(description="Time limit in whole minutes, only if the request states one. null otherwise")
    people: int | None = Field(description="People to carry, only if stated. null otherwise")
    notes: str = Field(description="Other transport details from the request, one short sentence. Empty if none")
    needs_human_review: list[str] = Field(description="Names of fields that were unclear, missing or conflicting")


class IntakeResult(BaseModel):
    category: Category
    origin_name: str | None = Field(None, description="Facility name as written by the requester")
    dest_name: str | None = None
    deadline_min: int | None = Field(None, ge=1, le=MAX_DEADLINE_MIN)
    people: int | None = Field(None, ge=0, le=MAX_PEOPLE)
    notes: str = ""
    needs_human_review: list[str] = Field(default_factory=list,
                                          description="Fields the model was not sure about")


def _name(value: str | None) -> str | None:
    value = " ".join((value or "").split())
    return value[:MAX_NAME_LEN] or None


def finalize(draft: IntakeDraft) -> IntakeResult:
    """Check a draft field by field. A bad value becomes None and is flagged, never guessed."""
    review = [f for f in draft.needs_human_review if f in IntakeResult.model_fields]
    category = draft.category.strip().lower().replace(" ", "_")
    if category not in get_args(Category):
        category = "other"
        review.append("category")
    deadline = draft.deadline_min
    if deadline is not None and not 1 <= deadline <= MAX_DEADLINE_MIN:
        deadline = None
    people = draft.people
    if people is not None and not 0 <= people <= MAX_PEOPLE:
        people = None
        review.append("people")
    origin, dest = _name(draft.origin_name), _name(draft.dest_name)
    review += [f for f, v in (("origin_name", origin), ("dest_name", dest), ("deadline_min", deadline)) if v is None]
    return IntakeResult(category=category, origin_name=origin, dest_name=dest, deadline_min=deadline,
                        people=people, notes=" ".join(draft.notes.split())[:MAX_NOTES_LEN],
                        needs_human_review=sorted(set(review)))
