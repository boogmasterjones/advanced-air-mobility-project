# Car or Air

**Team: claude's plan** · Florida Tech Showcase AI Hackathon 2026 · Theme: *Cleared for Takeoff: AI for Florida's Skies*

> **PROTOTYPE. Not for real dispatch.** Aircraft are simulated, road times are modeled, and every recommendation is advisory. A human makes the final decision.

Car or Air helps a hospital transfer coordinator decide whether an urgent trip (a stroke or trauma patient, an organ, or supplies) should go by **ground ambulance, air taxi, or air taxi with a ground backup**. It shows the chance of making the medical deadline, how sure it is, and a receipt (source and timestamp) for every fact it uses.

## Why it matters

Florida is the U.S. lightning capital, and air taxis are starting test flights here (Tampa, Orlando and the Space Coast, Oct 2026). An air taxi only helps a hospital if it can actually fly when the clock is running. See `RESEARCH.md` for the sourced background.

## The three screens

1. **New case.** Paste a transfer request or fill the form. The app compares the three options on one time scale, shows where the minutes go (waiting, time at the hospital, travel, handoff), draws the road route, the flight path and the landing places within reach, shows the weather outlook, writes a short brief where every number links to its receipt, and logs your Approve / Hold / Override decision with a reason. A labeled demo mode answers from saved weather when the live feed or the network is down.
2. **Time Machine.** Pick any moment in 2024. The app answers using only the weather known at that moment, then shows what really happened and how many minutes its suggestion lost against the best choice in hindsight.
3. **Evidence.** The test results below, read straight from the result files, plus a chart of how well the forecaster's percentages hold up.

## What the AI does, and what is plain code

| Part | Type | What it does |
|---|---|---|
| Flyable-window forecaster | **Machine learning** (LightGBM) | Chance each airport stays flyable for each of the next 4 hours, from the airport's own weather reports and its neighbors'. Trained on 2019 to 2023, tested once on 2024. |
| Request intake | **LLM** with a fixed form | Turns a pasted request into form fields. Every field is checked again in code, facility names are matched to real helipads in code, and a person confirms. |
| Case brief | **LLM**, then a code verifier | Writes 3 to 6 sentences from the case's facts. Code removes any sentence whose numbers do not match the facts it cites. |
| Comparing options | **Plain code** | 2,000 simulated outcomes per option. The LLM never calculates and never decides. |
| Battery check, road times, replay scoring | **Plain code** | Physics and arithmetic with every input in the receipts. |

Without an LLM key the app still runs: intake uses a simple parser and the brief uses a fixed template, both labeled on screen as "offline".

## Evidence

Every number comes from a script in this repository and is shown as it came out. Rebuild them with the commands in "Rebuild the data, the model and the evidence".

<!-- EVIDENCE:START -->
| Test | What was measured | Result | Compare with | How to read it |
|---|---|---|---|---|
| E1 | | not run | | Run the script for E1 (see below). |
| E2 | Aircraft sent for nothing in active weather (share of cases) | **0.167** | 0.167 | 30 cases with a storm or unflyable hour within 3 hours at the pick-up airport. Lower is better. Synthetic cases replayed on real 2024 weather; aircraft simulated, road times modeled. Compared with the old rule that looks only at the weather right now. |
| E2 | Minutes lost in active weather against the best choice in hindsight | **6.31** | 6.31 | Lower is better. Sending both vehicles every time loses 0 minutes but launches an aircraft in every case. Synthetic cases replayed on real 2024 weather; aircraft simulated, road times modeled. Compared with the old rule that looks only at the weather right now. |
| E2 | Minutes lost at random hours against the best choice in hindsight | **7.28** | 7.28 | 30 cases at random hours of the year. Synthetic cases replayed on real 2024 weather; aircraft simulated, road times modeled. Compared with the old rule that looks only at the weather right now. |
| E3 | Intake: requests with every main field right | **not run** | 0.51 | 100 synthetic requests (typos, abbreviations, Spanish mix, missing fields). Share of requests with category, both facilities and deadline all right. Baseline: a regex parser. LLM not run: set LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY, then run this script again. |
| E4 | Prompt-injection cases handled safely | **not run** | 0.733 | 30 attack requests (fake system messages, planted values, instructions inside facility names, prompt-reveal requests). Pass: valid output, no protected field changed, no forbidden phrase. Baseline: the regex parser, which cannot follow instructions but misreads messy text. LLM not run: set LLM_PROVIDER=anthropic and ANTHROPIC_API_KEY, then run this script again. |
| E5 | Planted errors the verifier caught | **1** | 0 | 536 deliberately wrong sentences (changed number, missing citation, made-up fact, wrong fact) built from 30 replayed cases. Without a verifier none would be caught. |
| E5 | Brief sentences that passed the check | **1** |  | 172 sentences over 30 replayed cases. Writer: offline (no LLM). The offline template is built to pass; run with an LLM key to measure a real writer. |
| E6 | Helicopter beats the road above this distance (miles), measured the study's way | **36** | 31.9 | Compared the way the study did, our model puts the helicopter break-even at 36.0 road miles against the study's 32: it agrees with the study to within 25%. With the ground delays the app really uses (waiting for the ambulance and time at the sending hospital, from published transfer studies), the helicopter wins from 8.5 miles. The study allowed the road only 10 minutes for all of that. Road times have no traffic. Sanity check only. |
<!-- EVIDENCE:END -->

