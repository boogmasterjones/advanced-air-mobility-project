"""Reads the official airport forecast (TAF) archive and judges it by our thresholds.

A TAF is a set of groups: the main forecast changes at stated times ("FM" groups), and
extra groups say "temporarily" (TEMPO) or "30% chance" (PROB30) for a time window. For a
target hour we put the forecast in one of five categories, from worst to best:

  prevailing_bad   the main forecast itself breaks a threshold (or says thunderstorm)
  tempo_bad        a TEMPO group covering the hour breaks a threshold
  prob_bad         a PROB30/40 group covering the hour breaks a threshold
  vicinity_ts      only "thunderstorms in the vicinity" (VCTS) is mentioned
  clean            nothing in the forecast breaks a threshold

The baseline then says "flyable with probability p", where p is how often hours in that
category really were flyable in the training years. That is the fairest reading of a TAF
we could build: it is the official forecast, calibrated on the same history as our model.
"""
from __future__ import annotations

import ast
import bisect
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.weather import THRESHOLDS

CATEGORIES = ["prevailing_bad", "tempo_bad", "prob_bad", "vicinity_ts", "clean"]
MAX_TAF_AGE = timedelta(hours=30)  # a TAF covers 24 to 30 hours


@dataclass(slots=True)
class Group:
    kind: str                 # "main" | "tempo" | "prob"
    start: datetime
    end: datetime | None      # only for tempo and prob
    bad: bool
    vicinity_ts: bool


@dataclass(slots=True)
class Taf:
    issued: datetime
    groups: list[Group]


def _time(text: str) -> datetime | None:
    if not text:
        return None
    return datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)


def _num(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _list(text: str) -> list:
    try:
        value = ast.literal_eval(text) if text else []
        return list(value) if isinstance(value, (list, tuple)) else []
    except (ValueError, SyntaxError):
        return []


def judge(row: dict) -> tuple[bool, bool]:
    """(breaks a threshold, mentions thunderstorms only in the vicinity) for one group."""
    wx = [str(w) for w in _list(row.get("presentwx", ""))]
    ts_here = any("TS" in w and not w.startswith("VC") for w in wx)
    ts_near = any(w.startswith("VC") and "TS" in w for w in wx)
    vis = _num(row.get("visibility"))
    covers, bases = _list(row.get("skyc", "")), _list(row.get("skyl", ""))
    ceiling = min((b for c, b in zip(covers, bases)
                   if str(c).strip() in ("BKN", "OVC", "VV") and b is not None), default=None)
    wind = max((w for w in (_num(row.get("sknt")), _num(row.get("gust"))) if w is not None), default=None)
    bad = (ts_here
           or (vis is not None and vis < THRESHOLDS["min_visibility_mi"])
           or (ceiling is not None and ceiling < THRESHOLDS["min_ceiling_ft"])
           or (wind is not None and wind > THRESHOLDS["max_gust_kt"]))
    return bad, ts_near


def load(path: Path) -> list[Taf]:
    """All forecasts in one archive file, oldest first."""
    by_product: dict[str, Taf] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            issued, start = _time(row.get("valid", "")), _time(row.get("fx_valid", ""))
            if issued is None or start is None:
                continue
            ftype = row.get("ftype", "")
            if ftype in ("Observation", "Forecast"):
                kind = "main"
            elif ftype == "Temporary":
                kind = "tempo"
            elif ftype.startswith("Probability"):
                kind = "prob"
            else:
                continue
            bad, near = judge(row)
            taf = by_product.setdefault(row.get("product_id") or row["valid"], Taf(issued, []))
            taf.groups.append(Group(kind, start, _time(row.get("fx_valid_end", "")), bad, near))
    tafs = sorted(by_product.values(), key=lambda t: t.issued)
    for taf in tafs:
        taf.groups.sort(key=lambda g: g.start)
    return tafs


def latest_before(tafs: list[Taf], issued_times: list[datetime], t: datetime) -> Taf | None:
    """Newest forecast issued at or before t, or None if it is too old to cover t."""
    i = bisect.bisect_right(issued_times, t) - 1
    if i < 0 or t - tafs[i].issued > MAX_TAF_AGE:
        return None
    return tafs[i]


def category(taf: Taf, start: datetime, end: datetime) -> str:
    """Forecast category for the window [start, end)."""
    mains = [g for g in taf.groups if g.kind == "main"]
    active = [g for g in mains if start <= g.start < end]            # changes inside the window
    before = [g for g in mains if g.start <= start]
    if before:
        active.append(before[-1])                                     # in force when it opens
    extras = [g for g in taf.groups if g.kind != "main" and g.start < end
              and (g.end is None or g.end > start)]
    if any(g.bad for g in active):
        return "prevailing_bad"
    if any(g.bad for g in extras if g.kind == "tempo"):
        return "tempo_bad"
    if any(g.bad for g in extras if g.kind == "prob"):
        return "prob_bad"
    if any(g.vicinity_ts for g in active + extras):
        return "vicinity_ts"
    return "clean"
