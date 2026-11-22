"""E3: how well does intake turn free text into the right fields? LLM vs a regex parser.

Run from backend/ (after eval_llm.make_intake_cases):
    python -m eval_llm.intake_eval
With LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY set, the LLM is scored too (100 short
requests; this costs a little money). Without them only the regex baseline is scored and
the LLM numbers stay empty: they are never estimated.

A field counts as right only if it equals the expected value exactly. "Not stated" is a
value too: inventing a deadline that was not in the text is wrong. Facility names count as
right when code (llm/match.py) resolves the extracted name to the expected pad.
Writes eval/results/e3.json.
"""
from __future__ import annotations

import sys

from .common import NO_LLM, extract, llm_label, llm_ready, load, now, save

FIELDS = ("category", "origin_id", "dest_id", "deadline_min", "people")


def score(cases: list[dict], parser: str) -> dict:
    right = {f: 0 for f in FIELDS}
    all_right, by_tag, misses, failures = 0, {}, [], 0
    for case in cases:
        got = extract(case["text"], parser)
        failures += got["failed"] is not None
        ok = {f: got[f] == case["expected"][f] for f in FIELDS}
        for f in FIELDS:
            right[f] += ok[f]
        core = all(ok[f] for f in FIELDS if f != "people")
        all_right += core
        for tag in case["tags"] or ["plain"]:
            n, good = by_tag.get(tag, (0, 0))
            by_tag[tag] = (n + 1, good + core)
        if not core and len(misses) < 15:
            misses.append({"id": case["id"], "text": case["text"],
                           "wrong": {f: {"expected": case["expected"][f], "got": got[f]}
                                     for f in FIELDS if not ok[f]}})
    n = len(cases)
    return {"cases": n, "field_accuracy": {f: round(right[f] / n, 3) for f in FIELDS},
            "all_main_fields_right": round(all_right / n, 3), "llm_call_failures": failures,
            "by_tag": {t: {"cases": c, "all_main_fields_right": round(g / c, 3)} for t, (c, g) in sorted(by_tag.items())},
            "sample_misses": misses}


def main() -> int:
    cases = load("intake_cases.json")["cases"]
    regex = score(cases, "regex")
    llm = score(cases, "llm") if llm_ready() else None
    note = (f"{len(cases)} synthetic requests (typos, abbreviations, Spanish mix, missing fields). Share of "
            f"requests with category, both facilities and deadline all right. Baseline: a regex parser.")
    save("e3.json", {
        "id": "E3", "generated_at": now(), "llm": llm_label(), "regex": regex, "llm_results": llm,
        "metrics": [{"id": "E3", "name": "Intake: requests with every main field right",
                     "value": llm["all_main_fields_right"] if llm else None,
                     "baseline": regex["all_main_fields_right"],
                     "note": note if llm else f"{note} {NO_LLM}."}],
    })
    print(f"{'parser':8} {'all main':>9} " + " ".join(f"{f:>13}" for f in FIELDS))
    for name, r in (("regex", regex), ("llm", llm)):
        if r:
            print(f"{name:8} {r['all_main_fields_right']:>9.0%} "
                  + " ".join(f"{r['field_accuracy'][f]:>13.0%}" for f in FIELDS))
    if not llm:
        print(NO_LLM)
    return 0


if __name__ == "__main__":
    sys.exit(main())
