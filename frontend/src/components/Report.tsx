import { ReactNode, useRef, useState } from "react";
import { Facility, runFileUrl, Verdict } from "../lib/api";
import { useTrace } from "../lib/trace";
import { RunState } from "../lib/useRun";
import { EvidencePanel } from "./EvidencePanel";
import { SiteHeader } from "./Header";
import { MethodTab } from "./MethodTab";
import { Plot } from "./Plot";
import { Trajectory } from "./Trajectory";
import { Segmented, StatusBadge } from "./ui";

const STAMP: Record<string, { text: string; color: string }> = {
  BUSTED: { text: "BUSTED", color: "#b50909" },
  ACCEPTED: { text: "ACCEPTED", color: "#008817" },
  INCONCLUSIVE: { text: "INCONCLUSIVE", color: "#936f38" },
  NOT_ASSESSED: { text: "NOT ASSESSED", color: "#565c65" },
};
const FIGURES = ["emission_distribution", "report_comparison", "flare_timeline", "regulatory_comparison"];
const RULE_NAMES: Record<string, string> = {
  US_SUPER_EMITTER: "Federal super-emitter threshold (40 CFR 60.5371a/b)",
  TX_EMISSIONS_EVENT_REPORTING: "Texas emissions-event reporting (30 TAC 101.201)",
  PLANT_PHYSICS_CEILING: "Plant capacity check",
  NOX_PERMIT_LIMITS: "NOx permit limits (NSR 177845)",
  GHGRP_REPORTED: "EPA greenhouse gas reporting",
};

const SOURCE_NAMES: Record<string, string> = {
  check_regulations: "regulatory screening", compute_emission_rate: "emission model", plume_map: "EMIT plume map",
  flare_activity: "VIIRS flares", physics_bounds: "physics check", reporting_timeline: "TCEQ reports", compare_estimates: "cross-check",
  annualize: "annual projection", get_wind: "ERA5 wind", list_available_data: "data inventory",
};
const fmt = (v: number, d = 0) => v.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });

function Hero({ v, f }: { v: Verdict; f: Facility | null }) {
  const s = STAMP[v.outcome?.outcome ?? "NOT_ASSESSED"];
  const img = f?.data_status === "cached" ? `/api/facilities/${f.facility_id}/imagery/site` : null;
  return (
    <section className="relative h-[calc(100vh-64px)] w-full overflow-hidden bg-[#3d4551]">
      {img && <img src={img} alt={`Aerial image of ${v.facility_name}`} className="absolute inset-0 h-full w-full object-cover" />}
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="stamp select-none bg-white/15 px-10 py-3 text-6xl font-black tracking-[0.12em] sm:px-14 sm:text-8xl lg:text-[8.5rem]"
          style={{ color: s.color, border: `9px solid ${s.color}` }} role="img" aria-label={`Screening outcome: ${s.text}`}>
          {s.text}
        </div>
      </div>
      <div className="absolute inset-x-0 bottom-0 bg-black/65 text-white">
        <div className="mx-auto flex max-w-6xl items-end justify-between gap-4 px-4 py-4">
          <div>
            <div className="text-2xl font-bold">{v.facility_name}</div>
            <div className="text-sm text-[#dfe1e2]">Event date {v.event_date_utc}{f ? ` · ${f.county} County, ${f.state}` : ""}</div>
          </div>
          <button onClick={() => document.getElementById("summary")?.scrollIntoView({ behavior: "smooth" })} className="text-sm font-semibold underline underline-offset-2">
            View findings
          </button>
        </div>
      </div>
      {img && <div className="absolute right-3 top-2 text-[10px] text-white/80">Imagery: Esri, Maxar, Earthstar Geographics</div>}
    </section>
  );
}

function Section({ id, title, children }: { id?: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="mx-auto max-w-6xl scroll-mt-20 border-t border-rule px-4 py-10 first:border-t-0">
      <h2 className="h2 mb-5">{title}</h2>
      {children}
    </section>
  );
}

function Figure({ n, caption, children }: { n: number; caption: string; children: ReactNode }) {
  return (
    <figure className="border border-rule">
      {children}
      <figcaption className="border-t border-rule bg-paper px-3 py-2 text-sm"><b>Figure {n}.</b> {caption}</figcaption>
    </figure>
  );
}

