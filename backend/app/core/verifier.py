"""Checks an LLM-written brief against the ledger before anyone sees it.

Rules for each sentence:
  1. It must cite at least one fact id in brackets, like [F3].
  2. Every cited id must exist in the ledger.
  3. Every number in the sentence must match a cited fact's value (within rounding).
  4. If the number is written with a unit (%, min, mi, kt, ft) and the fact has a unit,
     the units must agree. "45%" cannot be backed by a fact that says 45 min.
Sentences that fail are removed and counted.

Known limit: a number is checked against the cited facts, not against the meaning of the
sentence. A sentence that cites two facts and swaps their numbers passes when the units
are the same. eval_llm/brief_eval.py measures how many planted errors get through.
"""
from __future__ import annotations

import re

from pydantic import BaseModel

from .ledger import Ledger

CITE = re.compile(r"\[(F\d+)\]")
NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")
SENTENCE = re.compile(r"(?<=[.!?])\s+")
_UNIT_AFTER = re.compile(r"\s*(%|percent\b|minutes?\b|mins?\b|miles?\b|mi\b|knots?\b|kts?\b|feet\b|ft\b)", re.I)
_UNITS = {"%": "%", "percent": "%", "minute": "min", "minutes": "min", "min": "min", "mins": "min",
          "mile": "mi", "miles": "mi", "mi": "mi", "knot": "kt", "knots": "kt", "kt": "kt", "kts": "kt",
          "feet": "ft", "ft": "ft"}


class VerifiedBrief(BaseModel):
    kept: list[str]
    removed: list[dict]

    @property
    def pass_rate(self) -> float:
        total = len(self.kept) + len(self.removed)
        return len(self.kept) / total if total else 1.0


def _numbers_match(found: float, value, tolerance: float = 0.051) -> bool:
    if isinstance(value, bool):
        return False
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return abs(found - v) <= max(tolerance, abs(v) * 0.01) or abs(round(v) - found) < 1e-9


def _supported(number: str, unit: str | None, facts) -> bool:
    for fact in facts:
        if not _numbers_match(float(number), fact.value):
            continue
        fact_unit = _UNITS.get(fact.unit.strip().lower())
        if unit is None or fact_unit is None or unit == fact_unit:
            return True
    return False


def verify(brief: str, ledger: Ledger) -> VerifiedBrief:
    kept, removed = [], []
    for sentence in (s.strip() for s in SENTENCE.split(brief) if s.strip()):
        ids = CITE.findall(sentence)
        if not ids:
            removed.append({"sentence": sentence, "reason": "no citation"})
            continue
        facts = [ledger.get(i) for i in ids]
        if any(f is None for f in facts):
            removed.append({"sentence": sentence, "reason": "cites a fact that does not exist"})
            continue
        text = CITE.sub("", sentence)
        bad = []
        for m in NUMBER.finditer(text):
            after = _UNIT_AFTER.match(text, m.end())
            unit = _UNITS.get(after.group(1).lower()) if after else None
            if not _supported(m.group(), unit, facts):
                bad.append(m.group() + (after.group(1) if after else ""))
        if bad:
            removed.append({"sentence": sentence, "reason": f"numbers not in cited facts: {bad}"})
            continue
        kept.append(sentence)
    return VerifiedBrief(kept=kept, removed=removed)
