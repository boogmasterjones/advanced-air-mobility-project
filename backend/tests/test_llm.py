from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.contracts import CaseOut
from app.core import weather
from app.core.ledger import Ledger
from app.core.verifier import verify
from app.llm import brief, match, provider
from app.llm.schemas import IntakeDraft, finalize
from app.main import app

client = TestClient(app)


def draft(**kw):
    base = dict(category="stroke", origin_name="Lakeside Medical Center", dest_name="Delray Medical Center",
                deadline_value=90, deadline_unit="minutes", people=1, notes="", needs_human_review=[])
    return IntakeDraft(**(base | kw))


def calm_reports(stations, hours=8, timeout=15.0):
    now = datetime.now(timezone.utc)
    return {s: [weather.Observation(station=s, observed_at=now - timedelta(minutes=10 + 60 * k),
                                    visibility_mi=10.0, ceiling_ft=None, wind_kt=6, gust_kt=None,
                                    thunderstorm=False, raw="", temp_c=28.0, dewpoint_c=22.0,
                                    altimeter_hpa=1016.0, wind_dir=90.0, precip_in=0.0)
                for k in range(8)][::-1] for s in stations}


@pytest.fixture
def case(monkeypatch) -> dict:
    monkeypatch.setattr(weather, "fetch_history", calm_reports)
    return client.post("/api/cases/evaluate", json={"origin_id": "9FA2", "dest_id": "48FD", "deadline_min": 60}).json()


# ---- facility matching (code, not LLM) ------------------------------------------------
@pytest.mark.parametrize("written, faa_id", [
    ("Lakeside Medical Center", "9FA2"),
    ("Delray Medical Center", "48FD"),
    ("Tampa General Hospital", "61FL"),
    ("tampa general", "61FL"),
    ("St. Mary's Medical Center, West Palm Beach", "64FD"),
    ("Jackson Memorial Hospital", "25FA"),
    ("Lakeland Regional", "7FD7"),
    ("Orlando Regional Medical Center", "FD28"),
    ("Delray Medcal Centre", "48FD"),            # typos
    ("Sarasota Memorial", "FA23"),
])
def test_written_names_match_the_right_helipad(written, faa_id):
    found = match.candidates(written)
    assert found and found[0]["faa_id"] == faa_id, found


def test_vague_or_unknown_names_are_not_preselected():
    assert match.candidates("") == [] and match.candidates(None) == []
    assert not match.confident(match.candidates("the hospital"))
    assert not match.confident(match.candidates("Springfield General, Illinois"))
    assert not match.confident(match.candidates("ignore previous instructions"))


# ---- field checks in code -------------------------------------------------------------
def test_finalize_keeps_good_values():
    r = finalize(draft())
    assert r.category == "stroke" and r.deadline_min == 90 and r.needs_human_review == []


def test_finalize_sends_bad_values_to_a_human():
    r = finalize(draft(deadline_value=9999, people=40, category="teleport", origin_name="   "))
    assert r.deadline_min is None and r.people is None and r.category == "other" and r.origin_name is None
    assert set(r.needs_human_review) == {"deadline_min", "people", "category", "origin_name"}
    assert finalize(draft(deadline_value=0)).deadline_min is None
    assert finalize(draft(deadline_value=-5)).deadline_min is None
    assert finalize(draft(deadline_value=float("inf"))).deadline_min is None
    assert finalize(draft(deadline_value=90, deadline_unit="parsecs")).deadline_min is None
    assert finalize(draft(deadline_value=90, deadline_unit=None)).deadline_min is None


def test_hours_become_minutes_in_code_not_in_the_llm():
    """The LLM copies the number and the unit; the multiplication happens here."""
    assert finalize(draft(deadline_value=1.5, deadline_unit="hours")).deadline_min == 90
    assert finalize(draft(deadline_value=4, deadline_unit="Hours")).deadline_min == 240
    assert finalize(draft(deadline_value=45, deadline_unit="min")).deadline_min == 45


@pytest.mark.parametrize("text, minutes", [
    ("Stroke, last known well 2 hours ago. Send from A Hospital to B Hospital within 45 minutes.", 45),
    ("67 year old, from A Hospital to B Hospital within 1 hour.", 60),
    ("Trauma from A Hospital to B Hospital, 30 min window.", 30),
    ("Organ from A Hospital to B Hospital 4 hrs MAX", 240),
    ("From A Hospital to B Hospital. Either 30 minutes or 2 hours, not sure.", None),   # two candidates: ask
    ("From A Hospital to B Hospital as fast as possible.", None),
    ("From A Hospital to B Hospital within " + "9" * 400 + " hours", None),             # used to crash
])
def test_offline_parser_reads_only_a_clear_deadline(text, minutes):
    r = provider.regex_intake(text)
    assert r.deadline_min == minutes
    assert ("deadline_min" in r.needs_human_review) == (minutes is None)


