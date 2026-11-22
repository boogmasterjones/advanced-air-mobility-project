"""The flyable-window forecaster at run time.

Loads the models that models/train_forecaster.py saved and answers one question:
"What is the chance that an airport stays flyable for the 60 minutes starting h hours
after the newest weather report?" for h = 0, 1, 2, 3.

Safe defaults:
  * No fresh report (older than the staleness limit) means no forecast: the caller
    shows UNKNOWN and suggests ground.
  * If the model files or the LightGBM library are missing, `rule_forecast` gives a
    clearly labeled fallback ("rule-v0") so the app still runs.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np

from .features import FEATURE_NAMES, HORIZONS, HourRecord, Neighbor, build_features, hour_buckets
from .weather import THRESHOLDS, Observation

MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "forecaster_v1"
RULE_MODEL = "rule-v0"


@dataclass
class Forecast:
    issued_at: datetime          # time of the newest report the forecast is built on
    p_flyable: dict[int, float]  # horizon (hours after issued_at) -> probability
    model: str

    def window(self, start: datetime, end: datetime) -> float:
        """Chance the airport is flyable for the whole of [start, end].

        Takes the lowest hourly chance the window touches. Hours are strongly linked, so
        the lowest one is a fair, slightly optimistic summary (labeled as an assumption).
        Times beyond the last horizon use the last horizon.
        """
        last = max(self.p_flyable)
        first_h = max(0, min(last, int((start - self.issued_at).total_seconds() // 3600)))
        last_h = max(first_h, min(last, int((end - self.issued_at).total_seconds() // 3600)))
        return min(self.p_flyable[h] for h in range(first_h, last_h + 1))


class _Models:
    def __init__(self, meta: dict, boosters: dict) -> None:
        self.meta, self.boosters = meta, boosters

    def predict(self, features: list[float]) -> dict[int, float]:
        row = np.asarray([features], dtype=np.float64)
        out = {}
        for h, booster in self.boosters.items():
            cal = self.meta["calibration"][str(h)]
            p = float(np.interp(booster.predict(row)[0], cal["x"], cal["y"]))
            out[h] = min(self.meta["p_max"], max(self.meta["p_min"], p))
        return out


@lru_cache
def _load() -> _Models | None:
    try:
        import lightgbm as lgb

        meta = json.loads((MODEL_DIR / "meta.json").read_text(encoding="utf-8"))
        if meta["feature_names"] != FEATURE_NAMES or meta["thresholds"] != THRESHOLDS:
            return None  # the model was trained for different inputs or thresholds: refuse it
        boosters = {int(h): lgb.Booster(model_file=str(MODEL_DIR / f"h{h}.txt")) for h in meta["horizons"]}
        return _Models(meta, boosters)
    except Exception:  # missing files, missing library, corrupt model: fall back, never crash
        return None


def model_name() -> str:
    models = _load()
    return models.meta["model"] if models else RULE_MODEL


def rule_forecast(current: HourRecord) -> dict[int, float]:
    """Fallback without a model: assume the next hours look like the last hour."""
    return {h: (0.9 if current.flyable else 0.0) for h in HORIZONS}


def from_history(history: list[HourRecord | None], lat: float, lon: float, t: datetime,
                 neighbors: list[Neighbor] | None = None) -> Forecast | None:
    """Forecast from hourly records (newest first) for forecast time t.
    neighbors: (miles, history) of the nearest other airports; missing ones are fine."""
    features = build_features(history, lat, lon, t, neighbors)
    if features is None:
        return None
    models = _load()
    if models is None:
        return Forecast(t, rule_forecast(history[0]), RULE_MODEL)
    return Forecast(t, models.predict(features), models.meta["model"])


def from_reports(reports: list[Observation], lat: float, lon: float, now: datetime,
                 nearby: list[tuple[float, list[Observation]]] | None = None) -> Forecast | None:
    """Forecast from raw reports. Anchored at the newest usable report, which must be
    fresher than the staleness limit; otherwise None (UNKNOWN).
    nearby: (miles, reports) for the nearest other airports."""
    usable = [r for r in reports if r.visibility_mi is not None and r.observed_at <= now]
    if not usable:
        return None
    newest = max(usable, key=lambda r: r.observed_at)
    if now - newest.observed_at > timedelta(minutes=THRESHOLDS["max_obs_age_min"]):
        return None
    t = newest.observed_at
    # Airports report a few minutes apart; allow the neighbors' reports from the same round.
    t_nb = min(now, t + timedelta(minutes=15))
    neighbors = [(miles, hour_buckets(theirs, t_nb, 3)) for miles, theirs in nearby or []]
    return from_history(hour_buckets(usable, t), lat, lon, t, neighbors)
