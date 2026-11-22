#!/usr/bin/env python3
"""Task A4: fetch road routes once and save them, so the app does not depend on a live router.

For every hospital-style helipad in the FAA list, saves the road route to its two nearest
trauma centers, plus the demo pairs. Also fits the two numbers of the fallback road model
(road miles per straight-line mile, and average speed) to the routes it fetched.

Run from the repo root (needs the backend requirements installed):
    python scripts/cache_routes.py            # skips pairs already saved
    python scripts/cache_routes.py --force    # fetch everything again

Source: the public OSRM demo router (router.project-osrm.org), OpenStreetMap data.
One request per second, as its usage policy asks. Times are free-flow: no traffic.
Writes data/routes.json.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from app.core import roads  # noqa: E402
from app.core.geo import haversine_mi, heliports  # noqa: E402

HOSPITAL_WORDS = re.compile(r"HOSP|MED|HEALTH|MEML|RGNL|CLINIC|TRAUMA|SHANDS|BAPTIST|ADVENT", re.I)
DEMO_PAIRS = [("9FA2", "48FD"),   # Lakeside Medical Center (Belle Glade) -> Delray Medical Center
              ("61FL", "7FD7"),   # Tampa General -> Lakeland Regional
              ("7FD7", "FD28"),   # Lakeland Regional -> Orlando Regional
              ("61FL", "FD28")]   # Tampa General -> Orlando Regional
NEAREST_TRAUMA = 2


def wanted_pairs() -> list[tuple[str, str]]:
    pads = heliports()
    with open(REPO / "data" / "seeds" / "trauma_centers.csv", newline="", encoding="utf-8") as f:
        trauma = [r["faa_id"] for r in csv.DictReader(f) if r["faa_id"] in pads]
    pairs = list(DEMO_PAIRS)
    for pid, pad in pads.items():
        if not HOSPITAL_WORDS.search(pad["name"]):
            continue
        near = sorted((t for t in trauma if t != pid),
                      key=lambda t: haversine_mi(pad["lat"], pad["lon"], pads[t]["lat"], pads[t]["lon"]))
        pairs += [(pid, t) for t in near[:NEAREST_TRAUMA]]
    return list(dict.fromkeys(pairs))


def fit(pairs: dict) -> dict | None:
    """Fallback model numbers from the saved routes (trips of at least 3 straight miles)."""
    pads, ratios, miles, hours = heliports(), [], 0.0, 0.0
    for key, r in pairs.items():
        a, b = key.split("|")
        straight = haversine_mi(pads[a]["lat"], pads[a]["lon"], pads[b]["lat"], pads[b]["lon"])
        if straight >= 3 and r["minutes"] > 0:
            ratios.append(r["miles"] / straight)
            miles += r["miles"]
            hours += r["minutes"] / 60
    if len(ratios) < 20:
        return None
    return {"detour_factor": round(statistics.median(ratios), 3), "avg_mph": round(miles / hours, 1),
            "n": len(ratios), "note": "median road miles per straight-line mile, and total miles over "
                                      "total free-flow hours, across the saved routes"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    saved = {} if args.force or not roads.ROUTES_PATH.exists() else \
        json.loads(roads.ROUTES_PATH.read_text(encoding="utf-8")).get("pairs", {})
    pads, todo = heliports(), [p for p in wanted_pairs() if roads.pair_key(*p) not in saved]
    print(f"{len(saved)} routes already saved, {len(todo)} to fetch")
    failed = 0
    for i, (a, b) in enumerate(todo, 1):
        try:
            r = roads.fetch_osrm(pads[a]["lat"], pads[a]["lon"], pads[b]["lat"], pads[b]["lon"], timeout=30)
            r["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            saved[roads.pair_key(a, b)] = r
        except Exception as err:  # keep going; a rerun picks up what is missing
            failed += 1
            print(f"  {a}->{b} failed: {err}")
        if i % 25 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)}", flush=True)
        time.sleep(1.0)

    out = {"_note": "Road routes from the public OSRM demo router (OpenStreetMap data). Free-flow times, "
                    "no traffic. Written by scripts/cache_routes.py.",
           "fit": fit(saved), "pairs": dict(sorted(saved.items()))}
    roads.ROUTES_PATH.write_text(json.dumps(out, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Saved {len(saved)} routes ({failed} failed) to {roads.ROUTES_PATH} "
          f"({roads.ROUTES_PATH.stat().st_size / 1024:.0f} KB). Fallback fit: {out['fit']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
