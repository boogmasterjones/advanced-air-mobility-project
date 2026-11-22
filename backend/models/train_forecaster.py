"""Task A3: train and score the flyable-window forecaster.

Run from backend/ after data_build.build_dataset and data_build.baselines:
    python -m models.train_forecaster --skip-test   # while developing: never looks at 2024
    python -m models.train_forecaster               # final: scores once on the 2024 season

Method, in plain words:
  * One gradient-boosted tree model (LightGBM) per horizon: +0, +1, +2, +3 hours.
  * Inputs are only what an airport weather report gives at forecast time (see
    app/core/features.py). No future data, no forecast-model data.
  * Training years 2019-2023. Each year is held out in turn (train on the other four),
    which gives honest predictions for every training hour. Those are used to pick the
    number of trees and to calibrate the output, so a "70%" really means about 70%.
  * 2024 is the test season. It is never used to fit, tune or calibrate anything.

Writes backend/models/forecaster_v1/ (the models and calibration tables the app loads)
and eval/results/e1.json (the E1 evidence).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
from sklearn.isotonic import IsotonicRegression

from app.core.features import FEATURE_NAMES, HORIZONS
from app.core.weather import THRESHOLDS
from data_build import metrics
from data_build.baselines import PROCESSED, RESULTS, TEST_YEAR, load_dataset

from .season_report import add_seasons

MODEL_DIR = Path(__file__).resolve().parent / "forecaster_v1"
MODEL_NAME = "lightgbm-v1"
P_MIN, P_MAX = 0.01, 0.99  # never claim certainty
PARAMS = {
    "objective": "binary", "learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 200,
    "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0,
    "verbose": -1, "seed": 7, "num_threads": 0, "deterministic": True, "force_row_wise": True,
}
MAX_ROUNDS = 1500
WARN_BELOW = (0.5, 0.8)


def fit(X, y, rounds, valid=None):
    train = lgb.Dataset(X, y, feature_name=FEATURE_NAMES, free_raw_data=False)
    if valid is None:
        return lgb.train(PARAMS, train, num_boost_round=rounds)
    return lgb.train(PARAMS, train, num_boost_round=rounds,
                     valid_sets=[lgb.Dataset(valid[0], valid[1], reference=train)],
                     callbacks=[lgb.early_stopping(50, verbose=False)])


def out_of_year(X, y, years, rows):
    """Predict every training hour with a model that never saw that hour's year."""
    oof = np.full(len(y), np.nan)
    best = []
    for held in sorted(np.unique(years[rows])):
        tr, va = rows & (years != held), rows & (years == held)
        model = fit(X[tr], y[tr], MAX_ROUNDS, valid=(X[va], y[va]))
        oof[va] = model.predict(X[va], num_iteration=model.best_iteration)
        best.append(model.best_iteration)
    return oof, int(np.median(best))


def calibrate(raw: np.ndarray, y: np.ndarray) -> tuple[list[float], list[float]]:
    iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(raw, y)
    return [float(v) for v in iso.X_thresholds_], [float(v) for v in iso.y_thresholds_]


def apply_calibration(raw: np.ndarray, xs: list[float], ys: list[float]) -> np.ndarray:
    return np.clip(np.interp(raw, xs, ys), P_MIN, P_MAX)


