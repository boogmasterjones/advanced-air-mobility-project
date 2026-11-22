#!/usr/bin/env python3
"""Copy the evidence numbers from eval/results/*.json into README.md.

The README table and the app's Evidence tab both read the same result files, so they can
never disagree. A test (backend/tests/test_docs.py) fails if the README is out of date.

Run from the repo root:   python scripts/update_readme_evidence.py
Standard library only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "eval" / "results"
README = REPO / "README.md"
START, END = "<!-- EVIDENCE:START -->", "<!-- EVIDENCE:END -->"
IDS = ("E1", "E2", "E3", "E4", "E5", "E6")


def show(value) -> str:
    if value is None:
        return "not run"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def table() -> str:
    lines = ["| Test | What was measured | Result | Compare with | How to read it |", "|---|---|---|---|---|"]
    for eval_id in IDS:
        path = RESULTS / f"{eval_id.lower()}.json"
        try:
            metrics = json.loads(path.read_text(encoding="utf-8"))["metrics"]
        except (OSError, ValueError, KeyError):
            lines.append(f"| {eval_id} | | not run | | Run the script for {eval_id} (see below). |")
            continue
        for m in metrics:
            note = str(m.get("note", "")).replace("|", "/").replace("\n", " ")
            baseline = "" if m.get("baseline") is None else show(m["baseline"])
            lines.append(f"| {m['id']} | {m['name']} | **{show(m.get('value'))}** | {baseline} | {note} |")
    return "\n".join(lines)


def render(readme: str) -> str:
    head, rest = readme.split(START, 1)
    _, tail = rest.split(END, 1)
    return f"{head}{START}\n{table()}\n{END}{tail}"


def main() -> int:
    current = README.read_text(encoding="utf-8")
    updated = render(current)
    if "--check" in sys.argv:
        if updated != current:
            print("README evidence table is out of date. Run: python scripts/update_readme_evidence.py")
            return 1
        print("README evidence table is up to date.")
        return 0
    README.write_text(updated, encoding="utf-8", newline="\n")
    print("README evidence table updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
