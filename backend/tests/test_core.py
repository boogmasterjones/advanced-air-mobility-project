from datetime import datetime, timedelta, timezone

import numpy as np

from app.core import decision, energy, weather
from app.core.geo import bearing_deg, heliports
from app.core.ledger import Ledger
from app.core.verifier import verify
from app.llm.provider import regex_intake

NOW = datetime(2026, 7, 15, 18, 0, tzinfo=timezone.utc)


def obs(**kw):
    base = dict(station="KTPA", observed_at=NOW, visibility_mi=10.0, ceiling_ft=None,
                wind_kt=8, gust_kt=None, thunderstorm=False, raw="")
    return weather.Observation(**(base | kw))


def options(p_weather, deadline=120, hour=10, **kw):
    pads = heliports()
    opts = decision.evaluate(origin=pads["9FA2"], dest=pads["48FD"], deadline_min=deadline,
                             local_hour=hour, p_weather=p_weather, weather_reasons=[],
                             ledger=kw.pop("ledger", Ledger()), **kw)
    return {o.strategy: o for o in opts}, opts


# ---- weather rule ---------------------------------------------------------------------
def test_stale_or_missing_weather_is_unknown():
    assert weather.flyable_now(None, NOW)[0] == "UNKNOWN"
    assert weather.flyable_now(obs(observed_at=NOW - timedelta(hours=3)), NOW)[0] == "UNKNOWN"
    assert weather.flyable_now(obs(visibility_mi=None), NOW)[0] == "UNKNOWN"


def test_thunderstorm_low_ceiling_and_wind_are_not_flyable():
    assert weather.flyable_now(obs(thunderstorm=True), NOW)[0] == "NOT_FLYABLE"
    assert weather.flyable_now(obs(ceiling_ft=600), NOW)[0] == "NOT_FLYABLE"
    assert weather.flyable_now(obs(gust_kt=31), NOW)[0] == "NOT_FLYABLE"
    assert weather.flyable_now(obs(wind_kt=30), NOW)[0] == "NOT_FLYABLE"  # strong steady wind counts too
    assert weather.flyable_now(obs(visibility_mi=2.5), NOW)[0] == "NOT_FLYABLE"
    assert weather.flyable_now(obs(), NOW)[0] == "FLYABLE"
    assert weather.flyable_now(obs(ceiling_ft=1000, gust_kt=25, visibility_mi=3.0), NOW)[0] == "FLYABLE"


def test_parse_metar_json_ceiling_and_visibility():
    item = {"icaoId": "KMCO", "obsTime": 1794966780, "visib": "10+", "wspd": 10, "wgst": 18,
            "wdir": "VRB", "temp": 31.1, "dewp": 24.0, "altim": 1016.2,
            "wxString": "-TSRA", "clouds": [{"cover": "SCT", "base": 2000}, {"cover": "BKN", "base": 4800}]}
    o = weather.parse_metar_json(item)
    assert o.visibility_mi == 10 and o.ceiling_ft == 4800 and o.thunderstorm and o.gust_kt == 18
    assert o.wind_dir is None and o.temp_c == 31.1 and o.altimeter_hpa == 1016.2


def test_storm_report_without_visibility_still_counts():
    """Found by the independent review: such a report used to be thrown away whole."""
    from app.core.features import summarize_hour
    storm = obs(visibility_mi=None, thunderstorm=True)
    assert weather.report_is_flyable(storm) is False
    assert weather.report_is_flyable(obs(visibility_mi=None)) is None           # cannot be judged
    assert weather.report_is_flyable(obs(wind_kt=None, gust_kt=None)) is None   # no wind: cannot be judged
    assert weather.flyable_now(storm, NOW)[0] == "NOT_FLYABLE"
    mixed = summarize_hour([storm, obs(observed_at=NOW - timedelta(minutes=30))])
    assert mixed is not None and mixed.ts and not mixed.flyable and mixed.vis_min == 10
    alone = summarize_hour([storm])
    assert alone is not None and not alone.flyable and alone.vis_min != alone.vis_min   # NaN, not a made-up value
    assert summarize_hour([obs(visibility_mi=None)]) is None


def test_feed_values_of_the_wrong_type_do_not_crash():
    item = {"icaoId": "KMCO", "obsTime": 1794966780, "visib": "abc", "wspd": "12", "wgst": "strong",
            "wdir": None, "temp": "hot", "clouds": None, "wxString": None}
    o = weather.parse_metar_json(item)
    assert o.wind_kt == 12 and o.gust_kt is None and o.visibility_mi is None and o.temp_c is None
    assert weather.report_is_flyable(o) is None


# ---- decision engine ------------------------------------------------------------------
def test_unknown_weather_never_recommends_air():
    by, opts = options(None)
    assert by["air_only"].status == "UNKNOWN" and by["air_and_ground"].status == "UNKNOWN"
    assert by["ground_only"].status == "OK"
    assert decision.recommend(opts) == "ground_only"


def test_parallel_is_never_worse_than_either_single_choice():
    by, _ = options(0.9, hour=17)
    assert by["air_and_ground"].p_by_deadline >= by["ground_only"].p_by_deadline
    assert by["air_and_ground"].p_by_deadline >= by["air_only"].p_by_deadline
    assert by["air_and_ground"].median_min <= by["ground_only"].median_min


