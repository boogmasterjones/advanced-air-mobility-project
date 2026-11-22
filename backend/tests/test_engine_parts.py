from datetime import datetime, timedelta, timezone

from app.core import decision, history, replay, roads
from app.core.forecaster import Forecast
from app.core.geo import heliports, station_neighbors, stations_near
from app.core.ledger import Ledger

T0 = datetime(2024, 7, 15, 18, 0, tzinfo=timezone.utc)
MIN = timedelta(minutes=1)


# ---- forecast window ------------------------------------------------------------------
def test_window_takes_the_lowest_hour_it_touches():
    fc = Forecast(issued_at=T0, p_flyable={0: 0.9, 1: 0.6, 2: 0.8, 3: 0.7}, model="test")
    assert fc.window(T0 + 5 * MIN, T0 + 40 * MIN) == 0.9            # inside the first hour
    assert fc.window(T0 + 30 * MIN, T0 + 90 * MIN) == 0.6           # first and second hour
    assert fc.window(T0 + 70 * MIN, T0 + 170 * MIN) == 0.6          # second and third
    assert fc.window(T0 + 130 * MIN, T0 + 150 * MIN) == 0.8         # third only
    assert fc.window(T0 + 300 * MIN, T0 + 400 * MIN) == 0.7         # beyond the last hour: use the last
    assert fc.window(T0 - 30 * MIN, T0 + 10 * MIN) == 0.9           # never looks before the first hour


# ---- roads ----------------------------------------------------------------------------
def test_saved_route_is_used_and_labeled_as_routed():
    pads = heliports()
    r = roads.route(pads["9FA2"], pads["48FD"], decision.profiles()["ground_ambulance"])
    assert r.routed and "OSRM" in r.source and len(r.geometry) > 5 and 20 < r.miles < 80


def test_unsaved_route_falls_back_to_a_labeled_model():
    pads = heliports()   # conftest sets ROUTE_LOOKUP=cache, so nothing is fetched
    r = roads.route(pads["9FA2"], pads["FD18"], decision.profiles()["ground_ambulance"])  # to Tallahassee
    assert not r.routed and r.confidence == "assumption" and "modeled" in r.source and r.geometry == []
    assert r.fetched_at is None and r.miles > 300


# ---- rush hour ------------------------------------------------------------------------
def test_rush_hour_slowdown_follows_the_published_indexes():
    from app.core import congestion
    assert congestion.is_peak(8, True) and congestion.is_peak(17, True)
    assert not congestion.is_peak(12, True) and not congestion.is_peak(19, True)   # 3 to 7 p.m. ends at 7
    assert not congestion.is_peak(8, False)                                        # weekends: no peak
    miami, rural = {"lat": 25.77, "lon": -80.19}, {"lat": 27.2, "lon": -81.3}
    assert congestion.index_at(**miami) == (1.45, "Miami") and congestion.index_at(**rural) == (1.0, None)
    assert congestion.factor(miami, miami, [], 17, True)[0] == 1.45
    assert congestion.factor(miami, miami, [], 13, True)[0] == 1.0                 # off-peak
    assert congestion.factor(miami, miami, [], 17, False)[0] == 1.0                # Saturday
    assert congestion.factor(rural, rural, [], 17, True) == (
        1.0, "peak hour, but the route stays outside the metro areas, where no peak slowdown is measured")
    assert 1.2 < congestion.factor(miami, rural, [], 17, True)[0] < 1.25          # no route line: half and half
    # With a route line the slowdown is weighted by the miles inside the metro area.
    line = [[-80.19, 25.77], [-80.19, 25.90], [-80.60, 26.90], [-81.30, 27.20]]    # leaves Miami early
    mostly_rural, why = congestion.factor(miami, rural, line, 17, True)
    assert 1.0 < mostly_rural < 1.1 and "Miami" in why


def test_rush_hour_changes_the_ground_option_only_at_peak():
    pads = heliports()

    def ground(hour, weekday):
        opts = decision.evaluate(origin=pads["64FD"], dest=pads["48FD"], deadline_min=120, local_hour=hour,
                                 weekday=weekday, p_weather=None, weather_reasons=[], ledger=Ledger())
        return opts[0].median_min                                                  # West Palm Beach to Delray
    assert ground(17, True) > ground(13, True) == ground(17, False) == ground(3, True)


