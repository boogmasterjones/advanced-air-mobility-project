// Types mirror backend/app/contracts.py. Keep the two in step.

export type Facility = {
  faa_id: string; name: string; city: string; lat: number; lon: number;
  trauma_level?: string | null;
  known_as?: string | null; // the state's name for a trauma center
};

export type Strategy = "ground_only" | "air_only" | "air_and_ground";

export type Option = {
  strategy: Strategy;
  status: "OK" | "UNKNOWN" | "NOT_AVAILABLE";
  p_by_deadline: number | null;
  median_min: number | null;
  range_min: [number, number] | null;
  reasons: string[];
  fact_ids: string[];
  steps?: Step[]; // where the time goes at typical values
};

export type Step = { kind: "wait" | "positioning" | "hospital" | "travel" | "handoff"; label: string; minutes: number };

export type Fact = {
  id: string; label: string; value: string | number | boolean | null; unit: string;
  source: string; fetched_at: string; confidence: string;
};

export type ForecastPoint = { hours_ahead: number; p_flyable: number };
export type StationForecast = {
  station: string; role: string; issued_at: string; model: string; points: ForecastPoint[];
};

export type MapData = {
  road: [number, number][];
  road_is_routed: boolean;
  air_base: { name: string; icao: string; lat: number; lon: number };
  air: [number, number][];
  // "Always an Out": nearest landing places along the flight, and the smallest energy margin to one
  landing_places?: { id: string; name: string; kind: string; lat: number; lon: number }[];
  min_margin_min?: number | null;
};

export type CaseResult = {
  disclaimer: string;
  origin: Facility;
  dest: Facility;
  options: Option[];
  recommended: Strategy;
  facts: Fact[];
  decision_owner: string;
  as_of?: string | null;
  forecasts?: StationForecast[];
  map?: MapData | null;
};

export type Match = { faa_id: string; name: string; city: string; score: number };

export type IntakeResult = {
  result: {
    category: string; origin_name: string | null; dest_name: string | null;
    deadline_min: number | null; people: number | null; notes: string; needs_human_review: string[];
  };
  confirm_required: boolean;
  origin_matches: Match[];
  dest_matches: Match[];
  origin_id: string | null;
  dest_id: string | null;
  provider: string;
};

export type Brief = {
  sentences: string[];
  removed: { sentence: string; reason: string }[];
  pass_rate: number;
  provider: string;
};

export type Replay = {
  as_of: string;
  then: CaseResult;
  actual_flyable: boolean | null;
  actual_best_strategy: Strategy | null;
  regret_min: number | null;
  regret_chance?: number | null;
  actual_options?: Option[] | null;
};

export type ReplayRange = { first: string | null; last: string | null; stations: string[] };

export type EvalMetric = {
  id: string; name: string; value: number | string | null; baseline: number | string | null; note: string;
};
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- result files differ per eval
export type Evidence = { generated_at: string; metrics: EvalMetric[]; details: Record<string, any> };

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new Error("Could not reach the server. Check your connection and try again.");
  }
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : "";
    } catch { /* no JSON body */ }
    throw new Error(detail || `The server answered with an error (${res.status}).`);
  }
  return res.json();
}

const post = (body: unknown): RequestInit => ({
  method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
});

export const getFacilities = () => call<Facility[]>("/api/facilities");

export const evaluateCase = (body: {
  origin_id: string; dest_id: string; deadline_min: number; category: string;
  as_of?: string; // demo mode: answer as of this past moment, from the weather archive
}) => call<CaseResult>("/api/cases/evaluate", post(body));

export const readRequest = (text: string) => call<IntakeResult>("/api/intake", post({ text }));

export const getBrief = (c: CaseResult) => call<Brief>("/api/brief", post({ case: c }));

export const getReplay = (p: { date: string; origin_id: string; dest_id: string; deadline_min: number }) =>
  call<Replay>(`/api/replay?${new URLSearchParams({
    date: p.date, origin_id: p.origin_id, dest_id: p.dest_id, deadline_min: String(p.deadline_min),
  })}`);

export const getReplayRange = () => call<ReplayRange>("/api/replay/range");

export const getEvidence = () => call<Evidence>("/api/evidence");

export const STRATEGY_LABEL: Record<Strategy, string> = {
  ground_only: "Ground ambulance only",
  air_only: "Air taxi only",
  air_and_ground: "Air taxi with ground backup",
};

export const STATUS_LABEL: Record<Option["status"], string> = {
  OK: "Numbers available",
  UNKNOWN: "Unknown: weather data missing or old",
  NOT_AVAILABLE: "Not available for this trip",
};

/** "TAMPA GENERAL HOSPITAL" -> "Tampa General Hospital"; the FAA list is upper-case and abbreviated. */
export function niceName(name: string): string {
  const fixes: Record<string, string> = { MEML: "Memorial", RGNL: "Regional", HCA: "HCA", UF: "UF", ER: "ER", VA: "VA" };
  return name.split(/\s+/).map((w) => fixes[w] ?? (w.charAt(0) + w.slice(1).toLowerCase())).join(" ");
}

/** The name people know a place by: the state's name for trauma centers, else the FAA name tidied up. */
export function placeName(f: Facility): string {
  return f.known_as || niceName(f.name);
}

export function facilityLabel(f: Facility): string {
  const level = !f.trauma_level ? "" : / /.test(f.trauma_level) || f.trauma_level === "Pediatric"
    ? ` · ${f.trauma_level.toLowerCase()} trauma center` : ` · level ${f.trauma_level.replace("+Pediatric", " and pediatric")} trauma center`;
  return `${placeName(f)} (${niceName(f.city)})${level}`;
}
