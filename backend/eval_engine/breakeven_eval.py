"""E6: sanity check of the time model against a published study.

A Swiss study of 645 heart and stroke transfers by helicopter (PMC8650228) found the
helicopter faster than the road above about 51.3 km (32 miles) of road distance. Reading
the paper matters here: its helicopter time was measured (emergency call to landing at
the destination), but its road time was NOT measured. It was the map drive time plus a
flat 10 minutes for preparation and handover.

So this check runs our time model two ways:
  study_definition   the same comparison the study made: our helicopter time up to landing,
                     against drive time + 10 min. This is the number to hold against 32 mi.
  our_model          what the app actually uses: full ground time (wait for the ambulance,
                     time at the sending hospital, drive, handoff) against full air time.

Run from backend/:
    python -m eval_engine.breakeven_eval
Typical (median) values from data/aircraft_profiles.json and the road model in
data/routes.json, plain arithmetic. A sanity check only: one country, one provider, and
our road times have no traffic. Writes eval/results/e6.json.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from datetime import datetime, timezone

from app.core import decision, roads
from app.core.geo import DATA_DIR, heliports, nearest_station

RESULTS = DATA_DIR.parent / "eval" / "results"
SWISS_BREAKEVEN_MI = 51.3 / 1.609344  # 31.9
SWISS_GROUND_OVERHEAD_MIN = 10        # the study's flat allowance, an assumption of theirs
STEP_MI = 0.5
HOSPITAL_WORDS = re.compile(r"HOSP|MED|HEALTH|MEML|RGNL|CLINIC|TRAUMA|SHANDS|BAPTIST|ADVENT", re.I)


def road_model() -> tuple[float, float, str]:
    """(road miles per straight mile, average road mph, where the numbers come from)."""
    fit = roads._cache()["fit"]
    if fit:
        return fit["detour_factor"], fit["avg_mph"], f"fitted to {fit['n']} OSRM routes"
    ground = decision.profiles()["ground_ambulance"]
    return (float(ground["detour_factor"]["value"]), float(ground["avg_mph"]["value"]),
            "profile defaults (no saved routes yet)")


def _v(profile: str, key: str) -> float:
    return float(decision.profiles()[profile][key]["value"])


def drive_min(road_mi: float, mph: float) -> float:
    return road_mi / mph * 60


def ground_full(road_mi: float, mph: float) -> float:
    g = "ground_ambulance"
    return (_v(g, "dispatch_delay_min_median") + _v(g, "load_min_median") + drive_min(road_mi, mph)
            + _v(g, "handoff_min_median"))


def air_to_landing(road_mi: float, detour: float, aircraft: str, to_pickup_mi: float) -> float:
    """Call to landing at the destination: launch, fly in, time at the sender, fly."""
    flight_mi = road_mi / detour + to_pickup_mi
    return (_v(aircraft, "launch_delay_min_median") + flight_mi / _v(aircraft, "cruise_mph") * 60
            + _v(aircraft, "load_min_median"))


def breakeven(air, ground) -> float | None:
    """Shortest road distance at which the air time is below the ground time."""
    r = STEP_MI
    while r <= 300:
        if air(r) < ground(r):
            return r
        r += STEP_MI
    return None


def typical_base_distance() -> float:
    """Median distance from a hospital-style pad to the nearest airport in stations.csv,
    which is where the simulated aircraft waits."""
    return statistics.median(nearest_station(p["lat"], p["lon"])[1]
                             for p in heliports().values() if HOSPITAL_WORDS.search(p["name"]))


def main() -> int:
    detour, mph, how = road_model()
    base_mi = round(typical_base_distance(), 1)
    rows = {}
    for aircraft in ("helicopter", "air_taxi_a"):
        landing = lambda r, a=aircraft: air_to_landing(r, detour, a, base_mi)  # noqa: E731
        rows[aircraft] = {
            "study_definition": breakeven(landing, lambda r: drive_min(r, mph) + SWISS_GROUND_OVERHEAD_MIN),
            "our_model": breakeven(lambda r, a=aircraft: landing(r) + _v(a, "unload_min_median"),
                                   lambda r: ground_full(r, mph)),
        }
    ours, app = rows["helicopter"]["study_definition"], rows["helicopter"]["our_model"]
    if ours is None:
        verdict = "Compared the way the study did, our model never finds the helicopter faster."
    else:
        gap = (ours - SWISS_BREAKEVEN_MI) / SWISS_BREAKEVEN_MI
        close = "agrees with the study to within 25%" if abs(gap) <= 0.25 else \
            ("favors the helicopter more than the study" if gap < 0 else "favors the road more than the study")
        verdict = (f"Compared the way the study did, our model puts the helicopter break-even at {ours} road "
                   f"miles against the study's {SWISS_BREAKEVEN_MI:.0f}: it {close}.")
    verdict += (f" With the ground delays the app really uses (waiting for the ambulance and time at the "
                f"sending hospital, from published transfer studies), the helicopter wins from {app} miles. "
                f"The study allowed the road only 10 minutes for all of that.")
    out = {
        "id": "E6",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reference": {"road_miles": round(SWISS_BREAKEVEN_MI, 1),
                      "source": "https://pmc.ncbi.nlm.nih.gov/articles/PMC8650228/",
                      "how_it_was_measured": "helicopter: emergency call to landing at the destination "
                                             "(measured); road: map drive time plus a flat 10 minutes (assumed)"},
        "road_model": {"road_miles_per_straight_mile": detour, "avg_mph": mph, "from": how,
                       "note": "free-flow, no traffic; traffic would lower every break-even"},
        "typical_miles_from_base_to_pickup": base_mi,
        "breakeven_road_miles": rows,
        "verdict": verdict,
        "metrics": [{
            "id": "E6", "name": "Helicopter beats the road above this distance (miles), measured the study's way",
            "value": ours, "baseline": round(SWISS_BREAKEVEN_MI, 1),
            "note": verdict + " Road times have no traffic. Sanity check only.",
        }],
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "e6.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"Road model: {detour} road mi per straight mi, {mph} mph ({how})")
    print(f"Typical base-to-pickup distance: {base_mi} mi")
    for aircraft, r in rows.items():
        print(f"  {aircraft:12} break-even: {r['study_definition']} mi the study's way, "
              f"{r['our_model']} mi in our full model   (Swiss study: {SWISS_BREAKEVEN_MI:.1f} mi)")
    print(verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
