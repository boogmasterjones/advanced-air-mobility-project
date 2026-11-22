"""The archive of past airport weather that the Time Machine replays from.

data/replay/hourly_<year>.csv.gz holds one summary row per station and hour for the
held-out test year (written by data_build/build_dataset.py from Iowa Environmental
Mesonet downloads). The forecaster never trained on that year, so a replay is an honest
test: the app sees only hours up to the replay time, and later hours are used only to
check what really happened.
"""
from __future__ import annotations

import csv
import gzip
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from . import forecaster
from .case import StationWeather, from_hour_record
from .features import HISTORY_HOURS, HourRecord, top_of_hour
from .geo import DATA_DIR, station_neighbors

REPLAY_DIR = DATA_DIR / "replay"
SOURCE = "Iowa Environmental Mesonet archive of airport weather reports"
HOUR = timedelta(hours=1)


def _float(text: str) -> float:
    return float(text) if text != "" else float("nan")


def _record(row: dict) -> HourRecord:
    return HourRecord(
        vis_min=float(row["vis_min"]), ceil_min=float(row["ceil_min"]), wind_max=float(row["wind_max"]),
        gust_max=float(row["gust_max"]), ts=row["ts"] == "1", flyable=row["flyable"] == "1",
        temp_c=_float(row["temp_c"]), dewpoint_c=_float(row["dewpoint_c"]),
        altimeter_hpa=_float(row["altimeter_hpa"]), precip_in=float(row["precip_in"] or 0),
        wind_dir=_float(row["wind_dir"]), n_reports=int(row["n_reports"]))


@lru_cache
def archive() -> dict[str, dict[datetime, HourRecord]]:
    """station -> {hour end (UTC) -> record}. Empty when no replay file is present."""
    out: dict[str, dict[datetime, HourRecord]] = {}
    for path in sorted(REPLAY_DIR.glob("hourly_*.csv.gz")):
        with gzip.open(path, "rt", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                s = row["hour_end_utc"]  # "2024-07-15T19:00Z"; sliced by hand because this runs 180,000 times
                when = datetime(int(s[0:4]), int(s[5:7]), int(s[8:10]), int(s[11:13]), int(s[14:16]),
                                tzinfo=timezone.utc)
                out.setdefault(row["station"], {})[when] = _record(row)
    return out


def available_range() -> tuple[datetime, datetime] | None:
    times = [t for recs in archive().values() for t in (min(recs), max(recs))] if archive() else []
    return (min(times), max(times)) if times else None


class ArchiveWeather:
    """WeatherSource for replays: only hours that had ended by `now` are visible."""

    def station(self, station: dict, now: datetime) -> StationWeather:
        t = top_of_hour(now)
        recs = archive().get(station["icao"], {})
        history = [recs.get(t - k * HOUR) for k in range(HISTORY_HOURS)]
        if history[0] is None:
            return StationWeather(source=SOURCE)
        neighbors = [(miles, [archive().get(code, {}).get(t - k * HOUR) for k in range(3)])
                     for code, miles in station_neighbors(station["icao"])]
        fc = forecaster.from_history(history, station["lat"], station["lon"], t, neighbors)
        return from_hour_record(history[0], t, fc, SOURCE)


def actual_flyable(icao: str, start: datetime, end: datetime) -> bool | None:
    """What really happened at one airport over [start, end]: True when every hour the
    window touches was flyable, False when any was not, None when an hour is missing."""
    recs = archive().get(icao, {})
    t, hours = top_of_hour(start) + HOUR, []   # first bucket that ends after `start`
    while t - HOUR < end:
        hours.append(recs.get(t))
        t += HOUR
    if any(h is not None and not h.flyable for h in hours):
        return False
    return None if any(h is None for h in hours) else True
