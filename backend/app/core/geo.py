"""Geography helpers and seed-data loading (FAA heliports, weather stations)."""
from __future__ import annotations

import csv
import math
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
EARTH_RADIUS_MI = 3958.8


def haversine_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compass direction of travel from point 1 to point 2 (0 = north, 90 = east)."""
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.atan2(x, y)) % 360


@lru_cache
def heliports() -> dict[str, dict]:
    """Florida heliports from the FAA 28-day airport data (Oct 29, 2026 cycle)."""
    with open(DATA_DIR / "seeds" / "fl_heliports.csv", newline="") as f:
        return {r["faa_id"]: {**r, "lat": float(r["lat"]), "lon": float(r["lon"])} for r in csv.DictReader(f)}


@lru_cache
def stations() -> list[dict]:
    with open(DATA_DIR / "seeds" / "stations.csv", newline="") as f:
        return [{**r, "lat": float(r["lat"]), "lon": float(r["lon"])} for r in csv.DictReader(f)]


@lru_cache
def station_neighbors(icao: str, limit: int = 3, radius_mi: float = 100.0) -> tuple[tuple[str, float], ...]:
    """The nearest other weather stations as (icao, miles), nearest first."""
    here = next(s for s in stations() if s["icao"] == icao)
    others = sorted((haversine_mi(here["lat"], here["lon"], s["lat"], s["lon"]), s["icao"])
                    for s in stations() if s["icao"] != icao)
    return tuple((code, miles) for miles, code in others[:limit] if miles <= radius_mi)


def nearest_station(lat: float, lon: float) -> tuple[dict, float]:
    best = min(stations(), key=lambda s: haversine_mi(lat, lon, s["lat"], s["lon"]))
    return best, haversine_mi(lat, lon, best["lat"], best["lon"])
