"""Battery energy check for the simulated air taxi. Physics in plain code, no ML.

Energy needed  = hover (take-off and landing on every leg)
               + cruise power x time in the air (a headwind makes the flight longer)
               + the 20-minute reserve the FAA rule requires
Energy on hand = battery size x usable share x charge at dispatch x (1 - heat loss)

Charge at dispatch and the wind are uncertain, so we draw many possible values and
report the share of draws where the energy on hand covers the need: P(energy OK).
Every parameter comes from data/aircraft_profiles.json with its confidence tag.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

KT_TO_MPH = 1.15078
UNKNOWN_WIND_KT = 25.0  # assumed surface wind when the report has none (the gust limit in weather.py)


@dataclass
class Wind:
    speed_kt: float | None = None   # sustained surface wind at the nearest airport
    gust_kt: float | None = None
    from_deg: float | None = None   # direction the wind blows from; None when variable


@dataclass
class EnergyCheck:
    p_ok: float                     # share of draws with enough energy, reserve included
    ok: np.ndarray                  # one True/False per draw
    leg_minutes: list[np.ndarray]   # flight minutes per leg, per draw
    need_kwh: float                 # medians, for the receipts
    have_kwh: float
    spare_min: float                # cruise minutes left after the reserve (negative = short)
    headwind_mph: float             # median headwind on the last leg (negative = tailwind)
    heat_loss: float                # share of usable energy lost to heat
    temp_known: bool
    wind_known: bool = True


def _v(profile: dict, key: str) -> float:
    return float(profile[key]["value"])


def heat_loss(profile: dict, temp_c: float | None) -> float:
    """Share of usable energy lost in hot weather. Unknown temperature takes the worst case."""
    cap = _v(profile, "heat_loss_cap")
    if temp_c is None:
        return cap
    return float(min(cap, max(0.0, temp_c - 25.0) * _v(profile, "heat_loss_per_c_above_25")))


def check(profile: dict, legs: list[tuple[float, float]], wind: Wind, temp_c: float | None,
          rng: np.random.Generator, n: int) -> EnergyCheck:
    """legs: (miles, compass bearing of travel) for each flight leg, in order."""
    cruise_mph = _v(profile, "cruise_mph")
    cruise_kw = _v(profile, "cruise_kwh_per_mi") * cruise_mph

    # Wind at cruise height: between the sustained wind and the gust, scaled up from the surface.
    wind_known = wind.speed_kt is not None or wind.gust_kt is not None
    if wind_known:
        base = wind.speed_kt if wind.speed_kt is not None else wind.gust_kt
        top = max(base, wind.gust_kt or 0.0, base * 1.3)
    else:  # no wind report: assume a strong wind from any direction, never calm
        base, top, wind = UNKNOWN_WIND_KT, UNKNOWN_WIND_KT * 1.3, Wind()
    speed_mph = rng.uniform(base, top, n) * _v(profile, "wind_aloft_factor") * KT_TO_MPH
    if wind.from_deg is None:
        from_deg = rng.uniform(0, 360, n)          # variable or unknown: any direction
    else:
        from_deg = wind.from_deg + rng.normal(0, 20, n)

    need = np.zeros(n)
    leg_minutes, headwind = [], np.zeros(n)
    for miles, bearing in legs:
        headwind = speed_mph * np.cos(np.radians(from_deg - bearing))
        ground_speed = np.clip(cruise_mph - headwind, 0.5 * cruise_mph, 1.3 * cruise_mph)
        minutes = miles / ground_speed * 60 * rng.lognormal(0, 0.05, n)
        hover_min = _v(profile, "hover_min_per_leg") * rng.lognormal(0, 0.2, n)
        need += _v(profile, "hover_kw") * hover_min / 60 + cruise_kw * minutes / 60
        leg_minutes.append(minutes + hover_min)  # the clock runs during take-off and landing too
    need += cruise_kw * _v(profile, "reserve_min") / 60

    loss = heat_loss(profile, temp_c)
    charge = rng.uniform(_v(profile, "start_charge_min"), 1.0, n)
    have = _v(profile, "battery_kwh") * _v(profile, "usable_fraction") * charge * (1 - loss)
    ok = have >= need
    return EnergyCheck(
        p_ok=float(ok.mean()), ok=ok, leg_minutes=leg_minutes,
        need_kwh=float(np.median(need)), have_kwh=float(np.median(have)),
        spare_min=float(np.median((have - need) / cruise_kw * 60)),
        headwind_mph=float(np.median(headwind)), heat_loss=loss, temp_known=temp_c is not None,
        wind_known=wind_known,
    )
