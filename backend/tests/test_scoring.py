"""The scoring helpers behind the evidence numbers, checked on small hand-made data."""
import json

import numpy as np

from data_build import metrics


def test_brier_and_skill_by_hand():
    y = np.array([1, 1, 0, 1])
    assert metrics.brier(np.array([1, 1, 0, 1]), y) == 0                       # perfect
    assert abs(metrics.brier(np.array([0.5] * 4), y) - 0.25) < 1e-12           # coin flip
    assert abs(metrics.brier(np.array([0.8, 0.8, 0.2, 0.8]), y) - 0.04) < 1e-12
    assert abs(metrics.skill(0.04, 0.25) - 0.84) < 1e-12                       # removes 84% of the error
    assert metrics.skill(0.30, 0.25) < 0                                       # worse than the reference
    assert metrics.skill(0.1, 0.0) is None


def test_auc_and_reliability_by_hand():
    y = np.array([0, 0, 1, 1])
    assert metrics.auc(np.array([0.1, 0.2, 0.8, 0.9]), y) == 1.0
    assert metrics.auc(np.array([0.9, 0.8, 0.2, 0.1]), y) == 0.0
    assert metrics.auc(np.array([0.5, 0.5, 0.5, 0.5]), y) == 0.5               # ties count half
    assert metrics.auc(np.array([0.5, 0.5]), np.array([1, 1])) is None
    rows = metrics.reliability(np.array([0.05, 0.05, 0.95, 0.95]), np.array([0, 0, 1, 0]))
    assert [r["n"] for r in rows] == [2, 2] and rows[0]["observed_flyable"] == 0 and rows[1]["observed_flyable"] == 0.5
    assert abs(metrics.calibration_error(np.array([0.05, 0.05, 0.95, 0.95]), np.array([0, 0, 1, 0])) - 0.25) < 1e-9


def test_warning_scores_by_hand():
    p, y = np.array([0.2, 0.3, 0.9, 0.9, 0.4]), np.array([0, 1, 1, 1, 0])
    s = metrics.warning_scores(p, y, 0.5)   # three warnings; two of the two unflyable hours caught; one false alarm
    assert s["warnings"] == 3 and s["caught"] == 1.0 and s["missed"] == 0.0 and abs(s["false_alarms"] - 1 / 3) < 1e-3


def test_season_breakdown_on_made_up_data():
    from models.season_report import METRIC_NAME, add_seasons
    rng = np.random.default_rng(0)
    n = 4000
    month = rng.integers(1, 13, n)
    year = np.where(np.arange(n) < n // 2, 2023, 2024)
    truth = rng.random((n, 4)) < 0.85
    Y = truth.astype(np.int8)
    Y[::50, 2] = -1                                                # some hours have no label
    ds = {"year": year, "month": month, "Y": Y}
    taf = np.full((n, 4), 0.85)
    taf[::7] = np.nan                                              # some airports have no official forecast
    base = {"persistence": rng.integers(0, 2, n).astype(float), "climatology": np.full((n, 4), 0.85), "taf": taf}
    predictions = {h: np.where(year == 2024, np.clip(truth[:, h] * 0.8 + 0.1, 0.01, 0.99), np.nan) for h in range(4)}
    evidence = add_seasons({"metrics": [{"id": "E1", "name": "kept", "value": 1}]}, ds, base, predictions)
    for season in ("storm_season_jun_to_sep", "rest_of_year"):
        for h in "0123":
            row = evidence["by_season"][season][h]
            assert row["hours"] > 100 and row["skill_vs_climatology"] > 0.5 and row["skill_vs_official_forecast"] > 0.5
    storm_hours = evidence["by_season"]["storm_season_jun_to_sep"]["1"]["hours"]
    assert storm_hours == int(((year == 2024) & np.isin(month, (6, 7, 8, 9))).sum())
    assert [m["name"] for m in evidence["metrics"]] == ["kept", METRIC_NAME]
    again = add_seasons(evidence, ds, base, predictions)           # running twice does not duplicate the row
    assert len(again["metrics"]) == 2
    json.dumps(evidence, allow_nan=False)                          # valid JSON for a browser
