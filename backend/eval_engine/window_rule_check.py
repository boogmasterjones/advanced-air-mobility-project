"""Which rule should combine hourly, per-airport chances into one chance for a flight?

A flight needs every hour it touches, at both airports, to stay flyable. The forecaster
gives one chance per airport and hour. Three ways to combine them, none with a fitted
number:
  lowest      the lowest of the chances (right if the hours and airports move together)
  product     all of them multiplied (right if they are independent)
  midpoint    the square root of lowest x product: halfway between the two on a log scale

This script scores the three on TRAINING years only (the 2024 test year is not touched),
on pairs of nearby airports and two-hour windows, against what really happened. The
forecasts are in-sample there, so the absolute scores flatter all three alike; the
question is only which rule's numbers match the outcomes best.

Run from backend/:   python -m eval_engine.window_rule_check
Prints the comparison and writes eval/results/window_rule_check.json.
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timezone

import numpy as np

from app.core import forecaster
from app.core.geo import DATA_DIR, station_neighbors
from data_build import metrics
from data_build.baselines import TEST_YEAR, load_dataset

RESULTS = DATA_DIR.parent / "eval" / "results"
SAMPLE = 60000
RULES = {
    "lowest": lambda p: p.min(axis=1),
    "product": lambda p: p.prod(axis=1),
    "midpoint": lambda p: np.sqrt(p.min(axis=1) * p.prod(axis=1)),
}


def main() -> int:
    models = forecaster._load()
    if models is None:
        raise SystemExit("No trained forecaster found. Run: python -m models.train_forecaster")
    ds = load_dataset()
    train = ds["label_year"] < TEST_YEAR
    index = {(int(s), int(t)): i for i, (s, t) in enumerate(zip(ds["station"], ds["t"])) if train[i]}
    code_to_idx = {code: i for i, code in enumerate(ds["stations"])}
    pairs = [(code_to_idx[a], code_to_idx[b]) for a in ds["stations"]
             for b, miles in station_neighbors(a) if 10 <= miles <= 70]
    rng = random.Random(3)
    keys = list(index)
    rows_a, rows_b = [], []
    while len(rows_a) < SAMPLE:
        s, t = rng.choice(keys)
        partners = [b for a, b in pairs if a == s]
        if not partners:
            continue
        j = index.get((rng.choice(partners), t))
        i = index[(s, t)]
        if j is None or (ds["Y"][[i, j], :2] < 0).any():
            continue
        rows_a.append(i)
        rows_b.append(j)
    cols = []
    for rows in (rows_a, rows_b):
        X = ds["X"][rows].astype(np.float64)
        for h in (0, 1):
            cal = models.meta["calibration"][str(h)]
            raw = models.boosters[h].predict(X)
            cols.append(np.clip(np.interp(raw, cal["x"], cal["y"]), models.meta["p_min"], models.meta["p_max"]))
    p = np.column_stack(cols)                       # two hours at each of two airports
    truth = (ds["Y"][rows_a, :2].min(axis=1) & ds["Y"][rows_b, :2].min(axis=1)).astype(int)

    out = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "years": "training years only", "windows": len(truth),
           "stayed_flyable": round(float(truth.mean()), 4), "rules": {}}
    print(f"{len(truth):,} two-hour, two-airport windows from the training years; all flyable in {truth.mean():.1%}")
    print(f"{'rule':10} {'Brier':>8} {'calibration gap':>16}   said 50-70% / 70-85% / 85-95% -> really")
    for name, rule in RULES.items():
        q = rule(p)
        bands = []
        for lo, hi in ((0.5, 0.7), (0.7, 0.85), (0.85, 0.95)):
            m = (q >= lo) & (q < hi)
            bands.append(round(float(truth[m].mean()), 3) if m.sum() >= 50 else None)
        out["rules"][name] = {"brier": round(metrics.brier(q, truth), 5),
                              "calibration_error": round(metrics.calibration_error(q, truth), 4),
                              "really_flyable_when_said_50_70_85_95": bands}
        print(f"{name:10} {out['rules'][name]['brier']:>8.4f} {out['rules'][name]['calibration_error']:>16.4f}   {bands}")
    best = min(out["rules"], key=lambda k: out["rules"][k]["calibration_error"])
    out["best_calibrated"] = best
    print(f"Best calibrated on the training years: {best}")
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "window_rule_check.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
