"""Does the running app give the same forecasts that were scored in E1?

E1 scores the model on feature rows built by the training pipeline. The app builds its
features again from the Time Machine archive (values rounded for storage). This check
takes random hours from the test year and compares the two forecasts for the same
airport and hour. Large gaps would mean the evidence does not describe the app.

Run from backend/ (needs data/processed/dataset.npz, so only where the dataset was built):
    python -m eval_engine.serving_check
Prints a summary and writes eval/results/serving_check.json.
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timezone

import numpy as np

from app.core import forecaster, history
from app.core.geo import DATA_DIR, stations
from data_build.baselines import TEST_YEAR, load_dataset

RESULTS = DATA_DIR.parent / "eval" / "results"
SAMPLE = 3000


def main() -> int:
    models = forecaster._load()
    if models is None:
        raise SystemExit("No trained forecaster found. Run: python -m models.train_forecaster")
    ds = load_dataset()
    by_icao = {s["icao"]: s for s in stations()}
    rows = np.flatnonzero(ds["year"] == TEST_YEAR)
    rng = random.Random(11)
    picks = rng.sample(list(rows), min(SAMPLE, len(rows)))
    source = history.ArchiveWeather()
    gaps: dict[int, list[float]] = {h: [] for h in models.boosters}
    missing = 0
    for i in picks:
        st = by_icao[ds["stations"][ds["station"][i]]]
        t = datetime.fromtimestamp(int(ds["t"][i]), tz=timezone.utc)
        served = source.station(st, t).forecast
        if served is None:
            missing += 1
            continue
        scored = models.predict([float(v) for v in ds["X"][i]])
        for h in gaps:
            gaps[h].append(abs(served.p_flyable[h] - scored[h]))
    out = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "model": models.meta["model"], "hours_compared": len(picks) - missing,
           "hours_the_app_could_not_forecast": missing, "by_hours_ahead": {}}
    print(f"Compared {len(picks) - missing} random {TEST_YEAR} station-hours ({missing} had no archive record)")
    print(f"{'ahead':>6} {'mean gap':>9} {'largest':>8} {'over 1 point':>13} {'over 5 points':>14}")
    for h, g in gaps.items():
        a = np.asarray(g)
        row = {"mean_gap": round(float(a.mean()), 5), "largest_gap": round(float(a.max()), 4),
               "share_over_1_point": round(float((a > 0.01).mean()), 4),
               "share_over_5_points": round(float((a > 0.05).mean()), 4)}
        out["by_hours_ahead"][str(h)] = row
        print(f"{'+' + str(h) + ' h':>6} {row['mean_gap']:>9.4f} {row['largest_gap']:>8.3f} "
              f"{row['share_over_1_point']:>13.1%} {row['share_over_5_points']:>14.1%}")
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "serving_check.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
