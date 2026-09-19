import { ReactNode, useState } from "react";
import { fmtKgH, LedgerRecord, Verdict } from "../lib/api";
import { useTrace } from "../lib/trace";
import { RunState } from "../lib/useRun";
import { EvidencePanel } from "./EvidencePanel";
import { MethodTab } from "./MethodTab";
import { Plot } from "./Plot";
import { Card, Chip, Skeleton, StatusBadge } from "./ui";

/** Map evidence ids -> the tool calls that produced them (via ledger tool_call_ids and tool results). */
function callIdsFor(run: RunState, evidenceIds: string[], tools: string[] = []): string[] {
  const ids = new Set<string>();
  const byId: Record<string, LedgerRecord> = Object.fromEntries(run.ledger.map((r) => [r.id, r]));
  evidenceIds.forEach((e) => byId[e]?.tool_call_ids?.forEach((c) => ids.add(c)));
  run.events.forEach((ev) => {
    if (ev.type === "tool_result" && (tools.includes(ev.name) || (ev.evidence_ids ?? []).some((e: string) => evidenceIds.includes(e) && e.startsWith("omni:"))))
      ids.add(ev.call_id);
  });
  return [...ids];
}

function Traceable({ label, evidenceIds, tools, run, children, className = "" }: {
  label: string; evidenceIds: string[]; tools?: string[]; run: RunState; children: ReactNode; className?: string;
}) {
  const { sel, setSel } = useTrace();
  const on = sel?.label === label;
  return (
    <button type="button" title="Show where this number came from"
      onClick={() => setSel(on ? null : { label, evidenceIds, callIds: callIdsFor(run, evidenceIds, tools) })}
      className={`text-left transition ${on ? "rounded ring-2 ring-sky-400" : "hover:opacity-90"} ${className}`}>
      {children}
    </button>
  );
}

