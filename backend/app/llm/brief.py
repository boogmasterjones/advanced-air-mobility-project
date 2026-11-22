"""The case brief: a few plain sentences about one case, every number backed by a receipt.

Flow: the facts of the case go to the LLM as a numbered list -> the LLM writes sentences
that cite fact ids -> core/verifier.py checks every sentence (cited ids exist, every
number matches a cited fact) and removes the ones that fail -> the screen shows what was
kept, what was removed and why.

Without an LLM (offline provider, or the LLM failed) a fixed template writes the brief
from the same facts. It goes through the same verifier, so the rule "no number without a
receipt" is enforced the same way for both.
"""
from __future__ import annotations

from ..contracts import BriefOut, CaseOut
from ..core.ledger import Fact, Ledger
from ..core.verifier import verify
from . import provider

MAX_SENTENCES = 6


def facts_text(facts: list[Fact]) -> str:
    """The numbered fact list the LLM sees. Nothing else about the case is sent."""
    lines = []
    for f in facts:
        value = f"{f.value} {f.unit}".strip()
        lines.append(f"{f.id} | {f.label} | {value} | source: {f.source} | {f.confidence}")
    return "\n".join(lines)


def template_brief(case: CaseOut) -> str:
    """Brief written by code from the facts. Used offline and as the fallback."""
    by_label = {f.label: f for f in case.facts}

    def find(label: str) -> Fact | None:
        return by_label.get(label)

    out = []
    suggestion, deadline = find("Option the engine suggests"), find("Deadline")
    if suggestion:
        out.append(f"The engine suggests: {suggestion.value} [{suggestion.id}].")
    for name in ("Ground ambulance only", "Air taxi only", "Air taxi with ground backup"):
        chance, typical = find(f"{name}: chance to arrive by the deadline"), find(f"{name}: typical time")
        status = find(f"{name}: status")
        if chance and typical and deadline:
            out.append(f"{name} has a {chance.value}% chance to arrive within the {deadline.value} min "
                       f"deadline, with a typical time of {typical.value} min "
                       f"[{chance.id}][{typical.id}][{deadline.id}].")
        elif status:
            out.append(f"{name} is {str(status.value).lower()}, so it has no numbers [{status.id}].")
    weather = find("Chance the weather stays flyable for the flight")
    if weather:
        out.append(f"The forecaster gives a {weather.value}% chance that the weather stays flyable "
                   f"for the flight [{weather.id}].")
    if suggestion:
        out.append(f"This is advice only and a person makes the final decision [{suggestion.id}].")
    return " ".join(out[:MAX_SENTENCES])


def make_brief(case: CaseOut) -> BriefOut:
    ledger = Ledger.from_facts(case.facts)
    text, used = provider.brief_text(facts_text(case.facts))
    checked = verify(text, ledger) if text else None
    if checked is None or not checked.kept:
        # No LLM, or nothing it wrote survived the check: fall back to the template.
        llm_removed = checked.removed if checked else []
        checked = verify(template_brief(case), ledger)
        checked.removed = llm_removed + checked.removed
        if text:
            used = f"offline template (every LLM sentence failed the check; was {used})"
    return BriefOut(sentences=checked.kept[:MAX_SENTENCES], removed=checked.removed,
                    pass_rate=round(checked.pass_rate, 3), provider=used)
