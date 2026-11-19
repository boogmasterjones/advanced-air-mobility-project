"""Engine routes. Owner: A (boogmasterjones). Facilities, case evaluation, and later forecast and replay."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException

from ..contracts import CaseIn, CaseOut
from ..core import decision, weather
from ..core.geo import heliports, nearest_station
from ..core.ledger import Ledger

router = APIRouter(prefix="/api")
FLORIDA = ZoneInfo("America/New_York")
DISCLAIMER = "PROTOTYPE. Not for real dispatch. Aircraft are simulated. Road times are modeled."


@router.get("/facilities")
def facilities(q: str = ""):
    """FAA-listed Florida heliports (the UI filters to hospital-style names)."""
    items = list(heliports().values())
    if q:
        items = [h for h in items if q.lower() in h["name"].lower() or q.lower() in h["city"].lower()]
    return items[:500]


@router.post("/cases/evaluate", response_model=CaseOut)
def evaluate_case(case: CaseIn):
    if case.as_of:
        raise HTTPException(501, "as_of (Time Machine) is not built yet; see task A6")
    pads = heliports()
    if case.origin_id not in pads or case.dest_id not in pads:
        raise HTTPException(404, "Unknown facility id")
    origin, dest = pads[case.origin_id], pads[case.dest_id]
    ledger = Ledger()

    # Weather at the nearest reporting airport to each end; the worse one decides.
    ends = [nearest_station(origin["lat"], origin["lon"]), nearest_station(dest["lat"], dest["lon"])]
    try:
        obs = weather.fetch_observations(sorted({s["icao"] for s, _ in ends}))
    except Exception:
        obs = {}
    statuses, reasons = [], []
    for station, miles in ends:
        o = obs.get(station["icao"])
        status, why = weather.flyable_now(o)
        statuses.append(status)
        reasons += [f"{station['icao']}: {r}" for r in why]
        ledger.add(f"Flyable now at {station['icao']} ({miles:.0f} mi from pad)", status,
                   source="aviationweather.gov METAR", confidence="official",
                   fetched_at=o.observed_at if o else None)
        if o and o.gust_kt is not None:
            ledger.add(f"Gust at {station['icao']}", o.gust_kt, unit="kt",
                       source="aviationweather.gov METAR", confidence="official", fetched_at=o.observed_at)

    if "UNKNOWN" in statuses:
        p_air = None
    else:
        p_air = 0.0 if "NOT_FLYABLE" in statuses else 0.9  # v0 placeholder; task A3 replaces it
    if p_air is not None:
        ledger.add("Chance the flight can launch (v0 rule, forecaster pending)", p_air,
                   source="weather rule in weather.py", confidence="assumption")

    local_hour = datetime.now(timezone.utc).astimezone(FLORIDA).hour
    options = decision.evaluate(origin=origin, dest=dest, deadline_min=case.deadline_min,
                                local_hour=local_hour, p_air_flies=p_air,
                                weather_reasons=reasons, ledger=ledger)
    return CaseOut(disclaimer=DISCLAIMER, origin=origin, dest=dest,
                   options=[o.model_dump() for o in options],
                   recommended=decision.recommend(options), facts=ledger.all(),
                   decision_owner="human dispatcher (approve / hold / override)")


@router.get("/forecast")
def forecast(station: str):
    raise HTTPException(501, "Forecaster not built yet; see task A3")


@router.get("/replay")
def replay(date: str, origin_id: str, dest_id: str, deadline_min: int):
    raise HTTPException(501, "Time Machine not built yet; see task A6")
