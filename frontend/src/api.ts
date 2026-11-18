export type Facility = { faa_id: string; name: string; city: string; lat: number; lon: number };

export type Option = {
  strategy: "ground_only" | "air_only" | "air_and_ground";
  status: "OK" | "UNKNOWN" | "NOT_AVAILABLE";
  p_by_deadline: number | null;
  median_min: number | null;
  range_min: [number, number] | null;
  reasons: string[];
  fact_ids: string[];
};

export type Fact = {
  id: string; label: string; value: unknown; unit: string;
  source: string; fetched_at: string; confidence: string;
};

export type CaseResult = {
  disclaimer: string;
  origin: Facility;
  dest: Facility;
  options: Option[];
  recommended: string;
  facts: Fact[];
};

export async function getFacilities(): Promise<Facility[]> {
  const res = await fetch("/api/facilities");
  if (!res.ok) throw new Error("Could not load facilities");
  return res.json();
}

export async function evaluateCase(body: {
  origin_id: string; dest_id: string; deadline_min: number; category: string;
}): Promise<CaseResult> {
  const res = await fetch("/api/cases/evaluate", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Evaluation failed (${res.status})`);
  return res.json();
}