function Summary({ v, run, onSources }: { v: Verdict; run: RunState; onSources: () => void }) {
  const core = v.report_comparison?.core;
  const { setSel } = useTrace();
  const overlay = run.ledger.find((r) => r.slot_id === "site_imagery")?.preview_ref;
  const trace = (label: string, ids: string[]) => { setSel({ label, evidenceIds: ids, callIds: [] }); onSources(); };
  const me = v.methane_estimate;
  return (
    <Section id="summary" title="Summary">
      <div className="grid gap-8 lg:grid-cols-2">
        <div>
          <div className="flex items-center gap-3">
            <span className="label">Screening outcome</span>
            <span className="px-2 py-0.5 text-sm font-bold uppercase tracking-wide text-white"
              style={{ background: STAMP[v.outcome?.outcome ?? "NOT_ASSESSED"].color }}>{STAMP[v.outcome?.outcome ?? "NOT_ASSESSED"].text}</span>
          </div>
          {core ? (
            <dl className="mt-6 divide-y divide-rule border-y border-rule">
              <button type="button" className="block w-full py-5 text-left hover:bg-paper" title="Show sources"
                onClick={() => trace("Allowed", ["assumption:regulations.super_emitter_kg_h", "assumption:regulations.gwp100_ch4"])}>
                <dt className="label">Allowed</dt>
                <dd className="mt-1"><span className="text-6xl font-extrabold tracking-tight text-ink">{fmt(core.allowed.co2e_t_h, 1)}</span>
                  <span className="ml-2 text-lg text-muted">t CO₂e per hour</span></dd>
                <dd className="text-sm text-muted">EPA super-emitter threshold, {fmt(core.allowed.ch4_kg_h)} kg CH₄ per hour</dd>
              </button>
              <button type="button" className="block w-full py-5 text-left hover:bg-paper" title="Show sources"
                onClick={() => trace("Actual", [...(me.evidence_ids ?? []), "assumption:regulations.gwp100_ch4", "tceq_steers"])}>
                <dt className="label">Actual</dt>
                <dd className="mt-1"><span className="text-6xl font-extrabold tracking-tight text-alert-red">{fmt(core.actual.co2e_t_h)}</span>
                  <span className="ml-2 text-lg text-muted">t CO₂e per hour</span></dd>
                <dd className="text-sm text-muted">
                  {fmt(core.actual.ch4_kg_h / 1000, 1)} t CH₄ per hour · {fmt(core.ratio)} times the threshold · reported to TCEQ: {core.reported_same_day ? "yes" : "no"}
                </dd>
              </button>
            </dl>
          ) : <p className="mt-6 text-muted">No satellite observation is available for this facility and date.</p>}
          <p className="mt-3 text-xs text-muted">CO₂-equivalent uses GWP100 = {core?.gwp100_ch4 ?? 29.8} for methane. {v.disclaimer}</p>
        </div>
        {overlay ? (
          <Figure n={1} caption={`EMIT methane (CH₄) enhancement over the site, ${v.event_date_utc} 14:45 UTC. White outline: attributed plume.`}>
            <img src={runFileUrl(run.runId!, overlay)} alt="EMIT methane enhancement over the site" className="w-full" />
          </Figure>
        ) : run.charts.plume_map && (
          <Figure n={1} caption="EMIT methane enhancement."><Plot figure={run.charts.plume_map.figure_json} height={520} /></Figure>
        )}
      </div>
    </Section>
  );
}

function KeyEvidence({ v }: { v: Verdict }) {
  const ke = (v.key_evidence ?? []).slice(0, 6);
  if (!ke.length) return null;
  return (
    <Section title="Key evidence">
      <ol className="list-decimal space-y-2 pl-6 text-[15px]">
        {ke.map((k: any) => (
          <li key={k.id} className="pl-1">
            <b className="text-ink">{k.label || k.text}</b>
            {k.reason && !k.reason.startsWith("hybrid rank") && <span className="text-muted"> — {k.reason}</span>}
            <span className="ml-2 text-xs text-muted">({SOURCE_NAMES[k.source] ?? k.source}{k.flags?.length ? `; ${k.flags.join(", ").replace(/_/g, " ")}` : ""})</span>
          </li>
        ))}
      </ol>
      <p className="mt-3 text-xs text-muted">Ranked by hybrid search (BM25 and dense vectors) and a language-model rerank.</p>
    </Section>
  );
}

