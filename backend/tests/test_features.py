"""The forecaster must see the same inputs when it is trained and when it runs.

Training groups reports into hours through data_build.build_dataset; the live app groups
them through features.hour_buckets. These tests run both on the same real reports (a
three-day sample from Tampa, July 2024, kept in data/samples/) and require identical
results, so the two paths cannot drift apart unnoticed.
"""
import csv
import math
from datetime import datetime, timedelta, timezone

from app.core import forecaster
from app.core.features import FEATURE_NAMES, HISTORY_HOURS, build_features, hour_buckets
from app.core.geo import DATA_DIR
from data_build import taf
from data_build.build_dataset import load_hourly, parse_iem_row

SAMPLE = DATA_DIR / "samples" / "asos_KTPA_2024-07-14_to_16.csv"
TAF_SAMPLE = DATA_DIR / "samples" / "taf_KTPA_2024-07-14_to_16.csv"
HOUR = timedelta(hours=1)
LAT, LON = 27.975, -82.533


def reports():
    with open(SAMPLE, newline="", encoding="utf-8") as f:
        return [o for o in (parse_iem_row(row, "KTPA") for row in csv.DictReader(f)) if o is not None]


def same(a: float, b: float) -> bool:
    return (math.isnan(a) and math.isnan(b)) or a == b


def test_training_and_live_paths_build_identical_features():
    hourly, raw = load_hourly(SAMPLE, "KTPA"), reports()
    checked = 0
    for t in sorted(hourly)[HISTORY_HOURS:]:
        training = build_features([hourly.get(t - k * HOUR) for k in range(HISTORY_HOURS)], LAT, LON, t)
        live = build_features(hour_buckets(raw, t), LAT, LON, t)
        assert training is not None and live is not None
        assert all(same(a, b) for a, b in zip(training, live)), (t, training, live)
        assert len(live) == len(FEATURE_NAMES)
        checked += 1
    assert checked > 48


def test_reports_after_the_forecast_time_are_never_used():
    raw = reports()
    t = datetime(2024, 7, 15, 18, 0, tzinfo=timezone.utc)
    full = hour_buckets(raw, t)
    past_only = hour_buckets([r for r in raw if r.observed_at <= t], t)
    assert repr(full) == repr(past_only)  # repr, because a missing wind direction is NaN


def test_sample_contains_the_afternoon_storm():
    """The sample was picked because Tampa reported thunderstorms on July 15, 2024."""
    hourly = load_hourly(SAMPLE, "KTPA")
    storm = [t for t, r in hourly.items() if r.ts and t.day == 15]
    assert storm and all(not hourly[t].flyable for t in storm)


def test_forecast_drops_when_a_storm_is_reported():
    """Live path end to end on real reports: calm morning against the stormy afternoon."""
    raw = reports()
    hourly = load_hourly(SAMPLE, "KTPA")
    storm_hour = min(t for t, r in hourly.items() if r.ts and t.day == 15)
    calm = forecaster.from_reports(raw, LAT, LON, datetime(2024, 7, 15, 12, 30, tzinfo=timezone.utc))
    storm = forecaster.from_reports([r for r in raw if r.observed_at <= storm_hour], LAT, LON, storm_hour)
    assert calm is not None and storm is not None
    assert storm.p_flyable[0] < calm.p_flyable[0]
    assert all(0 <= p <= 1 for p in list(calm.p_flyable.values()) + list(storm.p_flyable.values()))


def test_official_forecast_categories_on_real_data():
    tafs = taf.load(TAF_SAMPLE)
    assert len(tafs) >= 6 and tafs == sorted(tafs, key=lambda t: t.issued)
    issued = [t.issued for t in tafs]
    t = datetime(2024, 7, 15, 12, 0, tzinfo=timezone.utc)
    current = taf.latest_before(tafs, issued, t)
    assert current is not None and current.issued <= t
    # Morning hours: nothing bad forecast. Afternoon: the forecast mentions thunderstorms.
    morning = taf.category(current, t, t + HOUR)
    afternoon = taf.category(current, t.replace(hour=20), t.replace(hour=21))
    assert morning in taf.CATEGORIES and afternoon in taf.CATEGORIES
    assert taf.CATEGORIES.index(afternoon) <= taf.CATEGORIES.index(morning)
    assert taf.latest_before(tafs, issued, datetime(2020, 1, 1, tzinfo=timezone.utc)) is None
