from datetime import datetime, timedelta, timezone

from app.core import decision, weather
from app.core.geo import heliports
from app.core.ledger import Ledger
from app.core.verifier import verify
from app.llm.provider import regex_intake

NOW = datetime(2026, 7, 15, 18, 0, tzinfo=timezone.utc)


def obs(**kw):
    base = dict(station="KTPA", observed_at=NOW, visibility_mi=10.0, ceiling_ft=None,
                wind_kt=8, gust_kt=None, thunderstorm=False, raw="")
    return weather.Observation(**(base | kw))


def test_stale_or_missing_weather_is_unknown():
    assert weather.flyable_now(None, NOW)[0] == "UNKNOWN"
    assert weather.flyable_now(obs(observed_at=NOW - timedelta(hours=3)), NOW)[0] == "UNKNOWN"


def test_thunderstorm_and_low_ceiling_are_not_flyable():
    assert weather.flyable_now(obs(thunderstorm=True), NOW)[0] == "NOT_FLYABLE"
    assert weather.flyable_now(obs(ceiling_ft=600), NOW)[0] == "NOT_FLYABLE"
    assert weather.flyable_now(obs(), NOW)[0] == "FLYABLE"


def test_parse_metar_json_ceiling_and_visibility():
    item = {"icaoId": "KMCO", "obsTime": 1794966780, "visib": "10+", "wspd": 10, "wgst": 18,
            "wxString": "-TSRA", "clouds": [{"cover": "SCT", "base": 2000}, {"cover": "BKN", "base": 4800}]}
    o = weather.parse_metar_json(item)
    assert o.visibility_mi == 10 and o.ceiling_ft == 4800 and o.thunderstorm and o.gust_kt == 18


def test_unknown_weather_never_recommends_air():
    pads = heliports()
    ledger = Ledger()
    opts = decision.evaluate(origin=pads["9FA2"], dest=pads["48FD"], deadline_min=60, local_hour=10,
                             p_air_flies=None, weather_reasons=["no report"], ledger=ledger)
    assert {o.strategy: o.status for o in opts}["air_only"] == "UNKNOWN"
    assert decision.recommend(opts) == "ground_only"


def test_parallel_is_never_slower_than_ground():
    pads = heliports()
    opts = decision.evaluate(origin=pads["9FA2"], dest=pads["48FD"], deadline_min=60, local_hour=17,
                             p_air_flies=0.9, weather_reasons=[], ledger=Ledger())
    by = {o.strategy: o for o in opts}
    assert by["air_and_ground"].p_by_deadline >= by["ground_only"].p_by_deadline


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
