"""Decision engine. All math lives here, never in the LLM.

Compares three strategies for one case by drawing many possible outcomes (Monte Carlo):
  ground_only      an ambulance drives the whole way
  air_only         the air taxi flies; if the flight is called off, an ambulance is
                   called late (that lost time is part of the math)
  air_and_ground   both start at once; whichever arrives first counts

Chance the flight happens = P(weather stays flyable) x P(enough battery) x P(pads free).
The weather part comes from the forecaster, the battery part from energy.py, and the pad
part is simulated (no real pad data exists). Every input is written to the ledger with
its source, so each number on screen has a receipt.
"""
from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
from pydantic import BaseModel

from . import alternates, energy, roads
from .geo import DATA_DIR, bearing_deg, haversine_mi
from .ledger import Ledger

N_DRAWS = 2000
CLOSE_CALL = 0.02  # options within 2 points of the best count as tied
SPREAD = 0.4       # log-scale spread of time spent waiting and at the sending hospital

# Assumption: congestion multiplier by local hour (rush hours slower). Labeled in the UI.
CONGESTION = {h: 1.0 for h in range(24)} | {7: 1.35, 8: 1.4, 9: 1.2, 16: 1.3, 17: 1.45, 18: 1.3}

# The order used to break close calls: ground alone first, then air with the ambulance
# already moving. Air alone is never better on the deadline than air with a ground backup
# (it only saves a vehicle), so it is shown for comparison and suggested last.
PREFERENCE = ["ground_only", "air_and_ground", "air_only"]


@lru_cache
def profiles() -> dict:
    return json.loads((DATA_DIR / "aircraft_profiles.json").read_text(encoding="utf-8"))


def _v(profile: dict, key: str) -> float:
    return float(profile[key]["value"])


class Option(BaseModel):
    strategy: str
    status: str  # OK | UNKNOWN | NOT_AVAILABLE
    p_by_deadline: float | None
    median_min: float | None
    range_min: tuple[float, float] | None
    reasons: list[str]
    fact_ids: list[str]


def _lognormal(rng, median: float, sigma: float, n: int) -> np.ndarray:
    return rng.lognormal(np.log(median), sigma, n)


def _summarize(name: str, times: np.ndarray, deadline_min: float, reasons: list[str], ids: list[str]) -> Option:
    return Option(strategy=name, status="OK",
                  p_by_deadline=round(float(np.mean(times <= deadline_min)), 3),
                  median_min=round(float(np.median(times)), 1),
                  range_min=(round(float(np.percentile(times, 10)), 1),
                             round(float(np.percentile(times, 90)), 1)),
                  reasons=reasons, fact_ids=ids)


def _blocked(name: str, status: str, reasons: list[str], ids: list[str]) -> Option:
    return Option(strategy=name, status=status, p_by_deadline=None, median_min=None,
                  range_min=None, reasons=reasons, fact_ids=ids)


