"""Scores for probability forecasts. Plain numpy so every number can be checked by hand.

`p` is always the predicted chance that the hour is FLYABLE, and `y` is 1 when it was.
"""
from __future__ import annotations

import numpy as np


def brier(p: np.ndarray, y: np.ndarray) -> float:
    """Mean squared error of the probabilities. 0 is perfect; lower is better."""
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))


def skill(score: float, reference: float) -> float | None:
    """Brier skill score: 1 is perfect, 0 ties the reference, below 0 is worse than it."""
    return None if reference == 0 else float(1 - score / reference)


def reliability(p: np.ndarray, y: np.ndarray, bins: int = 10) -> list[dict]:
    """For each band of predicted chance: how often the hour really was flyable."""
    p, y = np.asarray(p, float), np.asarray(y, float)
    idx = np.minimum((p * bins).astype(int), bins - 1)
    out = []
    for b in range(bins):
        m = idx == b
        if m.any():
            out.append({"band": f"{b / bins:.1f}-{(b + 1) / bins:.1f}", "n": int(m.sum()),
                        "mean_predicted": round(float(p[m].mean()), 4),
                        "observed_flyable": round(float(y[m].mean()), 4)})
    return out


def calibration_error(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    """Average gap between predicted and observed frequency, weighted by band size."""
    rows = reliability(p, y, bins)
    n = sum(r["n"] for r in rows)
    return float(sum(r["n"] * abs(r["mean_predicted"] - r["observed_flyable"]) for r in rows) / n)


def warning_scores(p: np.ndarray, y: np.ndarray, warn_below: float) -> dict:
    """Treat "p < warn_below" as a warning that the hour will NOT be flyable.

    caught          share of truly unflyable hours that were warned (hit rate)
    false_alarms    share of warnings where the hour turned out flyable
    missed          share of truly unflyable hours with no warning
    """
    p, y = np.asarray(p, float), np.asarray(y, int)
    warned, unflyable = p < warn_below, y == 0
    hits = int((warned & unflyable).sum())
    return {
        "warn_below": warn_below,
        "warnings": int(warned.sum()),
        "unflyable_hours": int(unflyable.sum()),
        "caught": round(hits / unflyable.sum(), 4) if unflyable.any() else None,
        "missed": round(1 - hits / unflyable.sum(), 4) if unflyable.any() else None,
        "false_alarms": round(1 - hits / warned.sum(), 4) if warned.any() else None,
    }


def auc(p: np.ndarray, y: np.ndarray) -> float | None:
    """Chance a random flyable hour got a higher score than a random unflyable one."""
    p, y = np.asarray(p, float), np.asarray(y, int)
    n1, n0 = int(y.sum()), int((1 - y).sum())
    if n1 == 0 or n0 == 0:
        return None
    order = np.argsort(p, kind="mergesort")
    ranks = np.empty(len(p), float)
    sorted_p = p[order]
    # average ranks for ties
    i = 0
    while i < len(p):
        j = i
        while j + 1 < len(p) and sorted_p[j + 1] == sorted_p[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))
