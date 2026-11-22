"""Task A2 (part 2): the three baselines the forecaster has to beat.

Run from backend/ after build_dataset.py:
    python -m data_build.baselines

  persistence   "the next hours will be like the hour that just ended"
  climatology   how often that station, month and hour of day was flyable in 2019-2023
  taf           the official airport forecast, read by our thresholds and calibrated on
                2019-2023 (see data_build/taf.py)

Writes eval/results/e1_baselines.json (scores on the 2024 test season) and
data/processed/baseline_preds.npz (per-row predictions, so the forecaster is compared on
exactly the same hours).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from app.core.features import FEATURE_NAMES, HORIZONS
from app.core.geo import DATA_DIR
from app.core.weather import THRESHOLDS

from . import metrics, taf

PROCESSED = DATA_DIR / "processed"
RESULTS = DATA_DIR.parent / "eval" / "results"
TEST_YEAR = 2024


def load_dataset() -> dict:
    path = PROCESSED / "dataset.npz"
    if not path.exists():
        raise SystemExit("data/processed/dataset.npz is missing. Run: python -m data_build.build_dataset")
    d = np.load(path, allow_pickle=False)
    times = d["t"].astype("datetime64[s]")
    return {"X": d["X"], "Y": d["Y"], "station": d["station"], "t": d["t"],
            "stations": [str(s) for s in d["stations"]],
            "year": times.astype("datetime64[Y]").astype(int) + 1970,
            "month": times.astype("datetime64[M]").astype(int) % 12 + 1,
            "hour": (d["t"] // 3600) % 24}


def persistence(ds: dict) -> np.ndarray:
    return ds["X"][:, FEATURE_NAMES.index("cur_flyable")].astype(float)


def climatology(ds: dict, train: np.ndarray, prior: float = 5.0) -> np.ndarray:
    """P(flyable) by station, month and hour of day, learned on the training rows only.
    Cells are pulled slightly toward the station's overall rate so thin cells are stable."""
    n = len(ds["t"])
    out = np.full((n, len(HORIZONS)), np.nan)
    for j, h in enumerate(HORIZONS):
        y = ds["Y"][:, j]
        target_hour = (ds["hour"] + h) % 24
        key = ds["station"].astype(np.int64) * 10000 + ds["month"] * 100 + target_hour
        ok = train & (y >= 0)
        station_rate = {s: y[ok & (ds["station"] == s)].mean() for s in np.unique(ds["station"][ok])}
        sums: dict[int, list[float]] = {}
        for k, v in zip(key[ok], y[ok]):
            cell = sums.setdefault(int(k), [0.0, 0.0])
            cell[0] += v; cell[1] += 1
        overall = float(y[ok].mean())
        for i in range(n):
            base = station_rate.get(ds["station"][i], overall)
            s, c = sums.get(int(key[i]), (0.0, 0.0))
            out[i, j] = (s + prior * base) / (c + prior)
    return out


def taf_categories(ds: dict) -> np.ndarray:
    """Category index (see taf.CATEGORIES) per row and horizon; -1 where no TAF applies."""
    n = len(ds["t"])
    cats = np.full((n, len(HORIZONS)), -1, dtype=np.int8)
    for s_idx, icao in enumerate(ds["stations"]):
        files = sorted((DATA_DIR / "raw" / "taf").glob(f"{icao}_*.csv"))
        tafs = [t for f in files for t in taf.load(f)]
        if not tafs:
            continue
        tafs.sort(key=lambda t: t.issued)
        issued = [t.issued for t in tafs]
        for i in np.flatnonzero(ds["station"] == s_idx):
            t0 = datetime.fromtimestamp(int(ds["t"][i]), tz=timezone.utc)
            forecast = taf.latest_before(tafs, issued, t0)
            if forecast is None:
                continue
            for j, h in enumerate(HORIZONS):
                start = t0 + timedelta(hours=h)
                cats[i, j] = taf.CATEGORIES.index(taf.category(forecast, start, start + timedelta(hours=1)))
    return cats


def taf_probabilities(ds: dict, cats: np.ndarray, train: np.ndarray) -> tuple[np.ndarray, dict]:
    out = np.full(cats.shape, np.nan)
    table: dict[str, dict[str, dict]] = {}
    for j, h in enumerate(HORIZONS):
        y = ds["Y"][:, j]
        table[str(h)] = {}
        fallback = float(y[train & (y >= 0) & (cats[:, j] >= 0)].mean())
        for c, name in enumerate(taf.CATEGORIES):
            m = train & (y >= 0) & (cats[:, j] == c)
            rate = float(y[m].mean()) if m.sum() >= 30 else fallback
            table[str(h)][name] = {"train_hours": int(m.sum()), "flyable_rate": round(rate, 4)}
            out[cats[:, j] == c, j] = rate
    return out, table


def score_block(p: np.ndarray, y: np.ndarray) -> dict:
    return {"n": int(len(y)), "brier": round(metrics.brier(p, y), 5),
            "auc": None if (a := metrics.auc(p, y)) is None else round(a, 4)}


def main() -> int:
    ds = load_dataset()
    train, test = ds["year"] < TEST_YEAR, ds["year"] == TEST_YEAR
    pers = persistence(ds)
    clim = climatology(ds, train)
    cats = taf_categories(ds)
    taf_p, taf_table = taf_probabilities(ds, cats, train)

    result = {
        "task": "A2 baselines for E1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "what_is_predicted": "chance that every weather report in the 60 minutes starting "
                             "h hours from now meets the flyable thresholds",
        "thresholds": THRESHOLDS,
        "train_years": sorted(int(v) for v in np.unique(ds["year"][train])),
        "test_year": TEST_YEAR,
        "stations": ds["stations"],
        "stations_with_taf": [s for i, s in enumerate(ds["stations"]) if (cats[ds["station"] == i] >= 0).any()],
        "taf_category_flyable_rate_in_training": taf_table,
        "horizons": {},
    }
    print(f"{'horizon':8} {'hours':>8} {'flyable':>8} {'persist.':>9} {'climat.':>9} | "
          f"{'TAF hours':>9} {'TAF':>8} {'persist.':>9} {'climat.':>9}")
    for j, h in enumerate(HORIZONS):
        y = ds["Y"][:, j]
        m = test & (y >= 0)
        mt = m & (cats[:, j] >= 0)
        block = {
            "flyable_rate": round(float(y[m].mean()), 4),
            "all_stations": {"persistence": score_block(pers[m], y[m]),
                             "climatology": score_block(clim[m, j], y[m])},
            "stations_with_taf": {"taf": score_block(taf_p[mt, j], y[mt]),
                                  "persistence": score_block(pers[mt], y[mt]),
                                  "climatology": score_block(clim[mt, j], y[mt])},
        }
        result["horizons"][str(h)] = block
        a, b = block["all_stations"], block["stations_with_taf"]
        print(f"+{h} h     {a['persistence']['n']:>8,} {block['flyable_rate']:>8.1%} "
              f"{a['persistence']['brier']:>9.4f} {a['climatology']['brier']:>9.4f} | "
              f"{b['taf']['n']:>9,} {b['taf']['brier']:>8.4f} {b['persistence']['brier']:>9.4f} "
              f"{b['climatology']['brier']:>9.4f}")
    print("(Brier score: lower is better)")

    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "e1_baselines.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    np.savez_compressed(PROCESSED / "baseline_preds.npz", persistence=pers, climatology=clim,
                        taf=taf_p, taf_category=cats)
    print(f"Wrote {RESULTS / 'e1_baselines.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
