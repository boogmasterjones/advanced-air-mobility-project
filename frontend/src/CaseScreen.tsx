import { useMemo, useState } from "react";
import {
  STRATEGY_LABEL, evaluateCase, facilityLabel, getBrief, niceName, placeName, readRequest,
  type Brief, type CaseResult, type Facility, type IntakeResult, type Match, type Strategy,
} from "./api";
import MapView from "./MapView";
import { BriefPanel, ForecastStrip, OptionCards, Receipts } from "./parts";

const CATEGORIES = [
  ["stroke", "Stroke"], ["trauma", "Trauma"], ["heart_attack", "Heart attack"],
  ["organ", "Organ"], ["supplies", "Supplies"], ["other", "Other"],
] as const;
const FIELD_NAME: Record<string, string> = {
  origin_name: "where from", dest_name: "where to", deadline_min: "the deadline", category: "the case type",
  people: "how many people",
};
const SAMPLE = "Stroke patient from Lakeside Medical Center to Delray Medical Center within 2 hours.";
const AUDIT_KEY = "car-or-air-audit";

type AuditEntry = { at: string; action: string; option: string; reason: string; trip: string };

function loadAudit(): AuditEntry[] {
  try {
    return JSON.parse(localStorage.getItem(AUDIT_KEY) ?? "[]");
  } catch {
    return [];
  }
}

