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
                deadline_min=90, people=1, notes="", needs_human_review=[])
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
    r = finalize(draft(deadline_min=9999, people=40, category="teleport", origin_name="   "))
    assert r.deadline_min is None and r.people is None and r.category == "other" and r.origin_name is None
    assert set(r.needs_human_review) == {"deadline_min", "people", "category", "origin_name"}
    assert finalize(draft(deadline_min=0)).deadline_min is None
    assert finalize(draft(deadline_min=-5)).deadline_min is None
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


# ---- evidence -------------------------------------------------------------------------
def test_evidence_lists_all_six_and_never_invents_numbers():
    out = client.get("/api/evidence").json()
    assert {m["id"] for m in out["metrics"]} == {"E1", "E2", "E3", "E4", "E5", "E6"}
    for m in out["metrics"]:
        assert m["value"] is not None or m["note"] == "not run yet"
