"""Task A2 (part 1): turn the raw downloads into hourly records, features and labels.

Run from backend/ after download_weather.py:
    python -m data_build.build_dataset

Writes (all under data/, see .gitignore for what is committed):
  data/processed/dataset.npz      features X, labels Y (one column per horizon), station
                                  index, forecast time; used by baselines and training
  data/replay/hourly_<year>.csv.gz  hourly records for the held-out test year. The Time
                                  Machine replays from this file, so it is committed.

Label for horizon h at forecast time T: 1 when every report in the 60 minutes starting
T + h hours met the thresholds in app/core/weather.py, else 0. Hours with no usable
report get no label (-1) and are skipped, never guessed.
"""
from __future__ import annotations

import csv
import gzip
import sys
from dataclasses import asdict, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from app.core.features import (FEATURE_NAMES, HISTORY_HOURS, HORIZONS, HourRecord,
                               build_features, summarize_hour)
from app.core.geo import DATA_DIR, station_neighbors, stations
from app.core.weather import PRESSURE_HPA, TEMP_C, VISIBILITY_MI, Observation, clean_wind, in_range

RAW = DATA_DIR / "raw"
PROCESSED = DATA_DIR / "processed"
REPLAY = DATA_DIR / "replay"
TEST_YEAR = 2024
HOUR = timedelta(hours=1)
RECORD_FIELDS = [f.name for f in fields(HourRecord)]


def _f(text: str) -> float | None:
    if text in ("M", "", None):
        return None
    if text == "T":  # trace of rain
        return 0.005
    try:
        return float(text)
    except ValueError:
        return None