export default function CaseScreen({ facilities }: { facilities: Facility[] }) {
  const [text, setText] = useState("");
  const [intake, setIntake] = useState<IntakeResult | null>(null);
  const [reading, setReading] = useState(false);
  const [originId, setOriginId] = useState("9FA2"); // Lakeside Medical Center, Belle Glade
  const [destId, setDestId] = useState("48FD"); // Delray Medical Center
  const [deadline, setDeadline] = useState(120);
  const [category, setCategory] = useState("stroke");
  const [result, setResult] = useState<CaseResult | null>(null);
  const [asked, setAsked] = useState(120); // the deadline the shown result was computed for
  const [brief, setBrief] = useState<Brief | null>(null);
  const [briefBusy, setBriefBusy] = useState(false);
  const [briefError, setBriefError] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [openFact, setOpenFact] = useState<string | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>(loadAudit);
  const [reason, setReason] = useState("");
  const [override, setOverride] = useState<Strategy>("ground_only");
  const [decisionError, setDecisionError] = useState("");

  const byId = useMemo(() => Object.fromEntries(facilities.map((f) => [f.faa_id, f])), [facilities]);
  const stale = result !== null &&
    (result.origin.faa_id !== originId || result.dest.faa_id !== destId || asked !== deadline);

  async function read() {
    setReading(true); setError(""); setIntake(null);
    try {
      const out = await readRequest(text);
      setIntake(out);
      // Fill the form with what was found. Nothing runs until the person presses Compare.
      if (out.origin_id) setOriginId(out.origin_id);
      if (out.dest_id) setDestId(out.dest_id);
      if (out.result.deadline_min) setDeadline(out.result.deadline_min);
      if (CATEGORIES.some(([id]) => id === out.result.category)) setCategory(out.result.category);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setReading(false);
    }
  }

  async function run() {
    setBusy(true); setError(""); setBrief(null); setBriefError(""); setOpenFact(null); setDecisionError("");
    try {
      const out = await evaluateCase({ origin_id: originId, dest_id: destId, deadline_min: deadline, category });
      setResult(out); setAsked(deadline); setOverride(out.recommended);
      setBriefBusy(true);
      getBrief(out).then(setBrief).catch((e: Error) => setBriefError(e.message)).finally(() => setBriefBusy(false));
    } catch (e) {
      setError((e as Error).message); setResult(null);
    } finally {
      setBusy(false);
    }
  }

  function decide(action: "Approve" | "Hold" | "Override") {
    if (!result) return;
    if (action !== "Approve" && reason.trim().length < 3) {
      setDecisionError(`Please write a short reason to ${action.toLowerCase()}.`);
      return;
    }
    const entry: AuditEntry = {
      at: new Date().toISOString(), action, reason: reason.trim(),
      option: STRATEGY_LABEL[action === "Override" ? override : result.recommended],
      trip: `${placeName(result.origin)} to ${placeName(result.dest)}, ${asked} min`,
    };
    const next = [entry, ...audit].slice(0, 50);
    setAudit(next); setReason(""); setDecisionError("");
    try { localStorage.setItem(AUDIT_KEY, JSON.stringify(next)); } catch { /* storage may be off */ }
  }

  const check = intake?.result.needs_human_review.map((f) => FIELD_NAME[f] ?? f) ?? [];
  const pick = (which: "origin" | "dest", m: Match) => (which === "origin" ? setOriginId : setDestId)(m.faa_id);

  return (
    <main>
      <section className="panel form">
        <h2>1. Paste the request <span className="muted">(optional)</span></h2>
        <label className="sr-only" htmlFor="request">Transfer request text</label>
        <textarea id="request" rows={4} maxLength={4000} value={text} placeholder={SAMPLE}
                  onChange={(e) => setText(e.target.value)} />
        <div className="row">
          <button onClick={read} disabled={reading || text.trim().length < 5}>{reading ? "Reading…" : "Read request"}</button>
          <button className="link" onClick={() => setText(SAMPLE)}>Use the sample</button>
        </div>
        {intake && (
          <div className="notice" role="status">
            <p><strong>Filled in below. Please check before comparing.</strong></p>
            {check.length > 0 && <p>Not clear from the text: {check.join(", ")}.</p>}
            {(["origin", "dest"] as const).map((which) => {
              const matches = intake[`${which}_matches`];
              const chosen = intake[`${which}_id`];
              const written = intake.result[`${which}_name`];
              if (chosen || !written) return null;
              return (
                <p key={which}>
                  “{written}” could be:{" "}
                  {matches.length === 0 ? "no match in the helipad list. Pick it by hand." : matches.map((m) => (
                    <button key={m.faa_id} className="chip" onClick={() => pick(which, m)}>
                      {niceName(m.name)} ({niceName(m.city)})
                    </button>
                  ))}
                </p>
              );
            })}
            {intake.result.notes && <p className="muted">Note from the text: {intake.result.notes}</p>}
            <p className="muted">Read by: {intake.provider}. Names are matched to helipads by code, not by the AI.</p>
          </div>
        )}

        <h2>2. Check the case</h2>
        <label>From
          <select id="origin" value={originId} onChange={(e) => setOriginId(e.target.value)}>
            {facilities.map((f) => <option key={f.faa_id} value={f.faa_id}>{facilityLabel(f)}</option>)}
          </select>
        </label>
        <label>To
          <select id="dest" value={destId} onChange={(e) => setDestId(e.target.value)}>
            {facilities.map((f) => <option key={f.faa_id} value={f.faa_id}>{facilityLabel(f)}</option>)}
          </select>
        </label>
        <label>Case type
          <select id="category" value={category} onChange={(e) => setCategory(e.target.value)}>
            {CATEGORIES.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </label>
        <label>Must arrive within (minutes, from now)
          <input id="deadline" type="number" min={1} max={2880} value={deadline}
                 onChange={(e) => setDeadline(Math.max(1, Math.min(2880, Number(e.target.value) || 1)))} />
        </label>
        <div className="row" aria-label="Quick deadlines">
          {[60, 90, 120, 180].map((m) => (
            <button key={m} className={deadline === m ? "chip on" : "chip"} onClick={() => setDeadline(m)}>{m} min</button>
          ))}
        </div>
        <button className="primary" onClick={run} disabled={busy || !originId || !destId || originId === destId}>
          {busy ? "Checking weather, roads and battery…" : "Compare options"}
        </button>
        {originId === destId && <p className="error">Pick two different places.</p>}
        {error && <p className="error" role="alert">{error}</p>}
      </section>

      <MapView origin={byId[originId]} dest={byId[destId]} map={stale ? null : result?.map ?? null} />

      {result && (
        <section className={`results ${stale ? "stale" : ""}`} aria-live="polite">
          {stale && <p className="notice">The form changed. Press “Compare options” to update the answer below.</p>}
          <h2>
            Suggested: {STRATEGY_LABEL[result.recommended]}
            <span className="muted"> · {placeName(result.origin)} to {placeName(result.dest)}, within {asked} min</span>
          </h2>
          <OptionCards options={result.options} recommended={result.recommended} deadline={asked} onFact={setOpenFact} />
          <div className="two-col">
            <BriefPanel brief={brief} busy={briefBusy} error={briefError} onFact={setOpenFact} />
            <ForecastStrip forecasts={result.forecasts ?? []} />
          </div>

          <section className="panel decide">
            <h3>Your decision <span className="muted">(the app only advises; {result.decision_owner})</span></h3>
            <label>Reason <span className="muted">(needed to hold or override)</span>
              <input type="text" value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)}
                     placeholder="For example: crew reports the pad is blocked" />
            </label>
            <div className="row">
              <button className="primary" onClick={() => decide("Approve")}>Approve the suggestion</button>
              <button onClick={() => decide("Hold")}>Hold</button>
              <span className="row">
                <button onClick={() => decide("Override")}>Override with</button>
                <select aria-label="Option to use instead" value={override} onChange={(e) => setOverride(e.target.value as Strategy)}>
                  {result.options.map((o) => <option key={o.strategy} value={o.strategy}>{STRATEGY_LABEL[o.strategy]}</option>)}
                </select>
              </span>
            </div>
            {decisionError && <p className="error" role="alert">{decisionError}</p>}
            {audit.length > 0 && (
              <>
                <h4>Decision log <span className="muted">(kept in this browser only)</span></h4>
                <ol className="audit">
                  {audit.map((a) => (
                    <li key={a.at}>
                      <strong>{a.action}</strong>: {a.option} <span className="muted">· {a.trip} · {new Date(a.at).toLocaleString()}</span>
                      {a.reason && <> · “{a.reason}”</>}
                    </li>
                  ))}
                </ol>
              </>
            )}
          </section>

          <Receipts facts={result.facts} selected={openFact} onSelect={setOpenFact} />
        </section>
      )}
    </main>
  );
}
