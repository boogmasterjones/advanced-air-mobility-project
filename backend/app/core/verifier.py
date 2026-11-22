"""Checks an LLM-written brief against the ledger before anyone sees it.

Rules for each sentence:
  1. It must cite at least one fact id in brackets, like [F3] or [F3, F7].
  2. Every cited id must exist in the ledger.
  3. Every number must match a cited fact's value at the precision it is written with:
     "42" may stand for 41.6, but "1190" may not stand for 1200.
  4. If the number is written with a unit (%, min, h, mi, kt, ft...) and the fact has a
     unit, the units must agree. "45%" or "45 hours" cannot be backed by a fact of 45 min.
  5. Numbers must be digits. A sentence with a number written as a word ("ninety
     percent", "twice", "half") is removed, because words cannot be checked.
Sentences that fail are removed and counted.

Known limits: a number is checked against the cited facts, not against the meaning of
the sentence, so a sentence that cites two facts with the same unit and swaps their
numbers passes. Clock times ("17:00") and ranges are treated as plain numbers and are
removed unless each number is a cited fact. eval_llm/brief_eval.py measures how many
planted errors get through.
"""
from __future__ import annotations

import math
import re

from pydantic import BaseModel

from .ledger import Ledger

CITE = re.compile(r"\[(F\d+)\]")
_CITE_GROUP = re.compile(r"\[\s*(F\d+(?:\s*[,;]\s*F\d+)+)\s*\]")
_ONLY_CITES = re.compile(r"^(?:\[F\d+\]\s*)+[.!?]?$")
_LEADING_CITES = re.compile(r"^(?:\[F\d+\]\s*)+")
NUMBER = re.compile(r"(?<![\w.,])-?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)")
SENTENCE = re.compile(r"(?<=[.!?])\s+")
_UNITS = {"%": "%", "percent": "%", "minute": "min", "minutes": "min", "min": "min", "mins": "min",
          "hour": "h", "hours": "h", "hr": "h", "hrs": "h", "h": "h", "second": "s", "seconds": "s", "sec": "s",
          "mile": "mi", "miles": "mi", "mi": "mi", "km": "km", "kilometers": "km", "kilometres": "km",
          "knot": "kt", "knots": "kt", "kt": "kt", "kts": "kt", "mph": "mph", "feet": "ft", "ft": "ft",
          "kwh": "kwh"}
_UNIT_AFTER = re.compile(r"\s*(%|" + "|".join(sorted((u for u in _UNITS if u != "%"), key=len, reverse=True)) + r")(?![\w])",
                         re.I)
_NUMBER_WORDS = re.compile(
    r"\b(zero|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
    r"seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|"
    r"half|halve|twice|double|doubles|triple|quarter|dozen|couple)\b|[½¼¾⅓⅔]", re.I)


class VerifiedBrief(BaseModel):
    kept: list[str]
    removed: list[dict]

    @property
    def pass_rate(self) -> float:
        total = len(self.kept) + len(self.removed)
        return len(self.kept) / total if total else 1.0


def _numbers_match(written: str, value) -> bool:
    """True when `written` is the fact's value rounded to the decimals it is written with."""
    if isinstance(value, bool):
        return False
    try:
        found, v = float(written.replace(",", "")), float(value)
    except (TypeError, ValueError):
        return False
    if not (math.isfinite(found) and math.isfinite(v)):
        return False
    decimals = len(written.split(".")[1]) if "." in written else 0
    return abs(found - v) <= 0.5 * 10 ** -decimals + 1e-9


def _supported(number: str, unit: str | None, facts) -> bool:
    for fact in facts:
        if not _numbers_match(number, fact.value):
            continue
        fact_unit = _UNITS.get(fact.unit.strip().lower())
        if unit is None or fact_unit is None or unit == fact_unit:
            return True
    return False


def sentences(brief: str) -> list[str]:
    """Split into sentences. Citations written after the full stop stay with their sentence."""
    text = _CITE_GROUP.sub(lambda m: "".join(f"[{i.strip()}]" for i in re.split(r"[,;]", m.group(1))), brief)
    out: list[str] = []
    for part in (s.strip() for s in SENTENCE.split(text) if s.strip()):
        if out and _ONLY_CITES.match(part):
            out[-1] = f"{out[-1]} {part}"
            continue
        lead = _LEADING_CITES.match(part)
        if lead and out and not CITE.search(out[-1]):   # "It is 87%. [F4] The deadline..." -> [F4] belongs to the first
            out[-1] = f"{out[-1]} {lead.group().strip()}"
            part = part[lead.end():].strip()
        if part:
            out.append(part)
    return out


def verify(brief: str, ledger: Ledger) -> VerifiedBrief:
    kept, removed = [], []
    for sentence in sentences(brief):
        ids = CITE.findall(sentence)
        if not ids:
            removed.append({"sentence": sentence, "reason": "no citation"})
            continue
        facts = [ledger.get(i) for i in ids]
        if any(f is None for f in facts):
            removed.append({"sentence": sentence, "reason": "cites a fact that does not exist"})
            continue
        text = CITE.sub("", sentence)
        words = _NUMBER_WORDS.findall(text)
        if words:
            removed.append({"sentence": sentence, "reason": "numbers must be written as digits so they can be checked"})
            continue
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
