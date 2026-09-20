import { useMemo } from "react";
import { LedgerRecord, runFileUrl } from "../lib/api";
import { useTrace } from "../lib/trace";
import { RunState } from "../lib/useRun";
import { CsvTable, useCsv } from "./CsvTable";
import { Chip, ShortHash } from "./ui";

const PROVIDER_TONE: Record<string, any> = { NASA: "sky", "Carbon Mapper": "violet", Copernicus: "emerald", TCEQ: "amber", "Open-Meteo": "slate" };

function toolData(run: RunState, name: string): any {
  const ev = [...run.events].reverse().find((e) => e.type === "tool_result" && e.name === name && e.status === "ok");
  return ev?.data ?? {};
}

function DataPreview({ rec, run }: { rec: LedgerRecord; run: RunState }) {
  const id = run.runId!;
  const u = (ref: string) => runFileUrl(id, ref);
  switch (rec.slot_id) {
    case "emit_ch4enh": {
      const pm = toolData(run, "plume_map");
      return (
        <div className="space-y-2">
          <div className="flex gap-3">
            <img src={u("evidence/emit_quicklook.png")} alt="EMIT crop quicklook with plume mask in orange"
              className="h-40 w-40 flex-none border border-rule object-cover [image-rendering:pixelated]" />
            <p className="text-[11px] text-muted">
              Crop quicklook (enhancement, mask pixels in orange). Using <b className="text-ink">{pm.n_pixels?.toLocaleString() ?? "?"}</b> of{" "}
              <b className="text-ink">{pm.valid_pixels_in_crop?.toLocaleString() ?? "?"}</b> valid pixels in the crop (k = {pm.k_default}).
              Background {pm.background_mu_ppm_m} ± {pm.background_sigma_ppm_m} ppm·m from {pm.background_pixels?.toLocaleString()} annulus pixels.
              <br /><a className="link" href={u("evidence/emit_crop.tif")}>Download GeoTIFF crop</a>
            </p>
          </div>
          <CsvTable url={u("evidence/emit_plume_pixels.csv")} caption="Plume-mask pixels (sortable)" />
        </div>
      );
    }
    case "emit_ch4uncert":
      return <p className="text-[11px] text-muted">Per-pixel 1σ values for the same mask pixels are in the <code>uncert_ppm_m</code> column of the EMIT pixel table above.</p>;
    case "carbonmapper": {
      return <CarbonMapperPreview run={run} />;
    }
    case "wind":
      return <CsvTable url={u("evidence/wind_hourly_near_overpass.csv")} highlight={(r) => String(r.time).includes("interpolated")}
        caption="Hourly rows around the overpass; interpolated overpass row highlighted" />;
    case "firms": {
      const fa = toolData(run, "flare_activity");
      const keys = [fa.nearest_before_overpass?.time_utc, fa.nearest_after_overpass?.time_utc].filter(Boolean).map((t: string) => t.slice(0, 10) + (t.slice(11, 13) + t.slice(14, 16)));
      return <CsvTable url={u("evidence/firms_subset.csv")}
        columns={["acq_date", "acq_time", "satellite", "product", "frp", "confidence", "daynight", "dist_km", "hours_from_overpass"]}
        highlight={(r) => keys.includes(r.acq_date + String(r.acq_time).padStart(4, "0"))}
        caption="VIIRS detections within 1.5 km; nearest detections before/after the overpass highlighted" />;
    }
    case "s2_truecolor":
    case "s2_swir":
      return (
        <div className="flex gap-3">
          {rec.preview_ref && <a href={u(rec.preview_ref)} target="_blank" rel="noreferrer"><img src={u(rec.preview_ref)} alt="image sent to OMNI" className="h-28 border border-rule" /></a>}
          <p className="text-[11px] text-muted">Exact image sent to Huawei OMNI (full scene with facility marker + 8× zoom). Acquisition shown in header: 2026-09-18. Bounds approximate (fitted from town labels).</p>
        </div>
      );
    case "tceq_sob": {
      const refs = [rec.preview_ref, ...(rec.extra_refs ?? [])].filter((r) => r && r.endsWith(".png")) as string[];
      return (
        <div className="space-y-2">
          <div className="flex gap-2 overflow-x-auto">
            {refs.map((r) => <a key={r} href={u(r)} target="_blank" rel="noreferrer"><img src={u(r)} alt={r} className="h-32 border border-rule bg-panel2" /></a>)}
          </div>
          <CsvTable url={u("evidence/tceq_sob_snippets.csv")} caption="Extracted text snippets (keyword matches) from the pages sent" pageSize={6} />
        </div>
      );
    }
    case "tceq_steers":
      return (
        <div className="space-y-2">
          <CsvTable url={u("evidence/steers_events.csv")} columns={["incident_no", "start_date", "end_date", "duration_h", "facility", "event_type", "methane_reported"]}
            caption="STEERS incidents parsed from the exports" />
          {run.omniCalls.some((c) => c.target_id === "tceq_steers") && (
            <a href={u("evidence/omni_tceq_steers_table.png")} target="_blank" rel="noreferrer" className="link text-[11px]">Table image sent to OMNI</a>
          )}
        </div>
      );
    default:
      return null;
  }
}