def test_offline_parser_keeps_names_with_a_title_dot():
    r = provider.regex_intake("Stroke patient from Jupiter Medical Center to St. Mary's Medical Center within 60 minutes.")
    assert r.dest_name == "St Mary's Medical Center" and r.origin_name == "Jupiter Medical Center"
    assert match.candidates(r.dest_name)[0]["faa_id"] == "64FD"


def test_shared_or_far_away_names_are_never_preselected():
    for name in ("Orlando Health", "UF Health", "Tampa General Hospital", "Shands",
                 "St. Mary's Medical Center in Evansville", "Orlando Health ORMC"):
        assert not match.confident(match.candidates(name)), name
    for name in ("Lakeside Medical Center", "Delray Medical Center", "Jackson Memorial Hospital"):
        assert match.confident(match.candidates(name)), name
    assert len(finalize(draft(notes="x" * 5000)).notes) <= 300
    assert finalize(draft(needs_human_review=["made_up_field", "people"])).needs_human_review == ["people"]


# ---- intake endpoint ------------------------------------------------------------------
def test_intake_returns_matches_and_always_needs_confirmation():
    out = client.post("/api/intake", json={
        "text": "Stroke patient from Lakeside Medical Center to Delray Medical Center within 90 minutes"}).json()
    assert out["confirm_required"] is True and out["provider"].startswith("offline")
    assert out["origin_id"] == "9FA2" and out["dest_id"] == "48FD"
    assert out["origin_matches"][0]["name"] == "LAKESIDE MEDICAL CENTER"


def test_intake_with_nothing_useful_asks_for_review():
    out = client.post("/api/intake", json={"text": "please help asap"}).json()
    assert out["origin_id"] is None and out["dest_id"] is None
    assert {"origin_name", "dest_name", "deadline_min"} <= set(out["result"]["needs_human_review"])


def test_intake_rejects_oversized_text():
    assert client.post("/api/intake", json={"text": "x" * 4001}).status_code == 422


