"""Keeps the written claims honest: docs and data files must match what the code produces."""
import csv
import importlib.util
import json
from pathlib import Path

from app.core.geo import DATA_DIR, heliports

REPO = DATA_DIR.parent


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_readme_evidence_table_matches_the_result_files():
    script = load_script("update_readme_evidence")
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert script.render(readme) == readme, "Run: python scripts/update_readme_evidence.py"


def test_every_result_file_has_metrics_in_the_shared_shape():
    for path in sorted((REPO / "eval" / "results").glob("e[1-6].json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert doc["metrics"], path.name
        for m in doc["metrics"]:
            assert m["id"] == path.stem.upper() and m["name"] and "note" in m
            assert m["value"] is not None or "not run" in m["note"].lower(), f"{path.name}: empty value must say why"


def test_every_aircraft_number_has_a_confidence_tag():
    profiles = json.loads((DATA_DIR / "aircraft_profiles.json").read_text(encoding="utf-8"))
    allowed = {"official", "reported", "estimate", "assumption", "simulated"}
    for name, profile in profiles.items():
        if name.startswith("_"):
            continue
        for key, entry in profile.items():
            if isinstance(entry, dict):
                assert entry["confidence"] in allowed, f"{name}.{key}"
                assert isinstance(entry["value"], (int, float)), f"{name}.{key}"


def test_trauma_centers_point_at_real_pads_and_have_sources():
    pads = heliports()
    with open(DATA_DIR / "seeds" / "trauma_centers.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 36
    for r in rows:
        assert r["source_url"].startswith("https://") and r["level"] and r["name"]
        assert 24.3 <= float(r["lat"]) <= 31.1 and -87.7 <= float(r["lon"]) <= -79.8
        if r["faa_id"]:
            assert r["faa_id"] in pads, r["name"]


def test_saved_routes_are_plausible():
    doc = json.loads((DATA_DIR / "routes.json").read_text(encoding="utf-8"))
    pads = heliports()
    assert len(doc["pairs"]) > 100 and doc["fit"]["n"] > 100
    assert 1.0 < doc["fit"]["detour_factor"] < 2.0 and 20 < doc["fit"]["avg_mph"] < 70
    for key, route in doc["pairs"].items():
        a, b = key.split("|")
        assert a in pads and b in pads
        assert route["miles"] > 0 and route["minutes"] > 0 and route["fetched_at"]
        assert 5 < route["miles"] / route["minutes"] * 60 < 80, key  # average speed in mph


def test_no_secret_looking_strings_in_tracked_text():
    """A cheap guard next to gitleaks: nothing that looks like an API key in the source tree."""
    import re
    pattern = re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----")
    for folder in ("backend", "frontend/src", "scripts", "docs", "data/seeds"):
        for path in (REPO / folder).rglob("*"):
            if path.is_file() and path.suffix in {".py", ".ts", ".tsx", ".md", ".json", ".csv", ".txt"} \
                    and "node_modules" not in path.parts:
                assert not pattern.search(path.read_text(encoding="utf-8", errors="ignore")), path
    assert not (REPO / ".env").exists() or ".env" in (REPO / ".gitignore").read_text()
