import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Facility, runFileUrl, Verdict } from "../lib/api";
import { useInView } from "../lib/hooks";
import { useTrace } from "../lib/trace";
import { RunState } from "../lib/useRun";
import { EvidencePanel } from "./EvidencePanel";
import { MethodTab } from "./MethodTab";
import { Plot } from "./Plot";
import { Trajectory } from "./Trajectory";
import { Card, Logo, Segmented } from "./ui";

const STAMP: Record<string, { text: string; color: string }> = {
  BUSTED: { text: "BUSTED", color: "#dc2626" },
  ACCEPTED: { text: "ACCEPTED", color: "#16a34a" },
  INCONCLUSIVE: { text: "INCONCLUSIVE", color: "#d97706" },
  NOT_ASSESSED: { text: "NOT ASSESSED", color: "#64748b" },
};
const FIGURES = ["emission_distribution", "report_comparison", "flare_timeline", "regulatory_comparison"];

const fmt = (v: number, d = 0) => v.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });

function Hero({ v, f }: { v: Verdict; f: Facility | null }) {
  const s = STAMP[v.outcome?.outcome ?? "NOT_ASSESSED"];
  const img = f?.data_status === "cached" ? `/api/facilities/${f.facility_id}/imagery/site` : null;
  return (
    <section className="relative h-screen w-full overflow-hidden bg-slate-800">
      {img && <img src={img} alt={`Aerial image of ${v.facility_name}`} className="absolute inset-0 h-full w-full object-cover" />}
      <div className="absolute inset-0 bg-gradient-to-b from-black/35 via-black/10 to-black/55" />
      <div className="absolute left-6 top-6 flex items-center gap-2.5 text-white">
        <Link to="/" className="flex items-center gap-2.5"><Logo size={30} /><span className="font-semibold">Save the North</span></Link>
      </div>
      <Link to="/" className="absolute right-6 top-6 rounded-xl bg-white/85 px-4 py-2 text-sm font-medium text-slate-800 backdrop-blur hover:bg-white">New search</Link>

      <div className="absolute inset-0 flex items-center justify-center">
        <div className="stamp select-none rounded-3xl px-10 py-4 text-6xl font-black tracking-[0.12em] sm:px-16 sm:text-8xl lg:text-[9rem]"
          style={{ color: s.color, border: `10px solid ${s.color}`, background: "rgba(255,255,255,0.18)", boxShadow: "0 20px 60px rgba(0,0,0,0.25)" }}
          role="img" aria-label={`Screening outcome: ${s.text}`}>
          {s.text}
        </div>
      </div>

      <div className="absolute bottom-8 left-6 right-6 flex items-end justify-between gap-4 text-white">
        <div>
          <div className="text-2xl font-semibold sm:text-3xl">{v.facility_name}</div>
          <div className="text-sm text-white/80">{v.event_date_utc}{f ? ` · ${f.county} County, ${f.state}` : ""}</div>
        </div>
        <button onClick={() => document.getElementById("core")?.scrollIntoView({ behavior: "smooth" })} aria-label="Scroll to details" className="text-white/80 hover:text-white">
          <svg viewBox="0 0 24 24" className="nudge h-7 w-7"><path fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" d="M6 9l6 6 6-6" /></svg>
        </button>
      </div>
      {img && <div className="absolute bottom-2 right-3 text-[10px] text-white/60">Imagery: Esri, Maxar, Earthstar Geographics</div>}
    </section>
  );
}

function Big({ label, value, unit, sub, tone = "slate", onClick }: {
  label: string; value: string; unit: string; sub: string; tone?: "slate" | "red"; onClick?: () => void;
}) {
  return (
    <button type="button" onClick={onClick} className="block w-full rounded-3xl p-2 text-left transition hover:bg-white/60" title="Show sources">
      <div className="label">{label}</div>
      <div className="mt-1 flex items-baseline gap-3">
        <span className={`text-6xl font-semibold tracking-tight sm:text-7xl ${tone === "red" ? "text-red-600" : "text-slate-900"}`}>{value}</span>
        <span className="text-lg text-slate-500">{unit}</span>
      </div>
      <div className="mt-1 text-sm text-slate-500">{sub}</div>
    </button>
  );
}

