"""Turns raw airport weather reports into the numbers the forecaster reads.

One code path for training and for the live app, on purpose: the training script and the
running server both call `hour_buckets` and `build_features`, so the model never sees
inputs at run time that were prepared differently from its training data.

Vocabulary:
  report      one airport weather report (routine, about hourly, or "special" when
              weather changes quickly)
  hour bucket every report in one 60-minute window, summarized as an HourRecord
  history     a list of hour buckets, newest first: index 0 is the hour ending at the
              forecast time T, index 1 the hour before that, and so on
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from .weather import Observation, report_is_flyable

HISTORY_HOURS = 7       # buckets the features look back over (T-0h ... T-6h)
HORIZONS = (0, 1, 2, 3)  # horizon h means the 60 minutes starting h hours after T
CEILING_CAP_FT = 12000.0  # "no ceiling" is stored as this value
VIS_CAP_MI = 10.0
NAN = float("nan")


@dataclass(slots=True)
class HourRecord:
    vis_min: float
    ceil_min: float            # feet; CEILING_CAP_FT when no ceiling was reported
    wind_max: float            # sustained wind, knots
    gust_max: float            # strongest of gust and sustained wind, knots
    ts: bool                   # a thunderstorm was reported at any time in the hour
    flyable: bool              # every usable report in the hour met the thresholds
    temp_c: float              # from the newest report in the hour (NaN if missing)
    dewpoint_c: float
    altimeter_hpa: float
    precip_in: float           # largest "rain so far this hour" value
    wind_dir: float            # degrees, NaN when variable or missing
    n_reports: int             # more than 1 means special reports: weather was changing


def _or_nan(v: float | None) -> float:
    return NAN if v is None else float(v)


def summarize_hour(reports: list[Observation]) -> HourRecord | None:
    """Summarize the reports that fall inside one hour. None means no usable report."""
    usable = [r for r in reports if r.visibility_mi is not None]
    if not usable:
        return None
    newest = max(usable, key=lambda r: r.observed_at)
    winds = [r.wind_kt for r in usable if r.wind_kt is not None]
    gusts = winds + [r.gust_kt for r in usable if r.gust_kt is not None]
    ceilings = [r.ceiling_ft for r in usable if r.ceiling_ft is not None]
    precip = [r.precip_in for r in usable if r.precip_in is not None]
    return HourRecord(
        vis_min=min(min(r.visibility_mi for r in usable), VIS_CAP_MI),
        ceil_min=min(min(ceilings), CEILING_CAP_FT) if ceilings else CEILING_CAP_FT,
        wind_max=max(winds, default=0.0),
        gust_max=max(gusts, default=0.0),
        ts=any(r.thunderstorm for r in usable),
        flyable=all(report_is_flyable(r) for r in usable),
        temp_c=_or_nan(newest.temp_c),
        dewpoint_c=_or_nan(newest.dewpoint_c),
        altimeter_hpa=_or_nan(newest.altimeter_hpa),
        precip_in=max(precip, default=0.0),
        wind_dir=_or_nan(newest.wind_dir),
        n_reports=len(usable),
    )


def hour_buckets(reports: list[Observation], t: datetime, n: int = HISTORY_HOURS) -> list[HourRecord | None]:
    """Group reports into n hourly buckets ending at t, newest first.

    Bucket k holds reports with  t-(k+1)h < time <= t-k h.  Reports after t are ignored,
    which is what keeps the Time Machine honest: it can only use what was known at t.
    """
    groups: list[list[Observation]] = [[] for _ in range(n)]
    for r in reports:
        age_h = (t - r.observed_at).total_seconds() / 3600
        if 0 <= age_h < n:
            groups[int(age_h)].append(r)
    return [summarize_hour(g) for g in groups]


FEATURE_NAMES = [
    # the hour that just ended
    "cur_vis", "cur_ceil", "cur_wind", "cur_gust", "cur_ts", "cur_flyable", "cur_temp",
    "cur_spread", "cur_alti", "cur_precip", "cur_wdir_sin", "cur_wdir_cos", "cur_nrep",
    # the three hours before that
    "fly_l1", "fly_l2", "fly_l3", "ts_l1", "ts_l2", "ts_l3",
    # trends (now minus k hours ago)
    "d_vis_1", "d_vis_3", "d_ceil_1", "d_ceil_3", "d_temp_1", "d_temp_3", "d_temp_6",
    "d_spread_3", "d_alti_1", "d_alti_3", "d_wind_1", "d_wind_3",
    # summaries of the whole look-back window
    "fly_frac", "ts_count", "hrs_since_ts", "hrs_since_unflyable", "gust_max_win",
    "vis_min_win", "ceil_min_win", "precip_win", "temp_max_win", "hours_known",
    # time and place
    "hour_sin", "hour_cos", "doy_sin", "doy_cos", "lat", "lon",
    # the nearest other airports (storms drift from one airport to the next)
    "nb_known", "nb_ts_now", "nb_ts_recent", "nb_unflyable_now", "nb_vis_min", "nb_gust_max",
    "nb1_dist", "nb1_ts", "nb1_flyable",
]
Neighbor =tuple[float, list["HourRecord | None"]]  # (miles away, history newest first)


def neighbor_features(neighbors: list[Neighbor]) -> list[float]:
    """Summary of the nearest airports' last hours. NaN where no neighbor has a report."""
    current = [(d, h[0]) for d, h in neighbors if h and h[0] is not None]
    recent = [r for _, h in neighbors for r in h[:3] if r is not None]
    if not current:
        return [0.0, NAN, float(sum(r.ts for r in recent)) if recent else NAN, NAN, NAN, NAN,
                neighbors[0][0] if neighbors else NAN, NAN, NAN]
    first_d, first = min(current, key=lambda x: x[0])
    return [
        float(len(current)), float(any(r.ts for _, r in current)), float(sum(r.ts for r in recent)),
        float(sum(not r.flyable for _, r in current)), min(r.vis_min for _, r in current),
        max(r.gust_max for _, r in current), first_d, float(first.ts), float(first.flyable),
    ]