Known limits, stated plainly:

- Road times come from a public router with no live traffic. On weekdays from 6 to 10 a.m. and 3 to 7 p.m. the part of the route inside a metro area is slowed by that area's published travel time index (`RESEARCH.md` section 13); where each metro area starts and ends is our assumption.
- The air taxi is simulated. Its battery, speed and delays are estimates or assumptions, each tagged in `data/aircraft_profiles.json`. Time at the hospital uses helicopter air ambulance figures because no air taxi data exists.
- Pad availability is simulated. Published studies disagree about when air beats ground (`RESEARCH.md` section 12).
- "Air taxi with ground backup" assumes the patient ends up on whichever vehicle would arrive first, which is the best case for that option.
- Weather comes from the nearest reporting airport, up to 40 miles from the pad. Farther than that, or with no report in 90 minutes, the air options show Unknown.
- The brief verifier checks numbers and units against the cited facts, not the meaning of a sentence. Two cited facts with the same unit could be swapped without being caught.
- The LLM scores (E3, E4, and the LLM half of E5) need an API key to run. Until then those rows say "not run".

## Repository layout

```
backend/app/core/     weather, features, forecaster, energy, roads, decision, case, replay, ledger, verifier
backend/app/llm/      provider (offline / Anthropic), schemas, facility matching, brief
backend/app/api/      routes: cases.py (engine), ai.py (LLM, evidence)
backend/app/contracts.py   every request and response shape
backend/data_build/   download weather history, build the dataset, baselines
backend/models/       train_forecaster.py and the saved model (forecaster_v1/)
backend/eval_engine/  E2 replay regret, E6 break-even check
backend/eval_llm/     E3 intake, E4 prompt injection, E5 brief and verifier
backend/tests/        tests; they never use the network
frontend/             React + TypeScript + Vite + MapLibre
data/                 seeds (FAA heliports, stations, trauma centers), aircraft_profiles.json,
                      routes.json (saved road routes), replay/ (2024 weather for the Time Machine), samples/
eval/datasets/        synthetic intake requests and injection attacks
eval/results/         e1.json to e6.json, written by the scripts
scripts/              check_data_access.py, cache_routes.py, update_readme_evidence.py
docs/                 TASKS.md, demo_days.md, JADEN_START_HERE.md
CLAUDE.md   team rules     PLAN.md   build plan     RESEARCH.md   sourced research notes
```

## Run locally

Requirements: Python 3.11+ (3.13 tested), Node 20+ (22 and 24 tested).

```bash
# 1. Backend (terminal 1)
cd backend
python3 -m venv .venv && source .venv/bin/activate     # Windows: py -m venv .venv ; .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest -q                 # all tests should pass, no network needed
uvicorn app.main:app --reload --port 8000

# 2. Frontend (terminal 2)
cd frontend
npm ci
npm run dev                         # open http://localhost:5173
```

To serve everything from one process (like production): `cd frontend && npm run build`, then run uvicorn and open http://localhost:8000.

**Environment variables** (copy `.env.example` to `.env`; never commit it):

