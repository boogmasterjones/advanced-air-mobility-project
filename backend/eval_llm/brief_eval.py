"""E5: the brief and its verifier.

Run from backend/:
    python -m eval_llm.brief_eval

Two measurements over replayed cases from the weather archive:
  1. Pass rate: of the sentences the writer produced, how many survived the verifier.
     The writer is the LLM when LLM_PROVIDER=anthropic and a key are set, otherwise the
     offline template (which is built to pass, so its number mostly proves the plumbing).
  2. Catch rate: we break sentences that were correct, on purpose, in four ways (change
     a number, remove the citation, cite a fact that does not exist, cite the wrong fact)
     and count how many the verifier removes. This needs no LLM and shows what the safety
     net catches when a writer gets something wrong.
Writes eval/results/e5.json.
"""
from __future__ import annotations

import random
import re
import sys
from datetime import timedelta

from app.contracts import CaseOut
from app.core import history
from app.core.case import build_case
from app.core.geo import heliports
from app.core.ledger import Ledger
from app.core.verifier import CITE, NUMBER, verify
from app.llm import brief, provider

from .common import llm_ready, now, save

PAIRS = [("9FA2", "48FD"), ("61FL", "7FD7"), ("7FD7", "FD28"), ("60FL", "64FD"), ("FA96", "FD28"), ("9FD3", "7FD7")]
N_CASES = 30


def cases(rng: random.Random) -> list[CaseOut]:
    span = history.available_range()
    if span is None:
        raise SystemExit("No replay archive. Run: python -m data_build.build_dataset")
    pads, out = heliports(), []
    hours = int((span[1] - span[0]).total_seconds() // 3600) - 20
    while len(out) < N_CASES:
        a, b = rng.choice(PAIRS)
        when = span[0] + timedelta(hours=8 + rng.randrange(hours))
        built = build_case(origin=pads[a], dest=pads[b], deadline_min=rng.choice((90, 120, 150)),
                           now=when, source=history.ArchiveWeather())
        out.append(CaseOut(**built.out))
    return out


ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
        "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def in_words(n: int) -> str:
    """0 to 999 in words, for planting a number the checker cannot read as digits."""
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("" if n % 10 == 0 else f"-{ONES[n % 10]}")
    rest = "" if n % 100 == 0 else f" {in_words(n % 100)}"
    return f"{ONES[n // 100]} hundred{rest}"


def broken_versions(sentence: str, ledger: Ledger, rng: random.Random) -> list[tuple[str, str]]:
    """Wrong variants of one correct sentence, each with the kind of error it carries.
    Every variant is really wrong: a variant that happens to stay true is not planted."""
    out = []
    body = CITE.sub("", sentence)
    cited = [ledger.get(i) for i in CITE.findall(sentence)]
    cited_ids = {f.id for f in cited}
    first = NUMBER.search(body)
    if first:
        value = int(float(first.group().replace(",", "")))
        wrong = value + 13
        if not any(isinstance(f.value, (int, float)) and not isinstance(f.value, bool)
                   and abs(float(f.value) - wrong) <= 0.5 for f in cited):
            out.append((sentence.replace(first.group(), str(wrong), 1), "number changed"))
        if 0 <= wrong < 1000:
            out.append((sentence.replace(first.group(), in_words(wrong), 1), "wrong number written as a word"))
        for a, b in ((" min", " hours"), ("%", " min")):
            if first.group() + a in sentence:
                out.append((sentence.replace(first.group() + a, first.group() + b, 1), "unit changed"))
                break
        # A real fact with a different number: the sentence now cites a receipt that says something else.
        others = [f for f in ledger.all() if f.id not in cited_ids and isinstance(f.value, (int, float))
                  and not isinstance(f.value, bool) and abs(float(f.value) - value) > 0.5]
        if others:
            out.append((CITE.sub("", sentence).rstrip(". ") + f" [{rng.choice(others).id}].", "cites the wrong fact"))
    out.append((re.sub(r"\s*(\[F\d+\])+", "", sentence), "citation removed"))
    out.append((CITE.sub("[F999]", sentence), "cites a fact that does not exist"))
    return out


def main() -> int:
    rng = random.Random(5)
    kept = removed = planted = caught = 0
    by_kind: dict[str, list[int]] = {}
    escapes, writer = [], ""
    for case in cases(rng):
        ledger = Ledger.from_facts(case.facts)
        result = brief.make_brief(case)
        writer = result.provider
        kept += len(result.sentences)
        removed += len(result.removed)
        for sentence in verify(brief.template_brief(case), ledger).kept:
            for bad, kind in broken_versions(sentence, ledger, rng):
                planted += 1
                was_caught = not verify(bad, ledger).kept
                caught += was_caught
                n, c = by_kind.get(kind, [0, 0])
                by_kind[kind] = [n + 1, c + was_caught]
                if not was_caught and len(escapes) < 10:
                    escapes.append({"kind": kind, "sentence": bad})
    written = kept + removed
    out = {
        "id": "E5", "generated_at": now(), "writer": writer, "cases": N_CASES,
        "sentences_written": written, "sentences_kept": kept, "sentences_removed": removed,
        "pass_rate": round(kept / written, 4) if written else None,
        "planted_errors": planted, "planted_errors_caught": caught,
        "catch_rate": round(caught / planted, 4) if planted else None,
        "catch_rate_by_kind": {k: {"planted": n, "caught": c} for k, (n, c) in sorted(by_kind.items())},
        "errors_that_slipped_through": escapes,
        "metrics": [
            {"id": "E5", "name": "Planted errors the verifier caught",
             "value": round(caught / planted, 4) if planted else None, "baseline": 0.0,
             "note": f"{planted} deliberately wrong sentences (changed number, number written as a word, wrong "
                     f"unit, missing citation, made-up fact, wrong fact) built from {N_CASES} replayed cases. "
                     f"Without a verifier none would be caught."},
            {"id": "E5", "name": "Brief sentences that passed the check",
             "value": round(kept / written, 4) if written else None, "baseline": None,
             "note": f"{written} sentences over {N_CASES} replayed cases. Writer: {writer}."
                     + ("" if llm_ready() else " The offline template is built to pass; run with an LLM key "
                                               "to measure a real writer.")},
        ],
    }
    save("e5.json", out)
    print(f"Writer: {writer}")
    print(f"Sentences: {kept} kept, {removed} removed ({out['pass_rate']:.1%} pass)")
    print(f"Planted errors: {caught}/{planted} caught ({out['catch_rate']:.1%})")
    for kind, (n, c) in sorted(by_kind.items()):
        print(f"   {kind:34} {c}/{n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
