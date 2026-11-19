# Jaden: start here

**How to use this file:** open a Claude Code session on the repo `boogmasterjones/advanced-air-mobility-project` and paste the whole block below as your first message. Everything your Claude needs is in the repo; this tells it what to read and what you own.

---

```
I'm Jaden, Person B on a 2-person hackathon team ("claude's plan"). My teammate is
boogmasterjones (Person A). We're building "Car or Air" for the Florida Tech Showcase AI
Hackathon (theme: "Cleared for Takeoff: AI for Florida's Skies"). Submission is due
Wed Dec 2 at 4:00 PM (public GitHub repo + 3–5 min narrated demo video); live judging Dec 3.

Before doing anything, read these files in this order and summarize them back to me in a
few bullets, so I know you've got it:
  1. CLAUDE.md            (team rules, folder ownership, git workflow: follow it exactly)
  2. docs/TASKS.md        (the build plan; my tasks are B0–B8)
  3. backend/app/contracts.py  (the API handshake between my side and Person A's side)
  4. PLAN.md              (overall plan, demo script, rubric)
  5. RESEARCH.md          (sourced facts; skim, use when we need a fact)

My role: the AI (LLM) features and the app the judges click on.
I OWN: frontend/, backend/app/llm/, backend/app/api/ai.py, eval/datasets/, backend/eval_llm/.
I DO NOT EDIT: backend/app/core/, backend/app/api/cases.py, data/, scripts/,
backend/data_build/, backend/models/ (Person A owns those). Shared files
(contracts.py, main.py, README.md, PLAN.md, docs/, Dockerfile, .github/) only change in
a small PR that my teammate has seen.

Rules that matter most:
- Start every session with: git checkout main && git pull
- One branch per task (e.g. b1-intake-llm), then a pull request into main. Never commit
  straight to main. Backend tests (cd backend && python -m pytest -q) and the frontend
  build (cd frontend && npm run build) must pass before pushing.
- Commit as me: run git config user.name "<my GitHub username>" and
  git config user.email "<my GitHub no-reply email from GitHub → Settings → Emails>"
  in the repo before the first commit. I'll give you both values.
- Do NOT add "Co-Authored-By: Claude" or "Claude-Session:" lines to commits or PRs. The
  team wants only the two of us in the git history.
- No secrets in the repo (API keys go in .env locally, Secret Manager in Google Cloud).
- No real personal data. All patient cases are synthetic.
- The LLM never calculates and never decides. It extracts fields and writes text from
  facts it is given. All numbers come from code. A human approves every decision.
- Missing or stale data shows UNKNOWN. Everything simulated is labeled. Keep the
  prototype banner on every screen.
- For endpoints Person A hasn't built yet (they return HTTP 501), build against the mock
  files in frontend/src/mocks/ and switch to the real endpoint later.

Start with task B0 from docs/TASKS.md: get the backend and frontend running locally, run
python3 scripts/check_data_access.py, and tell me what works. Then we'll do B1.
```

---

## What you're building, in plain words

A hospital coordinator has an urgent trip: a stroke patient from a small rural hospital to a big trauma center, or an organ that must arrive within a few hours. Our app compares three choices: **ground ambulance**, **air taxi**, or **both at once** (the ambulance leaves now, and the air taxi goes too if the weather allows). For each it shows the chance of arriving before the deadline and why.

Your part makes it feel smart and trustworthy:

- **Intake:** paste a messy request and the AI fills in the form. You also prove it works (E3) and can't be tricked (E4).
- **Brief:** the AI writes a short summary, and code deletes any sentence whose numbers aren't backed by a source (E5).
- **The screens:** the case screen, the Time Machine (replaying a real past storm day), and the Evidence tab with our accuracy numbers.

Your teammate builds the engine underneath: the weather forecaster, road and flight times, battery checks, and the Time Machine data.

## Checklist for your first day

- [ ] Accept the GitHub collaborator invite for `advanced-air-mobility-project`
- [ ] Connect your GitHub to Claude at https://claude.ai/connect-github
- [ ] Find your GitHub no-reply email (GitHub → Settings → Emails, under "Keep my email addresses private")
- [ ] Confirm you're **registered** for the hackathon (closes Nov 30)
- [ ] Paste the block above into a new Claude Code session on the repo
