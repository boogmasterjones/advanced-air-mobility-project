import { useEffect, useMemo, useState } from "react";
import {
  STRATEGY_LABEL, facilityLabel, getEvidence, getReplay, getReplayRange, niceName, placeName,
  type Facility, type Replay, type ReplayRange,
} from "./api";
import { ForecastStrip, OptionCards, Receipts } from "./parts";

const ZONE = "America/New_York";
type Preset = { label: string; date: string; hour: number; origin: string; dest: string; deadline: number };

/** Florida wall-clock time -> the matching UTC instant (handles daylight saving). */
function floridaToUtc(date: string, hour: number): Date {
  const guess = new Date(`${date}T${String(hour).padStart(2, "0")}:00:00Z`);
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: ZONE, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  }).formatToParts(guess);
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value);
  const shown = Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute"));
  return new Date(guess.getTime() - (shown - guess.getTime()));
}

function floridaParts(iso: string): { date: string; hour: number } {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: ZONE, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit",
  }).formatToParts(new Date(iso));
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return { date: `${get("year")}-${get("month")}-${get("day")}`, hour: Number(get("hour")) };
}

const hourLabel = (h: number) => `${h % 12 === 0 ? 12 : h % 12}:00 ${h < 12 ? "AM" : "PM"}`;

export default function TimeMachine({ facilities, active }: { facilities: Facility[]; active: boolean }) {
  const [range, setRange] = useState<ReplayRange | null>(null);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [date, setDate] = useState("2024-07-15");
  const [hour, setHour] = useState(15);
  const [originId, setOriginId] = useState("61FL"); // Tampa General
  const [destId, setDestId] = useState("7FD7"); // Lakeland Regional
  const [deadline, setDeadline] = useState(120);
  const [replay, setReplay] = useState<Replay | null>(null);
  const [asked, setAsked] = useState(120);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [openFact, setOpenFact] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!active || loaded) return;
    setLoaded(true);
    getReplayRange().then(setRange).catch((e: Error) => setError(e.message));
    // Storm cases picked by the replay evaluation (E2), if it has been run.
    getEvidence().then((ev) => {
      const cases = (ev.details?.E2?.demo_cases ?? []) as
        { when: string; origin: string; dest: string; deadline_min: number; origin_name: string }[];
      setPresets(cases.map((c) => {
        const { date: d, hour: h } = floridaParts(c.when);
        return { label: `${new Date(c.when).toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: ZONE })}, ${hourLabel(h)}: ${niceName(c.origin_name)}`,
                 date: d, hour: h, origin: c.origin, dest: c.dest, deadline: c.deadline_min };
      }));
    }).catch(() => { /* presets are optional */ });
  }, [active, loaded]);

  const span = useMemo(() => (range?.first && range.last
    ? { min: floridaParts(range.first).date, max: floridaParts(range.last).date } : null), [range]);

  async function run(p?: Preset) {
    const q = p ?? { date, hour, origin: originId, dest: destId, deadline };
    if (p) { setDate(p.date); setHour(p.hour); setOriginId(p.origin); setDestId(p.dest); setDeadline(p.deadline); }
    setBusy(true); setError(""); setOpenFact(null);
    try {
      const out = await getReplay({ date: floridaToUtc(q.date, q.hour).toISOString(), origin_id: q.origin,
                                    dest_id: q.dest, deadline_min: q.deadline });
      setReplay(out); setAsked(q.deadline);
    } catch (e) {
      setError((e as Error).message); setReplay(null);
    } finally {
      setBusy(false);
    }
  }

  const then = replay?.then;
  return (
    <main className="single">
      <section className="panel form wide">
        <h2>Time Machine</h2>
        <p className="muted">
          Pick a past moment. The app answers using only the weather known at that moment, then we show what
          really happened. The forecaster never trained on this year.
          {span && <> Dates available: {span.min} to {span.max}.</>}
        </p>
        <div className="form-row">
          <label>Date
            <input type="date" value={date} min={span?.min} max={span?.max} onChange={(e) => setDate(e.target.value)} />
          </label>
          <label>Florida time
            <select value={hour} onChange={(e) => setHour(Number(e.target.value))}>
              {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{hourLabel(h)}</option>)}
            </select>
          </label>
          <label>Must arrive within (min)
            <input type="number" min={1} max={2880} value={deadline}
                   onChange={(e) => setDeadline(Math.max(1, Math.min(2880, Number(e.target.value) || 1)))} />
          </label>
        </div>
        <div className="form-row">
          <label>From
            <select value={originId} onChange={(e) => setOriginId(e.target.value)}>
              {facilities.map((f) => <option key={f.faa_id} value={f.faa_id}>{facilityLabel(f)}</option>)}
            </select>
          </label>
          <label>To
            <select value={destId} onChange={(e) => setDestId(e.target.value)}>
              {facilities.map((f) => <option key={f.faa_id} value={f.faa_id}>{facilityLabel(f)}</option>)}
            </select>
          </label>
        </div>
        <div className="row">
          <button className="primary" onClick={() => run()} disabled={busy || !date || originId === destId}>
            {busy ? "Replaying…" : "Replay this moment"}
          </button>
        </div>
        {presets.length > 0 && (
          <p>
            <span className="muted">Storm cases to try:</span>{" "}
            {presets.map((p) => <button key={p.label} className="chip" onClick={() => run(p)}>{p.label}</button>)}
          </p>
        )}
        {error && <p className="error" role="alert">{error}</p>}
      </section>

      {replay && then && (
        <section className="results" aria-live="polite">
          <div className="then-now">
            <div>
              <h2>What the app said then</h2>
              <p className="muted">
                {new Date(replay.as_of).toLocaleString(undefined, { dateStyle: "full", timeStyle: "short", timeZone: ZONE })} Florida time ·
                {" "}{placeName(then.origin)} to {placeName(then.dest)} · within {asked} min
              </p>
              <p className="headline">Suggested: <strong>{STRATEGY_LABEL[then.recommended]}</strong></p>
              <OptionCards options={then.options} recommended={then.recommended} deadline={asked} onFact={setOpenFact} />
            </div>
            <div>
              <h2>What actually happened</h2>
              {replay.actual_flyable === null ? (
                <p className="notice">The weather record after this moment has gaps, so we cannot score this one.</p>
              ) : (
                <>
                  <p className={replay.actual_flyable ? "outcome good" : "outcome bad"}>
                    <span aria-hidden="true">{replay.actual_flyable ? "✓" : "×"}</span>{" "}
                    {replay.actual_flyable
                      ? "The weather stayed flyable for the whole flight."
                      : "The weather did not stay flyable for the flight."}
                  </p>
                  <p className="headline">
                    Best choice in hindsight: <strong>{replay.actual_best_strategy ? STRATEGY_LABEL[replay.actual_best_strategy] : "unknown"}</strong>
                  </p>
                  <div className="tiles">
                    <div className="tile"><span className="big">{replay.regret_min ?? "–"}</span><span className="muted">minutes lost against the fastest choice</span></div>
                    <div className="tile"><span className="big">{replay.regret_chance != null ? Math.round(replay.regret_chance * 100) : "–"}</span><span className="muted">points of on-time chance lost</span></div>
                  </div>
                  {replay.actual_options && (
                    <OptionCards options={replay.actual_options} recommended={replay.actual_best_strategy}
                                 deadline={asked} suggestedLabel="Best in hindsight" />
                  )}
                </>
              )}
            </div>
          </div>
          <ForecastStrip forecasts={then.forecasts ?? []} />
          <p className="muted">
            The right column reruns the same math with the real weather outcome. Road times are still modeled and
            the aircraft is still simulated, so this scores the weather call, not a real flight.
          </p>
          <Receipts facts={then.facts} selected={openFact} onSelect={setOpenFact} />
        </section>
      )}
    </main>
  );
}