def evaluate(*, origin: dict, dest: dict, deadline_min: float, local_hour: int,
             p_weather: float | None, weather_reasons: list[str], ledger: Ledger,
             road: roads.Route | None = None, base: dict | None = None,
             wind: energy.Wind | None = None, temp_c: float | None = None,
             aircraft: str = "air_taxi_a", seed: int = 7) -> list[Option]:
    """p_weather: chance the weather stays flyable for the flight, or None when unknown.
    base: where the aircraft starts (dict with name, lat, lon); None means it is already
    at the pick-up pad."""
    rng = np.random.default_rng(seed)
    prof = profiles()
    ground, air = prof["ground_ambulance"], prof[aircraft]
    n = N_DRAWS

    # ---- Ground ---------------------------------------------------------------------
    road = road or roads.modeled(origin, dest, ground)
    f_road = ledger.add("Road distance", road.miles, unit="mi", source=road.source,
                        confidence=road.confidence, fetched_at=road.fetched_at)
    f_drive = ledger.add("Drive time with clear roads", road.minutes, unit="min", source=road.source,
                         confidence=road.confidence, fetched_at=road.fetched_at)
    congestion = CONGESTION.get(local_hour, 1.0)
    f_cong = ledger.add(f"Road congestion factor at {local_hour:02d}:00", congestion,
                        source="modeled by hour of day (no live traffic data)", confidence="assumption")
    drive = road.minutes * congestion * _lognormal(rng, 1.0, 0.15, n)
    f_wait = ledger.add("Typical wait for the ambulance to reach the sending hospital",
                        _v(ground, "dispatch_delay_min_median"), unit="min", source="aircraft_profiles.json",
                        confidence=ground["dispatch_delay_min_median"]["confidence"])
    f_gload = ledger.add("Typical ambulance time at the sending hospital", _v(ground, "load_min_median"),
                         unit="min", source="aircraft_profiles.json",
                         confidence=ground["load_min_median"]["confidence"])
    # Wide spread on the fixed delays: published figures differ a lot between studies.
    ground_t = (_lognormal(rng, _v(ground, "dispatch_delay_min_median"), SPREAD, n)
                + _lognormal(rng, _v(ground, "load_min_median"), SPREAD, n) + drive
                + _lognormal(rng, _v(ground, "handoff_min_median"), 0.3, n))
    f_hand = ledger.add("Typical handoff time at the receiving hospital", _v(ground, "handoff_min_median"),
                        unit="min", source="aircraft_profiles.json",
                        confidence=ground["handoff_min_median"]["confidence"])
    ground_ids = [f_road, f_drive, f_cong, f_wait, f_gload, f_hand]
    ground_reasons = ["road time has no live traffic; rush hours use a modeled slowdown"
                      if road.routed else "road time is modeled from straight-line distance, not routed"]
    options = [_summarize("ground_only", ground_t, deadline_min, ground_reasons, ground_ids)]

    # ---- Air ------------------------------------------------------------------------
    flight_mi = haversine_mi(origin["lat"], origin["lon"], dest["lat"], dest["lon"])
    f_dist = ledger.add("Straight-line distance", round(flight_mi, 1), unit="mi",
                        source="computed from FAA coordinates", confidence="computed")
    f_range = ledger.add(f"{air['label']} range", _v(air, "range_mi"), unit="mi",
                         source="aircraft_profiles.json", confidence=air["range_mi"]["confidence"])
    air_ids = [f_dist, f_range]
    legs = [(flight_mi, bearing_deg(origin["lat"], origin["lon"], dest["lat"], dest["lon"]))]
    if base is not None:
        to_pickup = haversine_mi(base["lat"], base["lon"], origin["lat"], origin["lon"])
        legs.insert(0, (to_pickup, bearing_deg(base["lat"], base["lon"], origin["lat"], origin["lon"])))
        air_ids.append(ledger.add(f"Aircraft starts at {base['name']} (simulated base), distance to pick-up",
                                  round(to_pickup, 1), unit="mi",
                                  source="simulated: nearest airport in data/seeds/stations.csv",
                                  confidence="simulated"))

    if sum(miles for miles, _ in legs) > _v(air, "range_mi"):
        why = ["the flight is longer than the aircraft's range"]
        options.append(_blocked("air_only", "NOT_AVAILABLE", why, air_ids))
        options.append(_blocked("air_and_ground", "NOT_AVAILABLE", why, air_ids + ground_ids))
        return options
    if p_weather is None:
        why = weather_reasons or ["weather unknown"]
        options.append(_blocked("air_only", "UNKNOWN", why, air_ids))
        options.append(_blocked("air_and_ground", "UNKNOWN", why + ["ground alone is the safe choice"],
                                air_ids + ground_ids))
        return options

    power = energy.check(air, legs, wind or energy.Wind(), temp_c, rng, n)
    p_pad = _v(air, "pad_available_p")
    pct = lambda p: round(p * 100)  # noqa: E731  chances are shown in whole percent
    f_weather = ledger.add("Chance the weather stays flyable for the flight", pct(p_weather), unit="%",
                           source="flyable-window forecaster (see the forecast receipts)", confidence="computed")
    f_energy = ledger.add("Chance the battery covers the flight plus the reserve", pct(power.p_ok), unit="%",
                          source="energy check (energy.py)", confidence="computed")
    f_spare = ledger.add("Typical flying time left after the reserve", round(power.spare_min), unit="min",
                         source="energy check (energy.py)", confidence="computed")
    f_pad = ledger.add("Chance both landing pads are free", pct(p_pad), unit="%",
                       source="simulated (no real pad data)", confidence="simulated")
    p_flies = p_weather * power.p_ok * p_pad
    f_flies = ledger.add("Chance the flight happens (weather x battery x pads)", pct(p_flies), unit="%",
                         source="decision engine", confidence="computed")
    air_ids += [f_weather, f_energy, f_spare, f_pad, f_flies]

    for label, key, src in (
            ("Typical time from the call to lift-off at the base", "launch_delay_min_median", "aircraft_profiles.json"),
            ("Typical aircraft time at the sending hospital", "load_min_median",
             "aircraft_profiles.json (helicopter air ambulance figure)"),
            ("Typical time from landing to handover", "unload_min_median",
             "aircraft_profiles.json (helicopter air ambulance figure)")):
        air_ids.append(ledger.add(label, _v(air, key), unit="min", source=src, confidence=air[key]["confidence"]))
    air_ids.append(ledger.add("Extra delay to call an ambulance after a flight is called off",
                              _v(ground, "late_start_min_median"), unit="min", source="aircraft_profiles.json",
                              confidence=ground["late_start_min_median"]["confidence"]))
    launch = _lognormal(rng, _v(air, "launch_delay_min_median"), 0.3, n)
    air_t = (launch + sum(power.leg_minutes)
             + _lognormal(rng, _v(air, "load_min_median"), SPREAD, n)
             + _lognormal(rng, _v(air, "unload_min_median"), 0.3, n))
    flies = (rng.random(n) < p_weather) & power.ok & (rng.random(n) < p_pad)
    late = launch + _lognormal(rng, _v(ground, "late_start_min_median"), 0.3, n)

    air_reasons = [f"{round(p_weather * 100)}% chance the weather stays flyable for the flight"]
    air_reasons += weather_reasons
    if power.p_ok < 0.95:
        air_reasons.append(f"{round(power.p_ok * 100)}% chance the battery covers the trip and reserve")
    if not power.temp_known:
        air_reasons.append("temperature unknown, so the hottest case is assumed for the battery")
    if not power.wind_known:
        air_reasons.append("wind unknown, so a strong wind from any direction is assumed for the battery")
    out = alternates.check(air, origin, dest, base, temp_c)
    air_ids.append(ledger.add(
        "Smallest energy margin to the nearest landing place along the flight", round(out["min_margin_min"]),
        unit="min", source="always-an-out check (alternates.py): still air, lowest starting charge, reserve kept",
        confidence="computed"))
    air_reasons.append(
        f"a landing place stays within reach for the whole flight (at least {round(out['min_margin_min'])} min of energy to spare)"
        if out["always_reachable"] else
        f"around mile {round(out['worst_at_mile'])} of the flight, no landing place is within reach without using the reserve")
    late_min = round(float(np.median(late)))
    options.append(_summarize("air_only", np.where(flies, air_t, late + ground_t), deadline_min,
                              air_reasons + [f"if the flight is called off, an ambulance starts about {late_min} min late"],
                              air_ids + ground_ids))
    options.append(_summarize("air_and_ground", np.where(flies, np.minimum(air_t, ground_t), ground_t),
                              deadline_min,
                              ["ambulance leaves right away as the backup; uses two vehicles"] + air_reasons,
                              air_ids + ground_ids))
    return options


def recommend(options: list[Option]) -> str:
    """Best chance of making the deadline. Options within 2 points of the best count as
    tied, and a tie goes to ground alone, then to air with the ground backup. With no
    usable numbers at all, ground is the safe default."""
    usable = [o for o in options if o.status == "OK" and o.p_by_deadline is not None]
    if not usable:
        return "ground_only"
    best = max(o.p_by_deadline for o in usable)
    close = [o for o in usable if o.p_by_deadline >= best - CLOSE_CALL - 1e-9]  # exactly 2 points is a tie
    return min(close, key=lambda o: PREFERENCE.index(o.strategy)).strategy
