"""Road distance and free-flow drive time between two facilities.

Order of preference, and every answer says which one it used:
  1. data/routes.json   routes we already fetched from OSRM (works offline, used in the demo)
  2. live OSRM          the public demo router, short timeout (skipped when ROUTE_LOOKUP=cache)
  3. a simple model     straight-line distance x detour factor / average speed, with both
                        numbers fitted to the cached routes when there are enough of them

None of these know about traffic. The decision engine multiplies the free-flow time by a
labeled hour-of-day congestion factor.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache

import httpx

from .geo import DATA_DIR, haversine_mi

ROUTES_PATH = DATA_DIR / "routes.json"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{lon1:.5f},{lat1:.5f};{lon2:.5f},{lat2:.5f}"
USER_AGENT = "car-or-air-hackathon/0.1"
METERS_PER_MILE = 1609.344


@dataclass
class Route:
    miles: float
    minutes: float                       # free-flow, no traffic
    source: str
    confidence: str                      # "reported" for routed, "assumption" for modeled
    fetched_at: datetime | None          # when the route was fetched; None for the model
    geometry: list[list[float]] = field(default_factory=list)  # [lon, lat] points, may be empty

    @property
    def routed(self) -> bool:
        return self.confidence == "reported"


@lru_cache
def _cache() -> dict:
    if not ROUTES_PATH.exists():
        return {"pairs": {}, "fit": None}
    data = json.loads(ROUTES_PATH.read_text(encoding="utf-8"))
    return {"pairs": data.get("pairs", {}), "fit": data.get("fit")}


def pair_key(origin_id: str, dest_id: str) -> str:
    return f"{origin_id}|{dest_id}"


def fetch_osrm(lat1: float, lon1: float, lat2: float, lon2: float, timeout: float = 4.0) -> dict:
    """One OSRM request. Returns {"miles", "minutes", "geometry"}; raises on any failure."""
    resp = httpx.get(OSRM_URL.format(lat1=lat1, lon1=lon1, lat2=lat2, lon2=lon2),
                     params={"overview": "simplified", "geometries": "geojson"},
                     headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != "Ok" or not body.get("routes"):
        raise ValueError(f"OSRM answered {body.get('code')}")
    best = body["routes"][0]
    return {"miles": round(best["distance"] / METERS_PER_MILE, 2),
            "minutes": round(best["duration"] / 60, 1),
            "geometry": [[round(x, 4), round(y, 4)] for x, y in best["geometry"]["coordinates"]]}


@lru_cache(maxsize=512)
def _live(lat1: float, lon1: float, lat2: float, lon2: float) -> tuple | None:
    try:
        r = fetch_osrm(lat1, lon1, lat2, lon2)
    except Exception:
        return None
    return r["miles"], r["minutes"], tuple(map(tuple, r["geometry"])), datetime.now(timezone.utc)


def modeled(origin: dict, dest: dict, ground_profile: dict) -> Route:
    """Fallback when no routed answer exists. Clearly labeled as modeled."""
    fit = _cache()["fit"]
    if fit:
        detour, mph, how = fit["detour_factor"], fit["avg_mph"], f"fitted to {fit['n']} routed trips"
    else:
        detour = float(ground_profile["detour_factor"]["value"])
        mph = float(ground_profile["avg_mph"]["value"])
        how = "default detour factor and speed"
    miles = haversine_mi(origin["lat"], origin["lon"], dest["lat"], dest["lon"]) * detour
    return Route(miles=round(miles, 1), minutes=round(miles / mph * 60, 1),
                 source=f"modeled from straight-line distance ({how})", confidence="assumption",
                 fetched_at=None)


def route(origin: dict, dest: dict, ground_profile: dict) -> Route:
    cached = _cache()["pairs"].get(pair_key(origin["faa_id"], dest["faa_id"]))
    if cached:
        return Route(miles=cached["miles"], minutes=cached["minutes"],
                     source="OSRM road route (saved copy, no traffic)", confidence="reported",
                     fetched_at=datetime.fromisoformat(cached["fetched_at"]),
                     geometry=cached.get("geometry", []))
    if os.environ.get("ROUTE_LOOKUP", "live") == "live":
        live = _live(origin["lat"], origin["lon"], dest["lat"], dest["lon"])
        if live:
            miles, minutes, geometry, when = live
            return Route(miles=miles, minutes=minutes, source="OSRM road route (live, no traffic)",
                         confidence="reported", fetched_at=when, geometry=[list(p) for p in geometry])
    return modeled(origin, dest, ground_profile)
