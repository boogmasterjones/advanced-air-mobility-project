"""Shared API contracts between the engine (Person A, boogmasterjones) and the app (Person B, Jaden).

RULE: this file is the handshake between the two of you. Change it only in its own small
pull request that both of you have seen. Adding a new optional field is fine; renaming or
removing a field breaks the other person's code.

Status of each endpoint:
  LIVE     = implemented and returning real data
  PLANNED  = contract agreed, returns 501 until built (the frontend uses mocks meanwhile)
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .core.ledger import Fact
from .llm.schemas import IntakeResult

Strategy = Literal["ground_only", "air_only", "air_and_ground"]
Status = Literal["OK", "UNKNOWN", "NOT_AVAILABLE"]


# ---- POST /api/cases/evaluate  (LIVE, owner: A) --------------------------------------
class CaseIn(BaseModel):
    origin_id: str = Field(description="FAA facility id from /api/facilities, e.g. 9FA2")
    dest_id: str
    deadline_min: int = Field(ge=1, le=48 * 60)
    category: str = "other"
    as_of: str | None = Field(None, description="ISO time. Set only by the Time Machine (PLANNED)")


class OptionOut(BaseModel):
    strategy: Strategy
    status: Status
    p_by_deadline: float | None
    median_min: float | None
    range_min: tuple[float, float] | None
    reasons: list[str]
    fact_ids: list[str]


class CaseOut(BaseModel):
    disclaimer: str
    origin: dict
    dest: dict
    options: list[OptionOut]
    recommended: Strategy
    facts: list[Fact]
    decision_owner: str
    # Optional extras (added later; older clients can ignore them)
    as_of: str | None = None  # the time the answer was built for (UTC)
    forecasts: list[dict] = []  # per airport: {station, role, issued_at, model, points[]}
    map: dict | None = None  # {road: [[lon, lat]...], road_is_routed, air_base, air: [[lon, lat]...]}


# ---- GET /api/forecast?station=KTPA  (LIVE, owner: A) ---------------------------------
class ForecastPoint(BaseModel):
    hours_ahead: int  # 0, 1, 2, 3
    p_flyable: float  # calibrated probability 0..1
    model: str  # e.g. "lightgbm-v1" or "rule-v0"


class ForecastOut(BaseModel):
    station: str
    issued_at: str
    points: list[ForecastPoint]
    fact_ids: list[str] = []


# ---- GET /api/replay?date=2024-07-15T19:00Z&origin_id=..&dest_id=..&deadline_min=..
#      (LIVE, owner: A)  "Time Machine"
class ReplayOut(BaseModel):
    as_of: str
    then: CaseOut  # what the app would have said using only data available at as_of
    actual_flyable: bool | None  # what really happened (observed weather afterwards)
    actual_best_strategy: Strategy | None
    regret_min: float | None  # minutes lost vs the best choice in hindsight
    # Optional extras
    regret_chance: float | None = None  # on-time chance lost vs the best choice in hindsight
    actual_options: list[OptionOut] | None = None  # the options re-scored with the real weather


class ReplayRange(BaseModel):  # GET /api/replay/range
    first: str | None  # earliest and latest time a replay can use (UTC), None if no archive
    last: str | None
    stations: list[str]


# ---- POST /api/intake  (LIVE with offline parser, owner: B) ---------------------------
class IntakeIn(BaseModel):
    text: str = Field(max_length=4000)


class IntakeOut(BaseModel):
    result: IntakeResult
    confirm_required: bool = True
    # Optional extras. Matching names to real facilities happens in code (llm/match.py).
    origin_matches: list[dict] = []  # best helipad matches: {faa_id, name, city, score}
    dest_matches: list[dict] = []
    origin_id: str | None = None  # pre-selected only when the top match is strong and clear
    dest_id: str | None = None
    provider: str = ""  # which parser produced the fields, e.g. "anthropic: claude-haiku-5-5"


# ---- POST /api/brief  (LIVE, owner: B) -----------------------------------------------
class BriefIn(BaseModel):
    case: CaseOut  # the brief may only use facts in case.facts


class BriefOut(BaseModel):
    sentences: list[str]  # verified sentences, each citing [F#]
    removed: list[dict]  # sentences the verifier deleted, with the reason
    pass_rate: float
    provider: str = ""  # who wrote the text: an LLM, or the offline template


# ---- GET /api/evidence  (LIVE, owners: A and B write eval/results/*.json, B displays) --
class EvalMetric(BaseModel):
    id: str  # E1..E6
    name: str
    value: float | str | None
    baseline: float | str | None = None
    note: str = ""


class EvidenceOut(BaseModel):
    generated_at: str
    metrics: list[EvalMetric]
    details: dict = {}  # the full result files by id, for charts (optional)
