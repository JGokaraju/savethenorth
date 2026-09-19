import { ReactNode, useEffect, useRef, useState } from "react";
import { Facility, fmtKgH, LedgerRecord, ReportComparison, Verdict } from "../lib/api";
import { useTrace } from "../lib/trace";
import { RunState } from "../lib/useRun";
import { EvidencePanel } from "./EvidencePanel";
import { SiteMap } from "./FacilityPanel";
import { MethodTab } from "./MethodTab";
import { Plot } from "./Plot";
import { Trajectory } from "./Trajectory";
import { Card, Chip, Segmented, StatusBadge } from "./ui";

const OUTCOME: Record<string, { label: string; cls: string; dot: string }> = {
  BUSTED: { label: "BUSTED", cls: "bg-red-600 text-white", dot: "bg-red-500" },
  ACCEPTED: { label: "ACCEPTED", cls: "bg-emerald-600 text-white", dot: "bg-emerald-500" },
  INCONCLUSIVE: { label: "INCONCLUSIVE", cls: "bg-amber-500 text-white", dot: "bg-amber-500" },
  NOT_ASSESSED: { label: "NOT ASSESSED", cls: "bg-slate-500 text-white", dot: "bg-slate-400" },
};

const t = (kg?: number | null) => (kg == null ? "—" : fmtKgH(kg));
const n0 = (v?: number | null) => (v == null ? "—" : Math.round(v).toLocaleString());

/** Evidence ids -> tool calls that produced them. */
function callIdsFor(run: RunState, evidenceIds: string[], tools: string[] = []): string[] {
  const ids = new Set<string>();
  const byId: Record<string, LedgerRecord> = Object.fromEntries(run.ledger.map((r) => [r.id, r]));
  evidenceIds.forEach((e) => byId[e]?.tool_call_ids?.forEach((c) => ids.add(c)));
  run.events.forEach((ev) => { if (ev.type === "tool_result" && tools.includes(ev.name)) ids.add(ev.call_id); });
  return [...ids];
}

function Traceable({ label, evidenceIds, tools, run, children, onTrace }: {
  label: string; evidenceIds: string[]; tools?: string[]; run: RunState; children: ReactNode; onTrace: () => void;
}) {
  const { sel, setSel } = useTrace();
  const on = sel?.label === label;
  return (
    <button type="button" title="Show the data behind this number"
      onClick={() => { setSel(on ? null : { label, evidenceIds, callIds: callIdsFor(run, evidenceIds, tools) }); if (!on) onTrace(); }}
      className={`h-full w-full rounded-2xl text-left transition ${on ? "ring-2 ring-sky-400" : "hover:bg-white"}`}>
      {children}
    </button>
  );
}