def compare(p, y, refs: dict[str, np.ndarray]) -> dict:
    """Scores for our forecast plus skill against each reference forecast."""
    ours = metrics.brier(p, y)
    out = {"n": int(len(y)), "brier": round(ours, 5), "auc": round(metrics.auc(p, y), 4),
           "calibration_error": round(metrics.calibration_error(p, y), 4), "vs": {}}
    for name, ref in refs.items():
        ref_score = metrics.brier(ref, y)
        s = metrics.skill(ours, ref_score)
        out["vs"][name] = {"brier": round(ref_score, 5), "skill": None if s is None else round(s, 4)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--skip-test", action="store_true",
                    help="develop without looking at the test season; writes no files")
    args = ap.parse_args()

    ds = load_dataset()
    base_path = PROCESSED / "baseline_preds.npz"
    if not base_path.exists():
        raise SystemExit("Run first: python -m data_build.baselines")
    base = np.load(base_path)
    X, years = ds["X"], ds["year"]
    # label_year: no training row may have a label that looks into the test year.
    train_rows, test_rows = ds["label_year"] < TEST_YEAR, years == TEST_YEAR

    evidence = {
        "id": "E1", "model": MODEL_NAME,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "what_is_predicted": "chance that every weather report in the 60 minutes starting "
                             "h hours from now meets the flyable thresholds",
        "thresholds": THRESHOLDS,
        "train_years": sorted(int(v) for v in np.unique(years[train_rows])),
        "test_year": TEST_YEAR, "stations": ds["stations"],
        "how_to_read": "Brier score: lower is better. Skill: share of the reference "
                       "forecast's error that the model removes (above 0 beats it).",
        "horizons": {},
    }
    meta = {"model": MODEL_NAME, "feature_names": FEATURE_NAMES, "horizons": list(HORIZONS),
            "thresholds": THRESHOLDS, "train_years": evidence["train_years"],
            "trained_at": evidence["generated_at"], "lightgbm": lgb.__version__,
            "p_min": P_MIN, "p_max": P_MAX, "rounds": {}, "calibration": {}}
    models = {}
    season_preds: dict[int, np.ndarray] = {}

    for j, h in enumerate(HORIZONS):
        y = ds["Y"][:, j].astype(int)
        known = y >= 0
        tr = train_rows & known
        oof, rounds = out_of_year(X, y, years, tr)
        xs, ys = calibrate(oof[tr], y[tr])
        dev = compare(apply_calibration(oof[tr], xs, ys), y[tr],
                      {"persistence": base["persistence"][tr], "climatology": base["climatology"][tr, j]})
        print(f"+{h} h  trees {rounds:4d}  held-out-year Brier {dev['brier']:.4f}  "
              f"skill vs persistence {dev['vs']['persistence']['skill']:+.3f}  "
              f"vs climatology {dev['vs']['climatology']['skill']:+.3f}", flush=True)
        if args.skip_test:
            continue

        model = fit(X[tr], y[tr], rounds)
        models[h] = model
        meta["rounds"][str(h)] = rounds
        meta["calibration"][str(h)] = {"x": xs, "y": ys}

        te = test_rows & known
        p = apply_calibration(model.predict(X[te]), xs, ys)
        season_preds[h] = np.full(len(y), np.nan)
        season_preds[h][te] = p
        has_taf = ~np.isnan(base["taf"][te, j])
        block = {
            "flyable_rate": round(float(y[te].mean()), 4),
            "development_check_on_training_years": dev,
            "test": compare(p, y[te], {"persistence": base["persistence"][te],
                                       "climatology": base["climatology"][te, j]}),
            "test_stations_with_taf": compare(
                p[has_taf], y[te][has_taf],
                {"taf": base["taf"][te, j][has_taf], "persistence": base["persistence"][te][has_taf],
                 "climatology": base["climatology"][te, j][has_taf]}),
            "reliability": metrics.reliability(p, y[te]),
            "warnings": [metrics.warning_scores(p, y[te], w) for w in WARN_BELOW],
            "warnings_persistence": metrics.warning_scores(base["persistence"][te], y[te], 0.5),
            "by_station": {},
        }
        st = ds["station"][te]
        for s_idx, icao in enumerate(ds["stations"]):
            m = st == s_idx
            if m.sum() >= 100:
                ours, ref = metrics.brier(p[m], y[te][m]), metrics.brier(base["persistence"][te][m], y[te][m])
                block["by_station"][icao] = {"n": int(m.sum()), "brier": round(ours, 5),
                                             "skill_vs_persistence": round(metrics.skill(ours, ref) or 0, 4)}
        gain = model.feature_importance("gain")
        top = np.argsort(gain)[::-1][:10]
        block["top_features"] = [{"name": FEATURE_NAMES[i], "share_of_gain": round(float(gain[i] / gain.sum()), 4)}
                                 for i in top]
        evidence["horizons"][str(h)] = block
        t, tt = block["test"], block["test_stations_with_taf"]
        print(f"      TEST {TEST_YEAR}: Brier {t['brier']:.4f}  skill vs persistence "
              f"{t['vs']['persistence']['skill']:+.3f}  vs climatology {t['vs']['climatology']['skill']:+.3f}  "
              f"vs official forecast {tt['vs']['taf']['skill']:+.3f}", flush=True)

    if args.skip_test:
        print("Development run only: the test season was not touched and nothing was written.")
        return 0

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for h, model in models.items():
        model.save_model(str(MODEL_DIR / f"h{h}.txt"))
    (MODEL_DIR / "meta.json").write_text(json.dumps(meta) + "\n", encoding="utf-8")
    one = evidence["horizons"]["1"]
    evidence["headline"] = {
        "horizon_h": 1,
        "skill_vs_persistence": one["test"]["vs"]["persistence"]["skill"],
        "skill_vs_climatology": one["test"]["vs"]["climatology"]["skill"],
        "skill_vs_official_forecast": one["test_stations_with_taf"]["vs"]["taf"]["skill"],
    }
    n_hours = one["test"]["n"]
    note = (f"Brier skill score, 1 hour ahead, {TEST_YEAR} test season ({n_hours:,} station-hours, "
            f"{len(ds['stations'])} Florida airports). Above 0 beats the baseline; 1 would be perfect.")
    evidence["metrics"] = [
        {"id": "E1", "name": "Forecaster vs \"no change\" (persistence)",
         "value": evidence["headline"]["skill_vs_persistence"], "baseline": 0.0, "note": note},
        {"id": "E1", "name": "Forecaster vs typical weather for that hour (climatology)",
         "value": evidence["headline"]["skill_vs_climatology"], "baseline": 0.0, "note": note},
        {"id": "E1", "name": "Forecaster vs the official airport forecast (TAF)",
         "value": evidence["headline"]["skill_vs_official_forecast"], "baseline": 0.0,
         "note": note + " Airports with an official forecast only; the forecast was calibrated "
                        "on the same training years."},
    ]
    add_seasons(evidence, ds, base, season_preds)  # storm season against the rest of the year
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "e1.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"Saved models to {MODEL_DIR} and evidence to {RESULTS / 'e1.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
