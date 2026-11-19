# Car or Air

**Team: claude's plan** · Florida Tech Showcase AI Hackathon 2026 · Theme: *Cleared for Takeoff: AI for Florida's Skies*

> **PROTOTYPE. Not for real dispatch.** Aircraft are simulated, road times are modeled, and every recommendation is advisory. A human makes the final decision.

Car or Air helps a hospital transfer coordinator decide whether an urgent trip (a stroke or trauma patient, an organ, or supplies) should go by **ground ambulance, air taxi, or both in parallel**. It shows the chance of making the medical deadline, how sure it is, and a receipt (source and timestamp) for every fact it uses.

## Why it matters

Florida is the U.S. lightning capital, and air taxis are starting test flights here (Tampa, Orlando and the Space Coast, Oct 2026). An air taxi only helps a hospital if it can actually fly when the clock is running. See `RESEARCH.md` for the sourced background.

## What the AI does

| Part | Type | Status |
|---|---|---|
| Flyable-window forecaster (next 0 to 3 h) | ML (gradient boosting) on historical Florida airport weather | In progress. v0 uses a rule on live weather. |
| Request intake (free text to structured case) | LLM with schema validation; human confirms | Offline regex baseline works. LLM provider wired, needs a key. |
| Case brief | LLM, cited facts only, then a code verifier removes unsupported sentences | Verifier done. Brief generation next. |
| Comparing options and probabilities | **Plain code** (Monte Carlo). The LLM never calculates. | v0 done |

## Repository layout

```
backend/    FastAPI app: app/api (routes), app/contracts.py (API shapes), app/core (weather, decision, ledger, verifier), app/llm, tests
frontend/   React + TypeScript + Vite + MapLibre
data/       seeds/fl_heliports.csv (FAA, Oct 29 2026 cycle), seeds/stations.csv, aircraft_profiles.json
eval/       evaluation datasets (prompt-injection cases so far)
scripts/    check_data_access.py: tests every data source from your machine
docs/       TASKS.md (task board and dates), JADEN_START_HERE.md (teammate onboarding)
CLAUDE.md   team rules for humans and Claude sessions
PLAN.md     build plan and calendar     RESEARCH.md   sourced research notes
```

## Run locally

Requirements: Python 3.11+ (3.13 tested), Node 20+ (22 tested).

```bash
# 1. Backend (terminal 1)
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q                 # all tests should pass
uvicorn app.main:app --reload --port 8000

# 2. Frontend (terminal 2)
cd frontend
npm ci
npm run dev                         # open http://localhost:5173
```

To serve everything from one process (like production): `cd frontend && npm run build`, then run uvicorn. It serves the built site at `/`.

**Environment variables** (copy `.env.example` to `.env`; never commit it):

| Variable | Meaning |
|---|---|
| `LLM_PROVIDER` | `offline` (default, no network) or `anthropic` |
| `ANTHROPIC_API_KEY` | Needed only for `anthropic` |
| `INTAKE_MODEL` | Model id for intake |

## Deploy to Google Cloud Run

```bash
gcloud config set project YOUR_PROJECT_ID
gcloud run deploy car-or-air --source . --region us-east1 --allow-unauthenticated
# Optional LLM key from Secret Manager:
# gcloud secrets create anthropic-api-key --data-file=-   (paste key, then Ctrl-D)
# gcloud run services update car-or-air --region us-east1 \
#   --set-secrets ANTHROPIC_API_KEY=anthropic-api-key:latest --set-env-vars LLM_PROVIDER=anthropic
```

On demo days, keep one instance warm: `gcloud run services update car-or-air --region us-east1 --min-instances 1`.

## Data sources

Live airport weather from the [Aviation Weather Center API](https://aviationweather.gov/data/api/); Florida heliports and airports from the [FAA 28-day data](https://www.faa.gov/air_traffic/flight_info/aeronav/aero_data/NASR_Subscription/); aircraft figures from manufacturer pages, each tagged official, reported, estimate or assumption in `data/aircraft_profiles.json`. Full list in `RESEARCH.md`.

## Responsible AI

- Facts carry a source and timestamp (receipts), and a verifier checks the LLM's numbers.
- All calculations are in code.
- Missing or stale weather marks air as UNKNOWN, and ground is suggested.
- Uncertainty is shown as ranges and chances.
- Intake text is treated as untrusted, validated, and tested against prompt injection (`eval/datasets/injection_cases.json`).
- No secrets in the repo (`.pre-commit-config.yaml` runs gitleaks). All cases are synthetic, with no real patient data.
- Simulated aircraft and modeled road times are labeled in the app.

## Credits

Built by team claude's plan with help from Claude Code, an AI coding assistant (allowed by the event rules). Licensed under MIT; see `LICENSE`.
