"""Receipts ledger: every fact the app shows has an id, a source and a timestamp."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["official", "reported", "estimate", "assumption", "simulated", "computed"]


class Fact(BaseModel):
    id: str
    label: str
    value: float | str | bool | None
    unit: str = ""
    source: str
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: Confidence


class Ledger:
    """Collects facts for one case. Ids are short (F1, F2, ...) so the LLM can cite them."""

    def __init__(self, now: datetime | None = None) -> None:
        """now: the time stamped on facts that have no time of their own. The Time
        Machine passes the replay time so receipts never show a later clock."""
        self._facts: dict[str, Fact] = {}
        self._now = now

    def add(self, label: str, value, *, source: str, confidence: Confidence, unit: str = "",
            fetched_at: datetime | None = None) -> str:
        fact_id = f"F{len(self._facts) + 1}"
        stamp = fetched_at or self._now
        kwargs = {"fetched_at": stamp} if stamp else {}
        self._facts[fact_id] = Fact(id=fact_id, label=label, value=value, unit=unit,
                                    source=source, confidence=confidence, **kwargs)
        return fact_id

    @classmethod
    def from_facts(cls, facts: list[Fact]) -> "Ledger":
        """Rebuild a ledger from facts that already have ids (used to check a brief)."""
        ledger = cls()
        ledger._facts = {f.id: f for f in facts}
        return ledger

    def get(self, fact_id: str) -> Fact | None:
        return self._facts.get(fact_id)

    def all(self) -> list[Fact]:
        return list(self._facts.values())