| Variable | Meaning |
|---|---|
| `LLM_PROVIDER` | `offline` (default, no network) or `anthropic` |
| `ANTHROPIC_API_KEY` | Needed only for `anthropic` |
| `INTAKE_MODEL`, `BRIEF_MODEL` | Model ids; both default to `claude-haiku-5-5` |
| `ROUTE_LOOKUP` | `live` (default: ask the public OSRM router for trips not in `data/routes.json`) or `cache` (never call out) |

## Rebuild the data, the model and the evidence

Everything needed to run the app is already in the repository. These steps rebuild it from the public sources (about 500 MB of downloads and 30 to 60 minutes).

```bash
cd backend
pip install -r requirements-train.txt
python data_build/download_weather.py        # A1: 2019-2024 weather reports and official forecasts
python -m data_build.build_dataset           # A2: hourly records, features, labels, Time Machine archive
python -m data_build.baselines               # A2: persistence, climatology, official forecast
python -m models.train_forecaster --skip-test    # develop without looking at the 2024 test year
python -m models.train_forecaster            # A3: final model and E1
python ../scripts/cache_routes.py            # A4: saved road routes
python -m eval_engine.breakeven_eval         # E6
python -m eval_engine.replay_eval            # E2 and docs/demo_days.md
python -m eval_llm.make_intake_cases         # the 100 synthetic intake requests
python -m eval_llm.intake_eval               # E3 (LLM part needs a key)
python -m eval_llm.injection_eval            # E4 (LLM part needs a key)
python -m eval_llm.brief_eval                # E5
python ../scripts/update_readme_evidence.py  # copy the results into this README
```

## Deploy to Google Cloud Run

```bash
gcloud config set project YOUR_PROJECT_ID
gcloud run deploy car-or-air --source . --region us-east1 --allow-unauthenticated --memory 1Gi
# Optional LLM key from Secret Manager:
# gcloud secrets create anthropic-api-key --data-file=-   (paste key, then Ctrl-D)
# gcloud run services update car-or-air --region us-east1 \
#   --set-secrets ANTHROPIC_API_KEY=anthropic-api-key:latest --set-env-vars LLM_PROVIDER=anthropic
```

On demo days, keep one instance warm: `gcloud run services update car-or-air --region us-east1 --min-instances 1`. CI builds the same Docker image on every pull request and checks that it serves the app, loads the forecaster and replays a past case.

## Data sources

- Live airport weather: [Aviation Weather Center API](https://aviationweather.gov/data/api/).
- Past airport weather and official forecasts: [Iowa Environmental Mesonet](https://mesonet.agron.iastate.edu/request/download.phtml). 2.9 million reports from 41 Florida airports, 2019 to 2024. A few hundred contain typos (a steady wind of 86 knots "gusting" 16, visibility of 160 miles, pressure "A3993"); `clean_wind` and `in_range` in `backend/app/core/weather.py` turn such values into "unknown" for training and for the live feed alike.
- Heliports: [FAA 28-day data](https://www.faa.gov/air_traffic/flight_info/aeronav/aero_data/NASR_Subscription/), Oct 29, 2026 cycle.
- Trauma centers: [Florida Department of Health list](https://www.floridahealth.gov/wp-content/uploads/2025/08/Florida-Trauma-Centers.pdf), 36 centers, matched to helipads by hand.
- Road routes: the public [OSRM](https://project-osrm.org/) demo router on OpenStreetMap data.
- Aircraft and transfer-time figures: manufacturer pages and published studies, each tagged official, reported, estimate or assumption. Full list in `RESEARCH.md`.

## Responsible AI

- Facts carry a source and timestamp (receipts), and a verifier checks the LLM's numbers and units.
- All calculations are in code. The LLM extracts fields and writes text from given facts.
- Missing or old weather (over 90 minutes) marks both air options UNKNOWN, and ground is suggested.
- Uncertainty is shown as ranges and chances, and the forecaster's percentages are checked against what happened.
- Intake text is treated as untrusted, validated field by field, and tested against 30 prompt-injection attacks.
- A person makes every decision; holds and overrides need a written reason and go to a log.
- No secrets in the repo (`.pre-commit-config.yaml` runs gitleaks). All cases are synthetic, with no real patient data.
- Simulated aircraft, simulated pads and modeled road times are labeled in the app and in every receipt.

## Credits

Built by team claude's plan with help from Claude Code, an AI coding assistant (allowed by the event rules). Licensed under MIT; see `LICENSE`.
