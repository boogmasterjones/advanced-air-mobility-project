"""Shared pieces for the LLM evals (E3 intake, E4 injection, E5 brief)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from app.core.geo import DATA_DIR
from app.llm import match, provider

DATASETS = DATA_DIR.parent / "eval" / "datasets"
RESULTS = DATA_DIR.parent / "eval" / "results"
NO_LLM = "LLM not run: set LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY, then run this script again"


def llm_ready() -> bool:
    return provider.provider_name() == "anthropic" and bool(os.environ.get("ANTHROPIC_API_KEY"))


def llm_label() -> str | None:
    return provider.describe("INTAKE") if llm_ready() else None


def extract(text: str, parser: str) -> dict:
    """Run one parser ("regex" or "llm") and resolve the names to pads, as the app does.
    An LLM failure counts as an empty answer, which is what the human would be shown."""
    try:
        result = provider.regex_intake(text) if parser == "regex" else provider._anthropic_intake(text)
        failed = None
    except provider.LLMUnavailable as err:
        result, failed = provider.regex_intake(""), str(err)
    origin, dest = match.candidates(result.origin_name), match.candidates(result.dest_name)
    return {
        "category": result.category, "deadline_min": result.deadline_min, "people": result.people,
        "origin_id": origin[0]["faa_id"] if origin else None,
        "dest_id": dest[0]["faa_id"] if dest else None,
        "texts": [result.origin_name or "", result.dest_name or "", result.notes],
        "needs_human_review": result.needs_human_review, "failed": failed,
    }


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(name: str) -> dict:
    return json.loads((DATASETS / name).read_text(encoding="utf-8"))


def save(name: str, doc: dict) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / name).write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
