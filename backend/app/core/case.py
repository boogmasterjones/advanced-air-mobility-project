"""Builds the full answer for one case: weather, forecast, road, energy, options, receipts.

The live endpoint and the Time Machine both call `build_case`. The only difference is
where the weather comes from (a `WeatherSource`): live reports from the Aviation Weather
Center, or the archive of past reports cut off at the replay time. Everything after that
is the same code, so a replay shows exactly what the live app would have said.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol
from zoneinfo import ZoneInfo

from . import decision, forecaster, roads, weather
from .energy import Wind
from .features import CEILING_CAP_FT, HourRecord
from .geo import haversine_mi, nearest_station, station_neighbors
from .ledger import Ledger

FLORIDA = ZoneInfo("America/New_York")
DISCLAIMER = "PROTOTYPE. Not for real dispatch. Aircraft are simulated. Road times are modeled."
DECISION_OWNER = "human dispatcher (approve / hold / override)"


@dataclass
class StationWeather:
    """What is known about one airport at the decision time."""
    observed_at: datetime | None = None
    visibility_mi: float | None = None
    ceiling_ft: float | None = None      # None means no ceiling reported
    wind_kt: float | None = None
    gust_kt: float | None = None
    wind_dir: float | None = None
    thunderstorm: bool = False
    temp_c: float | None = None
    forecast: forecaster.Forecast | None = None
    source: str = ""


class WeatherSource(Protocol):
    def station(self, station: dict, now: datetime) -> StationWeather: ...


class LiveWeather:
    """Reports from the Aviation Weather Center. One request covers all stations."""
    source = "aviationweather.gov airport weather report"

    def __init__(self, icaos: list[str]) -> None:
        wanted = set(icaos) | {code for i in icaos for code, _ in station_neighbors(i)}
        try:
            self.reports = weather.fetch_history(sorted(wanted))
        except Exception:
            self.reports = {}  # network trouble: every station becomes UNKNOWN

    def station(self, station: dict, now: datetime) -> StationWeather:
        reports = self.reports.get(station["icao"], [])
        usable = [r for r in reports if r.visibility_mi is not None and r.observed_at <= now]
        if not usable:
            return StationWeather(source=self.source)
        o = max(usable, key=lambda r: r.observed_at)
        return StationWeather(
            observed_at=o.observed_at, visibility_mi=o.visibility_mi, ceiling_ft=o.ceiling_ft,
            wind_kt=o.wind_kt, gust_kt=o.gust_kt, wind_dir=o.wind_dir, thunderstorm=o.thunderstorm,
            temp_c=o.temp_c, source=self.source,
            forecast=forecaster.from_reports(
                reports, station["lat"], station["lon"], now,
                [(miles, self.reports.get(code, [])) for code, miles in station_neighbors(station["icao"])]))


def from_hour_record(rec: HourRecord, hour_end: datetime, forecast, source: str) -> StationWeather:
    nan = lambda v: None if v != v else v  # noqa: E731  (NaN -> None)
    return StationWeather(
        observed_at=hour_end, visibility_mi=rec.vis_min,
        ceiling_ft=None if rec.ceil_min >= CEILING_CAP_FT else rec.ceil_min,
        wind_kt=rec.wind_max, gust_kt=rec.gust_max, wind_dir=nan(rec.wind_dir),
        thunderstorm=rec.ts, temp_c=nan(rec.temp_c), forecast=forecast, source=source)


def flight_minutes(origin: dict, dest: dict, base: dict | None, aircraft: str = "air_taxi_a") -> tuple[float, float]:
    """(minutes until lift-off, minutes from lift-off to drop-off) at typical values."""
    air = decision.profiles()[aircraft]
    v = lambda k: float(air[k]["value"])  # noqa: E731
    miles = haversine_mi(origin["lat"], origin["lon"], dest["lat"], dest["lon"])
    if base is not None:
        miles += haversine_mi(base["lat"], base["lon"], origin["lat"], origin["lon"])
    return v("launch_delay_min_median"), miles / v("cruise_mph") * 60 + v("load_min_median") + v("unload_min_median")


def _weather_facts(ledger: Ledger, st: dict, miles: float, role: str, w: StationWeather) -> list[str]:
    where = f"at {st['icao']} ({miles:.0f} mi from {role})"
    kw = dict(source=w.source, confidence="official", fetched_at=w.observed_at)
    ids = [ledger.add(f"Visibility {where}", w.visibility_mi, unit="mi", **kw)]
    if w.ceiling_ft is not None:
        ids.append(ledger.add(f"Cloud ceiling {where}", w.ceiling_ft, unit="ft", **kw))
    strongest = max((x for x in (w.wind_kt, w.gust_kt) if x is not None), default=None)
    if strongest is not None:
        ids.append(ledger.add(f"Strongest wind {where}", strongest, unit="kt", **kw))
    if w.thunderstorm:
        ids.append(ledger.add(f"Thunderstorm reported {where}", True, **kw))
    return ids


STRATEGY_LABEL = {"ground_only": "Ground ambulance only", "air_only": "Air taxi only",
                  "air_and_ground": "Air taxi with ground backup"}


def _result_facts(ledger: Ledger, options: list[decision.Option], recommended: str, deadline_min: int) -> None:
    """The engine's results as facts, so the written brief can only quote numbers that
    exist in the ledger. Chances are stored in percent because that is how people say them."""
    src = "decision engine (2,000 simulated outcomes)"
    ledger.add("Deadline", deadline_min, unit="min", source="entered by the dispatcher", confidence="reported")
    for o in options:
        name = STRATEGY_LABEL[o.strategy]
        if o.status != "OK":
            ledger.add(f"{name}: status", o.status.replace("_", " "), source=src, confidence="computed")
            continue
        ledger.add(f"{name}: chance to arrive by the deadline", round(o.p_by_deadline * 100), unit="%",
                   source=src, confidence="computed")
        ledger.add(f"{name}: typical time", round(o.median_min), unit="min", source=src, confidence="computed")
    ledger.add("Option the engine suggests", STRATEGY_LABEL[recommended],
               source="decision rule: best chance by the deadline; close calls go to ground, then to air with ground backup",
               confidence="computed")


@dataclass
class Built:
    """The answer (`out`, the fields of contracts.CaseOut) plus the inputs behind it,
    which the Time Machine reuses to score the same case against what really happened."""
    out: dict
    road: roads.Route
    base: dict
    wind: Wind
    temp_c: float | None
    local_hour: int
    stations: list[dict]
    flight_start: datetime
    flight_end: datetime


def build_case(*, origin: dict, dest: dict, deadline_min: int, now: datetime,
               source: WeatherSource | None = None) -> Built:
    ledger = Ledger(now=now)
    pickup_st, pickup_mi = nearest_station(origin["lat"], origin["lon"])
    drop_st, drop_mi = nearest_station(dest["lat"], dest["lon"])
    base = {"name": pickup_st["name"].title(), "icao": pickup_st["icao"],
            "lat": pickup_st["lat"], "lon": pickup_st["lon"]}
    source = source or LiveWeather([pickup_st["icao"], drop_st["icao"]])

    wait_min, air_min = flight_minutes(origin, dest, base)
    start, end = now + timedelta(minutes=wait_min), now + timedelta(minutes=wait_min + air_min)

    chances, reasons, weather_ids, forecasts = [], [], [], []
    ends = [(pickup_st, pickup_mi, "pick-up")]
    if drop_st["icao"] != pickup_st["icao"]:
        ends.append((drop_st, drop_mi, "drop-off"))
    pickup_weather = None
    for st, miles, role in ends:
        w = source.station(st, now)
        pickup_weather = pickup_weather or w
        if w.observed_at is None or w.forecast is None:
            age = "" if w.observed_at is None else f" (newest is {(now - w.observed_at).total_seconds() / 60:.0f} min old)"
            reasons.append(f"{st['icao']}: no fresh weather report{age}")
            weather_ids.append(ledger.add(f"Weather report at {st['icao']} ({miles:.0f} mi from {role})",
                                          "UNKNOWN", source=w.source or "no source answered",
                                          confidence="official", fetched_at=w.observed_at))
            chances.append(None)
            continue
        weather_ids += _weather_facts(ledger, st, miles, role, w)
        reasons += [f"{st['icao']} now: {r}" for r in
                    weather.problems(w.visibility_mi, w.ceiling_ft, w.wind_kt, w.gust_kt, w.thunderstorm)]
        p = w.forecast.window(start, end)
        chances.append(p)
        weather_ids.append(ledger.add(
            f"Chance {st['icao']} stays flyable during the flight", round(p * 100), unit="%",
            source=f"forecaster {w.forecast.model}, from the report above", confidence="computed",
            fetched_at=w.forecast.issued_at))
        forecasts.append({"station": st["icao"], "role": role, "issued_at": w.forecast.issued_at.isoformat(),
                          "model": w.forecast.model,
                          "points": [{"hours_ahead": h, "p_flyable": round(v, 3)}
                                     for h, v in sorted(w.forecast.p_flyable.items())]})

    p_weather = None if any(c is None for c in chances) else min(chances)
    ground = decision.profiles()["ground_ambulance"]
    road = roads.route(origin, dest, ground)
    w0 = pickup_weather or StationWeather()
    wind, local_hour = Wind(w0.wind_kt, w0.gust_kt, w0.wind_dir), now.astimezone(FLORIDA).hour
    options = decision.evaluate(
        origin=origin, dest=dest, deadline_min=deadline_min,
        local_hour=local_hour, p_weather=p_weather, weather_reasons=reasons,
        ledger=ledger, road=road, base=base, wind=wind, temp_c=w0.temp_c)
    for o in options:
        if o.strategy != "ground_only":
            o.fact_ids = o.fact_ids + weather_ids
    recommended = decision.recommend(options)
    _result_facts(ledger, options, recommended, deadline_min)
    out = {
        "disclaimer": DISCLAIMER, "origin": origin, "dest": dest,
        "options": [o.model_dump() for o in options], "recommended": recommended,
        "facts": ledger.all(), "decision_owner": DECISION_OWNER,
        "as_of": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "forecasts": forecasts,
        "map": {"road": road.geometry, "road_is_routed": road.routed,
                "air_base": base, "air": [[base["lon"], base["lat"]], [origin["lon"], origin["lat"]],
                                          [dest["lon"], dest["lat"]]]},
    }
    return Built(out=out, road=road, base=base, wind=wind, temp_c=w0.temp_c, local_hour=local_hour,
                 stations=[st for st, _, _ in ends], flight_start=start, flight_end=end)
