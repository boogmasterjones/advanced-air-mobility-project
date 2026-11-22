"""Rush-hour slowdown for the drive, from published travel time indexes.

The router gives a drive time with no traffic. At weekday peak hours that time is
multiplied by a factor built from the Travel Time Index of each metro area the route
passes through (Texas A&M Urban Mobility Report; values and source in
data/congestion.json). Only the part of the route inside a metro area is slowed: rural
Florida roads show no measurable peak effect in FDOT's data.

What is published: the index per metro area and the peak windows.
What is our assumption: the circles that mark where each metro area is, and applying the
index to the urban share of this one route. Both are labeled in the receipts.
There is still no live traffic in this app.
"""
from __future__ import annotations

import json
from functools import lru_cache

from .geo import DATA_DIR, haversine_mi


@lru_cache
def table() -> dict:
    return json.loads((DATA_DIR / "congestion.json").read_text(encoding="utf-8"))


def is_peak(local_hour: int, weekday: bool) -> bool:
    peaks = table()["peak_hours_local"]
    if peaks["weekdays_only"] and not weekday:
        return False
    return any(lo <= local_hour < hi for lo, hi in (peaks["am"], peaks["pm"]))


def index_at(lat: float, lon: float) -> tuple[float, str | None]:
    """(peak index, metro area name) for a point; the outside-metro index and None elsewhere."""
    best, name = table()["outside_metro_index"], None
    for area in table()["areas"]:
        if haversine_mi(lat, lon, area["lat"], area["lon"]) <= area["radius_mi"] and area["index"] > best:
            best, name = area["index"], area["name"]
    return best, name


def peak_index_for_route(origin: dict, dest: dict, geometry: list[list[float]]) -> tuple[float, list[str]]:
    """Length-weighted peak index along the route, and the metro areas it touches.
    With no route line (modeled road time) the two end points count half each."""
    areas: list[str] = []
    if len(geometry) < 2:
        parts = [index_at(p["lat"], p["lon"]) for p in (origin, dest)]
        areas = [name for _, name in parts if name]
        return sum(i for i, _ in parts) / 2, sorted(set(areas))
    total = weighted = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(geometry, geometry[1:]):
        length = haversine_mi(lat1, lon1, lat2, lon2)
        index, name = index_at((lat1 + lat2) / 2, (lon1 + lon2) / 2)
        total += length
        weighted += length * index
        if name:
            areas.append(name)
    return (weighted / total if total else table()["outside_metro_index"]), sorted(set(areas))


def factor(origin: dict, dest: dict, geometry: list[list[float]], local_hour: int, weekday: bool
           ) -> tuple[float, str]:
    """(multiplier for the no-traffic drive time, plain-language explanation)."""
    if not is_peak(local_hour, weekday):
        return 1.0, "outside weekday peak hours (6 to 10 a.m. and 3 to 7 p.m.), so no slowdown is applied"
    index, areas = peak_index_for_route(origin, dest, geometry)
    if not areas:
        return round(index, 2), "peak hour, but the route stays outside the metro areas, where no peak slowdown is measured"
    return round(index, 2), f"peak hour; part of the route is in {', '.join(areas)}"
