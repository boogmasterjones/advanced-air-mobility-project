# Build plan and task board

Today is **Thu Nov 19**. Submission is **Wed Dec 2, 4:00 PM**. Live judging is **Thu Dec 3**.

- **Person A: boogmasterjones** owns data, ML and the decision engine (Python, `backend/app/core/`).
- **Person B: Jaden** owns the AI (LLM) features and the app the judges click on (`frontend/`, `backend/app/llm/`).

Folder ownership and git rules are in `CLAUDE.md`. In short: each task gets its own branch and pull request, and **you never edit the other person's folders**. You meet in the middle through `backend/app/contracts.py`. Until the other side is built, B uses the mocks in `frontend/src/mocks/`.

## How the pieces fit

```
  Jaden (B)                                     boogmasterjones (A)
  ─────────                                     ──────────────────
  Intake screen ── POST /api/intake ──► LLM ─┐
                                             │ fills the case form
  Case screen ──── POST /api/cases/evaluate ─┼──► decision engine ◄── forecaster (A3)
       │                                     │         ▲             ◄── road times (A4)
       └──► POST /api/brief ─► LLM + verifier│         │             ◄── energy check (A5)
  Time Machine ─── GET /api/replay ──────────┼──► replay + regret (A6)
  Evidence tab ─── GET /api/evidence ◄───────┴──── eval/results/*.json (A and B write)
```

## Milestones (everyone aims for these)

| Date | Gate | What must work |
|---|---|---|
| **Sun Nov 22** | **Gate 1** | App live on a public Cloud Run URL. Intake screen fills the case form from pasted text. Forecaster training data downloaded. |
| **Sat Nov 28** | **Gate 2** | Forecaster drives the air chance (E1 number exists). Brief with verifier on screen. Time Machine replays a real storm day. Intake and injection evals run (E3, E4). |
| **Mon Nov 30** | **Feature freeze** (evening) | After this, only bug fixes, docs and demo prep. **Registration closes Nov 30.** |
| **Tue Dec 1** | Record | Final evals, README tested on a clean machine, demo video recorded. |
| **Wed Dec 2** | **Submit by noon** | Hard deadline 4:00 PM. |

Thanksgiving is **Thu Nov 26**. Plan for lighter days around it.

---

## Person A: boogmasterjones (data, ML, engine)