# ---- stations -------------------------------------------------------------------------
def test_station_helpers():
    assert all(miles <= 100 for _, miles in station_neighbors("KTPA"))
    assert "KTPA" not in [code for code, _ in station_neighbors("KTPA")]
    near = stations_near(27.94, -82.46)  # Tampa General
    assert near[0][0]["icao"] in ("KTPA", "KPIE", "KSPG") and near == sorted(near, key=lambda x: x[1])
    far = stations_near(24.56, -81.80, radius_mi=5)  # the nearest is always offered, even if far
    assert len(far) >= 1


# ---- what really happened -------------------------------------------------------------
def test_actual_flyable_reads_only_the_hours_the_flight_touches():
    recs = history.archive()["KTPA"]
    storm = min(t for t, r in recs.items() if not r.flyable and t.month == 7 and t.day == 15)
    assert history.actual_flyable("KTPA", storm - 30 * MIN, storm - 10 * MIN) is False   # inside the bad hour
    clear = next(t for t in sorted(recs) if t.month == 7 and all(
        recs.get(t + timedelta(hours=k)) and recs[t + timedelta(hours=k)].flyable for k in range(1, 4)))
    assert history.actual_flyable("KTPA", clear + 5 * MIN, clear + 110 * MIN) is True
    assert history.actual_flyable("KTPA", datetime(2031, 1, 1, tzinfo=timezone.utc),
                                  datetime(2031, 1, 1, 1, tzinfo=timezone.utc)) is None
    assert history.actual_flyable("NOPE", clear, clear + 30 * MIN) is None


# ---- always an out --------------------------------------------------------------------
def test_always_an_out_margin_shrinks_with_distance_heat_and_a_far_base():
    from app.core import alternates
    air, pads = decision.profiles()["air_taxi_a"], heliports()
    short = alternates.check(air, pads["61FL"], pads["7FD7"], None, 22)      # Tampa to Lakeland, about 33 mi
    assert short["always_reachable"] and short["min_margin_min"] > 0
    assert short["points"][0]["mile"] == 0 and abs(short["points"][-1]["mile"] - 33) < 5
    assert short["points"][-1]["site_miles"] < 1                              # at the end, the destination pad
    assert all(p["site_miles"] >= 0 for p in short["points"]) and short["sites"]
    hot = alternates.check(air, pads["61FL"], pads["7FD7"], None, 40)
    far_base = alternates.check(air, pads["61FL"], pads["7FD7"], {"lat": 28.43, "lon": -81.31}, 22)  # Orlando
    assert hot["min_margin_min"] < short["min_margin_min"]
    assert far_base["min_margin_min"] < short["min_margin_min"]
    margins = [p["margin_min"] for p in short["points"]]
    assert margins[-1] < margins[0]                                           # energy only goes down


# ---- regret ---------------------------------------------------------------------------
def opt(name, p, median):
    return decision.Option(strategy=name, status="OK", p_by_deadline=p, median_min=median,
                           range_min=(median - 10, median + 10), reasons=[], fact_ids=[])


def test_regret_is_measured_against_the_fastest_choice_under_the_real_weather():
    flew = [opt("ground_only", 0.40, 130), opt("air_only", 0.85, 95), opt("air_and_ground", 0.86, 94)]
    assert replay.score("air_and_ground", flew)["regret_min"] == 0
    r = replay.score("ground_only", flew)
    assert r["regret_min"] == 36 and abs(r["regret_chance"] - 0.46) < 1e-9
    assert r["actual_best_strategy"] == "air_and_ground"
    grounded = [opt("ground_only", 0.40, 130), opt("air_only", 0.20, 150), opt("air_and_ground", 0.40, 130)]
    assert replay.score("air_only", grounded)["regret_min"] == 20
    assert replay.score("air_and_ground", grounded)["regret_min"] == 0
    assert replay.score("ground_only", grounded)["actual_best_strategy"] == "ground_only"
