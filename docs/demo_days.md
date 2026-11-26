# Demo days for the Time Machine

Written by `python -m eval_engine.replay_eval` (task A6). Replayed cases from the held-out
weather year where the forecaster disagreed with the old "weather right now" rule and turned
out right. All patient cases are synthetic. Aircraft are simulated and road times are modeled.

## 1. Saturday October 26, 2024, 01:30 AM Florida time (saw it clearing)
- From **Sarasota Meml Hospital** (`FA23`) to **Bayfront Health - St Petersburg** (`2FD3`), deadline 150 min
- Replay time (UTC): `2024-10-26T05:30+00:00`
- The app gave a 98% chance that the weather stays flyable for the flight. What happened: it stayed flyable.
- The app suggested `air_and_ground`. The "weather right now" rule would have picked `ground_only`. The weather looked bad, so the old rule kept to ground and lost 33.8 min.

## 2. Wednesday October 09, 2024, 09:00 PM Florida time (roughest weather of the year at Tampa (gusts 81 kt three hours later))
- From **Tampa General Hospital** (`61FL`) to **Lakeland Rgnl Medical Center** (`7FD7`), deadline 150 min
- Replay time (UTC): `2024-10-10T01:00+00:00`
- The app gave a 0% chance that the weather stays flyable for the flight. What happened: it did not stay flyable.
- The app suggested `ground_only`. The "weather right now" rule would have picked `ground_only`. 

