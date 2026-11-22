"""E6: sanity check of the time model against a published study.

A Swiss study of 645 heart and stroke transfers found helicopters faster than ground
ambulances above about 51.3 km (32 miles) of road distance (RESEARCH.md section 4). Our
time model should put the helicopter break-even in the same region. This is a sanity
check only: one country, one provider, and our road times have no traffic.

Run from backend/:
    python -m eval_engine.breakeven_eval

The check uses typical (median) values from data/aircraft_profiles.json and the road
model in data/routes.json, with plain arithmetic so every step can be followed:
  ground  = dispatch delay + road miles / road speed + handoff
  air     = launch delay + flight to the pick-up pad + loading + flight + unloading
Writes eval/results/e6.json.
"""
from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime, timezone

from app.core import decision, roads
from app.core.geo import DATA_DIR, haversine_mi, heliports, nearest_station

RESULTS = DATA_DIR.parent / "eval" / "results"
SWISS_BREAKEVEN_MI = 51.3 / 1.609344  # 31.9
STEP_MI = 0.5


def road_model() -> tuple[float, float, str]:
    """(road miles per straight mile, average road mph, where the numbers come from)."""
    fit = roads._cache()["fit"]
    if fit:
        return fit["detour_factor"], fit["avg_mph"], f"fitted to {fit['n']} OSRM routes"
    ground = decision.profiles()["ground_ambulance"]
    return (float(ground["detour_factor"]["value"]), float(ground["avg_mph"]["value"]),
            "profile defaults (no saved routes yet)")


def ground_min(road_mi: float, mph: float) -> float:
    g = decision.profiles()["ground_ambulance"]
    return (g["dispatch_delay_min_median"]["value"] + road_mi / mph * 60
            + g["handoff_min_median"]["value"])


def air_min(road_mi: float, detour: float, aircraft: str, to_pickup_mi: float) -> float:
    a = decision.profiles()[aircraft]
    flight_mi = road_mi / detour + to_pickup_mi
    return (a["launch_delay_min_median"]["value"] + flight_mi / a["cruise_mph"]["value"] * 60
            + a["load_min_median"]["value"] + a["unload_min_median"]["value"])


def breakeven(detour: float, mph: float, aircraft: str, to_pickup_mi: float) -> float | None:
    """Shortest road distance at which the aircraft is faster than the ambulance."""
    r = STEP_MI
    while r <= 300:
        if air_min(r, detour, aircraft, to_pickup_mi) < ground_min(r, mph):
            return r
        r += STEP_MI
    return None


def typical_base_distance() -> float:
    """Median distance from a hospital-style pad to the nearest airport in stations.csv,
    which is where the simulated aircraft waits."""
    import re
    words = re.compile(r"HOSP|MED|HEALTH|MEML|RGNL|CLINIC|TRAUMA|SHANDS|BAPTIST|ADVENT", re.I)
    return statistics.median(nearest_station(p["lat"], p["lon"])[1]
                             for p in heliports().values() if words.search(p["name"]))


def main() -> int:
    detour, mph, how = road_model()
    base_mi = round(typical_base_distance(), 1)
    rows = {}
    for aircraft in ("helicopter", "air_taxi_a"):
        rows[aircraft] = {
            "aircraft_already_at_pickup": breakeven(detour, mph, aircraft, 0.0),
            "aircraft_flies_in_from_base": breakeven(detour, mph, aircraft, base_mi),
        }
    heli = rows["helicopter"]["aircraft_flies_in_from_base"]
    if heli is None:
        verdict = "Our model never finds the helicopter faster, which disagrees with the study."
    elif heli < 0.75 * SWISS_BREAKEVEN_MI:
        verdict = ("Our model finds the helicopter faster at shorter distances than the study did, so it "
                   "probably favors air: real missions spend longer at the bedside and on the pad than our "
                   "labeled assumptions. Read air times as optimistic.")
    elif heli > 1.25 * SWISS_BREAKEVEN_MI:
        verdict = "Our model needs longer distances than the study before the helicopter wins, so it probably favors ground."
    else:
        verdict = "Our model agrees with the study to within 25%."
    out = {
        "id": "E6",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reference": {"road_miles": round(SWISS_BREAKEVEN_MI, 1),
                      "source": "Swiss study of 645 heart and stroke transfers (RESEARCH.md section 4)"},
        "road_model": {"road_miles_per_straight_mile": detour, "avg_mph": mph, "from": how,
                       "note": "free-flow, no traffic; traffic would lower the break-even"},
        "typical_miles_from_base_to_pickup": base_mi,
        "breakeven_road_miles": rows,
        "how_to_read": "Road distance above which the aircraft's typical time beats the ambulance's. "
                       "The study measured real missions, where the helicopter flies in from its base.",
        "metrics": [{
            "id": "E6", "name": "Helicopter beats ambulance above this road distance (miles)",
            "value": heli, "baseline": round(SWISS_BREAKEVEN_MI, 1),
            "note": f"Our time model, helicopter flying in {base_mi} mi from its base, against the Swiss "
                    f"study's 32 miles. With the helicopter already at the pick-up pad: "
                    f"{rows['helicopter']['aircraft_already_at_pickup']} mi. Road times have no traffic. "
                    f"{verdict}",
        }],
        "verdict": verdict,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "e6.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"Road model: {detour} road mi per straight mi, {mph} mph ({how})")
    print(f"Typical base-to-pickup distance: {base_mi} mi")
    for aircraft, r in rows.items():
        print(f"  {aircraft:12} break-even: {r['aircraft_already_at_pickup']} mi at the pad, "
              f"{r['aircraft_flies_in_from_base']} mi flying in   (Swiss study: {SWISS_BREAKEVEN_MI:.1f} mi)")
    print(verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
