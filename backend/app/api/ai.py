"""LLM routes. Owner: B (Jaden). Intake, brief and evidence."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter

from ..contracts import BriefIn, BriefOut, EvalMetric, EvidenceOut, IntakeIn, IntakeOut
from ..core.geo import DATA_DIR
from ..llm import brief as brief_writer
from ..llm import match, provider

router = APIRouter(prefix="/api")
RESULTS_DIR = DATA_DIR.parent / "eval" / "results"

# What each evidence number is, shown even before its eval has been run.
PLANNED = {
    "E1": "Forecaster accuracy against three baselines",
    "E2": "Decision regret on replayed past days",
    "E3": "Intake accuracy: LLM against a simple parser",
    "E4": "Prompt-injection cases handled safely",
    "E5": "Brief sentences that pass the number check",
    "E6": "Sanity check of the time model (helicopter break-even distance)",
}


@router.post("/intake", response_model=IntakeOut)
def intake(body: IntakeIn):
    """Free text -> form fields. The human reviews and confirms; nothing is dispatched here."""
    result, used = provider.intake(body.text)
    origin, dest = match.candidates(result.origin_name), match.candidates(result.dest_name)
    return IntakeOut(
        result=result, confirm_required=True, provider=used,
        origin_matches=origin, dest_matches=dest,
        origin_id=origin[0]["faa_id"] if match.confident(origin) else None,
        dest_id=dest[0]["faa_id"] if match.confident(dest) else None)


@router.post("/brief", response_model=BriefOut)
def brief(body: BriefIn):
    return brief_writer.make_brief(body.case)


@router.get("/evidence", response_model=EvidenceOut)
def evidence():
    """Every eval script writes eval/results/eN.json with a top-level "metrics" list.
    This reads them as they are. Evals that have not run show as pending, never as numbers."""
    metrics: list[EvalMetric] = []
    details, newest = {}, None
    for eval_id, title in PLANNED.items():
        path = RESULTS_DIR / f"{eval_id.lower()}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            rows = [EvalMetric(**m) for m in data["metrics"]]
        except (OSError, ValueError, KeyError, TypeError):
            metrics.append(EvalMetric(id=eval_id, name=title, value=None, note="not run yet"))
            continue
        metrics += rows
        details[eval_id] = data
        stamp = data.get("generated_at")
        newest = max(newest, stamp) if newest and stamp else (stamp or newest)
    return EvidenceOut(generated_at=newest or datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       metrics=metrics, details=details)
