import { ReactNode, useRef, useState } from "react";
import { Facility, runFileUrl, Verdict } from "../lib/api";
import { useCountUp, useInView } from "../lib/hooks";
import { useTrace } from "../lib/trace";
import { RunState } from "../lib/useRun";
import { EvidencePanel } from "./EvidencePanel";
import { FieldNote } from "./FieldNote";
import { SiteHeader } from "./Header";
import { MethodTab } from "./MethodTab";
import { Plot } from "./Plot";
import { Trajectory } from "./Trajectory";
import { Eyebrow, Segmented, StatusBadge } from "./ui";

const FIGURES = ["emission_distribution", "report_comparison", "flare_timeline", "regulatory_comparison"];
const FIGURE_HEIGHT: Record<string, number> = { flare_timeline: 470 };
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

function Section({ id, title, eyebrow, children, flush = false }: {
  id?: string; title?: string; eyebrow?: string; children: ReactNode; flush?: boolean;
}) {
  const { ref, inView } = useInView<HTMLDivElement>(0.12);
  return (
    <section id={id} className={`mx-auto max-w-6xl scroll-mt-20 px-6 py-14 ${flush ? "" : "border-t border-rule"}`}>
      <div ref={ref} className={`reveal ${inView ? "in" : ""}`}>
        {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
        {title && <h2 className="h2 mb-6 mt-3">{title}</h2>}
        {children}
      </div>
    </section>
  );
}

/** Result banner: the facility and the one-line reason set in white over the site imagery. */
function ResultBanner({ v, f }: { v: Verdict; f: Facility | null }) {
  const img = f?.data_status === "cached" ? `/api/facilities/${f.facility_id}/imagery/site` : null;
  return (
    <section className="relative overflow-hidden bg-primary-darker">
      {img && <img src={img} alt="" aria-hidden className="slow-zoom absolute inset-0 h-full w-full object-cover" />}
      <div className="absolute inset-0 bg-gradient-to-r from-primary-darker/95 via-primary-darker/85 to-primary-darker/55" aria-hidden />
      <div className="relative mx-auto max-w-6xl px-6 py-16">
        <p className="flex items-center gap-2 text-[12px] font-bold uppercase tracking-[0.1em] text-white/80">
          <span className="block h-[3px] w-6 bg-white/80" aria-hidden />Screening result
        </p>
        <h1 className="mt-4 text-3xl font-bold leading-tight tracking-tight text-white sm:text-5xl">{v.facility_name}</h1>
        <p className="mt-3 text-[15px] text-white/80">
          Event date {v.event_date_utc}{f ? ` · ${f.county} County, ${f.state}` : ""}
          {f?.operator ? ` · ${f.operator.split(" — ")[0]}` : ""}
        </p>
        {v.outcome?.reason && <p className="mt-6 max-w-3xl text-lg leading-relaxed text-white">{v.outcome.reason}</p>}
      </div>
      {img && <span className="absolute bottom-1 right-3 text-[10px] text-white/60">Imagery: Esri, Maxar, Earthstar Geographics</span>}
    </section>
  );
}

/** Log-scale bar comparing the observed rate with the threshold — the ×N gap at a glance. */
function ScaleBar({ ratio }: { ratio: number }) {
  const { ref, inView } = useInView<HTMLDivElement>(0.4);
  const decades = Math.max(3, Math.ceil(Math.log10(Math.max(ratio, 10))) + 1); // headroom past the value
  const pct = (Math.log10(Math.max(ratio, 1)) / decades) * 100;
  return (
    <div ref={ref} className="mt-6">
      <div className="flex items-end justify-between text-[11px] font-semibold uppercase tracking-wide">
        <span className="text-muted">Federal threshold</span>
        <span className="text-alert-red">{Math.round(ratio).toLocaleString()}× over</span>
      </div>
      <div className="relative mt-1 h-7 w-full border border-rule bg-panel2">
        <div className="absolute inset-y-0 left-0 bg-alert-red transition-[width] duration-[1200ms] ease-out" style={{ width: inView ? `${pct}%` : "0%" }} />
        {Array.from({ length: decades }, (_, i) => i + 1).map((d) => (
          <span key={d} className="absolute inset-y-0 w-px bg-rule" style={{ left: `${(d / decades) * 100}%` }} aria-hidden />
        ))}
        <span className="absolute inset-y-0 left-0 w-[3px] bg-ink" aria-hidden />
      </div>
      <div className="relative mt-0.5 h-4 text-[10px] text-muted">
        <span className="absolute left-0">1×</span>
        {Array.from({ length: decades }, (_, i) => i + 1).map((d) => (
          <span key={d} className="absolute -translate-x-1/2" style={{ left: `${(d / decades) * 100}%` }}>{`10${"⁰¹²³⁴⁵"[d] ?? ""}×`}</span>
        ))}
      </div>
    </div>
  );
}

function Figure({ n, caption, children }: { n: number; caption: string; children: ReactNode }) {
  return (
    <figure className="border border-rule">
      {children}
      <figcaption className="border-t border-rule bg-panel2 px-3 py-2 text-sm"><b>Figure {n}.</b> {caption}</figcaption>
    </figure>
  );
}

function Summary({ v, f, run, onSources }: { v: Verdict; f: Facility | null; run: RunState; onSources: () => void }) {
  const core = v.report_comparison?.core;
  const counted = useCountUp(core?.actual.co2e_t_h, true, 1100);
  const { setSel } = useTrace();
  const overlay = run.ledger.find((r) => r.slot_id === "site_imagery")?.preview_ref;
  const trace = (label: string, ids: string[]) => { setSel({ label, evidenceIds: ids, callIds: [] }); onSources(); };
  const me = v.methane_estimate;
  return (
    <>
    <ResultBanner v={v} f={f} />
    <Section id="summary" flush>
      <div className="grid gap-8 lg:grid-cols-2">
        <div>
          {core ? (
            <dl className="divide-y divide-rule border-y border-rule">
              <button type="button" className="block w-full py-5 text-left hover:bg-panel" title="Show sources"
                onClick={() => trace("Allowed", ["assumption:regulations.super_emitter_kg_h", "assumption:regulations.gwp100_ch4"])}>
                <dt className="label">Federal threshold</dt>
                <dd className="mt-1"><span className="text-6xl font-bold tracking-tight tabular-nums text-ink">{fmt(core.allowed.co2e_t_h, 1)}</span>
                  <span className="ml-2 text-lg text-muted">t CO₂e per hour</span></dd>
                <dd className="text-sm text-muted">EPA super-emitter threshold, {fmt(core.allowed.ch4_kg_h)} kg CH₄ per hour</dd>
              </button>
              <button type="button" className="block w-full py-5 text-left hover:bg-panel" title="Show sources"
                onClick={() => trace("Actual", [...(me.evidence_ids ?? []), "assumption:regulations.gwp100_ch4", "tceq_steers"])}>
                <dt className="label">Observed</dt>
                <dd className="mt-1"><span className="text-6xl font-bold tracking-tight tabular-nums text-alert-red">{fmt(counted ?? core.actual.co2e_t_h)}</span>
                  <span className="ml-2 text-lg text-muted">t CO₂e per hour</span></dd>
                <dd className="text-sm text-muted">
                  {fmt(core.actual.ch4_kg_h / 1000, 1)} t CH₄ per hour · {fmt(core.ratio)} times the threshold · reported to TCEQ: {core.reported_same_day ? "yes" : "no"}
                </dd>
              </button>
            </dl>
          ) : <p className="text-muted">No satellite observation is available for this facility and date.</p>}
          {core && <ScaleBar ratio={core.ratio} />}
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
    </>
  );
}

function KeyEvidence({ v }: { v: Verdict }) {
  const ke = (v.key_evidence ?? []).slice(0, 6);
  if (!ke.length) return null;
  return (
    <Section title="Key evidence" eyebrow="What mattered most">
      <ol className="list-decimal space-y-2 pl-6 text-[15px]">
        {ke.map((k: any) => (
          <li key={k.id} className="pl-1">
            <span className="mb-1 mt-0.5 block h-1 w-24 bg-rule" aria-hidden>
              <span className="block h-1 bg-accent" style={{ width: `${Math.round((k.importance ?? 0) * 100)}%` }} />
            </span>
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
    <Section title="Regulatory findings" eyebrow="Rules screened">
      <table className="w-full border border-rule text-sm">
        <thead className="bg-panel2 text-left text-[11px] uppercase tracking-[0.16em] text-muted">
          <tr><th className="px-4 py-2">Rule</th><th className="px-4 py-2">Status</th><th className="hidden px-4 py-2 md:table-cell">Observed</th></tr>
        </thead>
        <tbody>
          {v.regulatory_findings.map((r) => (
            <tr key={r.rule_id} className="border-t border-rule align-top">
              <td className="px-4 py-2.5 text-ink">{RULE_NAMES[r.rule_id] ?? r.rule_id}</td>
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
    <Section title="Figures" eyebrow="The measurements">
      <div className="grid items-start gap-6 lg:grid-cols-2">
        {ids.map((c, i) => (
          <Figure key={c} n={i + 2} caption={run.charts[c].title}>
            <Plot figure={run.charts[c].figure_json} height={FIGURE_HEIGHT[c] ?? 380} />
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
        className="flex w-full items-center justify-between bg-panel2 px-5 py-3 text-left text-base font-bold text-ink hover:text-accent">
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
      <SiteHeader right={<a href="/" className="hover:text-accent">New assessment</a>} />
      <Summary v={v} f={f} run={run} onSources={showSources} />
      <KeyEvidence v={v} />
      <Findings v={v} />
      <Figures run={run} />
      <Section title="From the field" eyebrow="Spoken follow-up">
        <FieldNote facilityId={v.facility_id ?? f?.facility_id ?? ""} context={v.outcome?.reason} />
      </Section>
      <Section title="Records" eyebrow="Download and audit">
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
