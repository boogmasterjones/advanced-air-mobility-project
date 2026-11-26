// Building blocks shared by the case screen and the Time Machine.
import { useEffect, useRef } from "react";
import {
  STATUS_LABEL, STRATEGY_LABEL, type Brief, type Fact, type Option, type StationForecast, type Step, type Strategy,
} from "./api";

const pct = (p: number) => `${Math.round(p * 100)}%`;

export function formatValue(f: Fact): string {
  if (f.value === null) return "unknown";
  if (typeof f.value === "boolean") return f.value ? "yes" : "no";
  return `${f.value}${f.unit === "%" ? "%" : f.unit ? ` ${f.unit}` : ""}`;
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit",
  });
}

/** One card per option, on a shared time scale so the three can be compared at a glance. */
export function OptionCards({ options, recommended, deadline, onFact, suggestedLabel = "Suggested" }: {
  options: Option[]; recommended: Strategy | null; deadline: number;
  onFact?: (id: string) => void; suggestedLabel?: string;
}) {
  const scaleMax = Math.max(deadline, ...options.map((o) => o.range_min?.[1] ?? 0)) * 1.08;
  const x = (min: number) => `${Math.min(100, (min / scaleMax) * 100)}%`;
  return (
    <div className="cards">
      {options.map((o) => {
        const picked = o.strategy === recommended;
        return (
          <article key={o.strategy} className={`card ${picked ? "recommended" : ""} status-${o.status}`}>
            <header>
              <h3>{STRATEGY_LABEL[o.strategy]}</h3>
              {picked && <span className="pill">{suggestedLabel}</span>}
            </header>
            {o.status === "OK" && o.p_by_deadline !== null && o.range_min && o.median_min !== null ? (
              <>
                <p className="big">{pct(o.p_by_deadline)}</p>
                <p className="muted">chance to arrive within {deadline} min</p>
                <div className="range" role="img"
                     aria-label={`Typical time ${Math.round(o.median_min)} minutes, likely between ${Math.round(o.range_min[0])} and ${Math.round(o.range_min[1])}. Deadline ${deadline} minutes.`}>
                  <div className="range-track">
                    <div className="range-band" style={{ left: x(o.range_min[0]), width: `calc(${x(o.range_min[1])} - ${x(o.range_min[0])})` }}
                         title={`8 in 10 trips take ${Math.round(o.range_min[0])} to ${Math.round(o.range_min[1])} min`} />
                    <div className="range-median" style={{ left: x(o.median_min) }} title={`Typical: ${Math.round(o.median_min)} min`} />
                    <div className="range-deadline" style={{ left: x(deadline) }} title={`Deadline: ${deadline} min`} />
                  </div>
                  <div className="range-labels">
                    <span>Typical <strong>{Math.round(o.median_min)} min</strong></span>
                    <span>likely {Math.round(o.range_min[0])} to {Math.round(o.range_min[1])} min</span>
                  </div>
                </div>
              </>
            ) : (
              <p className={`status-line s-${o.status}`}>
                <span aria-hidden="true">{o.status === "UNKNOWN" ? "?" : "×"}</span> {STATUS_LABEL[o.status]}
              </p>
            )}
            {o.status === "OK" && o.steps && o.steps.length > 0 && (
              <Steps steps={o.steps} flight={o.strategy !== "ground_only"} />
            )}
            <ul className="reasons">{o.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            {onFact && (
              <p className="receipt-links">
                <span className="muted">Receipts:</span>{" "}
                {o.fact_ids.map((id) => (
                  <button key={id} className="chip" onClick={() => onFact(id)} aria-label={`Open receipt ${id}`}>{id}</button>
                ))}
              </p>
            )}
          </article>
        );
      })}
      <p className="scale-note muted">
        Bars share one time scale. Dark tick: typical time. Band: 8 in 10 simulated trips. Red line: the deadline.
      </p>
    </div>
  );
}

// One fixed color per kind of step, the same on every card (validated for color-blind
// separation; every step is also listed in words with its minutes, so color is never alone).
const STEP_COLOR: Record<Step["kind"], string> = {
  wait: "#2a78d6", hospital: "#eb6834", travel: "#1baf7a", handoff: "#eda100", positioning: "#e87ba4",
};

/** Where the minutes go at typical values: a segmented bar plus the same data as a list. */
function Steps({ steps, flight }: { steps: Step[]; flight: boolean }) {
  const total = steps.reduce((sum, s) => sum + s.minutes, 0);
  return (
    <details className="steps" open>
      <summary>Where the time goes{flight ? " when the flight happens" : ""} (about {Math.round(total)} min)</summary>
      <div className="steps-bar" role="img" aria-label={steps.map((s) => `${s.label}: ${Math.round(s.minutes)} minutes`).join(", ")}>
        {steps.map((s) => (
          <div key={s.label} style={{ flexGrow: Math.max(s.minutes, 0.5), background: STEP_COLOR[s.kind] }}
               title={`${s.label}: ${Math.round(s.minutes)} min`} />
        ))}
      </div>
      <ul className="steps-list">
        {steps.map((s) => (
          <li key={s.label}>
            <i style={{ background: STEP_COLOR[s.kind] }} aria-hidden="true" />
            <span>{s.label}</span>
            <strong>{Math.round(s.minutes)} min</strong>
          </li>
        ))}
      </ul>
    </details>
  );
}

const HOUR_LABEL = ["Next hour", "1 to 2 h", "2 to 3 h", "3 to 4 h"];

/** Chance each airport stays flyable, hour by hour. One measure, one hue, every bar labeled. */
export function ForecastStrip({ forecasts }: { forecasts: StationForecast[] }) {
  if (!forecasts.length) return null;
  return (
    <section className="panel forecast">
      <h3>Weather outlook from the forecaster</h3>
      <p className="muted">
        Chance each airport stays flyable for the whole hour, counted from its newest weather report.
        Model: {forecasts[0].model}.
      </p>
      {forecasts[0].model.startsWith("rule") && (
        <p className="notice">The trained forecaster is not installed on this server, so a simple rule is used:
          90% if the airport is flyable now, otherwise 0%.</p>
      )}
      <div className="forecast-grid">
        {forecasts.map((f) => (
          <figure key={f.station}>
            <figcaption><strong>{f.station}</strong> · airport near {f.role} · report from {formatTime(f.issued_at)}</figcaption>
            <div className="bars" role="img"
                 aria-label={f.points.map((p) => `${HOUR_LABEL[p.hours_ahead]}: ${pct(p.p_flyable)}`).join(", ")}>
              {f.points.map((p) => (
                <div key={p.hours_ahead} className="bar-col" title={`${HOUR_LABEL[p.hours_ahead]}: ${pct(p.p_flyable)} chance it stays flyable`}>
                  <span className="bar-value">{pct(p.p_flyable)}</span>
                  <div className="bar-slot"><div className="bar" style={{ height: `${Math.max(2, p.p_flyable * 100)}%` }} /></div>
                  <span className="bar-label">{HOUR_LABEL[p.hours_ahead]}</span>
                </div>
              ))}
            </div>
          </figure>
        ))}
      </div>
    </section>
  );
}

/** The written brief. Each [F#] is a button that opens that receipt. */
export function BriefPanel({ brief, busy, error, onFact }: {
  brief: Brief | null; busy: boolean; error: string; onFact: (id: string) => void;
}) {
  return (
    <section className="panel brief">
      <h3>Brief</h3>
      {busy && <p className="muted">Writing the brief…</p>}
      {error && <p className="error">The brief could not be written: {error}</p>}
      {brief && (
        <>
          {brief.sentences.map((s, i) => (
            <p key={i}>
              {s.split(/(\[F\d+\])/).map((part, j) => {
                const m = /^\[(F\d+)\]$/.exec(part);
                return m
                  ? <button key={j} className="chip" onClick={() => onFact(m[1])} aria-label={`Open receipt ${m[1]}`}>{m[1]}</button>
                  : <span key={j}>{part}</span>;
              })}
            </p>
          ))}
          <p className="muted">
            Written by: {brief.provider}. A code check compared every number with its receipt:
            {" "}{brief.sentences.length} sentence{brief.sentences.length === 1 ? "" : "s"} kept,
            {" "}{brief.removed.length} removed.
          </p>
          {brief.removed.length > 0 && (
            <details>
              <summary>Sentences the check removed ({brief.removed.length})</summary>
              <ul>{brief.removed.map((r, i) => <li key={i}><s>{r.sentence}</s> <em>({r.reason})</em></li>)}</ul>
            </details>
          )}
        </>
      )}
    </section>
  );
}

/** Every fact behind the answer, with its source, time and how sure it is. */
export function Receipts({ facts, selected, onSelect }: {
  facts: Fact[]; selected: string | null; onSelect: (id: string | null) => void;
}) {
  const rowRef = useRef<HTMLTableRowElement>(null);
  useEffect(() => {
    rowRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [selected]);
  return (
    <section className="panel receipts">
      <h3>Receipts <span className="muted">({facts.length} facts behind this answer)</span></h3>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Id</th><th>Fact</th><th>Value</th><th>Source</th><th>How sure</th><th>As of</th></tr></thead>
          <tbody>
            {facts.map((f) => (
              <tr key={f.id} ref={f.id === selected ? rowRef : undefined}
                  className={f.id === selected ? "selected" : ""} onClick={() => onSelect(f.id === selected ? null : f.id)}>
                <td><span className="chip static">{f.id}</span></td>
                <td>{f.label}</td>
                <td className="num">{formatValue(f)}</td>
                <td>{f.source}</td>
                <td><span className={`tag tag-${f.confidence}`}>{f.confidence}</span></td>
                <td className="muted">{formatTime(f.fetched_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted">
        official: from a primary source · reported: from a study or a router · estimate: unofficial analysis ·
        assumption: ours, change it in the settings file · simulated: made up for the demo · computed: math on the facts above
      </p>
    </section>
  );
}
