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

from app.core import decision, forecaster, history, replay, weather
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
            "aircraft_sent": round(mean(r["choice"] != "ground_only" for r in rows), 3),
            # An aircraft was sent and the weather then closed: a launch that helped nobody.
            "aircraft_sent_for_nothing": round(mean(r["choice"] != "ground_only" and not c["actual_flyable"]
                                                    for r, c in zip(rows, cases)), 3),
        }
    return out


def weather_calibration(cases: list[dict]) -> list[dict]:
    """End-to-end check of the number shown on screen: when the app said "X% chance the
    weather stays flyable for the flight", how often did it stay flyable?"""
    bands = [(0, 50), (50, 70), (70, 85), (85, 95), (95, 101)]
    out = []
    for lo, hi in bands:
        hit = [c for c in cases if c["forecast_chance_pct"] is not None and lo <= c["forecast_chance_pct"] < hi]
        if hit:
            out.append({"app_said": f"{lo} to {min(hi, 100)}%", "cases": len(hit),
                        "mean_app_said_pct": round(mean(c["forecast_chance_pct"] for c in hit), 1),
                        "stayed_flyable_pct": round(100 * mean(c["actual_flyable"] for c in hit), 1)})
    return out


def demo_days(cases: list[dict], path) -> list[dict]:
    """Cases worth showing live, on three different days:
      saw it coming   the sky was fine at decision time, the old rule would have launched,
                      the app kept to ground, and the weather then closed
      saw it clearing the weather was bad at decision time, the old rule kept to ground,
                      the app sent the aircraft as well, and the flight got through"""
    def kind(c) -> str | None:
        ours, rule = c["policies"]["ours"]["choice"], c["policies"]["weather_now"]["choice"]
        if not c["actual_flyable"] and ours == "ground_only" and rule != "ground_only":
            return "saw it coming"
        if c["actual_flyable"] and ours != "ground_only" and rule == "ground_only":
            return "saw it clearing"
        return None

    def strength(c) -> float:  # the more the forecast disagreed with "right now", the clearer the demo
        pct = c["forecast_chance_pct"] or 50
        return (100 - pct) if kind(c) == "saw it coming" else c["policies"]["weather_now"]["regret_min"]

    picks, seen_days = [], set()
    ranked = sorted((c for c in cases if kind(c)), key=strength, reverse=True)
    for wanted in ("saw it coming", "saw it coming", "saw it clearing"):
        for c in ranked:
            if kind(c) == wanted and c["when"][:10] not in seen_days:
                seen_days.add(c["when"][:10])
                picks.append({**c, "kind": wanted})
                break
    lines = ["# Demo days for the Time Machine", "",
             "Written by `python -m eval_engine.replay_eval` (task A6). Replayed cases from the held-out",
             "weather year where the forecaster disagreed with the old \"weather right now\" rule and turned",
             "out right. All patient cases are synthetic. Aircraft are simulated and road times are modeled.", ""]
    if not picks:
        lines.append("No case in this run met the bar. Run the eval again with more cases.")
    for i, c in enumerate(picks, 1):
        local = datetime.fromisoformat(c["when"]).astimezone(FLORIDA)
        ours, rule = c["policies"]["ours"], c["policies"]["weather_now"]
        happened = "it stayed flyable" if c["actual_flyable"] else "it did not stay flyable"
        story = ("The sky looked fine, so the old rule would have launched an aircraft for nothing."
                 if c["kind"] == "saw it coming" else
                 f"The weather looked bad, so the old rule kept to ground and lost {rule['regret_min']} min.")
        lines += [f"## {i}. {local:%A %B %d, %Y, %I:%M %p} Florida time ({c['kind']})",
                  f"- From **{c['origin_name'].title()}** (`{c['origin']}`) to **{c['dest_name'].title()}** "
                  f"(`{c['dest']}`), deadline {c['deadline_min']} min",
                  f"- Replay time (UTC): `{c['when']}`",
                  f"- The app gave a {c['forecast_chance_pct']}% chance that the weather stays flyable for the "
                  f"flight. What happened: {happened}.",
                  f"- The app suggested `{ours['choice']}`. The \"weather right now\" rule would have picked "
                  f"`{rule['choice']}`. {story}", ""]
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
    n_active = summary.get("active_weather_hours", {}).get("cases", 0)
    model = forecaster.model_name()
    note = (f"Synthetic cases replayed on real {span[0].year} weather; aircraft simulated, road times modeled. "
            f"Compared with the old rule that looks only at the weather right now. Forecaster: {model}.")
    if model == forecaster.RULE_MODEL:
        note += " WARNING: the trained forecaster was not installed, so the app and the old rule are the same here."
        print("WARNING: no trained forecaster found; this run compares the rule with itself.")
    get = lambda group, policy, key: group.get(policy, {}).get(key)  # noqa: E731
    out = {
        "id": "E2", "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "weather_year": span[0].year, "seed": args.seed, "forecaster": forecaster.model_name(),
        "summary": summary,
        "weather_chance_check": weather_calibration(every),
        "demo_cases": picks, "cases": every,
        "how_to_read": "regret_min: minutes lost against the fastest choice under the weather that really "
                       "happened. aircraft_sent_for_nothing: an aircraft was sent and the weather then closed. "
                       "always_both loses no minutes by construction but sends an aircraft every time. "
                       "weather_chance_check: the chance shown on screen against how often the weather held.",
        "metrics": [
            {"id": "E2", "name": "Aircraft sent for nothing in active weather (share of cases)",
             "value": get(active, "ours", "aircraft_sent_for_nothing"),
             "baseline": get(active, "weather_now", "aircraft_sent_for_nothing"),
             "note": f"{n_active} cases with a storm or unflyable hour within 3 hours at the pick-up airport. "
                     f"Lower is better. {note}"},
            {"id": "E2", "name": "Minutes lost in active weather against the best choice in hindsight",
             "value": get(active, "ours", "mean_regret_min"), "baseline": get(active, "weather_now", "mean_regret_min"),
             "note": f"Lower is better. Sending both vehicles every time loses 0 minutes but launches an aircraft "
                     f"in every case. {note}"},
            {"id": "E2", "name": "Minutes lost at random hours against the best choice in hindsight",
             "value": get(calm, "ours", "mean_regret_min"), "baseline": get(calm, "weather_now", "mean_regret_min"),
             "note": f"{summary.get('random_hours', {}).get('cases', 0)} cases at random hours of the year. {note}"},
        ],
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "e2.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    for name, s in summary.items():
        print(f"{name}: {s['cases']} cases, weather stayed flyable in {s['weather_stayed_flyable']:.0%}")
        print(f"  {'policy':14} {'min lost':>9} {'on time':>8} {'air sent':>9} {'for nothing':>12}")
        for policy, r in s["policies"].items():
            print(f"  {policy:14} {r['mean_regret_min']:>9.2f} {r['mean_chance_on_time']:>8.1%} "
                  f"{r['aircraft_sent']:>9.0%} {r['aircraft_sent_for_nothing']:>12.0%}")
    print("When the app said X% chance the weather holds for the flight:")
    for row in out["weather_chance_check"]:
        print(f"  {row['app_said']:>12}: {row['cases']:>4} cases, it held in {row['stayed_flyable_pct']}%")
    print(f"Wrote {RESULTS / 'e2.json'} and {DOCS / 'demo_days.md'} ({len(picks)} demo cases)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
