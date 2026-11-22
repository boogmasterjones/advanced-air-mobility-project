import { useEffect, useState } from "react";
import { getEvidence, type EvalMetric, type Evidence } from "./api";

type Band = { band: string; n: number; mean_predicted: number; observed_flyable: number };
type Versus = Record<string, { brier: number; skill: number | null }>;
type Horizon = {
  flyable_rate: number;
  test: { n: number; brier: number; vs: Versus };
  test_stations_with_taf: { n: number; brier: number; vs: Versus };
  reliability: Band[];
};

const SERIES = "#2a78d6";
const pct = (v: number) => `${Math.round(v * 100)}%`;
const skill = (v: number | null | undefined) => (v == null ? "–" : `${v > 0 ? "+" : ""}${Math.round(v * 100)}%`);

function show(v: EvalMetric["value"]): string {
  if (v === null || v === undefined) return "not run yet";
  return typeof v === "number" ? String(Math.round(v * 1000) / 1000) : v;
}

/** When the forecaster says 70%, does it happen about 70% of the time? Dots on the line mean yes. */
function ReliabilityChart({ bands }: { bands: Band[] }) {
  const size = 300, pad = 40, inner = size - pad - 12;
  const x = (v: number) => pad + v * inner;
  const y = (v: number) => 12 + (1 - v) * inner;
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="chart" role="img"
         aria-label="Calibration chart: predicted chance against how often the hour was really flyable">
      {ticks.map((t) => (
        <g key={t}>
          <line x1={x(0)} x2={x(1)} y1={y(t)} y2={y(t)} stroke="#e1e0d9" strokeWidth={1} />
          <text x={x(0) - 6} y={y(t) + 4} textAnchor="end" className="axis">{pct(t)}</text>
          <text x={x(t)} y={y(0) + 16} textAnchor="middle" className="axis">{pct(t)}</text>
        </g>
      ))}
      <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke="#898781" strokeWidth={1.5} strokeDasharray="4 4" />
      <text x={x(0.5) + 6} y={y(0.5) + 14} className="axis" transform={`rotate(-45 ${x(0.5) + 6} ${y(0.5) + 14})`}>perfect</text>
      <polyline fill="none" stroke={SERIES} strokeWidth={2}
                points={bands.map((b) => `${x(b.mean_predicted)},${y(b.observed_flyable)}`).join(" ")} />
      {bands.map((b) => (
        <g key={b.band}>
          <circle cx={x(b.mean_predicted)} cy={y(b.observed_flyable)} r={5} fill={SERIES} stroke="#fcfcfb" strokeWidth={2} />
          <circle cx={x(b.mean_predicted)} cy={y(b.observed_flyable)} r={12} fill="transparent">
            <title>{`Forecast near ${pct(b.mean_predicted)}: really flyable ${pct(b.observed_flyable)} of the time (${b.n.toLocaleString()} hours)`}</title>
          </circle>
        </g>
      ))}
      <text x={x(0.5)} y={size - 2} textAnchor="middle" className="axis">chance the forecaster gave</text>
      <text x={10} y={y(0.5)} textAnchor="middle" className="axis" transform={`rotate(-90 10 ${y(0.5)})`}>how often it was flyable</text>
    </svg>
  );
}

function ForecasterDetail({ e1 }: { e1: { horizons: Record<string, Horizon>; test_year: number; train_years: number[]; stations: string[] } }) {
  const [h, setH] = useState("1");
  const hz = e1.horizons[h];
  if (!hz) return null;
  return (
    <section className="panel">
      <h3>The weather forecaster, in detail (E1)</h3>
      <p className="muted">
        Trained on {e1.train_years[0]} to {e1.train_years[e1.train_years.length - 1]}, tested once on {e1.test_year},
        a year it never saw, at {e1.stations.length} Florida airports. Skill is the share of a baseline's error
        that the forecaster removes: above 0% beats the baseline.
      </p>
      <div className="table-wrap">
        <table>
          <thead><tr>
            <th>Hours ahead</th><th>Hours tested</th><th>Really flyable</th>
            <th>vs “no change”</th><th>vs typical for that hour</th><th>vs official airport forecast</th>
          </tr></thead>
          <tbody>
            {Object.entries(e1.horizons).map(([k, v]) => (
              <tr key={k} className={k === h ? "selected" : ""} onClick={() => setH(k)}>
                <td>{k === "0" ? "next hour" : `${k} to ${Number(k) + 1} h`}</td>
                <td className="num">{v.test.n.toLocaleString()}</td>
                <td className="num">{pct(v.flyable_rate)}</td>
                <td className="num">{skill(v.test.vs.persistence?.skill)}</td>
                <td className="num">{skill(v.test.vs.climatology?.skill)}</td>
                <td className="num">{skill(v.test_stations_with_taf.vs.taf?.skill)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="two-col">
        <figure>
          <figcaption>
            <strong>Can you trust the percentages?</strong>{" "}
            <label>Hours ahead{" "}
              <select value={h} onChange={(e) => setH(e.target.value)}>
                {Object.keys(e1.horizons).map((k) => <option key={k} value={k}>{k === "0" ? "next hour" : `${k} to ${Number(k) + 1} h`}</option>)}
              </select>
            </label>
          </figcaption>
          <ReliabilityChart bands={hz.reliability} />
        </figure>
        <div>
          <p>Each dot groups the hours where the forecaster gave about the same chance. A dot on the dashed line
            means the chance was right: of the hours it called 70%, about 70% really were flyable.</p>
          <details>
            <summary>Same data as a table</summary>
            <table>
              <thead><tr><th>Forecast</th><th>Really flyable</th><th>Hours</th></tr></thead>
              <tbody>{hz.reliability.map((b) => (
                <tr key={b.band}><td className="num">{pct(b.mean_predicted)}</td><td className="num">{pct(b.observed_flyable)}</td><td className="num">{b.n.toLocaleString()}</td></tr>
              ))}</tbody>
            </table>
          </details>
        </div>
      </div>
    </section>
  );
}

export default function EvidenceScreen({ active }: { active: boolean }) {
  const [data, setData] = useState<Evidence | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (active && !data) getEvidence().then(setData).catch((e: Error) => setError(e.message));
  }, [active, data]);

  return (
    <main className="single">
      <section className="panel">
        <h2>Evidence</h2>
        <p className="muted">
          Every number here was written by a script in the repository and can be rebuilt. Tests that have not
          been run say so. We show the results as they came out, including where we lose.
          {data && <> Last updated {new Date(data.generated_at).toLocaleString()}.</>}
        </p>
        {error && <p className="error" role="alert">{error}</p>}
        {data && (
          <div className="table-wrap">
            <table className="evidence">
              <thead><tr><th>Test</th><th>What was measured</th><th>Result</th><th>Compare with</th><th>How to read it</th></tr></thead>
              <tbody>
                {data.metrics.map((m, i) => (
                  <tr key={i} className={m.value === null ? "pending" : ""}>
                    <td><span className="chip static">{m.id}</span></td>
                    <td>{m.name}</td>
                    <td className="num"><strong>{show(m.value)}</strong></td>
                    <td className="num">{m.baseline === null ? "–" : show(m.baseline)}</td>
                    <td className="muted">{m.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {data?.details?.E1?.horizons && <ForecasterDetail e1={data.details.E1} />}
    </main>
  );
}
