"""E2: decision regret on replayed past days.

Synthetic transfer cases (a hospital pad to one of its two nearest trauma centers) are
replayed at real past moments from the held-out weather year. For each case the app's
suggestion, made with only the weather known at that moment, is scored against the best
choice under the weather that really followed (see app/core/replay.py).

Policies compared on exactly the same cases:
  ours            the app: forecaster + decision rule
  weather_now     the v0 rule: 90% if every airport is flyable right now, else 0%
  always_ground / always_air / always_both   fixed choices

Half the cases are drawn at random hours (mostly calm, like real life) and half from
"active" hours with a thunderstorm or unflyable weather within 3 hours at the pick-up
airport, because calm hours cannot tell the policies apart. Both groups are reported.
Road times and the aircraft are modeled or simulated in the replay, as in the app.

Run from backend/:
    python -m eval_engine.replay_eval            # 400 cases
    python -m eval_engine.replay_eval --cases 100
Writes eval/results/e2.json and docs/demo_days.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from datetime import datetime, timedelta, timezone
from statistics import mean

from app.core import decision, history, replay, weather
from app.core.case import FLORIDA, build_case
from app.core.geo import DATA_DIR, haversine_mi, heliports, nearest_station
from app.core.ledger import Ledger

RESULTS = DATA_DIR.parent / "eval" / "results"
DOCS = DATA_DIR.parent / "docs"
HOSPITAL_WORDS = re.compile(r"HOSP|MED|HEALTH|MEML|RGNL|CLINIC|TRAUMA|SHANDS|BAPTIST|ADVENT", re.I)
DEADLINES = (90, 120, 150, 180)
MIN_FLIGHT_MI, MAX_FLIGHT_MI = 15, 70
VEHICLES = {"ground_only": 1, "air_only": 1, "air_and_ground": 2}
HOUR = timedelta(hours=1)


def candidate_pairs() -> list[tuple[dict, dict]]:
    pads = heliports()
    with open(DATA_DIR / "seeds" / "trauma_centers.csv", newline="", encoding="utf-8") as f:
        trauma = [pads[r["faa_id"]] for r in csv.DictReader(f) if r["faa_id"] in pads]
    pairs = []
    for pad in pads.values():
        if not HOSPITAL_WORDS.search(pad["name"]):
            continue
        near = sorted((t for t in trauma if t["faa_id"] != pad["faa_id"]),
                      key=lambda t: haversine_mi(pad["lat"], pad["lon"], t["lat"], t["lon"]))[:2]
        pairs += [(pad, t) for t in near
                  if MIN_FLIGHT_MI <= haversine_mi(pad["lat"], pad["lon"], t["lat"], t["lon"]) <= MAX_FLIGHT_MI]
    return pairs


def active_hours(icao: str) -> list[datetime]:
    """Hours with a thunderstorm or unflyable weather within 3 hours at this airport."""
    recs = history.archive().get(icao, {})
    bad = {t for t, r in recs.items() if r.ts or not r.flyable}
    return sorted({t + k * HOUR for t in bad for k in range(-3, 4)} & set(recs))


def weather_now_choice(built, origin, dest, deadline, when) -> str:
    """The v0 rule the forecaster replaced: look only at the weather right now."""
    source = history.ArchiveWeather()
    statuses = []
    for st in built.stations:
        w = source.station(st, when)
        if w.observed_at is None:
            return "ground_only"
        statuses.append(not weather.problems(w.visibility_mi, w.ceiling_ft, w.wind_kt, w.gust_kt, w.thunderstorm))
    options = decision.evaluate(
        origin=origin, dest=dest, deadline_min=deadline, local_hour=built.local_hour,
        p_weather=0.9 if all(statuses) else 0.0, weather_reasons=[], ledger=Ledger(),
        road=built.road, base=built.base, wind=built.wind, temp_c=built.temp_c)
    return decision.recommend(options)


def run_case(origin: dict, dest: dict, deadline: int, when: datetime) -> dict | None:
    built = build_case(origin=origin, dest=dest, deadline_min=deadline, now=when,
                       source=history.ArchiveWeather())
    flew = replay.actual_weather(built)
    if flew is None:
        return None
    truth = replay.hindsight(built, origin, dest, deadline, flew)
    if any(o.status != "OK" for o in truth):
        return None  # out of range for the aircraft: nothing to compare
    choices = {"ours": built.out["recommended"],
               "weather_now": weather_now_choice(built, origin, dest, deadline, when),
               "always_ground": "ground_only", "always_air": "air_only", "always_both": "air_and_ground"}
    weather_fact = next((f.value for f in built.out["facts"]
                         if f.label == "Chance the weather stays flyable for the flight"), None)
    return {"when": when.isoformat(timespec="minutes"), "origin": origin["faa_id"], "dest": dest["faa_id"],
            "origin_name": origin["name"], "dest_name": dest["name"], "deadline_min": deadline,
            "actual_flyable": flew, "forecast_chance_pct": weather_fact,
            "best": replay.score("ground_only", truth)["actual_best_strategy"],
            "policies": {name: {"choice": choice, **replay.score(choice, truth)} for name, choice in choices.items()}}


def summarize(cases: list[dict]) -> dict:
    out = {"cases": len(cases), "weather_stayed_flyable": round(mean(c["actual_flyable"] for c in cases), 3),
           "policies": {}}
    for name in cases[0]["policies"]:
        rows = [c["policies"][name] for c in cases]
        out["policies"][name] = {
            "mean_regret_min": round(mean(r["regret_min"] for r in rows), 2),
            "mean_chance_on_time": round(mean(r["chance_on_time"] for r in rows), 4),
            "mean_chance_lost": round(mean(r["regret_chance"] for r in rows), 4),
            "picked_best_choice": round(mean(r["choice"] == r["actual_best_strategy"] for r in rows), 3),
            "vehicles_per_case": round(mean(VEHICLES[r["choice"]] for r in rows), 2),
        }
    return out


def demo_days(cases: list[dict], path) -> list[dict]:
    """Storm cases where the forecast changed the answer for the better: good to show live."""
    def gain(c):
        return c["policies"]["weather_now"]["regret_min"] - c["policies"]["ours"]["regret_min"]

    picks, seen_days = [], set()
    for c in sorted((c for c in cases if not c["actual_flyable"]), key=gain, reverse=True):
        day = c["when"][:10]
        if day in seen_days or gain(c) <= 0:
            continue
        seen_days.add(day)
        picks.append(c)
        if len(picks) == 3:
            break
    lines = ["# Demo days for the Time Machine", "",
             "Written by `python -m eval_engine.replay_eval` (task A6). These are replayed cases from the",
             "held-out weather year where the weather turned unflyable after the decision time and the",
             "forecaster avoided minutes that the old \"weather right now\" rule would have lost.",
             "All patient cases are synthetic. Aircraft are simulated and road times are modeled.", ""]
    if not picks:
        lines.append("No case in this run met the bar. Run the eval again with more cases.")
    for i, c in enumerate(picks, 1):
        local = datetime.fromisoformat(c["when"]).astimezone(FLORIDA)
        ours, rule = c["policies"]["ours"], c["policies"]["weather_now"]
        lines += [f"## {i}. {local:%A %B %d, %Y, %I:%M %p} Florida time",
                  f"- From **{c['origin_name'].title()}** (`{c['origin']}`) to **{c['dest_name'].title()}** "
                  f"(`{c['dest']}`), deadline {c['deadline_min']} min",
                  f"- Replay time (UTC): `{c['when']}`",
                  f"- Forecast chance the weather stays flyable: {c['forecast_chance_pct']}%. "
                  f"What happened: it did not stay flyable.",
                  f"- The app suggested `{ours['choice']}` and lost {ours['regret_min']} min against the best "
                  f"choice in hindsight. The \"weather right now\" rule would have picked `{rule['choice']}` "
                  f"and lost {rule['regret_min']} min.", ""]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return picks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--cases", type=int, default=400)
    ap.add_argument("--seed", type=int, default=2024)
    args = ap.parse_args()
    span = history.available_range()
    if span is None:
        raise SystemExit("No replay archive. Run: python -m data_build.build_dataset")
    rng = random.Random(args.seed)
    pairs = candidate_pairs()
    first, last = span[0] + 8 * HOUR, span[1] - 6 * HOUR
    total_hours = int((last - first) / HOUR)

    groups: dict[str, list[dict]] = {"random_hours": [], "active_weather_hours": []}
    tries = 0
    while min(len(g) for g in groups.values()) < args.cases // 2 and tries < args.cases * 40:
        tries += 1
        origin, dest = rng.choice(pairs)
        group = "random_hours" if len(groups["random_hours"]) <= len(groups["active_weather_hours"]) else "active_weather_hours"
        if group == "random_hours":
            when = first + rng.randrange(total_hours) * HOUR
        else:
            hours = active_hours(nearest_station(origin["lat"], origin["lon"])[0]["icao"])
            hours = [h for h in hours if first <= h <= last]
            if not hours:
                continue
            when = rng.choice(hours)
        when += timedelta(minutes=rng.choice((0, 10, 20, 30, 40, 50)))
        case = run_case(origin, dest, rng.choice(DEADLINES), when)
        if case is not None:
            groups[group].append(case)

    every = groups["random_hours"] + groups["active_weather_hours"]
    summary = {name: summarize(cases) for name, cases in groups.items() if cases}
    picks = demo_days(every, DOCS / "demo_days.md")
    active = summary.get("active_weather_hours", {}).get("policies", {})
    calm = summary.get("random_hours", {}).get("policies", {})
    note = (f"{len(every)} synthetic cases replayed on real {span[0].year} weather; aircraft simulated, road "
            f"times modeled. Minutes lost against the best choice in hindsight.")
    out = {
        "id": "E2", "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "weather_year": span[0].year, "seed": args.seed, "summary": summary,
        "demo_cases": picks, "cases": every,
        "how_to_read": "regret_min: minutes lost against the fastest choice under the weather that really "
                       "happened. chance_on_time: chance of meeting the deadline under that weather. "
                       "always_both has zero regret by construction but always uses two vehicles.",
        "metrics": [
            {"id": "E2", "name": "Minutes lost in active weather: app vs \"weather right now\" rule",
             "value": active.get("ours", {}).get("mean_regret_min"),
             "baseline": active.get("weather_now", {}).get("mean_regret_min"),
             "note": note + " Active weather: a storm or unflyable hour within 3 hours at the pick-up airport. "
                            f"Vehicles sent per case: app {active.get('ours', {}).get('vehicles_per_case')}, "
                            f"rule {active.get('weather_now', {}).get('vehicles_per_case')}."},
            {"id": "E2", "name": "Minutes lost at random hours: app vs \"weather right now\" rule",
             "value": calm.get("ours", {}).get("mean_regret_min"),
             "baseline": calm.get("weather_now", {}).get("mean_regret_min"), "note": note},
        ],
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "e2.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    for name, s in summary.items():
        print(f"{name}: {s['cases']} cases, weather stayed flyable in {s['weather_stayed_flyable']:.0%}")
        print(f"  {'policy':14} {'min lost':>9} {'on time':>8} {'best pick':>10} {'vehicles':>9}")
        for policy, r in s["policies"].items():
            print(f"  {policy:14} {r['mean_regret_min']:>9.2f} {r['mean_chance_on_time']:>8.1%} "
                  f"{r['picked_best_choice']:>10.0%} {r['vehicles_per_case']:>9.2f}")
    print(f"Wrote {RESULTS / 'e2.json'} and {DOCS / 'demo_days.md'} ({len(picks)} demo cases)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