function TraceBanner({ run, onShowData }: { run: RunState; onShowData: () => void }) {
  const { sel, setSel } = useTrace();
  if (!sel) return null;
  const recs = run.ledger.filter((r) => sel.evidenceIds.includes(r.id));
  return (
    <div className="rounded-lg border border-sky-500/40 bg-sky-950/30 p-3 text-xs text-sky-100">
      <div className="flex items-center justify-between">
        <b>Traced: {sel.label}</b>
        <button className="text-sky-300 hover:underline" onClick={() => setSel(null)}>clear</button>
      </div>
      <div className="mt-1 text-sky-200/80">{sel.callIds.length} tool call(s) highlighted in the trace · ledger records:</div>
      <div className="mt-1 flex flex-wrap gap-1">
        {recs.map((r) => (
          <button key={r.id} onClick={() => { onShowData(); setTimeout(() => document.getElementById(`ledger-${r.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 80); }}>
            <Chip tone={r.type === "assumption" ? "amber" : r.type === "ai_analysis" ? "violet" : "sky"}>{r.id}</Chip>
          </button>
        ))}
      </div>
    </div>
  );
}

function BigNumber({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3">
      <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-slate-50">{value}</div>
      {sub && <div className="text-xs text-slate-400">{sub}</div>}
    </div>
  );
}

const conf = (c: string) => <Chip tone={c === "high" ? "emerald" : c === "medium" ? "amber" : "slate"}>{c} confidence</Chip>;

function VerdictBody({ v, run }: { v: Verdict; run: RunState }) {
  const me = v.methane_estimate;
  const times = me.median_kg_h ? me.median_kg_h / 100 : null;
  const list = (xs: string[]) => xs.length
    ? <ul className="list-disc space-y-1 pl-5 text-xs text-slate-300">{xs.map((x, i) => <li key={i}>{x}</li>)}</ul>
    : <p className="text-xs text-slate-500">None</p>;
  const a = v.annual_scenarios_t_ch4;
  return (
    <div className="space-y-4">
      <p className="text-base font-semibold leading-snug text-slate-50">{v.headline}</p>
      {me.median_kg_h != null && (
        <div className="grid grid-cols-2 gap-2">
          <Traceable label="Methane estimate (median, p5–p95)" evidenceIds={me.evidence_ids} tools={["compute_emission_rate", "plume_map", "get_wind"]} run={run}>
            <BigNumber label="Estimated emission" value={fmtKgH(me.median_kg_h)} sub={`p5–p95 ${fmtKgH(me.p5_kg_h)} – ${fmtKgH(me.p95_kg_h)}`} />
          </Traceable>
          <Traceable label="Multiple of the super-emitter threshold" evidenceIds={[...me.evidence_ids, "assumption:regulations.super_emitter_kg_h"]} tools={["compute_emission_rate", "check_regulations"]} run={run}>
            <BigNumber label="vs 100 kg/h threshold" value={times ? `×${Math.round(times).toLocaleString()}` : "—"} sub="EPA super-emitter (screening)" />
          </Traceable>
        </div>
      )}
      {v.cross_check.their_kg_h != null && (
        <Traceable label="Carbon Mapper cross-check" evidenceIds={v.cross_check.evidence_ids} tools={["compare_estimates"]} run={run} className="block w-full">
          <div className="rounded-lg border border-slate-800 p-3 text-xs text-slate-300">
            <b className="text-slate-100">Cross-check · {v.cross_check.source}</b>: {fmtKgH(v.cross_check.their_kg_h)} · ratio {v.cross_check.ratio?.toFixed(2)} ·{" "}
            {v.cross_check.consistent ? <span className="text-emerald-300">consistent</span> : <span className="text-amber-300">not consistent</span>}
            <div className="mt-1 text-slate-500">{v.cross_check.note}</div>
          </div>
        </Traceable>
      )}
      {v.regulatory_findings.length > 0 && (
        <div className="space-y-1.5">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Regulatory screening</h4>
          {v.regulatory_findings.map((r) => (
            <Traceable key={r.rule_id} label={`Rule ${r.rule_id}`} evidenceIds={r.evidence_ids} tools={["check_regulations"]} run={run} className="block w-full">
              <div className="rounded-lg border border-slate-800 p-2.5">
                <div className="flex items-center justify-between gap-2"><code className="text-xs text-slate-200">{r.rule_id}</code><StatusBadge status={r.status} /></div>
                <div className="mt-1 text-[11px] text-slate-400">{r.rule}</div>
                {r.observed && r.observed !== "n/a" && <div className="text-[11px] text-slate-300">Observed: {r.observed} · Threshold: {r.threshold}</div>}
                {r.note && <div className="mt-0.5 text-[11px] text-slate-500">{r.note}</div>}
              </div>
            </Traceable>
          ))}
        </div>
      )}
      <div className="space-y-2">
        <div className="flex items-center gap-2"><h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Attribution</h4>{conf(v.attribution.confidence)}</div>
        <p className="text-sm text-slate-200">{v.attribution.conclusion}</p>{list(v.attribution.evidence)}
      </div>
      <div className="space-y-2">
        <div className="flex items-center gap-2"><h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Likely cause</h4>{conf(v.likely_cause.confidence)}</div>
        <p className="text-sm text-slate-200">{v.likely_cause.conclusion}</p>{list(v.likely_cause.evidence)}
      </div>
      {a.central != null && (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Annualized scenarios</h4>
          <p className="text-sm text-slate-200">{a.low?.toLocaleString()} – {a.high?.toLocaleString()} t CH₄/yr (central {a.central?.toLocaleString()})</p>
          <p className="text-[11px] text-amber-300/80">{a.caveat}</p>
        </div>
      )}
      <div><h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Data gaps</h4>{list(v.data_gaps)}</div>
      <div><h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Conflicts</h4>{list(v.conflicts)}</div>
      <div><h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Recommended actions</h4>
        <ol className="list-decimal space-y-1 pl-5 text-xs text-slate-300">{v.recommended_actions.map((x, i) => <li key={i}>{x}</li>)}</ol></div>
      <p className="rounded border border-amber-500/30 bg-amber-950/20 p-2 text-xs text-amber-200">{v.disclaimer}</p>
      {run.shownCharts.map((c) => run.charts[c.chart_id] && (
        <figure key={c.chart_id} className="rounded-lg border border-slate-800">
          <Plot figure={run.charts[c.chart_id].figure_json} height={c.chart_id === "plume_map" ? 520 : 380} />
          {c.caption && <figcaption className="px-3 pb-2 text-[11px] text-slate-400">{c.caption}</figcaption>}
        </figure>
      ))}
    </div>
  );
}

export function VerdictPanel({ run }: { run: RunState }) {
  const initialTab = new URLSearchParams(window.location.search).get("tab");  // deep link: ?tab=data|method
  const [tab, setTab] = useState<"verdict" | "data" | "method">(
    initialTab === "data" || initialTab === "method" ? initialTab : "verdict");
  const v = run.verdict;
  const download = () => {
    const blob = new Blob([JSON.stringify(v, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `verdict_${v?.facility_id}_${v?.event_date_utc}.json`;
    a.click();
  };
  const tabs: [typeof tab, string][] = [["verdict", "Verdict"], ["data", "Data used"], ["method", "Method"]];
  return (
    <Card
      title={<div className="flex gap-1" role="tablist">{tabs.map(([k, l]) => (
        <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
          className={`rounded-md px-2.5 py-1 text-xs ${tab === k ? "bg-slate-700 text-white" : "text-slate-400 hover:text-slate-200"}`}>{l}</button>))}</div>}
      right={v && (
        <div className="flex gap-1">
          <button onClick={download} className="rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-800">⬇ JSON</button>
          <a href={`/api/runs/${run.runId}/report.html`} target="_blank" rel="noreferrer" className="rounded border border-slate-700 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-800">Export report</a>
        </div>
      )}>
      <div className="space-y-3">
        <TraceBanner run={run} onShowData={() => setTab("data")} />
        {tab === "verdict" && (v ? <VerdictBody v={v} run={run} /> : (
          <div className="space-y-3">
            <p className="text-xs text-slate-500">{run.status === "idle" ? "The verdict appears here when the agent finishes." : "Waiting for the agent's verdict…"}</p>
            <Skeleton className="h-6 w-4/5" /><div className="grid grid-cols-2 gap-2"><Skeleton className="h-20" /><Skeleton className="h-20" /></div>
            <Skeleton className="h-14" /><Skeleton className="h-14" /><Skeleton className="h-24" />
          </div>
        ))}
        {tab === "data" && <EvidencePanel run={run} />}
        {tab === "method" && <MethodTab run={run} />}
      </div>
    </Card>
  );
}
