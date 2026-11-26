"""Time Machine: replay one case at a past moment, then score it against what happened.

"Then" is the normal answer built with only the weather known at the replay time.
"Actual" looks at the hours after that time: did the airports really stay flyable for the
flight? The same decision math is then run again with the real weather outcome (chance
1 or 0 instead of a forecast) to find the best choice in hindsight.

regret_min   minutes lost: typical time of the choice the app suggested, under the real
             weather, minus the typical time of the fastest choice under the real weather
regret_chance  points of on-time chance lost against the best choice in hindsight
Road times and the aircraft are still modeled or simulated, in the replay as in the app.
"""
from __future__ import annotations

from datetime import datetime

from . import decision, history
from .case import Built, build_case
from .ledger import Ledger


def hindsight(built: Built, origin: dict, dest: dict, deadline_min: int, flew: bool) -> list[decision.Option]:
    """The same case with the weather outcome known."""
    return decision.evaluate(
        origin=origin, dest=dest, deadline_min=deadline_min, local_hour=built.local_hour,
        weekday=built.weekday,
        p_weather=1.0 if flew else 0.0, weather_reasons=[], ledger=Ledger(),
        road=built.road, base=built.base, wind=built.wind, temp_c=built.temp_c)


def actual_weather(built: Built) -> bool | None:
    results = [history.actual_flyable(st["icao"], built.flight_start, built.flight_end)
               for st in built.stations]
    if any(r is False for r in results):
        return False
    return None if any(r is None for r in results) else True


def score(recommended: str, truth: list[decision.Option]) -> dict:
    """Regret of one choice against the options under the real weather."""
    usable = {o.strategy: o for o in truth if o.status == "OK"}
    chosen = usable.get(recommended) or usable["ground_only"]
    return {
        "actual_best_strategy": decision.recommend(truth),
        "regret_min": round(max(0.0, chosen.median_min - min(o.median_min for o in usable.values())), 1),
        "regret_chance": round(max(0.0, max(o.p_by_deadline for o in usable.values()) - chosen.p_by_deadline), 3),
        "chance_on_time": chosen.p_by_deadline,
    }


def replay(*, origin: dict, dest: dict, deadline_min: int, as_of: datetime) -> dict:
    """Returns the fields of contracts.ReplayOut as a dict."""
    built = build_case(origin=origin, dest=dest, deadline_min=deadline_min, now=as_of,
                       source=history.ArchiveWeather())
    flew = actual_weather(built)
    out = {"as_of": built.out["as_of"], "then": built.out, "actual_flyable": flew,
           "actual_best_strategy": None, "regret_min": None, "regret_chance": None, "actual_options": None}
    if flew is None:
        return out
    truth = hindsight(built, origin, dest, deadline_min, flew)
    result = score(built.out["recommended"], truth)
    out.update(actual_best_strategy=result["actual_best_strategy"], regret_min=result["regret_min"],
               regret_chance=result["regret_chance"], actual_options=[o.model_dump() for o in truth])
    return out
