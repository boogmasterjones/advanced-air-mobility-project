"""Checks an LLM-written brief against the ledger before anyone sees it.

Rules for each sentence:
  1. It must cite at least one fact id in brackets, like [F3].
  2. Every cited id must exist in the ledger.
  3. Every number in the sentence must match a cited fact's value (within rounding).
Sentences that fail are removed and counted.
"""
from __future__ import annotations

import re

from pydantic import BaseModel

from .ledger import Ledger

CITE = re.compile(r"\[(F\d+)\]")
NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")
SENTENCE = re.compile(r"(?<=[.!?])\s+")


class VerifiedBrief(BaseModel):
    kept: list[str]
    removed: list[dict]

    @property
    def pass_rate(self) -> float:
        total = len(self.kept) + len(self.removed)
        return len(self.kept) / total if total else 1.0


def _numbers_match(found: float, value, tolerance: float = 0.051) -> bool:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    return abs(found - v) <= max(tolerance, abs(v) * 0.01) or abs(round(v) - found) < 1e-9


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
        bad = [n for n in NUMBER.findall(text)
               if not any(_numbers_match(float(n), f.value) for f in facts)]
        if bad:
            removed.append({"sentence": sentence, "reason": f"numbers not in cited facts: {bad}"})
            continue
        kept.append(sentence)
    return VerifiedBrief(kept=kept, removed=removed)
