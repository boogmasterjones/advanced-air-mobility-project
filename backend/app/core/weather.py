"""Live airport weather and a simple, rule-based "flyable now" check.

The thresholds below are labeled assumptions (real air taxi limits are unpublished).
The ML forecaster that predicts the next 0-3 hours will replace `flyable_now` as the
input to the decision engine; this module stays as the observation layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

AWC_URL = "https://aviationweather.gov/api/data/metar"
USER_AGENT = "car-or-air-hackathon/0.1"

# Assumptions (see RESEARCH.md section 6). Change here, never in the UI or the LLM.
THRESHOLDS = {
    "min_visibility_mi": 3.0,
    "min_ceiling_ft": 1000,
    "max_gust_kt": 25,
    "max_obs_age_min": 90,
}


@dataclass
class Observation:
    station: str
    observed_at: datetime
    visibility_mi: float | None
    ceiling_ft: int | None
    wind_kt: float | None
    gust_kt: float | None
    thunderstorm: bool
    raw: str


def parse_metar_json(item: dict) -> Observation:
    vis = item.get("visib")
    if isinstance(vis, str):  # AWC reports "10+" for 10 or more miles
        vis = float(vis.rstrip("+")) if vis.rstrip("+").replace(".", "", 1).isdigit() else None
    ceiling = None
    for layer in item.get("clouds") or []:
        if layer.get("cover") in ("BKN", "OVC", "OVX") and layer.get("base") is not None:
            ceiling = layer["base"] if ceiling is None else min(ceiling, layer["base"])
    wx = item.get("wxString") or ""
    return Observation(
        station=item["icaoId"],
        observed_at=datetime.fromtimestamp(item["obsTime"], tz=timezone.utc),
        visibility_mi=vis,
        ceiling_ft=ceiling,
        wind_kt=item.get("wspd"),
        gust_kt=item.get("wgst"),
        thunderstorm="TS" in wx,
        raw=item.get("rawOb", ""),
    )


def fetch_observations(stations: list[str], timeout: float = 15.0) -> dict[str, Observation]:
    resp = httpx.get(AWC_URL, params={"ids": ",".join(stations), "format": "json"},
                     headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    return {o.station: o for o in map(parse_metar_json, resp.json())}


def flyable_now(obs: Observation | None, now: datetime | None = None) -> tuple[str, list[str]]:
    """Return ("FLYABLE" | "NOT_FLYABLE" | "UNKNOWN", reasons). Missing or stale data is UNKNOWN."""
    now = now or datetime.now(timezone.utc)
    if obs is None:
        return "UNKNOWN", ["no weather report available"]
    age_min = (now - obs.observed_at).total_seconds() / 60
    if age_min > THRESHOLDS["max_obs_age_min"]:
        return "UNKNOWN", [f"weather report is {age_min:.0f} min old"]
    reasons = []
    if obs.thunderstorm:
        reasons.append("thunderstorm reported")
    if obs.visibility_mi is not None and obs.visibility_mi < THRESHOLDS["min_visibility_mi"]:
        reasons.append(f"visibility {obs.visibility_mi} mi")
    if obs.ceiling_ft is not None and obs.ceiling_ft < THRESHOLDS["min_ceiling_ft"]:
        reasons.append(f"cloud ceiling {obs.ceiling_ft} ft")
    if obs.gust_kt is not None and obs.gust_kt > THRESHOLDS["max_gust_kt"]:
        reasons.append(f"gusts {obs.gust_kt} kt")
    if obs.visibility_mi is None:
        return "UNKNOWN", ["visibility missing from report"]
    return ("NOT_FLYABLE", reasons) if reasons else ("FLYABLE", [])
