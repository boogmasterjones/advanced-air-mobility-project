"""Airport weather reports and the rule that says whether one report is "flyable".

This is the observation layer. The thresholds below are labeled assumptions (real air taxi
limits are unpublished). The same rule is used to judge live reports, to label the
training data for the forecaster, and to score the official forecast, so there is exactly
one definition of "flyable" in the whole project.
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
    temp_c: float | None = None
    dewpoint_c: float | None = None
    altimeter_hpa: float | None = None
    wind_dir: float | None = None
    precip_in: float | None = None


def problems(visibility_mi: float | None, ceiling_ft: float | None, wind_kt: float | None,
             gust_kt: float | None, thunderstorm: bool) -> list[str]:
    """Plain-language reasons a report fails the thresholds. Empty list means flyable."""
    reasons = []
    if thunderstorm:
        reasons.append("thunderstorm reported")
    if visibility_mi is not None and visibility_mi < THRESHOLDS["min_visibility_mi"]:
        reasons.append(f"visibility {visibility_mi:g} mi")
    if ceiling_ft is not None and ceiling_ft < THRESHOLDS["min_ceiling_ft"]:
        reasons.append(f"cloud ceiling {ceiling_ft:g} ft")
    strongest = max((w for w in (wind_kt, gust_kt) if w is not None), default=None)
    if strongest is not None and strongest > THRESHOLDS["max_gust_kt"]:
        reasons.append(f"wind gusts {strongest:g} kt")
    return reasons


def report_is_flyable(obs: Observation) -> bool | None:
    """False when the report shows any problem, True when it shows none and is complete,
    None when it shows none but lacks visibility or wind (it cannot be judged, so it is
    not used). A thunderstorm report with no visibility still counts as not flyable."""
    if problems(obs.visibility_mi, obs.ceiling_ft, obs.wind_kt, obs.gust_kt, obs.thunderstorm):
        return False
    if obs.visibility_mi is None or (obs.wind_kt is None and obs.gust_kt is None):
        return None
    return True


MAX_PLAUSIBLE_WIND_KT = 130.0


def clean_wind(direction: float | None, speed: float | None, gust: float | None
               ) -> tuple[float | None, float | None, float | None]:
    """Drop wind values that cannot be right. Hand-typed reports sometimes carry typos
    such as "030086G16KT" (86 kt steady wind with a 16 kt gust) or "30669KT" (direction
    306). A value we cannot trust becomes None (unknown), never a corrected guess.
      * the steady wind is higher than the gust reported with it
      * the direction is not a multiple of 10 degrees (reports only use tens)
      * any speed above 130 kt
      * a steady wind above 60 kt with no gust reported (real storms always report gusts)
      * a gust above 90 kt that is far out of line with the steady wind ("16G227KT")
    Returns (direction, speed, gust)."""
    if direction is not None and direction % 10 != 0:
        return None, None, None
    if speed is not None and gust is not None and speed > gust:
        speed = None
    if speed is not None and (not 0 <= speed <= MAX_PLAUSIBLE_WIND_KT or (speed > 60 and gust is None)):
        speed = None
    if gust is not None and not 0 <= gust <= MAX_PLAUSIBLE_WIND_KT:
        gust = None
    if gust is not None and gust > 90 and gust > 2 * (speed or 0) + 20:
        gust = None
    return direction, speed, gust


def in_range(value: float | None, low: float, high: float) -> float | None:
    """The value, or None when it is outside what is physically possible in Florida."""
    return value if value is not None and low <= value <= high else None


# Limits for the checks above and below. Wide on purpose: they remove typos ("160SM",
# "A3993", minus 16 C in Brooksville), not unusual weather. Hurricane lows stay in.
VISIBILITY_MI = (0.0, 20.0)
TEMP_C = (-15.0, 48.0)
PRESSURE_HPA = (897.0, 1057.0)


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_metar_json(item: dict) -> Observation:
    vis = item.get("visib")
    if isinstance(vis, str):  # AWC reports "10+" for 10 or more miles
        vis = float(vis.rstrip("+")) if vis.rstrip("+").replace(".", "", 1).isdigit() else None
    ceiling = None
    for layer in item.get("clouds") or []:
        if layer.get("cover") in ("BKN", "OVC", "OVX", "VV") and layer.get("base") is not None:
            ceiling = layer["base"] if ceiling is None else min(ceiling, layer["base"])
    wx = item.get("wxString") or ""
    wind_dir, wind_kt, gust_kt = clean_wind(_num(item.get("wdir")), _num(item.get("wspd")), _num(item.get("wgst")))
    return Observation(
        station=item["icaoId"],
        observed_at=datetime.fromtimestamp(item["obsTime"], tz=timezone.utc),
        visibility_mi=in_range(vis, *VISIBILITY_MI),
        ceiling_ft=ceiling,
        wind_kt=wind_kt,
        gust_kt=gust_kt,
        thunderstorm="TS" in wx,
        raw=item.get("rawOb", ""),
        temp_c=in_range(_num(item.get("temp")), *TEMP_C),
        dewpoint_c=in_range(_num(item.get("dewp")), *TEMP_C),
        altimeter_hpa=in_range(_num(item.get("altim")), *PRESSURE_HPA),
        wind_dir=wind_dir,  # "VRB" becomes None
        precip_in=_num(item.get("precip")),
    )


def fetch_history(stations: list[str], hours: int = 8, timeout: float = 15.0) -> dict[str, list[Observation]]:
    """Every report from the last `hours` hours for each station, oldest first."""
    resp = httpx.get(AWC_URL, params={"ids": ",".join(stations), "format": "json", "hours": hours},
                     headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    out: dict[str, list[Observation]] = {s: [] for s in stations}
    for item in resp.json() if resp.content else []:
        try:
            o = parse_metar_json(item)
        except (KeyError, TypeError, ValueError):
            continue  # one malformed report must not hide the rest
        out.setdefault(o.station, []).append(o)
    for reports in out.values():
        reports.sort(key=lambda o: o.observed_at)
    return out


def fetch_observations(stations: list[str], timeout: float = 15.0) -> dict[str, Observation]:
    """Latest report per station (kept for callers that only need 'now')."""
    history = fetch_history(stations, hours=3, timeout=timeout)
    return {s: reports[-1] for s, reports in history.items() if reports}


def flyable_now(obs: Observation | None, now: datetime | None = None) -> tuple[str, list[str]]:
    """Return ("FLYABLE" | "NOT_FLYABLE" | "UNKNOWN", reasons). Missing or stale data is UNKNOWN."""
    now = now or datetime.now(timezone.utc)
    if obs is None:
        return "UNKNOWN", ["no weather report available"]
    age_min = (now - obs.observed_at).total_seconds() / 60
    if age_min > THRESHOLDS["max_obs_age_min"]:
        return "UNKNOWN", [f"weather report is {age_min:.0f} min old"]
    reasons = problems(obs.visibility_mi, obs.ceiling_ft, obs.wind_kt, obs.gust_kt, obs.thunderstorm)
    if reasons:
        return "NOT_FLYABLE", reasons
    if report_is_flyable(obs) is None:
        return "UNKNOWN", ["visibility or wind missing from report"]
    return "FLYABLE", []