function CarbonMapperPreview({ run }: { run: RunState }) {
  const u = (ref: string) => runFileUrl(run.runId!, ref);
  const match = useCsv(u("evidence/carbonmapper_match.csv"));
  const pid = match.data?.rows[0]?.plume_id;
  return <CsvTable url={u("evidence/carbonmapper_rows.csv")} columns={["plume_id", "datetime_utc", "emission_rate_kg_h", "emission_uncertainty_kg_h", "instrument", "detected", "synthetic"]}
    highlight={(r) => !!pid && r.plume_id === pid} caption="Rows used; the matching plume row is highlighted" />;
}

function SourceCard({ rec, run, active }: { rec: LedgerRecord; run: RunState; active: boolean }) {
  return (
    <div id={`ledger-${rec.id}`} className={`space-y-2 border p-3 ${active ? "border-accent" : "border-rule"} bg-panel`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            {rec.provider && <Chip tone={PROVIDER_TONE[rec.provider] ?? "slate"}>{rec.provider}</Chip>}
            <span className="text-[15px] font-bold text-ink">{rec.source_name}</span>
            {rec.synthetic && <Chip tone="violet">SYNTHETIC placeholder</Chip>}
            {rec.quality === "low" && <Chip tone="amber">low quality</Chip>}
          </div>
          <div className="mt-1 text-[11px] text-muted"><code>{rec.file}</code> · <ShortHash hash={rec.sha256} /> · {rec.date_coverage}</div>
        </div>
        {rec.preview_ref && (
          <a href={runFileUrl(run.runId!, rec.preview_ref)} className="border border-rule px-2 py-1 text-[11px] text-muted hover:border-accent hover:text-accent">⬇ Download subset</a>
        )}
      </div>
      <div className="text-[11px] text-muted">{rec.citation} · {rec.source_url && <a href={rec.source_url} target="_blank" rel="noreferrer" className="link">source</a>}</div>
      {rec.subset && <div className="text-[11px] text-muted"><span className="text-muted">Subset used:</span> {rec.subset}</div>}
      {rec.warnings && rec.warnings.length > 0 && <ul className="list-disc pl-5 text-[11px] text-alert-amber">{rec.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>}
      <div className="flex flex-wrap items-center gap-1 text-[11px] text-muted">Used by {rec.used_by_tools.map((t) => <Chip key={t}>{t}</Chip>)}</div>
      <DataPreview rec={rec} run={run} />
    </div>
  );
}

export function EvidencePanel({ run }: { run: RunState }) {
  const { sel } = useTrace();
  const data = useMemo(() => run.ledger.filter((r) => r.type === "data"), [run.ledger]);
  const assumptions = useMemo(() => run.ledger.filter((r) => r.type === "assumption"), [run.ledger]);
  const derived = useMemo(() => run.ledger.filter((r) => r.type === "derived"), [run.ledger]);
  const active = (id: string) => !!sel?.evidenceIds.includes(id);
  if (!run.runId) return <p className="text-sm text-muted">Run an assessment to see the data it used.</p>;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted">{data.length} datasets, {assumptions.length} assumptions, {run.omniCalls.length} AI analyses in this run's Evidence Ledger.</p>
        <a href={`/api/runs/${run.runId}/evidence.zip`} className="border border-accent/60 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-accent hover:text-accent-light">⬇ Download all evidence (.zip)</a>
      </div>
      <section className="space-y-3">
        <h4 className="label">Measured data</h4>
        {data.map((r) => <SourceCard key={r.id} rec={r} run={run} active={active(r.id)} />)}
        {derived.map((r) => (
          <div key={r.id} id={`ledger-${r.id}`} className={`border p-3 text-[11px] text-muted ${active(r.id) ? "border-accent" : "border-rule"}`}>
            <b className="text-ink">{r.name}</b> · {r.record_count?.toLocaleString()} values · {r.source}
            {r.preview_ref && <> · <a className="link" href={runFileUrl(run.runId!, r.preview_ref)}>download</a></>}
          </div>
        ))}
      </section>
      <section className="space-y-2">
        <h4 className="label">Assumptions (hard-coded inputs, not measurements)</h4>
        <div className="overflow-x-auto border border-rule">
          <table className="w-full text-[11px]">
            <thead className="bg-panel2 text-left text-muted"><tr><th className="px-2 py-1">Constant</th><th className="px-2 py-1">Value</th><th className="px-2 py-1">Rationale</th><th className="px-2 py-1">Used by</th></tr></thead>
            <tbody>
              {assumptions.map((a) => (
                <tr key={a.id} id={`ledger-${a.id}`} className={`border-t border-rule align-top ${active(a.id) ? "bg-panel2" : ""}`}>
                  <td className="px-2 py-1 font-mono text-muted">{a.name}{a.verify && <span className="ml-1"><Chip tone="amber">needs verification</Chip></span>}</td>
                  <td className="whitespace-nowrap px-2 py-1 font-mono text-ink">{JSON.stringify(a.value)} {a.unit}{a.range ? <span className="text-muted"> (range {a.range.join("–")})</span> : null}</td>
                  <td className="px-2 py-1 text-muted">{a.rationale} <span className="text-muted/70">[{a.source}]</span></td>
                  <td className="px-2 py-1 text-muted">{a.used_by_tools.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="space-y-2">
        <h4 className="label">AI analysis log (Huawei OMNI)</h4>
        {run.omniCalls.map((c) => (
          <div key={c.id} id={`ledger-${c.id}`} className={`flex gap-3 border p-3 ${active(c.id) ? "border-accent" : "border-rule"}`}>
            {c.input_ref && <a href={runFileUrl(run.runId!, c.input_ref)} target="_blank" rel="noreferrer"><img src={runFileUrl(run.runId!, c.input_ref)} alt="" className="h-16 w-24 flex-none border border-rule bg-panel2 object-cover" /></a>}
            <div className="min-w-0 text-[11px]">
              <div className="flex flex-wrap items-center gap-2">
                <code className="text-muted">{c.id}</code><Chip>{c.tool}</Chip><span className="text-muted">{c.target_id}</span>
                <Chip tone={c.mode === "LIVE" ? "emerald" : c.mode === "CACHED" ? "sky" : "amber"}>{c.mode}</Chip>
                <span className="text-muted">{c.model} · {c.timestamp}</span>
              </div>
              <div className="mt-1 text-muted">Q: {c.question}</div>
              <div className="mt-1 line-clamp-4 whitespace-pre-wrap text-ink/85">{c.answer}</div>
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}
