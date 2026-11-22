"""Engine routes. Owner: A (boogmasterjones). Facilities, case evaluation, forecast, replay."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from fastapi import APIRouter, HTTPException

from ..contracts import CaseIn, CaseOut, ForecastOut, ForecastPoint, ReplayOut, ReplayRange
from ..core import history, replay as replay_engine, weather
from ..core.case import DISCLAIMER, build_case
from ..core.forecaster import from_reports
from ..core.geo import DATA_DIR, heliports, stations
from ..core.ledger import Ledger

router = APIRouter(prefix="/api")


@lru_cache
def trauma_centers() -> dict[str, dict]:
    """FAA pad id -> the state's row for that trauma center (hand-checked list of 36)."""
    path = DATA_DIR / "seeds" / "trauma_centers.csv"
    if not path.exists():
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        return {r["faa_id"]: r for r in csv.DictReader(f) if r["faa_id"]}


@router.get("/facilities")
def facilities(q: str = ""):
    """FAA-listed Florida heliports (the UI filters to hospital-style names). Trauma
    centers also carry their level and the name the state uses, which is the name people
    know ("UF Health Shands Hospital" is "SHANDS HELISTOP" in the FAA list)."""
    centers = trauma_centers()
    items = [{**h, "trauma_level": centers.get(h["faa_id"], {}).get("level"),
              "known_as": centers.get(h["faa_id"], {}).get("name")} for h in heliports().values()]
    if q:
        items = [h for h in items if q.lower() in h["name"].lower() or q.lower() in h["city"].lower()]
    return items[:500]


def _pads(origin_id: str, dest_id: str) -> tuple[dict, dict]:
    pads = heliports()
    if origin_id not in pads or dest_id not in pads:
        raise HTTPException(404, "Unknown facility id")
    if origin_id == dest_id:
        raise HTTPException(422, "Pick-up and drop-off must be different places")
    centers = trauma_centers()

    def with_names(pad: dict) -> dict:
        row = centers.get(pad["faa_id"], {})
        return {**pad, "trauma_level": row.get("level"), "known_as": row.get("name")}

    return with_names(pads[origin_id]), with_names(pads[dest_id])


def _time(text: str) -> datetime:
    try:
        when = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(422, "Time must look like 2024-07-15T19:00Z") from None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _replay(origin_id: str, dest_id: str, deadline_min: int, as_of: str) -> dict:
    origin, dest = _pads(origin_id, dest_id)
    when, span = _time(as_of), history.available_range()
    if span is None:
        raise HTTPException(503, "The weather archive is not installed on this server")
    if not (span[0] + timedelta(hours=6) <= when <= span[1] - timedelta(hours=4)):
        raise HTTPException(422, f"Pick a time between {span[0]:%Y-%m-%d} and {span[1]:%Y-%m-%d}")
    return replay_engine.replay(origin=origin, dest=dest, deadline_min=deadline_min, as_of=when)


@router.post("/cases/evaluate", response_model=CaseOut)
def evaluate_case(case: CaseIn):
    if case.as_of:  # Time Machine: answer as the app would have at that moment
        return _replay(case.origin_id, case.dest_id, case.deadline_min, case.as_of)["then"]
    origin, dest = _pads(case.origin_id, case.dest_id)
    return build_case(origin=origin, dest=dest, deadline_min=case.deadline_min,
                      now=datetime.now(timezone.utc)).out


@router.get("/forecast", response_model=ForecastOut)
def forecast(station: str):
    """Chance the airport stays flyable for each of the next four hours."""
    icao = station.upper()
    st = next((s for s in stations() if s["icao"] == icao), None)
    if st is None:
        raise HTTPException(404, "Unknown station; see data/seeds/stations.csv")
    now = datetime.now(timezone.utc)
    try:
        reports = weather.fetch_history([icao]).get(icao, [])
    except Exception:
        raise HTTPException(503, "Weather service did not answer; forecast UNKNOWN") from None
    fc = from_reports(reports, st["lat"], st["lon"], now)
    if fc is None:
        raise HTTPException(503, "No fresh weather report for this airport; forecast UNKNOWN")
    ledger = Ledger(now=now)
    ids = [ledger.add(f"Newest weather report used for {icao}", fc.issued_at.isoformat(),
                      source="aviationweather.gov airport weather report", confidence="official",
                      fetched_at=fc.issued_at)]
    return ForecastOut(station=icao, issued_at=fc.issued_at.isoformat(), fact_ids=ids,
                       points=[ForecastPoint(hours_ahead=h, p_flyable=round(p, 3), model=fc.model)
                               for h, p in sorted(fc.p_flyable.items())])


@router.get("/replay", response_model=ReplayOut)
def replay(date: str, origin_id: str, dest_id: str, deadline_min: int):
    if not 1 <= deadline_min <= 48 * 60:
        raise HTTPException(422, "deadline_min must be between 1 and 2880")
    return _replay(origin_id, dest_id, deadline_min, date)


@router.get("/replay/range", response_model=ReplayRange)
def replay_range():
    span = history.available_range()
    return ReplayRange(first=span[0].isoformat() if span else None,
                       last=span[1].isoformat() if span else None,
                       stations=sorted(history.archive()))
