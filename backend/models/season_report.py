"""Adds a storm-season breakdown to the forecaster evidence (E1).

Florida's thunderstorm season is June to September. This scores the saved forecaster on
the same held-out test year as E1, split into the storm season and the rest of the year,
against the same three baselines. It fits nothing and tunes nothing.

Run from backend/ after models.train_forecaster (which also calls `add_seasons` itself):
    python -m models.season_report
Updates eval/results/e1.json in place (adds "by_season" and one metric row).
"""
from __future__ import annotations

import json
import sys

import numpy as np

from app.core import forecaster
from data_build import metrics
from data_build.baselines import PROCESSED, RESULTS, TEST_YEAR, load_dataset

SEASONS = {"storm_season_jun_to_sep": (6, 7, 8, 9), "rest_of_year": (1, 2, 3, 4, 5, 10, 11, 12)}
METRIC_NAME = "Forecaster vs the official airport forecast, storm season only (June to September)"


def _skill(p, y, ref) -> float | None:
    s = metrics.skill(metrics.brier(p, y), metrics.brier(ref, y))
    return None if s is None else round(s, 4)


def season_tables(ds: dict, base, predictions: dict[int, np.ndarray]) -> dict:
    """predictions: horizon -> calibrated P(flyable) for every dataset row (NaN where unused)."""
    out: dict[str, dict] = {}
    test = ds["year"] == TEST_YEAR
    for name, months in SEASONS.items():
        in_season = test & np.isin(ds["month"], months)
        out[name] = {}
        for j, h in enumerate(sorted(predictions)):
            y = ds["Y"][:, j].astype(int)
            m = in_season & (y >= 0)
            mt = m & ~np.isnan(base["taf"][:, j])
            p = predictions[h]
            out[name][str(h)] = {
                "hours": int(m.sum()), "flyable_rate": round(float(y[m].mean()), 4),
                "brier": round(metrics.brier(p[m], y[m]), 5),
                "skill_vs_persistence": _skill(p[m], y[m], base["persistence"][m]),
                "skill_vs_climatology": _skill(p[m], y[m], base["climatology"][m, j]),
                "skill_vs_official_forecast": _skill(p[mt], y[mt], base["taf"][mt, j]),
            }
    return out


def add_seasons(evidence: dict, ds: dict, base, predictions: dict[int, np.ndarray]) -> dict:
    evidence["by_season"] = season_tables(ds, base, predictions)
    storm = evidence["by_season"]["storm_season_jun_to_sep"]["1"]
    row = {"id": "E1", "name": METRIC_NAME, "value": storm["skill_vs_official_forecast"], "baseline": 0.0,
           "note": f"Brier skill score, 1 hour ahead, June to September {TEST_YEAR} only ({storm['hours']:,} "
                   f"station-hours, flyable {storm['flyable_rate']:.0%} of the time). Against \"no change\" the "
                   f"skill is {storm['skill_vs_persistence']}, against typical weather {storm['skill_vs_climatology']}."}
    evidence["metrics"] = [m for m in evidence.get("metrics", []) if m["name"] != METRIC_NAME] + [row]
    return evidence


def main() -> int:
    models = forecaster._load()
    path = RESULTS / "e1.json"
    if models is None or not path.exists():
        raise SystemExit("Train first: python -m models.train_forecaster")
    ds = load_dataset()
    base = np.load(PROCESSED / "baseline_preds.npz")
    test = ds["year"] == TEST_YEAR
    predictions = {}
    for h, booster in models.boosters.items():
        cal = models.meta["calibration"][str(h)]
        p = np.full(len(ds["t"]), np.nan)
        raw = booster.predict(ds["X"][test].astype(np.float64))
        p[test] = np.clip(np.interp(raw, cal["x"], cal["y"]), models.meta["p_min"], models.meta["p_max"])
        predictions[h] = p
    evidence = add_seasons(json.loads(path.read_text(encoding="utf-8")), ds, base, predictions)
    path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"{'season':26} {'ahead':>5} {'hours':>8} {'flyable':>8} {'vs no change':>13} {'vs typical':>11} {'vs official':>12}")
    for name, table in evidence["by_season"].items():
        for h, r in table.items():
            print(f"{name:26} {'+' + h + ' h':>5} {r['hours']:>8,} {r['flyable_rate']:>8.1%} "
                  f"{r['skill_vs_persistence']:>+13.3f} {r['skill_vs_climatology']:>+11.3f} "
                  f"{r['skill_vs_official_forecast']:>+12.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
