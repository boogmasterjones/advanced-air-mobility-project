# Instructions for Claude sessions on this repo

Every Claude session working here reads this file first. Humans should read it too.

## The project in one paragraph

**Car or Air** is a hackathon entry (Florida Tech Showcase AI Hackathon; theme "Cleared for Takeoff: AI for Florida's Skies"). It helps a hospital transfer coordinator decide whether an urgent trip (a patient, an organ, or supplies) should go by ground ambulance, air taxi, or both in parallel. It shows the chance of making the medical deadline, the uncertainty, and a "receipt" (source and timestamp) for every fact. AI does real jobs: an ML weather forecaster, an LLM that turns free-text requests into structured cases, and an LLM brief whose numbers a code verifier checks. All math is plain code, and a human makes every decision.

**Deadline: Wed Dec 2, 4:00 PM** (demo video and public GitHub repo). Live judging Thu Dec 3. Late is not accepted.

Read `PLAN.md` (the build plan), `docs/TASKS.md` (who does what), and `RESEARCH.md` (sourced facts) before big changes.

## Team and ownership (do not edit the other person's files)

| Person | Role | Owns |
|---|---|---|
| **A: boogmasterjones** | Data, ML, decision engine | `backend/app/core/`, `backend/app/api/cases.py`, `backend/data_build/`, `backend/models/`, `data/`, `scripts/`, `eval/results/` |
| **B: Jaden** | AI (LLM) and app (frontend) | `frontend/`, `backend/app/llm/`, `backend/app/api/ai.py`, `eval/datasets/`, `backend/eval_llm/` |
| **Shared, change only with a PR the other has seen** | | `backend/app/contracts.py`, `backend/app/main.py`, `README.md`, `PLAN.md`, `docs/`, `Dockerfile`, `.github/` |

If a task needs a change in the other person's area, open an issue or ask them. Do not edit their files yourself.

## Git workflow (required)

1. Start every session with `git checkout main && git pull`.
2. Work on a branch named after the task: `a3-forecaster`, `b1-intake-llm`, and so on. Never commit straight to `main`.
3. Before pushing: `cd backend && python -m pytest -q` and `cd frontend && npm run build` must both pass. CI runs both on every PR.
4. Open a pull request into `main` with a short description of what changed and how it was tested. Keep PRs small, ideally one task each, and merge at least daily.
5. Each person merges their own PR once CI is green and it touches only their own files. PRs that touch shared files wait for the other person to look.
6. **Commit identity:** commit under your own GitHub name and no-reply email (GitHub → Settings → Emails). Set it with `git config user.name` and `git config user.email` in the repo.
7. **No Claude attribution lines.** Do not add "Co-Authored-By: Claude" or "Claude-Session:" lines to commit messages or PR descriptions. The team wants only the two humans in the history. The README already credits the use of an AI coding assistant, which the rules allow.

## Hard rules (the hackathon judges check these)

- **No secrets in the repo.** Keys go in `.env` (gitignored) locally and in Google Cloud Secret Manager when deployed. `.pre-commit-config.yaml` runs gitleaks.
- **No real personal or sensitive data.** Every patient case is synthetic.
- **The LLM never calculates and never decides.** It extracts fields and writes text from facts it is given. All numbers come from code in `backend/app/core/`.
- **Missing or stale data is UNKNOWN, never a guess.** Ground is the safe default.
- **Label everything simulated or assumed.** Aircraft are simulated; road times are modeled. The prototype banner stays on every screen.
- **Facts need sources.** New facts go through the ledger (`backend/app/core/ledger.py`) with a source, timestamp and confidence tag. New claims in docs go in `RESEARCH.md` with a link.
- **Our own code only.** No copying an existing project (that disqualifies us).
- **Must run on Google Cloud** (Cloud Run) with a public URL. Keep `Dockerfile` working.

## How to run

```bash
cd backend && pip install -r requirements.txt && python -m pytest -q && uvicorn app.main:app --reload --port 8000
cd frontend && npm ci && npm run dev      # http://localhost:5173 (proxies /api to port 8000)
```

## API contracts

`backend/app/contracts.py` defines every endpoint's request and response. Endpoints not built yet return HTTP 501, and the frontend uses matching files in `frontend/src/mocks/` until they are. Adding an optional field is fine; renaming or removing a field needs both people to agree.

## Style

Python: type hints, small functions, tests in `backend/tests/` for anything with logic. TypeScript: strict mode, no `any` without a reason. UI text in plain language with no aviation jargon (say "cloud ceiling", not "BKN012").