function Stat({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="h-full rounded-2xl border border-slate-200/70 bg-white/70 p-4">
      <div className="label">{label}</div>
      <div className="mt-1.5 text-2xl font-semibold tracking-tight text-slate-900">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

function Hero({ v, run, onTrace, onSteps, stepCount }: { v: Verdict; run: RunState; onTrace: () => void; onSteps: () => void; stepCount: number }) {
  const o = OUTCOME[v.outcome?.outcome ?? "NOT_ASSESSED"];
  const me = v.methane_estimate;
  const rc = v.report_comparison;
  const proj = rc?.projection_t_ch4_yr;
  const reportedSameDay = rc ? rc.reported_on_event_date.length : null;
  return (
    <Card pad={false} className="fade-up overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-4 p-6">
        <div className="min-w-0 max-w-3xl space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className={`rounded-xl px-4 py-1.5 text-xl font-bold tracking-wider ${o.cls}`}>{o.label}</span>
            <span className="text-sm text-slate-500">{v.facility_name} · {v.event_date_utc}</span>
          </div>
          <p className="text-lg font-medium leading-snug text-slate-800">{v.headline}</p>
          {v.outcome?.reason && <p className="text-sm text-slate-500">{v.outcome.reason}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="btn-light" onClick={onSteps}>Agent steps ({stepCount})</button>
          <a className="btn-light" href={`/api/runs/${run.runId}/evidence.zip`}>Evidence (.zip)</a>
          <a className="btn-dark" href={`/api/runs/${run.runId}/report.html`} target="_blank" rel="noreferrer">Export report</a>
        </div>
      </div>
      {me.median_kg_h != null && (
        <div className="grid grid-cols-2 gap-3 border-t border-slate-200/70 bg-slate-50/50 p-4 lg:grid-cols-4">
          <Traceable label="Estimated emission rate" evidenceIds={me.evidence_ids} tools={["compute_emission_rate", "plume_map", "get_wind"]} run={run} onTrace={onTrace}>
            <Stat label="Estimated methane" value={t(me.median_kg_h)} sub={`likely range ${t(me.p5_kg_h)} – ${t(me.p95_kg_h)}`} />
          </Traceable>
          <Traceable label="Multiple of the federal threshold" evidenceIds={[...me.evidence_ids, "assumption:regulations.super_emitter_kg_h"]} tools={["check_regulations"]} run={run} onTrace={onTrace}>
            <Stat label="vs 100 kg/h federal threshold" value={`×${n0(me.median_kg_h / 100)}`} sub="EPA super-emitter definition" />
          </Traceable>
          <Traceable label="Annual projection" evidenceIds={v.annual_scenarios_t_ch4.evidence_ids} tools={["annualize"]} run={run} onTrace={onTrace}>
            <Stat label="Projected per year" value={proj ? `${n0(proj.central)} t` : "—"} sub={proj ? `range ${n0(proj.low)} – ${n0(proj.high)} t CH₄` : "not computed"} />
          </Traceable>
          <Traceable label="Reported to TCEQ" evidenceIds={["tceq_steers"]} tools={["reporting_timeline"]} run={run} onTrace={onTrace}>
            <Stat label="Reported to TCEQ that day" value={reportedSameDay === 0 ? "None" : reportedSameDay ?? "—"}
              sub={rc ? `${rc.reported_events.length} event report(s) on file` : undefined} />
          </Traceable>
        </div>
      )}
      <div className="border-t border-slate-200/70 px-6 py-2.5 text-[11px] text-slate-400">{v.disclaimer}</div>
    </Card>
  );
}

function Rules({ v, run, onTrace }: { v: Verdict; run: RunState; onTrace: () => void }) {
  if (!v.regulatory_findings.length) return null;
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
      {v.regulatory_findings.map((r) => (
        <Traceable key={r.rule_id} label={`Rule ${r.rule_id}`} evidenceIds={r.evidence_ids} tools={["check_regulations"]} run={run} onTrace={onTrace}>
          <div className="glass h-full space-y-2 p-4">
            <StatusBadge status={r.status} />
            <div className="text-[13px] font-medium text-slate-800">{RULE_NAMES[r.rule_id] ?? r.rule_id}</div>
            <div className="text-[11px] leading-snug text-slate-500">{r.observed !== "n/a" ? r.observed : r.note}</div>
          </div>
        </Traceable>
      ))}
    </div>
  );
}

const RULE_NAMES: Record<string, string> = {
  US_SUPER_EMITTER: "Federal super-emitter threshold", TX_EMISSIONS_EVENT_REPORTING: "Texas emissions-event reporting",
  PLANT_PHYSICS_CEILING: "Plant capacity sanity check", NOX_PERMIT_LIMITS: "NOx permit limits", GHGRP_REPORTED: "EPA GHG reporting",
};

const CHART_ORDER = ["plume_map", "emission_distribution", "flare_timeline", "reporting_timeline", "regulatory_comparison", "wind_sensitivity", "wind_timeseries"];

function Charts({ run, f }: { run: RunState; f: Facility | null }) {
  const ids = CHART_ORDER.filter((c) => run.charts[c]);
  if (!ids.length) return null;
  const [main, ...rest] = ids;
  return (
    <div className="space-y-4">
      <h2 className="px-1 text-lg font-semibold text-slate-800">Evidence</h2>
      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2" pad={false}><div className="p-2"><Plot figure={run.charts[main].figure_json} height={560} /></div></Card>
        {f && <Card title="Site map"><SiteMap f={f} run={run} /></Card>}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        {rest.map((c) => <Card key={c} pad={false}><div className="p-2"><Plot figure={run.charts[c].figure_json} height={400} /></div></Card>)}
      </div>
    </div>
  );
}

function Projection({ rc, run }: { rc: ReportComparison; run: RunState }) {
  const sat = rc.satellite;
  const proj = rc.projection_t_ch4_yr;
  return (
    <div className="space-y-4">
      <h2 className="px-1 text-lg font-semibold text-slate-800">Satellite projection vs the technical report</h2>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="What the satellite shows">
          {sat ? (
            <dl className="space-y-3 text-sm">
              <Row k="Observed rate on the overpass" v={`${t(sat.median_kg_h)}  (${t(sat.p5_kg_h)} – ${t(sat.p95_kg_h)})`} />
              <Row k="Methane released in one hour" v={`${sat.lb_per_hour.toLocaleString()} lb`} />
              <Row k="If sustained for 24 hours" v={`${sat.lb_if_24h.toLocaleString()} lb`} />
              {proj && <Row k="Projected annual emissions" v={`${n0(proj.low)} – ${n0(proj.high)} t CH₄ (central ${n0(proj.central)} t)`} />}
              {proj?.caveat && <p className="text-xs text-slate-400">{proj.caveat}</p>}
            </dl>
          ) : <p className="text-sm text-slate-500">No satellite estimate available.</p>}
        </Card>
        <Card title="What the operator reported (TCEQ)">
          <div className="space-y-3 text-sm">
            <div className={`rounded-xl px-3 py-2 text-sm font-medium ${rc.reported_on_event_date.length ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-700"}`}>
              {rc.reported_on_event_date.length
                ? `A matching emissions-event report exists for ${rc.event_date}.`
                : `No emissions-event report filed within ±1 day of ${rc.event_date}.`}
            </div>
            <ul className="space-y-2">
              {rc.reported_events.map((e) => {
                const voc = Object.entries(e.lb_by_contaminant).find(([k]) => /voc|natural gas/i.test(k));
                return (
                  <li key={e.incident_no} className="flex items-start justify-between gap-3 border-b border-slate-100 pb-2 last:border-0">
                    <div>
                      <div className="font-medium text-slate-800">Incident #{e.incident_no}</div>
                      <div className="text-xs text-slate-500">{(e.start ?? "").slice(0, 10)} · {e.duration_h ?? "?"} h · {e.emission_points.join(", ")}</div>
                    </div>
                    <div className="text-right text-xs text-slate-600">
                      {voc ? `${Math.round(voc[1]).toLocaleString()} lb VOCs` : "—"}
                      <div className="text-slate-400">{e.methane_reported ? "methane reported" : "methane not itemised"}</div>
                    </div>
                  </li>
                );
              })}
            </ul>
            {proj && rc.reported_voc_total_t > 0 && (
              <p className="text-xs text-slate-500">
                Projected annual methane is about <b className="text-slate-800">{rc.projection_vs_reported_ratio?.toLocaleString()}×</b> the total
                natural-gas VOCs in the reports on file ({rc.reported_voc_total_t.toLocaleString()} t).
              </p>
            )}
          </div>
        </Card>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        {["report_comparison", "annual_scenarios"].filter((c) => run.charts[c]).map((c) => (
          <Card key={c} pad={false}><div className="p-2"><Plot figure={run.charts[c].figure_json} height={400} /></div></Card>
        ))}
      </div>
      <p className="px-1 text-xs text-slate-400">{rc.note}</p>
    </div>
  );
}

function Row({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-slate-100 pb-2 last:border-0">
      <dt className="text-slate-500">{k}</dt><dd className="text-right font-medium text-slate-800">{v}</dd>
    </div>
  );
}

function Findings({ v }: { v: Verdict }) {
  const list = (xs: string[]) => xs.length
    ? <ul className="list-disc space-y-1 pl-5 text-[13px] text-slate-600">{xs.map((x, i) => <li key={i}>{x}</li>)}</ul>
    : <p className="text-[13px] text-slate-400">None</p>;
  const conf = (c: string) => <Chip tone={c === "high" ? "emerald" : c === "medium" ? "amber" : "slate"}>{c} confidence</Chip>;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Attribution and likely cause">
        <div className="space-y-4">
          <div className="space-y-1.5"><div className="flex items-center gap-2"><span className="label">Attribution</span>{conf(v.attribution.confidence)}</div>
            <p className="text-sm text-slate-800">{v.attribution.conclusion}</p>{list(v.attribution.evidence)}</div>
          <div className="space-y-1.5"><div className="flex items-center gap-2"><span className="label">Likely cause</span>{conf(v.likely_cause.confidence)}</div>
            <p className="text-sm text-slate-800">{v.likely_cause.conclusion}</p>{list(v.likely_cause.evidence)}</div>
        </div>
      </Card>
      <Card title="Recommended actions">
        <ol className="list-decimal space-y-1.5 pl-5 text-[13px] text-slate-700">{v.recommended_actions.map((x, i) => <li key={i}>{x}</li>)}</ol>
        <div className="mt-5 space-y-1.5"><span className="label">Data gaps</span>{list(v.data_gaps)}</div>
        <div className="mt-4 space-y-1.5"><span className="label">Conflicts</span>{list(v.conflicts)}</div>
      </Card>
    </div>
  );
}

function TraceBanner({ run }: { run: RunState }) {
  const { sel, setSel } = useTrace();
  if (!sel) return null;
  const recs = run.ledger.filter((r) => sel.evidenceIds.includes(r.id));
  return (
    <div className="rounded-2xl border border-sky-200 bg-sky-50 p-3 text-xs text-sky-900">
      <div className="flex items-center justify-between"><b>Sources for: {sel.label}</b>
        <button className="text-sky-700 hover:underline" onClick={() => setSel(null)}>clear</button></div>
      <div className="mt-1.5 flex flex-wrap gap-1">
        {recs.map((r) => (
          <button key={r.id} onClick={() => document.getElementById(`ledger-${r.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" })}>
            <Chip tone={r.type === "assumption" ? "amber" : r.type === "ai_analysis" ? "violet" : "sky"}>{r.id}</Chip>
          </button>
        ))}
      </div>
    </div>
  );
}

export function Summary({ run, f }: { run: RunState; f: Facility | null }) {
  const v = run.verdict!;
  const [tab, setTab] = useState<"data" | "method">(() => (new URLSearchParams(window.location.search).get("tab") === "method" ? "method" : "data"));
  const [showSteps, setShowSteps] = useState(false);
  const dataRef = useRef<HTMLDivElement>(null);
  const stepCount = run.events.filter((e) => e.type === "tool_call").length;
  const toData = () => { setTab("data"); setTimeout(() => dataRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50); };
  useEffect(() => { if (new URLSearchParams(window.location.search).get("tab")) setTimeout(() => dataRef.current?.scrollIntoView(), 300); }, []);
  return (
    <div className="space-y-6">
      <Hero v={v} run={run} onTrace={toData} onSteps={() => setShowSteps((s) => !s)} stepCount={stepCount} />
      {showSteps && <Card title="Agent steps" className="fade-up"><Trajectory run={run} compact /></Card>}
      <Rules v={v} run={run} onTrace={toData} />
      <Charts run={run} f={f} />
      {v.report_comparison && <Projection rc={v.report_comparison} run={run} />}
      <Findings v={v} />
      <div ref={dataRef} className="scroll-mt-24">
        <Card title={<Segmented value={tab} onChange={setTab} options={[{ value: "data", label: "Data used" }, { value: "method", label: "Method" }]} />}>
          <div className="space-y-3">
            <TraceBanner run={run} />
            {tab === "data" ? <EvidencePanel run={run} /> : <MethodTab run={run} />}
          </div>
        </Card>
      </div>
    </div>
  );
}