def parse_iem_row(row: dict, icao: str) -> Observation | None:
    """One line of the IEM download as an Observation (same shape the live feed gives)."""
    try:
        when = datetime.strptime(row["valid"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except (KeyError, ValueError):
        return None
    ceiling = None
    for i in "1234":
        cover, base = (row.get(f"skyc{i}") or "").strip(), _f(row.get(f"skyl{i}", "M"))
        if cover in ("BKN", "OVC", "VV") and base is not None:
            ceiling = base if ceiling is None else min(ceiling, base)
    tmpf, dwpf, alti = _f(row.get("tmpf")), _f(row.get("dwpf")), _f(row.get("alti"))
    wx = row.get("wxcodes") or ""
    wind_dir, wind_kt, gust_kt = clean_wind(_f(row.get("drct")), _f(row.get("sknt")), _f(row.get("gust")))
    return Observation(
        station=icao, observed_at=when,
        visibility_mi=in_range(_f(row.get("vsby")), *VISIBILITY_MI), ceiling_ft=ceiling,
        wind_kt=wind_kt, gust_kt=gust_kt,
        thunderstorm="TS" in wx if wx != "M" else False, raw=row.get("metar", ""),
        temp_c=in_range((tmpf - 32) * 5 / 9 if tmpf is not None else None, *TEMP_C),
        dewpoint_c=in_range((dwpf - 32) * 5 / 9 if dwpf is not None else None, *TEMP_C),
        altimeter_hpa=in_range(alti * 33.8639 if alti is not None else None, *PRESSURE_HPA),
        wind_dir=wind_dir, precip_in=_f(row.get("p01i")),
    )


def hour_end(when: datetime) -> datetime:
    """The top of the hour that closes the bucket this report belongs to."""
    floor = when.replace(minute=0, second=0, microsecond=0)
    return floor if when == floor else floor + HOUR


def load_hourly(path: Path, icao: str) -> dict[datetime, HourRecord]:
    groups: dict[datetime, list[Observation]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            obs = parse_iem_row(row, icao)
            if obs is not None:
                groups.setdefault(hour_end(obs.observed_at), []).append(obs)
    out = {}
    for end, reports in groups.items():
        rec = summarize_hour(reports)
        if rec is not None:
            out[end] = rec
    return out


def rows_for(hourly: dict[datetime, HourRecord], lat: float, lon: float,
             nearby: list[tuple[float, dict[datetime, HourRecord]]]):
    """Yield (T, features, labels) for every hour that has a current record.
    nearby: (miles, hourly records) for the nearest other stations, nearest first."""
    for t in sorted(hourly):
        history = [hourly.get(t - k * HOUR) for k in range(HISTORY_HOURS)]
        neighbors = [(miles, [recs.get(t - k * HOUR) for k in range(3)]) for miles, recs in nearby]
        feats = build_features(history, lat, lon, t, neighbors)
        if feats is None:
            continue
        labels = []
        for h in HORIZONS:
            target = hourly.get(t + (h + 1) * HOUR)
            labels.append(-1 if target is None else int(target.flyable))
        yield t, feats, labels


def write_replay(year: int, per_station: dict[str, dict[datetime, HourRecord]]) -> Path:
    REPLAY.mkdir(parents=True, exist_ok=True)
    path = REPLAY / f"hourly_{year}.csv.gz"
    with gzip.open(path, "wt", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["station", "hour_end_utc"] + RECORD_FIELDS)
        for icao in sorted(per_station):
            for end in sorted(per_station[icao]):
                rec = asdict(per_station[icao][end])
                w.writerow([icao, end.strftime("%Y-%m-%dT%H:%MZ")]
                           + [_fmt(rec[k]) for k in RECORD_FIELDS])
    return path


def _fmt(v) -> str:
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float):
        # Four decimals: enough that features rebuilt from this file match the training rows.
        return "" if v != v else f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


def main() -> int:
    station_list = stations()
    X, Y, S, T = [], [], [], []
    replay: dict[str, dict[datetime, HourRecord]] = {}
    all_hourly: dict[str, dict[datetime, HourRecord]] = {}
    for st in station_list:
        icao = st["icao"]
        all_hourly[icao] = {}
        for path in sorted((RAW / "asos").glob(f"{icao}_*.csv")):
            all_hourly[icao].update(load_hourly(path, icao))

    print(f"{'station':8} {'hours':>8} {'flyable now':>12}  nearest stations")
    for idx, st in enumerate(station_list):
        icao, hourly = st["icao"], all_hourly[st["icao"]]
        if not hourly:
            print(f"{icao:8} {'no data':>8}")
            continue
        replay[icao] = {t: r for t, r in hourly.items() if t.year == TEST_YEAR}
        nearby = [(miles, all_hourly[code]) for code, miles in station_neighbors(icao)]
        n0 = len(X)
        for t, feats, labels in rows_for(hourly, st["lat"], st["lon"], nearby):
            X.append(feats); Y.append(labels); S.append(idx); T.append(int(t.timestamp()))
        share = np.mean([r.flyable for r in hourly.values()])
        near = ", ".join(f"{code} {miles:.0f} mi" for code, miles in station_neighbors(icao)) or "none within 100 mi"
        print(f"{icao:8} {len(X) - n0:>8,} {share:>11.1%}  {near}", flush=True)

    if not X:
        print("No raw data found. Run data_build/download_weather.py first.")
        return 1
    PROCESSED.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        PROCESSED / "dataset.npz",
        X=np.asarray(X, dtype=np.float32), Y=np.asarray(Y, dtype=np.int8),
        station=np.asarray(S, dtype=np.int16), t=np.asarray(T, dtype=np.int64),
        feature_names=np.asarray(FEATURE_NAMES), stations=np.asarray([s["icao"] for s in station_list]),
    )
    y = np.asarray(Y)
    print(f"Rows: {len(X):,}   features: {len(FEATURE_NAMES)}")
    for j, h in enumerate(HORIZONS):
        known = y[:, j] >= 0
        print(f"  +{h} h: labeled {known.sum():,}   flyable {y[known, j].mean():.1%}")
    path = write_replay(TEST_YEAR, replay)
    print(f"Replay file: {path} ({path.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
