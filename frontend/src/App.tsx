import { useEffect, useMemo, useState } from "react";
import { evaluateCase, getFacilities, type CaseResult, type Facility, type Option } from "./api";
import MapView from "./MapView";

const STRATEGY_LABEL: Record<Option["strategy"], string> = {
  ground_only: "Ground ambulance only",
  air_only: "Air taxi only (simulated)",
  air_and_ground: "Air taxi + ground backup in parallel",
};

const HOSPITAL_WORDS = /HOSP|MED|HEALTH|MEML|RGNL|CLINIC|TRAUMA|SHANDS|BAPTIST|ADVENT/i;

export default function App() {
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [originId, setOriginId] = useState("9FA2"); // Lakeside Medical Center, Belle Glade
  const [destId, setDestId] = useState("48FD"); // Delray Medical Center
  const [deadline, setDeadline] = useState(90);
  const [category, setCategory] = useState("stroke");
  const [result, setResult] = useState<CaseResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [decision, setDecision] = useState<string>("");
  const [openFact, setOpenFact] = useState<string | null>(null);

  useEffect(() => {
    getFacilities()
      .then((all) => setFacilities(all.filter((f) => HOSPITAL_WORDS.test(f.name))))
      .catch((e) => setError(e.message));
  }, []);

  const byId = useMemo(() => Object.fromEntries(facilities.map((f) => [f.faa_id, f])), [facilities]);

  async function run() {
    setBusy(true); setError(""); setDecision("");
    try {
      setResult(await evaluateCase({ origin_id: originId, dest_id: destId, deadline_min: deadline, category }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const facts = Object.fromEntries((result?.facts ?? []).map((f) => [f.id, f]));

  return (
    <div className="app">
      <div className="banner" role="note">
        PROTOTYPE. Not for real dispatch. Aircraft are simulated. Road times are modeled.
      </div>
      <header><h1>Car or Air</h1><p>Should this urgent hospital trip go by road or by air, and how sure are we?</p></header>

      <main>
        <section className="panel form">
          <label>From
            <select id="origin" value={originId} onChange={(e) => setOriginId(e.target.value)}>
              {facilities.map((f) => <option key={f.faa_id} value={f.faa_id}>{f.name} ({f.city})</option>)}
            </select>
          </label>
          <label>To
            <select id="dest" value={destId} onChange={(e) => setDestId(e.target.value)}>
              {facilities.map((f) => <option key={f.faa_id} value={f.faa_id}>{f.name} ({f.city})</option>)}
            </select>
          </label>
          <label>Case
            <select id="category" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="stroke">Stroke</option><option value="trauma">Trauma</option>
              <option value="heart_attack">Heart attack</option><option value="organ">Organ</option>
              <option value="supplies">Supplies</option>
            </select>
          </label>
          <label>Deadline (minutes)
            <input id="deadline" type="number" min={1} value={deadline} onChange={(e) => setDeadline(Number(e.target.value))} />
          </label>
          <button onClick={run} disabled={busy || !originId || !destId}>{busy ? "Checking…" : "Compare options"}</button>
          {error && <p className="error">{error}</p>}
        </section>

        <MapView origin={byId[originId]} dest={byId[destId]} />

        {result && (
          <section className="results">
            <div className="cards">
              {result.options.map((o) => (
                <article key={o.strategy} className={`card ${o.strategy === result.recommended ? "recommended" : ""}`}>
                  <h3>{STRATEGY_LABEL[o.strategy]}</h3>
                  {o.strategy === result.recommended && <span className="pill">Suggested</span>}
                  <p className={`status s-${o.status}`}>{o.status === "OK" ? "Data OK" : o.status.replace("_", " ")}</p>
                  {o.p_by_deadline !== null && (
                    <>
                      <p className="big">{Math.round(o.p_by_deadline * 100)}%</p>
                      <p className="muted">chance to arrive within {deadline} min</p>
                      {o.range_min && <p>Typical: {o.range_min[0]}–{o.range_min[1]} min (median {o.median_min})</p>}
                    </>
                  )}
                  <ul>{o.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
                  <p className="muted">Sources: {o.fact_ids.map((id) => (
                    <button key={id} className="link" onClick={() => setOpenFact(id)}>[{id}]</button>
                  ))}</p>
                </article>
              ))}
            </div>

            {openFact && facts[openFact] && (
              <aside className="panel receipt">
                <strong>Receipt {openFact}</strong>
                <p>{facts[openFact].label}: {String(facts[openFact].value)} {facts[openFact].unit}</p>
                <p className="muted">Source: {facts[openFact].source} · {facts[openFact].confidence} · as of {new Date(facts[openFact].fetched_at).toLocaleString()}</p>
                <button className="link" onClick={() => setOpenFact(null)}>Close</button>
              </aside>
            )}

            <div className="panel decide">
              <strong>Your decision</strong> (the app only advises)
              <div className="row">
                {["Approve", "Hold", "Override"].map((d) => (
                  <button key={d} onClick={() => setDecision(`${d} at ${new Date().toLocaleTimeString()}`)}>{d}</button>
                ))}
              </div>
              {decision && <p className="muted">Logged: {decision}</p>}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
