""""Always an Out" (task A8): is a landing place within reach at every point of the flight?

For points along the flight from pick-up to drop-off we work out how much energy is left
and how far that would carry the aircraft while still keeping the 20-minute reserve,
then find the nearest known landing place (an FAA-listed heliport or a weather-station
airport). The margin is how many extra minutes of flying would remain on arrival there.

Deliberately cautious: the battery starts at the lowest charge the simulation allows,
hot-weather loss is applied, and the positioning leg from the base is already spent.
Wind is not included (it is in the main energy check), so read the margin as "in still
air". Plain arithmetic; every parameter comes from data/aircraft_profiles.json.
"""
from __future__ import annotations

from . import energy
from .geo import haversine_mi, heliports, stations

STEP_MI = 4.0


def landing_sites() -> list[dict]:
    """Every place the simulated aircraft could put down: heliports and station airports."""
    sites = [{"id": h["faa_id"], "name": h["name"], "kind": "heliport", "lat": h["lat"], "lon": h["lon"]}
             for h in heliports().values()]
    sites += [{"id": s["icao"], "name": s["name"], "kind": "airport", "lat": s["lat"], "lon": s["lon"]}
              for s in stations()]
    return sites


def _v(profile: dict, key: str) -> float:
    return float(profile[key]["value"])


def check(profile: dict, origin: dict, dest: dict, base: dict | None, temp_c: float | None) -> dict:
    """Returns {"points": [...], "min_margin_min", "always_reachable", "sites": [...]}."""
    per_mi = _v(profile, "cruise_kwh_per_mi")
    cruise_mph = _v(profile, "cruise_mph")
    hover_kwh = _v(profile, "hover_kw") * _v(profile, "hover_min_per_leg") / 60   # one take-off plus landing
    reserve_kwh = per_mi * cruise_mph * _v(profile, "reserve_min") / 60
    have = (_v(profile, "battery_kwh") * _v(profile, "usable_fraction") * _v(profile, "start_charge_min")
            * (1 - energy.heat_loss(profile, temp_c)))
    if base is not None:  # the leg from the base to the pick-up pad is already flown
        have -= hover_kwh + per_mi * haversine_mi(base["lat"], base["lon"], origin["lat"], origin["lon"])

    total = haversine_mi(origin["lat"], origin["lon"], dest["lat"], dest["lon"])
    steps = max(2, int(total // STEP_MI) + 1)
    sites, points, used = landing_sites(), [], {}
    for i in range(steps + 1):
        share = i / steps
        lat = origin["lat"] + (dest["lat"] - origin["lat"]) * share     # straight line is fine at this range
        lon = origin["lon"] + (dest["lon"] - origin["lon"]) * share
        flown = total * share
        # Energy left after the take-off half of the hover, the miles flown, the landing half and the reserve.
        spare_kwh = have - hover_kwh - per_mi * flown - reserve_kwh
        reach_mi = spare_kwh / per_mi
        site = min(sites, key=lambda s: haversine_mi(lat, lon, s["lat"], s["lon"]))
        away = haversine_mi(lat, lon, site["lat"], site["lon"])
        margin = (reach_mi - away) / cruise_mph * 60
        points.append({"mile": round(flown, 1), "site_id": site["id"], "site_name": site["name"],
                       "site_miles": round(away, 1), "margin_min": round(margin, 1)})
        used[site["id"]] = site
    worst = min(points, key=lambda p: p["margin_min"])
    return {"points": points, "min_margin_min": worst["margin_min"], "worst_at_mile": worst["mile"],
            "always_reachable": worst["margin_min"] >= 0, "sites": list(used.values())}