| ID | Task | Due | Depends on | Done when |
|---|---|---|---|---|
| **A0** | **Deploy to Cloud Run.** Create the GCP project, run `gcloud run deploy` from the README, share the public URL with Jaden. | Fri Nov 20 | none | URL loads the app on a phone |
| **A1** | **Weather history download.** Script in `backend/data_build/` that pulls hourly airport weather from the Iowa Environmental Mesonet for about 8 stations (KTPA, KMCO, KLAL, KSRQ, KMIA, KFLL, KLNA, KJAX), Jun to Sep, 2019 to 2024, plus their official forecasts (TAF). Raw data is gitignored; commit only the script and a tiny sample. | Sat Nov 21 | none | Re-runnable script; row counts printed |
| **A2** | **Labels and baselines.** For each hour, label "flyable at +0, +1, +2, +3 h" using `weather.THRESHOLDS`. Build three baselines: persistence, hourly climatology, and a TAF-based rule. | Sun Nov 22 | A1 | Baseline scores for 2024 in `eval/results/e1_baselines.json` |
| **A3** | **Forecaster.** LightGBM on observation features (current values, 6-hour trends, hour, month, station). Train 2019 to 2023, test 2024. Calibrate. Write E1 (Brier skill score, reliability, false alarms) to `eval/results/e1.json`. Implement `GET /api/forecast` per the contract and use it for `p_air` in `/api/cases/evaluate`, replacing the 0.9 placeholder. | Wed Nov 25 | A2 | E1 written; app uses the model; tests pass |
| **A4** | **Better road times.** Cache OSRM routes for the demo pairs in `data/routes.json` and use them in the decision engine instead of straight-line distance x 1.3. Add the E6 sanity check (helicopter break-even distance vs the Swiss study's ~32 miles) to `eval/results/e6.json`. | Mon Nov 23 | none | Demo pairs use routed times; E6 written |
| **A5** | **Energy check.** In `core/energy.py`: hover plus cruise energy, the 20-minute reserve, and heat and wind adjustment. It gives P(energy OK), which feeds `P(air flies)`. Every parameter tagged in `data/aircraft_profiles.json`. | Tue Nov 24 | none | Long trip on a hot, windy day lowers the air chance; test covers it |
| **A6** | **Time Machine backend.** `GET /api/replay` per the contract. Rebuild the case with *only* data available at `as_of` (past weather from A1, forecaster from A3), then compare with what actually happened. Compute regret. Run 50+ synthetic cases on real past days and write E2 to `eval/results/e2.json`. Pick 3 good storm days for the demo. | Fri Nov 27 | A3 | Endpoint returns real replays; E2 written; 3 demo days listed in `docs/demo_days.md` |
| **A7** | **Trauma centers list.** Hand-build `data/seeds/trauma_centers.csv` (36 centers: name, level, city, FAA helipad id if it has one, lat, lon, source URL) from the Florida Department of Health trauma page. Add a `trauma_level` field to `/api/facilities` (optional field, so no contract break). | Sun Nov 22 | none | CSV has 36 rows with sources |
| **A8** | *Stretch, only after Gate 2:* "Always an Out", the nearest airports and helipads within remaining energy reach along the route. | | A5 | |

## Person B: Jaden (AI and app)

| ID | Task | Due | Depends on | Done when |
|---|---|---|---|---|
| **B0** | **Setup.** Clone, run backend and frontend locally (README), and run `python3 scripts/check_data_access.py`. Ask the organizers (Discord office hours or ai-hackathon@floridapoly.edu) whether GCP credits cover Vertex AI (Gemini). Pick the LLM provider with your teammate. | Fri Nov 20 | none | App runs locally; provider decided |
| **B1** | **Real LLM intake.** Finish the provider in `backend/app/llm/provider.py` (Anthropic is drafted; add Vertex/Gemini if chosen). Build an **Intake screen**: paste a request, the LLM fills the fields, the human reviews and confirms, and the case form is filled in. Matching facility names to FAA ids happens in code, not in the LLM (fuzzy match against `/api/facilities`). | Sun Nov 22 | B0 | Paste-to-confirmed-case works on the deployed URL |
| **B2** | **Intake eval (E3).** 100 synthetic request texts with correct answers in `eval/datasets/intake_cases.json`: varied wording, typos, missing fields, Spanish and English mixes. Script `backend/eval_llm/intake_eval.py` scores field-level accuracy for the LLM vs the regex baseline and writes `eval/results/e3.json`. | Tue Nov 24 | B1 | E3 written |
| **B3** | **Prompt-injection suite (E4).** Grow `eval/datasets/injection_cases.json` to 30 cases: hidden instructions, fake system messages, instructions in facility names, requests to reveal the prompt, attempts to set impossible deadlines. Pass means the output still validates and no field was changed by the attack. Write `eval/results/e4.json`. | Wed Nov 25 | B1 | E4 written; failures fixed or documented |
| **B4** | **Case brief and verifier (E5).** `POST /api/brief`: the LLM writes 3 to 6 sentences using **only** `case.facts`, citing `[F#]`; then run `core/verifier.py` (already built) and return kept and removed sentences. Show the brief on the case screen; clicking `[F#]` opens the receipt. Log the pass rate over the demo cases to `eval/results/e5.json`. | Fri Nov 27 | B1 | Brief on screen; E5 written |
| **B5** | **Time Machine screen.** Date and time picker plus a case. Show "what we said then" next to "what actually happened" and the regret. Build it on `frontend/src/mocks/replay.json` now, then switch to the real `/api/replay` when A6 lands. | Sat Nov 28 | mock now, A6 later | Works with real data on 3 demo days |
| **B6** | **Evidence tab.** `GET /api/evidence` reads `eval/results/*.json` and returns the contract shape; a tab shows E1 to E6 with baselines and plain-language notes. Use `mocks/evidence.json` until results exist. Never show mock numbers as real. | Sat Nov 28 | results files | Tab shows real numbers |
| **B7** | **Polish.** Approve / Hold / Override with a required reason, kept in an audit log list on screen. Plain-language labels, phone layout, keyboard focus, an "UNKNOWN" state that is clear, and a frozen-data demo mode (cached responses, clearly labeled) in case the venue Wi-Fi fails. | Mon Nov 30 | none | Usable on a phone; demo mode works offline |
| **B8** | *Stretch, only after Gate 2:* Police mode (patrol car, drone, air taxi) UI. Needs a matching engine task from A, so agree first. | | | |

## Shared tasks (both)

| ID | Task | Due |
|---|---|---|
| **S1** | Confirm both of you are **registered** (closes Nov 30). | Fri Nov 20 |
| **S2** | 15-minute check-in every other day: what merged, what's blocked, any contract change. | ongoing |
| **S3** | Pitch deck (6 slides max) and a **Future Work** answer (mandatory judge question): statewide pad planner, real FDOT traffic data, police mode, certified aircraft, Cloud Run scaling. | Mon Nov 30 |
| **S4** | README final pass, tested by following it on a clean machine. | Tue Dec 1 |
| **S5** | **Demo video**, 3 to 5 min, narrated, with a live walkthrough (script in `PLAN.md` section 13). | Tue Dec 1 |
| **S6** | Submit (public repo, video link, public URL). | **Wed Dec 2, by noon** |
| **S7** | Rehearse the live demo 3 times; keep the video offline as backup. | Dec 2 to 3 |

## If you fall behind (cut in this order)

1. Stretch tasks (A8, B8)
2. Evidence tab becomes a README table (B6)
3. Time Machine replays 3 fixed days instead of any date (A6, B5)
4. Energy check becomes a simple range calculation (A5)
5. Injection suite down to 15 cases (B3)

**Never cut:** forecaster plus E1 (A3), intake (B1), brief and verifier (B4), the case screen, the video.

## Where the two of you could collide, and the rule for each

| Risk | Rule |
|---|---|
| Both need a new API field | Add it as optional in `contracts.py` in its own tiny PR; tell the other person |
| Both editing `main.py` | Don't. Routes go in `api/cases.py` (A) or `api/ai.py` (B) |
| Both editing `README.md` or `PLAN.md` | Only during S4; otherwise small separate PRs |
| `package-lock.json` conflicts | Only B adds frontend packages |
| `requirements.txt` conflicts | Add your line in its own small PR; rebase if it conflicts |
| Eval result files | Each `eval/results/eN.json` has exactly one writer (see tasks) |