function Core({ v, run, onSources }: { v: Verdict; run: RunState; onSources: () => void }) {
  const core = v.report_comparison?.core;
  const { setSel } = useTrace();
  const { ref, inView } = useInView<HTMLDivElement>(0.2);
  const overlay = run.ledger.find((r) => r.slot_id === "site_imagery")?.preview_ref;
  const trace = (label: string, ids: string[]) => { setSel({ label, evidenceIds: ids, callIds: [] }); onSources(); };
  if (!core) return null;
  const me = v.methane_estimate;
  return (
    <section id="core" className="mx-auto max-w-6xl px-4 py-16">
      <div ref={ref} className={`reveal grid items-center gap-8 lg:grid-cols-2 ${inView ? "in" : ""}`}>
        <div className="glass space-y-8 p-8">
          <Big label="Allowed" value={fmt(core.allowed.co2e_t_h, 1)} unit="t CO₂e / h"
            sub={`EPA super-emitter threshold · ${fmt(core.allowed.ch4_kg_h)} kg CH₄/h`}
            onClick={() => trace("Allowed", ["assumption:regulations.super_emitter_kg_h", "assumption:regulations.gwp100_ch4"])} />
          <div className="h-px bg-slate-200" />
          <Big label="Actual" value={fmt(core.actual.co2e_t_h)} unit="t CO₂e / h" tone="red"
            sub={`${fmt(core.actual.ch4_kg_h / 1000, 1)} t CH₄/h · ×${fmt(core.ratio)} · reported: ${core.reported_same_day ? "yes" : "none"}`}
            onClick={() => trace("Actual", [...(me.evidence_ids ?? []), "assumption:regulations.gwp100_ch4", "tceq_steers"])} />
        </div>
        <figure className="glass overflow-hidden p-2">
          {overlay
            ? <img src={runFileUrl(run.runId!, overlay)} alt="EMIT methane enhancement over the site" className="w-full rounded-2xl" />
            : run.charts.plume_map && <Plot figure={run.charts.plume_map.figure_json} height={520} />}
          <figcaption className="px-3 py-2 text-xs text-slate-500">EMIT CH₄ enhancement · {v.event_date_utc} 14:45 UTC</figcaption>
        </figure>
      </div>
    </section>
  );
}

function Figures({ run }: { run: RunState }) {
  const ids = FIGURES.filter((c) => run.charts[c]);
  if (!ids.length) return null;
  return (
    <section className="mx-auto grid max-w-6xl gap-4 px-4 pb-10 lg:grid-cols-2">
      {ids.map((c) => <Card key={c} pad={false}><div className="p-2"><Plot figure={run.charts[c].figure_json} height={380} /></div></Card>)}
    </section>
  );
}

export function Report({ run, f }: { run: RunState; f: Facility | null }) {
  const v = run.verdict!;
  const [panel, setPanel] = useState<"none" | "steps" | "sources">("none");
  const [tab, setTab] = useState<"data" | "method">("data");
  const panelRef = useRef<HTMLDivElement>(null);
  const open = (p: "steps" | "sources") => {
    setPanel((cur) => (cur === p ? "none" : p));
    setTimeout(() => panelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
  };
  return (
    <div>
      <Hero v={v} f={f} />
      <Core v={v} run={run} onSources={() => { setPanel("sources"); setTab("data"); setTimeout(() => panelRef.current?.scrollIntoView({ behavior: "smooth" }), 60); }} />
      <Figures run={run} />
      <section className="mx-auto max-w-6xl space-y-4 px-4 pb-10">
        <div className="flex flex-wrap justify-center gap-2">
          <a className="btn-dark" href={`/api/runs/${run.runId}/report.html`} target="_blank" rel="noreferrer">Export report</a>
          <a className="btn-light" href={`/api/runs/${run.runId}/evidence.zip`}>Evidence (.zip)</a>
          <button className="btn-light" onClick={() => open("sources")}>Sources and method</button>
          <button className="btn-light" onClick={() => open("steps")}>Agent steps</button>
        </div>
        <div ref={panelRef} className="scroll-mt-6">
          {panel === "steps" && <Card className="fade-up"><Trajectory run={run} compact /></Card>}
          {panel === "sources" && (
            <Card className="fade-up" title={<Segmented value={tab} onChange={setTab} options={[{ value: "data", label: "Data used" }, { value: "method", label: "Method" }]} />}>
              {tab === "data" ? <EvidencePanel run={run} /> : <MethodTab run={run} />}
            </Card>
          )}
        </div>
        <p className="text-center text-[11px] text-slate-400">{v.disclaimer}</p>
      </section>
    </div>
  );
}
