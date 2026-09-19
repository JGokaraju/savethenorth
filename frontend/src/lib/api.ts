export type Availability = Record<string, { available: boolean; quality: "ok" | "low" | "synthetic" | null }>;

export interface Facility {
  facility_id: string;
  name: string;
  operator?: string;
  state?: string;
  county?: string;
  nearest_city?: string;
  lat: number;
  lon: number;
  title_v_permit?: string;
  nsr_authorization?: string;
  regulated_entity_number?: string;
  design_capacity_mmscfd?: number;
  sector?: string;
  data_status: string;
  availability?: Availability;
}

export interface GeoResult {
  label: string;
  lat: number;
  lon: number;
  kind: string;
  facility_id?: string;
  nearest_facility?: { facility_id: string; name: string; distance_km: number } | null;
}

export interface Health {
  mode: { mock_llm: boolean; mock_omni: boolean; demo_replay: boolean; label: "LIVE" | "MOCK" | "REPLAY" };
  keys_present: { openai: boolean; omni: boolean };
  models: { openai: string | null; omni: string };
  omni_calls: { live_calls: number; cached: number; mock: number };
  live_available: boolean;
  omni_live_available: boolean;
}

export interface ReportComparison {
  event_date: string;
  reported_events: { incident_no: string; start: string | null; end: string | null; duration_h: number | null; event_type: string;
    emission_points: string[]; lb_by_contaminant: Record<string, number>; methane_reported: boolean }[];
  reported_on_event_date: any[];
  reported_voc_total_lb: number;
  reported_voc_total_t: number;
  methane_reported_anywhere: boolean;
  note: string;
  satellite?: { median_kg_h: number; p5_kg_h: number; p95_kg_h: number; lb_per_hour: number; lb_if_24h: number };
  projection_t_ch4_yr?: { low: number; central: number; high: number; detection_frequency: number | null; caveat: string };
  projection_vs_reported_ratio?: number;
  core?: {
    gwp100_ch4: number;
    allowed: { ch4_kg_h: number; co2e_t_h: number; basis: string };
    actual: { ch4_kg_h: number; co2e_t_h: number; co2e_t_h_p5: number; co2e_t_h_p95: number };
    ratio: number;
    reported_same_day: number;
  } | null;
}

export interface RunEvent {
  type: string;
  ts: string;
  run_id: string;
  [k: string]: any;
}

export interface Finding {
  conclusion: string;
  confidence: "low" | "medium" | "high";
  evidence: string[];
  evidence_ids: string[];
}

export interface RegFinding {
  rule_id: string;
  rule: string;
  threshold: string;
  observed: string;
  status: string;
  note: string;
  evidence_ids: string[];
}

export interface Verdict {
  facility_id: string;
  facility_name: string;
  event_date_utc: string;
  headline: string;
  methane_estimate: { median_kg_h: number | null; p5_kg_h: number | null; p95_kg_h: number | null; method: string; key_assumptions: string[]; evidence_ids: string[] };
  cross_check: { source: string; their_kg_h: number | null; ratio: number | null; consistent: boolean | null; note: string; evidence_ids: string[] };
  attribution: Finding;
  likely_cause: Finding;
  annual_scenarios_t_ch4: { low: number | null; central: number | null; high: number | null; caveat: string; evidence_ids: string[] };
  regulatory_findings: RegFinding[];
  data_gaps: string[];
  conflicts: string[];
  recommended_actions: string[];
  charts: string[];
  evidence_ids: string[];
  disclaimer: string;
  outcome?: { outcome: "BUSTED" | "ACCEPTED" | "INCONCLUSIVE" | "NOT_ASSESSED"; reason: string } | null;
  report_comparison?: ReportComparison | null;
  key_evidence?: { id: string; importance: number; reason: string; question: string; text: string; label?: string; source: string; flags: string[] }[] | null;
}

export interface LedgerRecord {
  id: string;
  type: "data" | "assumption" | "ai_analysis" | "derived";
  slot_id?: string;
  file?: string;
  sha256?: string;
  source_name?: string;
  source_url?: string;
  citation?: string;
  provider?: string;
  date_coverage?: string;
  subset?: string;
  record_count?: number;
  preview_ref?: string;
  extra_refs?: string[];
  subsets?: { subset?: string; record_count?: number; preview_ref?: string; extra_refs?: string[]; tool: string }[];
  used_by_tools: string[];
  tool_call_ids?: string[];
  synthetic?: boolean;
  quality?: string;
  warnings?: string[];
  // assumption
  name?: string;
  value?: any;
  unit?: string;
  rationale?: string;
  verify?: boolean;
  range?: number[];
  source?: string;
  // ai analysis
  tool?: string;
  target_id?: string;
  question?: string;
  answer?: string;
  model?: string;
  mode?: string;
  timestamp?: string;
  input_ref?: string;
  all_inputs?: string[];
}

export interface Dataset {
  slot_id: string;
  status: string;
  type?: string;
  file?: string;
  source_name?: string;
  source_url?: string;
  citation?: string;
  provider?: string;
  sha256?: string;
  date_coverage?: string;
  reason?: string;
  warnings?: string[];
  quality?: string;
  synthetic?: boolean;
  size_bytes?: number | null;
}

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}: ${await r.text().catch(() => "")}`.slice(0, 300));
  return r.json();
}

export const api = {
  health: () => j<Health>("/api/health"),
  facilities: (q = "") => j<Facility[]>(`/api/facilities?q=${encodeURIComponent(q)}`),
  facility: (id: string) => j<Facility>(`/api/facilities/${id}`),
  geocode: (q: string) => j<GeoResult[]>(`/api/geocode?q=${encodeURIComponent(q)}`),
  datasets: () => j<Dataset[]>("/api/datasets"),
  preview: (slot: string) => j<any>(`/api/datasets/${slot}/preview`),
  startRun: (facility_id: string, date: string, mode: "demo" | "live") =>
    j<{ run_id: string; mode: string }>("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ facility_id, date, mode }),
    }),
  evidence: (runId: string) => j<{ ledger: LedgerRecord[]; omni_calls: LedgerRecord[]; tool_calls: any[] }>(`/api/runs/${runId}/evidence`),
  image: (id: string) => j<{ url: string; bounds: { west: number; south: number; east: number; north: number }; date: string; warnings: string[] }>(`/api/images/${id}`),
};

export const runFileUrl = (runId: string, ref: string) => `/api/runs/${runId}/${ref.replace(/^\/+/, "")}`;

export async function fetchCsv(url: string): Promise<{ columns: string[]; rows: Record<string, string>[] }> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status}`);
  const text = await r.text();
  const lines = text.split(/\r?\n/).filter((l) => l.length);
  const parse = (line: string) => {
    const out: string[] = [];
    let cur = "";
    let q = false;
    for (let i = 0; i < line.length; i++) {
      const c = line[i];
      if (q) {
        if (c === '"' && line[i + 1] === '"') { cur += '"'; i++; }
        else if (c === '"') q = false;
        else cur += c;
      } else if (c === '"') q = true;
      else if (c === ",") { out.push(cur); cur = ""; }
      else cur += c;
    }
    out.push(cur);
    return out;
  };
  const columns = parse(lines[0] ?? "");
  const rows = lines.slice(1).map((l) => {
    const v = parse(l);
    return Object.fromEntries(columns.map((c, i) => [c, v[i] ?? ""]));
  });
  return { columns, rows };
}

export const fmtKgH = (v: number | null | undefined) =>
  v == null ? "—" : v >= 1000 ? `${(v / 1000).toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })} t/h` : `${Math.round(v).toLocaleString()} kg/h`;