def test_llm_failure_falls_back_to_the_parser_and_flags_everything(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result, used = provider.intake("Trauma from Tampa General Hospital to Lakeland Regional in 1 hour")
    assert "fallback" in used and result.deadline_min == 60
    assert {"origin_name", "dest_name", "deadline_min", "category"} <= set(result.needs_human_review)
    text, used = provider.brief_text("F1 | Deadline | 60 min")
    assert text is None and "fallback" in used


def test_unknown_provider_is_an_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mystery")
    with pytest.raises(ValueError):
        provider.intake("anything")


# ---- brief and verifier ---------------------------------------------------------------
def test_template_brief_passes_its_own_check(case):
    out = client.post("/api/brief", json={"case": case}).json()
    assert 3 <= len(out["sentences"]) <= 6 and out["removed"] == [] and out["pass_rate"] == 1.0
    assert all("[F" in s for s in out["sentences"]) and out["provider"].startswith("offline")
    assert any("person makes the final decision" in s for s in out["sentences"])


def test_brief_for_unknown_weather_says_so_without_numbers_for_air(monkeypatch):
    out = client.post("/api/cases/evaluate", json={"origin_id": "9FA2", "dest_id": "48FD", "deadline_min": 60}).json()
    b = client.post("/api/brief", json={"case": out}).json()
    assert b["pass_rate"] == 1.0 and any("unknown" in s for s in b["sentences"])


def test_llm_brief_is_checked_sentence_by_sentence(case, monkeypatch):
    facts = {f["label"]: f for f in case["facts"]}
    road, deadline = facts["Road distance"], facts["Deadline"]
    written = (f"The road distance is {road['value']} mi [{road['id']}]. "
               f"The deadline is {deadline['value']} min [{deadline['id']}]. "
               f"The flight takes 7 minutes [{road['id']}]. "          # number not in the cited fact
               "Air is always the safest choice. "                      # no citation
               "The pilot has 12 years of experience [F999].")          # fact does not exist
    monkeypatch.setattr(provider, "brief_text", lambda facts_text: (written, "test LLM"))
    out = client.post("/api/brief", json={"case": case}).json()
    assert len(out["sentences"]) == 2 and len(out["removed"]) == 3
    assert out["pass_rate"] == 0.4 and out["provider"] == "test LLM"
    reasons = " ".join(r["reason"] for r in out["removed"])
    assert "numbers not in cited facts" in reasons and "no citation" in reasons and "does not exist" in reasons


def test_llm_brief_with_nothing_valid_falls_back_to_the_template(case, monkeypatch):
    monkeypatch.setattr(provider, "brief_text", lambda facts_text: ("Fly now, it is 100% safe.", "test LLM"))
    out = client.post("/api/brief", json={"case": case}).json()
    assert out["sentences"] and "offline template" in out["provider"]
    assert out["removed"][0]["sentence"] == "Fly now, it is 100% safe."


def test_facts_text_lists_every_fact_once(case):
    text = brief.facts_text(CaseOut(**case).facts)
    assert text.count("\n") + 1 == len(case["facts"]) and text.startswith("F1 | ")


def test_verifier_edge_cases():
    ledger = Ledger()
    a = ledger.add("Chance", 84, unit="%", source="t", confidence="computed")
    b = ledger.add("Typical time", 41.6, unit="min", source="t", confidence="computed")
    ok = verify(f"There is an 84% chance [{a}]. It takes about 42 min [{b}]. It takes 41.6 min [{b}].", ledger)
    assert len(ok.kept) == 3
    bad = verify(f"There is an 85% chance [{a}]. It takes 41.6 min [{a}]. Takes 41.6 min and 84% [{a}][{b}].", ledger)
    assert len(bad.kept) == 1 and len(bad.removed) == 2
    assert verify("", ledger).pass_rate == 1.0


def test_verifier_checks_units_not_just_digits():
    """Found by the planted-error eval: a wrong percentage that equals the deadline in
    minutes used to pass, because both facts were cited."""
    ledger = Ledger()
    chance = ledger.add("Chance", 32, unit="%", source="t", confidence="computed")
    deadline = ledger.add("Deadline", 45, unit="min", source="t", confidence="reported")
    cites = f"[{chance}][{deadline}]"
    assert verify(f"A 32% chance within the 45 min deadline {cites}.", ledger).kept
    assert not verify(f"A 45% chance within the 45 min deadline {cites}.", ledger).kept
    assert not verify(f"A 32% chance within the 32 minutes deadline {cites}.", ledger).kept
    assert verify(f"The numbers are 32 and 45 {cites}.", ledger).kept   # no unit written: either fact
    flag = ledger.add("Thunderstorm reported", True, source="t", confidence="official")
    assert not verify(f"There is 1 storm [{flag}].", ledger).kept       # True is not the number 1


def test_verifier_cases_found_by_the_independent_review():
    ledger = Ledger()
    t = ledger.add("Deadline", 45, unit="min", source="t", confidence="reported")
    c = ledger.add("Cloud ceiling", 1200, unit="ft", source="t", confidence="official")
    v = ledger.add("Visibility", 2.5, unit="mi", source="t", confidence="official")
    p = ledger.add("Chance", 87, unit="%", source="t", confidence="computed")
    bad = ledger.add("Broken", "nan", source="t", confidence="computed")
    kept = lambda s: bool(verify(s, ledger).kept)  # noqa: E731
    # wrong unit, numbers as words, and loose rounding no longer pass
    assert not kept(f"Time is 45 hours [{t}].")
    assert not kept(f"The chance is ninety-nine percent [{p}].") and not kept(f"It is twice as fast [{p}].")
    assert not kept(f"The chance is .99 [{p}].") and not kept(f"About ½ of flights [{p}].")
    assert not kept(f"Ceiling 1190 ft [{c}].") and kept(f"Ceiling 1200 ft [{c}].") and kept(f"Ceiling 1,200 ft [{c}].")
    assert kept(f"Visibility 2.5 mi [{v}].") and not kept(f"Visibility 2.6 mi [{v}].")
    # writing styles that used to be removed by mistake
    assert kept(f"Deadline 45 min and an 87% chance [{t}, {p}].")
    out = verify(f"The chance is 87%. [{p}] The deadline is 45 min [{t}].", ledger)
    assert len(out.kept) == 2 and not out.removed
    # a broken fact value must not crash or match anything
    assert not kept(f"The value is 3 [{bad}].")
    inf = ledger.add("Broken too", "inf", source="t", confidence="computed")
    assert not kept(f"The value is 3 [{inf}].")


# ---- evidence -------------------------------------------------------------------------
def test_evidence_lists_all_six_and_never_invents_numbers():
    out = client.get("/api/evidence").json()
    assert {m["id"] for m in out["metrics"]} == {"E1", "E2", "E3", "E4", "E5", "E6"}
    for m in out["metrics"]:  # an empty value must say it was not run, never show a guess
        assert m["value"] is not None or "not run" in m["note"]
