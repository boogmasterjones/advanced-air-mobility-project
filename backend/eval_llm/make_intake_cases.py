"""Builds the synthetic intake test set for E3 (task B2). Every case is made up.

Run from backend/:
    python -m eval_llm.make_intake_cases
Writes eval/datasets/intake_cases.json: 100 request texts with the correct answer for
each field. The texts vary on purpose: formal and rushed wording, abbreviations, typos,
English and Spanish mixed, extra numbers that are not the deadline, and missing fields
(where the right answer is "not stated", never a guess).

The generator is seeded, so the file can be rebuilt exactly. Facility names come from
the public FAA heliport list and the state trauma center list; no person is real.
"""
from __future__ import annotations

import csv
import json
import random
import sys

from app.core.geo import DATA_DIR, heliports

OUT = DATA_DIR.parent / "eval" / "datasets" / "intake_cases.json"
SEED = 3
EXPAND = {"MEML": "Memorial", "RGNL": "Regional", "HOSP": "Hospital"}

# (origin FAA id, how a person might write it)
SENDERS = [
    ("9FA2", "Lakeside Medical Center"), ("9FA2", "Lakeside Med Ctr in Belle Glade"),
    ("FD85", "DeSoto Memorial Hospital"), ("9FD3", "Highlands Regional Medical Center"),
    ("28FD", "Jackson County Hospital"), ("60FL", "Jupiter Medical Center"),
    ("FA96", "Oviedo Medical Center"), ("7FA0", "Lower Keys Medical Center"),
    ("44FA", "Orlando Health Lakeland"), ("3FD2", "UF Health Leesburg Hospital"),
    ("FL39", "Wellington Medical Center"), ("FA16", "Jay Hospital"),
]


def receivers() -> list[tuple[str, str]]:
    """Trauma centers by the name the state uses, which is how staff would write them."""
    pads = heliports()
    with open(DATA_DIR / "seeds" / "trauma_centers.csv", newline="", encoding="utf-8") as f:
        return [(r["faa_id"], r["name"]) for r in csv.DictReader(f)
                if r["faa_id"] in pads and r["name"] != "Baptist Hospital"]  # two pads share that name


# (template, category, deadline in minutes or None, people or None)
TEMPLATES = [
    ("Stroke patient from {a} to {b} within 90 minutes.", "stroke", 90, None),
    ("Stroke alert. Transfer from {a} to {b}, needs to arrive within 60 min for clot removal.", "stroke", 60, None),
    ("pt w/ CVA at {a}, xfer to {b} in under 45 mins pls", "stroke", 45, None),
    ("67 year old with stroke symptoms, last known well 2 hours ago. Send from {a} to {b} within 1 hour.", "stroke", 60, 1),
    ("Trauma from {a} to {b} in 1 hour.", "trauma", 60, None),
    ("Car crash victim, 2 units of blood given, moving from {a} to {b}. Must be there in 45 minutes.", "trauma", 45, 1),
    ("Level 1 trauma activation: {a} to {b}, 30 min window.", "trauma", 30, None),
    ("We have a STEMI at {a}. Receiving hospital is {b}. Door to balloon target is 90 minutes.", "heart_attack", 90, None),
    ("Heart attack patient needs cath lab. From {a} to {b} within 1.5 hours.", "heart_attack", 90, 1),
    ("Kidney for transplant leaving {a}, going to {b}. Must arrive within 6 hours.", "organ", 360, 0),
    ("Organ transport from {a} to {b} within 4 hours.", "organ", 240, None),
    ("Liver for a transplant team: pick up at {a}, deliver to {b} in 3 hrs.", "organ", 180, 0),
    ("Need 6 units of O negative blood moved from {a} to {b} within 2 hours.", "supplies", 120, 0),
    ("Supplies run: ventilator parts from {a} to {b}, needed in 90 min.", "supplies", 90, 0),
    ("Paciente con derrame cerebral (stroke), de {a} a {b}, within 60 minutes por favor.", "stroke", 60, 1),
    ("Traslado urgente: trauma patient from {a} to {b}, tiene que llegar in 45 minutes.", "trauma", 45, 1),
    ("Please arrange transfer from {a} to {b} for a stroke patient.", "stroke", None, 1),
    ("Trauma patient at {a} needs a higher level of care at {b}. How fast can we get there?", "trauma", None, 1),
    ("STEMI, 54 y/o male, BP 90/60, from {a} to {b}.", "heart_attack", None, 1),
    ("Burn patient and one nurse escort from {a} to {b} within 2 hours.", "other", 120, 2),
    ("Pediatric patient with parent, {a} to {b}, within 75 minutes.", "other", 75, 2),
    ("From {a} to {b} within 40 minutes, stroke.", "stroke", 40, None),
    ("Stroke patient needs transfer to {b} within 90 minutes.", "stroke", 90, 1),           # no origin
    ("Trauma patient at {a}, needs transfer out within 60 minutes.", "trauma", 60, 1),      # no destination
    ("URGENT!!! organ (heart for transplant) {a} >> {b} 4 hrs MAX", "organ", 240, 0),
]


def typo(name: str, rng: random.Random) -> str:
    """Drop one letter from a long word."""
    words = name.split()
    long = [i for i, w in enumerate(words) if len(w) > 5]
    if not long:
        return name
    i = rng.choice(long)
    k = rng.randrange(1, len(words[i]) - 1)
    words[i] = words[i][:k] + words[i][k + 1:]
    return " ".join(words)


def vary(name: str, rng: random.Random) -> tuple[str, str]:
    roll = rng.random()
    if roll < 0.15:
        return typo(name, rng), "typo"
    if roll < 0.30:
        return name.lower(), "lowercase"
    if roll < 0.42:
        return name.replace("Medical Center", "Med Ctr").replace("Hospital", "Hosp"), "abbreviated"
    return name, "as listed"


def main() -> int:
    rng = random.Random(SEED)
    dests = receivers()
    cases = []
    for i in range(100):
        template, category, deadline, people = TEMPLATES[i % len(TEMPLATES)]
        (a_id, a_name), (b_id, b_name) = rng.choice(SENDERS), rng.choice(dests)
        while b_id == a_id:
            b_id, b_name = rng.choice(dests)
        a_text, a_kind = vary(a_name, rng)
        b_text, b_kind = vary(b_name, rng)
        has_a, has_b = "{a}" in template, "{b}" in template
        cases.append({
            "id": f"intake-{i + 1:03d}",
            "text": template.format(a=a_text, b=b_text),
            "expected": {"category": category, "deadline_min": deadline, "people": people,
                         "origin_id": a_id if has_a else None, "dest_id": b_id if has_b else None},
            "tags": sorted({k for k, used in ((a_kind, has_a), (b_kind, has_b)) if used and k != "as listed"}
                           | ({"no deadline"} if deadline is None else set())
                           | ({"missing place"} if not (has_a and has_b) else set())
                           | ({"spanish mix"} if "Paciente" in template or "Traslado" in template else set())),
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = {"_note": "Synthetic intake requests for E3. Every case is made up; facility names are public. "
                    "Built by backend/eval_llm/make_intake_cases.py (seeded).",
           "cases": cases}
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(cases)} cases to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
