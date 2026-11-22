"""Match a facility name as a person wrote it to an FAA helipad. Plain code, no LLM.

The LLM only copies the name out of the request. Deciding which real facility that is
happens here, and the human confirms the match on screen. FAA names are upper-case and
abbreviated ("ST MARYS HOSPITAL", "LAKELAND RGNL MEDICAL CENTER"), so both sides are
reduced to the same short tokens before they are compared.
"""
from __future__ import annotations

import csv
import math
import re
from difflib import SequenceMatcher
from functools import lru_cache

from ..core.geo import DATA_DIR, heliports

# Long form -> the short token used for comparing. Applied to both sides.
SHORT = {
    "MEMORIAL": "MEML", "REGIONAL": "RGNL", "HOSPITAL": "HOSP", "HOSPITALS": "HOSP", "HOSP": "HOSP",
    "MEDICAL": "MED", "CENTER": "CTR", "CENTRE": "CTR", "SAINT": "ST", "MOUNT": "MT",
    "CHILDRENS": "CHILDRENS", "CHILDREN": "CHILDRENS", "UNIVERSITY": "UNIV", "GENERAL": "GEN",
    "COMMUNITY": "CMNTY", "INTERNATIONAL": "INTL", "COUNTY": "CO", "HEALTHCARE": "HEALTH",
    "JOHN": "JOHNS",
}
NOISE = {"THE", "OF", "AT", "AND", "HELIPORT", "HELISTOP", "HELIPAD", "EMERGENCY", "ER", "CAMPUS", "INC"}
CONFIDENT, CLEAR_LEAD = 0.72, 0.06  # score needed, and lead over the runner-up, to pre-select


def tokens(name: str) -> list[str]:
    text = re.sub(r"['’`]", "", name.upper())            # ST. MARY'S -> ST MARYS
    text = text.replace("ADVENT HEALTH", "ADVENTHEALTH")  # the FAA list spells it both ways
    words = re.sub(r"[^A-Z0-9]+", " ", text).split()
    return [SHORT.get(w, w) for w in words if w not in NOISE]


COMMON_IN = 15      # a word in more pad names than this is "common" (MED, CTR, HOSP...)
ONLY_COMMON_CAP = 0.6  # a match on common words alone can never be pre-selected


@lru_cache
def _index() -> tuple[list[tuple[dict, list[list[str]], list[str]]], dict[str, float], set[str]]:
    """Every pad with its names as tokens (the FAA name, plus the state's name for the 35
    trauma centers, since "UF Health Shands Hospital" is "SHANDS HELISTOP" to the FAA),
    a weight per token (rare words count for more), and the set of common tokens."""
    aliases: dict[str, list[str]] = {}
    path = DATA_DIR / "seeds" / "trauma_centers.csv"
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["faa_id"]:
                    aliases.setdefault(row["faa_id"], []).append(row["name"])
    pads = [(pad, [tokens(n) for n in [pad["name"]] + aliases.get(pad["faa_id"], [])], tokens(pad["city"]))
            for pad in heliports().values()]
    seen: dict[str, int] = {}
    for _, names, _ in pads:
        for tok in {t for name in names for t in name}:
            seen[tok] = seen.get(tok, 0) + 1
    weight = {tok: math.log(1 + len(pads) / n) for tok, n in seen.items()}
    return pads, weight, {tok for tok, n in seen.items() if n > COMMON_IN}


def _score(query: list[str], name: list[str], city: list[str], weight: dict[str, float],
           common: set[str]) -> float:
    if not query or not name:
        return 0.0
    q, n = set(query), set(name)
    w = lambda toks: sum(weight.get(t, 6.0) for t in toks)  # noqa: E731  unseen words are rare
    city_named = bool(city) and set(city) <= q
    # The city in the request should neither dilute the match nor create one: "WEST PALM
    # BEACH POLICE STATION" must not win just because the request says West Palm Beach.
    q_core = (q - set(city)) or q if city_named else q
    name_found = w(q & n) / w(n)                 # how much of the pad's name the request has
    request_found = w(q_core & n) / w(q_core)    # how much of the request the name explains
    overlap = 0.5 * name_found + 0.5 * request_found
    spelling = SequenceMatcher(None, " ".join(query), " ".join(name)).ratio()  # catches typos
    score = max(overlap, spelling) * 0.7 + min(overlap, spelling) * 0.3 + (0.08 if city_named else 0.0)
    only_city = city_named and not q - set(city)  # the request names a city, not a facility
    if only_city or (not (q_core & n) - common and spelling < 0.8):
        score = min(score, ONLY_COMMON_CAP)      # nothing distinctive in common
    return min(1.0, score)


def candidates(name: str | None, limit: int = 3) -> list[dict]:
    """Best helipad matches for a written name, best first, with a 0-1 score."""
    if not name or not name.strip():
        return []
    query = tokens(name)
    pads, weight, common = _index()
    scored = sorted(((max(_score(query, n, city, weight, common) for n in names), pad)
                     for pad, names, city in pads), key=lambda x: -x[0])
    return [{"faa_id": pad["faa_id"], "name": pad["name"], "city": pad["city"], "score": round(s, 3)}
            for s, pad in scored[:limit] if s >= 0.35]


def confident(matches: list[dict]) -> bool:
    """True when the top match is strong and clearly ahead, so the form can pre-select it.
    The human still confirms every case."""
    if not matches or matches[0]["score"] < CONFIDENT:
        return False
    if len(matches) == 1:
        return True
    top, second = matches[0]["score"], matches[1]["score"]
    exact = top >= 0.995 > second          # the written name is exactly one pad's name
    return exact or top - second >= CLEAR_LEAD
