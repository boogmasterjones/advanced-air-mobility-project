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
        built = build_case(origin=pads[a], dest=pads[b], deadline_min=rng.choice((45, 60, 90)),
                           now=when, source=history.ArchiveWeather())
        out.append(CaseOut(**built.out))
    return out


def broken_versions(sentence: str, ledger: Ledger, rng: random.Random) -> list[tuple[str, str]]:
    """Wrong variants of one correct sentence, each with the kind of error it carries."""
    out = []
    body = CITE.sub("", sentence)
    cited = set(CITE.findall(sentence))
    cited_values = {str(ledger.get(i).value) for i in cited}
    for m in NUMBER.finditer(body):
        wrong = str(int(float(m.group())) + 13)
        if wrong not in cited_values:
            bad = sentence.replace(m.group(), wrong, 1)
            out.append((bad, "number changed"))
            break
    out.append((re.sub(r"\s*(\[F\d+\])+", "", sentence), "citation removed"))
    out.append((CITE.sub("[F999]", sentence), "cites a fact that does not exist"))
    others = [f.id for f in ledger.all() if f.id not in cited and isinstance(f.value, str)]
    if others and NUMBER.search(body):
        out.append((CITE.sub("", sentence).rstrip(". ") + f" [{rng.choice(others)}].", "cites the wrong fact"))
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
             "note": f"{planted} deliberately wrong sentences (changed number, missing citation, made-up fact, "
                     f"wrong fact) built from {N_CASES} replayed cases. Without a verifier none would be caught."},
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