def test_bad_weather_makes_air_only_slower_than_ground():
    """A called-off flight costs time: the ambulance starts late."""
    by, opts = options(0.0)
    assert by["air_only"].median_min > by["ground_only"].median_min
    assert by["air_and_ground"].median_min == by["ground_only"].median_min
    assert decision.recommend(opts) == "ground_only"


def test_more_flyable_weather_never_lowers_the_air_chance():
    chances = [options(p, deadline=100)[0]["air_only"].p_by_deadline for p in (0.0, 0.3, 0.6, 0.9, 1.0)]
    assert chances == sorted(chances)


def test_close_calls_go_to_ground_then_to_air_with_ground_backup():
    def opt(name, p):
        return decision.Option(strategy=name, status="OK", p_by_deadline=p, median_min=30,
                               range_min=(20, 40), reasons=[], fact_ids=[])

    assert decision.recommend([opt("ground_only", 0.97), opt("air_only", 0.98), opt("air_and_ground", 0.985)]) == "ground_only"
    assert decision.recommend([opt("ground_only", 0.50), opt("air_only", 0.89), opt("air_and_ground", 0.90)]) == "air_and_ground"
    assert decision.recommend([opt("ground_only", 0.885), opt("air_only", 0.89), opt("air_and_ground", 0.90)]) == "ground_only"
    assert decision.recommend([opt("ground_only", 0.50), opt("air_only", 0.70), opt("air_and_ground", 0.90)]) == "air_and_ground"
    assert decision.recommend([]) == "ground_only"


def test_trip_beyond_range_is_not_available():
    pads = heliports()
    opts = decision.evaluate(origin=pads["61FL"], dest=pads["25FA"], deadline_min=240, local_hour=10,
                             p_weather=0.9, weather_reasons=[], ledger=Ledger())  # Tampa to Miami
    by = {o.strategy: o for o in opts}
    assert by["air_only"].status == "NOT_AVAILABLE" and by["ground_only"].status == "OK"
    assert decision.recommend(opts) == "ground_only"


def test_every_option_fact_has_a_receipt():
    ledger = Ledger()
    _, opts = options(0.8, ledger=ledger)
    for o in opts:
        assert o.fact_ids and all(ledger.get(i) is not None for i in o.fact_ids)


def test_same_inputs_give_the_same_answer():
    assert options(0.7)[1] == options(0.7)[1]


# ---- energy ---------------------------------------------------------------------------
def test_long_trip_on_a_hot_windy_day_lowers_the_air_chance():
    air = decision.profiles()["air_taxi_a"]

    def p(miles, temp, wind):
        rng = np.random.default_rng(1)
        return energy.check(air, [(miles, 90.0)], wind, temp, rng, 4000).p_ok

    calm = energy.Wind(5, None, 0)                # light crosswind
    headwind = energy.Wind(25, 35, 90)            # strong wind from the east, flying east
    assert p(30, 22, calm) > 0.99                 # short cool trip: plenty of energy
    assert p(85, 22, calm) > p(85, 36, calm)      # heat costs energy
    assert p(85, 22, calm) > p(85, 22, headwind)  # a headwind costs energy
    assert p(85, 36, headwind) < 0.5              # long, hot and into the wind: usually short
    assert p(85, None, calm) == p(85, 99, calm)   # unknown temperature takes the worst case


def test_headwind_slows_the_flight_and_tailwind_speeds_it():
    air = decision.profiles()["air_taxi_a"]
    east = 90.0
    slow = energy.check(air, [(60, east)], energy.Wind(20, None, 90), 20, np.random.default_rng(1), 2000)
    fast = energy.check(air, [(60, east)], energy.Wind(20, None, 270), 20, np.random.default_rng(1), 2000)
    assert np.median(slow.leg_minutes[0]) > 24 > np.median(fast.leg_minutes[0])  # 24 min in still air
    assert slow.headwind_mph > 0 > fast.headwind_mph


def test_bearing():
    assert abs(bearing_deg(27, -82, 28, -82) - 0) < 0.01
    assert abs(bearing_deg(27, -82, 27, -81) - 90) < 0.5
    assert abs(bearing_deg(28, -82, 27, -82) - 180) < 0.01


# ---- verifier and intake --------------------------------------------------------------
def test_verifier_removes_unsupported_numbers():
    ledger = Ledger()
    fid = ledger.add("Straight-line distance", 41.2, unit="mi", source="test", confidence="computed")
    brief = (f"The hospitals are 41.2 miles apart [{fid}]. "
             f"The flight takes 12 minutes [{fid}]. "
             "Air is always safe.")
    result = verify(brief, ledger)
    assert result.kept == [f"The hospitals are 41.2 miles apart [{fid}]."]
    assert len(result.removed) == 2


def test_regex_intake_baseline():
    r = regex_intake("Stroke patient from Lakeside Medical Center to Delray Medical Center within 90 minutes")
    assert r.category == "stroke" and r.deadline_min == 90
    assert r.origin_name == "Lakeside Medical Center" and r.dest_name == "Delray Medical Center"