def _delta(history: list[HourRecord | None], k: int, attr: str) -> float:
    if k >= len(history) or history[0] is None or history[k] is None:
        return NAN
    return getattr(history[0], attr) - getattr(history[k], attr)


def build_features(history: list[HourRecord | None], lat: float, lon: float, t: datetime,
                   neighbors: list[Neighbor] | None = None) -> list[float] | None:
    """Feature row for forecast time t (UTC). None when the current hour has no report:
    without a fresh report there is no forecast, and the app shows UNKNOWN.
    neighbors: (miles, history) for the nearest other airports, nearest first; may be empty."""
    cur = history[0]
    if cur is None:
        return None
    known = [h for h in history if h is not None]

    def lag(k: int, attr: str) -> float:
        return float(getattr(history[k], attr)) if k < len(history) and history[k] is not None else NAN

    def hours_since(attr: str, value: bool) -> float:
        for k, h in enumerate(history):
            if h is not None and getattr(h, attr) is value:
                return float(k)
        return float(len(history))  # not seen anywhere in the window

    wdir = math.radians(cur.wind_dir) if not math.isnan(cur.wind_dir) else None
    solar_hour = (t.hour + t.minute / 60 + lon / 15) % 24  # local solar time, no time zones
    hour_angle = 2 * math.pi * solar_hour / 24
    doy_angle = 2 * math.pi * t.timetuple().tm_yday / 365.25
    temps = [h.temp_c for h in known if not math.isnan(h.temp_c)]

    row = [
        cur.vis_min, cur.ceil_min, cur.wind_max, cur.gust_max, float(cur.ts), float(cur.flyable),
        cur.temp_c, cur.temp_c - cur.dewpoint_c, cur.altimeter_hpa, cur.precip_in,
        math.sin(wdir) if wdir is not None else NAN, math.cos(wdir) if wdir is not None else NAN,
        float(cur.n_reports),
        lag(1, "flyable"), lag(2, "flyable"), lag(3, "flyable"),
        lag(1, "ts"), lag(2, "ts"), lag(3, "ts"),
        _delta(history, 1, "vis_min"), _delta(history, 3, "vis_min"),
        _delta(history, 1, "ceil_min"), _delta(history, 3, "ceil_min"),
        _delta(history, 1, "temp_c"), _delta(history, 3, "temp_c"), _delta(history, 6, "temp_c"),
        (_delta(history, 3, "temp_c") - _delta(history, 3, "dewpoint_c")),
        _delta(history, 1, "altimeter_hpa"), _delta(history, 3, "altimeter_hpa"),
        _delta(history, 1, "wind_max"), _delta(history, 3, "wind_max"),
        sum(h.flyable for h in known) / len(known),
        float(sum(h.ts for h in known)),
        hours_since("ts", True), hours_since("flyable", False),
        max(h.gust_max for h in known), min(h.vis_min for h in known),
        min(h.ceil_min for h in known), sum(h.precip_in for h in known),
        max(temps) if temps else NAN, float(len(known)),
        math.sin(hour_angle), math.cos(hour_angle), math.sin(doy_angle), math.cos(doy_angle),
        lat, lon,
    ] + neighbor_features(neighbors or [])
    assert len(row) == len(FEATURE_NAMES)
    return row


def top_of_hour(t: datetime) -> datetime:
    return t.replace(minute=0, second=0, microsecond=0)


def hours_between(start: datetime, end: datetime) -> list[datetime]:
    """Every top-of-hour time from start to end, inclusive."""
    out, t = [], top_of_hour(start)
    while t <= end:
        out.append(t)
        t += timedelta(hours=1)
    return out
