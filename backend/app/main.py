"""Car or Air API. Serves the built frontend from /, the API under /api."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .core import decision, weather
from .core.geo import heliports, nearest_station
from .core.ledger import Ledger
from .llm import provider

app = FastAPI(title="Car or Air", version="0.1.0")
FLORIDA = ZoneInfo("America/New_York")
DISCLAIMER = ("PROTOTYPE. Not for real dispatch. Aircraft are simulated. "
              "Road times are modeled.")


@app.get("/api/health")
def health():
    return {"ok": True, "disclaimer": DISCLAIMER}


@app.get("/api/facilities")
def facilities(q: str = ""):
    """FAA-listed Florida heliports (rough filter for hospital names lives in the UI)."""
    items = list(heliports().values())
    if q:
        items = [h for h in items if q.lower() in h["name"].lower() or q.lower() in h["city"].lower()]
    return items[:500]


class CaseIn(BaseModel):
    origin_id: str
    dest_id: str
    deadline_min: int = Field(ge=1, le=48 * 60)
    category: str = "other"


@app.post("/api/cases/evaluate")
def evaluate_case(case: CaseIn):
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
        p_air = 0.0 if "NOT_FLYABLE" in statuses else 0.9  # v0 placeholder until the forecaster lands
    if p_air is not None:
        ledger.add("Chance the flight can launch (v0 rule, forecaster pending)", p_air,
                   source="weather rule in weather.py", confidence="assumption")

    local_hour = datetime.now(timezone.utc).astimezone(FLORIDA).hour
    options = decision.evaluate(origin=origin, dest=dest, deadline_min=case.deadline_min,
                                local_hour=local_hour, p_air_flies=p_air,
                                weather_reasons=reasons, ledger=ledger)
    return {
        "disclaimer": DISCLAIMER,
        "origin": origin, "dest": dest,
        "options": [o.model_dump() for o in options],
        "recommended": decision.recommend(options),
        "facts": [f.model_dump(mode="json") for f in ledger.all()],
        "decision_owner": "human dispatcher (approve / hold / override)",
    }


class IntakeIn(BaseModel):
    text: str = Field(max_length=4000)


@app.post("/api/intake")
def intake(body: IntakeIn):
    result = provider.intake(body.text)
    return {"result": result.model_dump(), "confirm_required": True}


STATIC = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if STATIC.exists():
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="frontend")
