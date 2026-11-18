"""Decision engine. All math lives here, never in the LLM.

Compares three strategies for one case with a Monte Carlo over uncertain times:
  ground only, air only, and both in parallel (whichever arrives first).
Version 0: road time is straight-line distance x detour factor / average speed with an
hour-of-day congestion factor; P(air flies) comes from current weather only. The ML
forecaster, energy check and routed road times plug in here later.
"""
from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
from pydantic import BaseModel

from .geo import DATA_DIR, haversine_mi
from .ledger import Ledger

N_DRAWS = 2000

# Assumption: congestion multiplier by local hour (rush hours slower). Labeled in the UI.
CONGESTION = {h: 1.0 for h in range(24)} | {7: 1.35, 8: 1.4, 9: 1.2, 16: 1.3, 17: 1.45, 18: 1.3}


@lru_cache
def profiles() -> dict:
    return json.loads((DATA_DIR / "aircraft_profiles.json").read_text())


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


def evaluate(*, origin: dict, dest: dict, deadline_min: float, local_hour: int,
             p_air_flies: float | None, weather_reasons: list[str], ledger: Ledger,
             aircraft: str = "air_taxi_a", seed: int = 7) -> list[Option]:
    rng = np.random.default_rng(seed)
    prof = profiles()
    ground, air = prof["ground_ambulance"], prof[aircraft]

    dist = haversine_mi(origin["lat"], origin["lon"], dest["lat"], dest["lon"])
    f_dist = ledger.add("Straight-line distance", round(dist, 1), unit="mi",
                        source="computed from FAA coordinates", confidence="computed")

    # Ground: dispatch delay + travel with congestion and noise.
    congestion = CONGESTION.get(local_hour, 1.0)
    f_cong = ledger.add(f"Road congestion factor at {local_hour:02d}:00", congestion,
                        source="modeled (no live traffic data)", confidence="assumption")
    road_min = dist * _v(ground, "detour_factor") / _v(ground, "avg_mph") * 60 * congestion
    ground_t = (_lognormal(rng, _v(ground, "dispatch_delay_min_median"), 0.3, N_DRAWS)
                + road_min * _lognormal(rng, 1.0, 0.15, N_DRAWS))

    # Air: launch delay + flight time (+ 5 min handoff). Fails with prob 1 - p_air_flies.
    in_range = dist <= _v(air, "range_mi")
    f_range = ledger.add(f"{air['label']} range", _v(air, "range_mi"), unit="mi",
                         source="aircraft_profiles.json", confidence=air["range_mi"]["confidence"])
    air_t = (_lognormal(rng, _v(air, "launch_delay_min_median"), 0.3, N_DRAWS)
             + dist / _v(air, "cruise_mph") * 60 * _lognormal(rng, 1.0, 0.08, N_DRAWS) + 5)

    def summarize(name, times, ok_mask, status, reasons, ids):
        if status != "OK":
            return Option(strategy=name, status=status, p_by_deadline=None, median_min=None,
                          range_min=None, reasons=reasons, fact_ids=ids)
        arrived = np.where(ok_mask, times, np.inf)
        finite = arrived[np.isfinite(arrived)]
        p = float(np.mean(arrived <= deadline_min))
        med = float(np.median(finite)) if finite.size else None
        rng_ = (float(np.percentile(finite, 10)), float(np.percentile(finite, 90))) if finite.size else None
        return Option(strategy=name, status="OK", p_by_deadline=round(p, 3),
                      median_min=round(med, 1) if med else None,
                      range_min=(round(rng_[0], 1), round(rng_[1], 1)) if rng_ else None,
                      reasons=reasons, fact_ids=ids)

    options = [summarize("ground_only", ground_t, np.ones(N_DRAWS, bool), "OK",
                         ["road time is modeled, not live traffic"], [f_dist, f_cong])]

    if not in_range:
        air_status, air_reasons = "NOT_AVAILABLE", ["trip is longer than the aircraft's range"]
    elif p_air_flies is None:
        air_status, air_reasons = "UNKNOWN", weather_reasons or ["weather unknown"]
    else:
        air_status, air_reasons = "OK", weather_reasons
    flies = rng.random(N_DRAWS) < (p_air_flies or 0.0)
    options.append(summarize("air_only", air_t, flies, air_status, air_reasons, [f_dist, f_range]))

    # Parallel: ground leaves immediately; air also launches; first arrival wins.
    parallel_t = np.where(flies, np.minimum(air_t, ground_t), ground_t)
    options.append(summarize("air_and_ground", parallel_t, np.ones(N_DRAWS, bool),
                             "OK" if air_status != "NOT_AVAILABLE" else "NOT_AVAILABLE",
                             ["ground backup always moving"] + (air_reasons if air_status != "OK" else []),
                             [f_dist, f_cong, f_range]))
    return options


def recommend(options: list[Option]) -> str:
    """Highest chance of making the deadline; ties go to ground (the safe default)."""
    usable = [o for o in options if o.status == "OK" and o.p_by_deadline is not None]
    if not usable:
        return "ground_only"
    order = {"ground_only": 0, "air_and_ground": 1, "air_only": 2}
    return max(usable, key=lambda o: (o.p_by_deadline, -order[o.strategy])).strategy