function Findings({ v }: { v: Verdict }) {
  if (!v.regulatory_findings.length) return null;
  return (
    <Section title="Regulatory findings">
      <table className="w-full border border-rule text-sm">
        <thead className="bg-paper text-left text-xs uppercase tracking-wide text-muted">
          <tr><th className="px-4 py-2">Rule</th><th className="px-4 py-2">Status</th><th className="hidden px-4 py-2 md:table-cell">Observed</th></tr>
        </thead>
        <tbody>
          {v.regulatory_findings.map((r) => (
            <tr key={r.rule_id} className="border-t border-rule align-top">
              <td className="px-4 py-2.5 font-semibold text-ink">{RULE_NAMES[r.rule_id] ?? r.rule_id}</td>
              <td className="px-4 py-2.5"><StatusBadge status={r.status} /></td>
              <td className="hidden px-4 py-2.5 text-muted md:table-cell">{r.observed !== "n/a" ? r.observed : "Not assessed: data not available"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Section>
  );
}

function Figures({ run }: { run: RunState }) {
  const ids = FIGURES.filter((c) => run.charts[c]);
  if (!ids.length) return null;
  return (
    <Section title="Figures">
      <div className="grid gap-6 lg:grid-cols-2">
        {ids.map((c, i) => (
          <Figure key={c} n={i + 2} caption={run.charts[c].title}>
            <Plot figure={run.charts[c].figure_json} height={380} />
          </Figure>
        ))}
      </div>
    </Section>
  );
}

function Accordion({ title, open, onToggle, children }: { title: string; open: boolean; onToggle: () => void; children: ReactNode }) {
  return (
    <div className="border border-rule">
      <button onClick={onToggle} aria-expanded={open}
        className="flex w-full items-center justify-between bg-paper px-5 py-3 text-left font-bold text-ink hover:bg-[#e6e6e6]">
        {title}<span aria-hidden className="text-xl leading-none">{open ? "−" : "+"}</span>
      </button>
      {open && <div className="border-t border-rule p-5">{children}</div>}
    </div>
  );
}

export function Report({ run, f }: { run: RunState; f: Facility | null }) {
  const v = run.verdict!;
  const [open, setOpen] = useState<{ sources: boolean; steps: boolean }>({ sources: false, steps: false });
  const [tab, setTab] = useState<"data" | "method">("data");
  const moreRef = useRef<HTMLDivElement>(null);
  const showSources = () => {
    setOpen((o) => ({ ...o, sources: true })); setTab("data");
    setTimeout(() => moreRef.current?.scrollIntoView({ behavior: "smooth" }), 60);
  };
  return (
    <div>
      <SiteHeader right={<a href="/" className="font-semibold text-white underline underline-offset-2">New assessment</a>} />
      <Hero v={v} f={f} />
      <Summary v={v} run={run} onSources={showSources} />
      <KeyEvidence v={v} />
      <Findings v={v} />
      <Figures run={run} />
      <Section title="Records">
        <div className="mb-5 flex flex-wrap gap-3">
          <a className="btn-dark" href={`/api/runs/${run.runId}/report.html`} target="_blank" rel="noreferrer">Export report</a>
          <a className="btn-light" href={`/api/runs/${run.runId}/evidence.zip`}>Download evidence (.zip)</a>
        </div>
        <div ref={moreRef} className="scroll-mt-20 space-y-2">
          <Accordion title="Sources and method" open={open.sources} onToggle={() => setOpen((o) => ({ ...o, sources: !o.sources }))}>
            <div className="mb-4"><Segmented value={tab} onChange={setTab} options={[{ value: "data", label: "Data used" }, { value: "method", label: "Method" }]} /></div>
            {tab === "data" ? <EvidencePanel run={run} /> : <MethodTab run={run} />}
          </Accordion>
          <Accordion title="Agent steps" open={open.steps} onToggle={() => setOpen((o) => ({ ...o, steps: !o.steps }))}>
            <Trajectory run={run} compact />
          </Accordion>
        </div>
      </Section>
    </div>
  );
}
