import { useEffect, useMemo, useRef, useState } from "react";
import { RunEvent } from "../lib/api";
import { useTrace } from "../lib/trace";
import { RunState } from "../lib/useRun";
import { Spinner } from "./ui";

const titleCase = (s: string) => s.replace(/[-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

const CHART_NAMES: Record<string, string> = {
  plume_map: "plume map", emission_distribution: "emission distribution", flare_timeline: "flare timeline",
  reporting_timeline: "reporting timeline", regulatory_comparison: "regulatory comparison", annual_scenarios: "annual projection",
  wind_sensitivity: "wind sensitivity", wind_timeseries: "wind record", report_comparison: "report comparison",
};
const DOCS: Record<string, string> = { tceq_sob: "the Title V permit (Statement of Basis)", tceq_steers: "TCEQ emissions-event reports" };
const IMAGES: Record<string, string> = { s2_truecolor: "Sentinel-2 true-colour image", s2_swir: "Sentinel-2 shortwave-infrared image" };

/** Plain-language label for a tool call — the trajectory never shows raw responses. */
export function stepLabel(name: string, args: any = {}): string {
  switch (name) {
    case "list_skills": return "Reviewing analysis playbooks";
    case "load_skill": return `Reading playbook: ${titleCase(args.name ?? "")}`;
    case "find_facility": return "Looking up the facility";
    case "list_available_data": return "Inventorying available data";
    case "describe_dataset": return `Inspecting dataset: ${args.slot_id}`;
    case "plume_map": return "Mapping the methane plume";
    case "get_wind": return "Retrieving wind at the satellite overpass";
    case "compute_emission_rate": return "Estimating the emission rate (Monte Carlo)";
    case "compare_estimates": return "Cross-checking against Carbon Mapper";
    case "flare_activity": return "Checking flare heat signatures";
    case "physics_bounds": return "Testing against plant capacity";
    case "annualize": return "Projecting annual emissions";
    case "reporting_timeline": return "Matching against TCEQ emissions-event reports";
    case "check_regulations": return "Screening against federal and Texas rules";
    case "rank_evidence": return "Ranking evidence by importance";
    case "analyze_chart": return `Reading the ${CHART_NAMES[args.chart_id] ?? args.chart_id}`;
    case "analyze_image": return `Inspecting the ${IMAGES[args.image_id] ?? args.image_id}`;
    case "read_document": return `Reading ${DOCS[args.doc_id] ?? args.doc_id}`;
    case "show_chart": return "Preparing figures";
    case "submit_verdict": return "Writing the verdict";
    default: return titleCase(name);
  }
}

/** Which system each tool draws on — shown as a small tag beside the step. */
const SOURCE_TAG: Record<string, string> = {
  plume_map: "NASA EMIT", compute_emission_rate: "NASA EMIT", get_wind: "ERA5", flare_activity: "NASA VIIRS",
  compare_estimates: "Carbon Mapper", physics_bounds: "Permit data", reporting_timeline: "TCEQ", check_regulations: "Federal and Texas rules",
  annualize: "Projection", rank_evidence: "Hybrid search · GPT", analyze_chart: "Huawei OMNI", analyze_image: "Huawei OMNI",
  read_document: "Huawei OMNI", describe_dataset: "Data inventory", list_available_data: "Data inventory",
};

type Media = { src: string; caption: string; kind: "page" | "image" | "chart" };
type Step = { id: string; name: string; label: string; status: "running" | "ok" | "data_gap" | "error"; callIds: string[]; media: Media[] };

const runFile = (runId: string, ref: string) => `/api/runs/${runId}/${ref.replace(/^\/+/, "")}`;

function buildSteps(events: RunEvent[]): Step[] {
  const steps: Step[] = [];
  const byCall: Record<string, Step> = {};
  let current: Step | null = null;
  const addMedia = (st: Step | null, m: Media) => { if (st && !st.media.some((x) => x.src === m.src)) st.media.push(m); };
  for (const ev of events) {
    if (ev.type === "tool_call") {
      const label = stepLabel(ev.name, ev.args);
      const last = steps[steps.length - 1];
      if (ev.name === "show_chart" && last?.label === label) { // collapse repeated figure selection
        last.callIds.push(ev.call_id); byCall[ev.call_id] = last; last.status = "running"; current = last; continue;
      }
      const st: Step = { id: ev.call_id, name: ev.name, label, status: "running", callIds: [ev.call_id], media: [] };
      byCall[ev.call_id] = st; steps.push(st); current = st;
    } else if (ev.type === "tool_result" && byCall[ev.call_id]) {
      const st = byCall[ev.call_id];
      st.status = ev.status === "ok" ? "ok" : ev.status === "data_gap" ? "data_gap" : ev.name === "submit_verdict" ? "running" : "error";
      if (ev.data?.overlay_ref) addMedia(st, { src: runFile(ev.run_id, ev.data.overlay_ref), caption: "EMIT methane over the site", kind: "image" });
    } else if (ev.type === "chart") {
      const st = byCall[ev.call_id] ?? current;
      if (st && st.name !== "show_chart") addMedia(st, { src: `/api/charts/${ev.chart_id}.png?r=${ev.run_id}`, caption: ev.title, kind: "chart" });
    } else if (ev.type === "omni_analysis") {
      if (ev.tool === "read_document" && Array.isArray(ev.all_inputs)) {
        ev.all_inputs.forEach((ref: string, i: number) =>
          addMedia(current, { src: runFile(ev.run_id, ref), caption: ev.pages?.[i] ? `Page ${ev.pages[i]}` : "Document", kind: "page" }));
      } else if (ev.thumbnail_url) {
        addMedia(current, { src: ev.thumbnail_url, caption: ev.tool === "analyze_image" ? "Satellite image sent for reading" : "Chart sent for reading",
          kind: ev.tool === "analyze_image" ? "image" : "chart" });
      }
    }
  }
  return steps;
}

function Icon({ status }: { status: Step["status"] }) {
  if (status === "running") return <Spinner />;
  if (status === "ok") return (
    <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 text-alert-green" aria-label="done"><path fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="square" d="M3.5 8.5l3 3 6-7" /></svg>
  );
  if (status === "data_gap") return <span className="block h-2 w-2 bg-alert-amber" aria-label="data gap" />;
  return <span className="block h-2 w-2 bg-alert-red" aria-label="error" />;
}

function MediaStrip({ media, onOpen }: { media: Media[]; onOpen: (m: Media) => void }) {
  if (!media.length) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {media.map((m) => (
        <figure key={m.src} className="fade-up">
          <button type="button" onClick={() => onOpen(m)} className="block border border-rule bg-panel2 p-0.5 hover:border-gold"
            aria-label={`Enlarge: ${m.caption}`}>
            <img src={m.src} alt={m.caption} loading="lazy"
              className={`${m.kind === "page" ? "h-36 w-auto" : "h-28 w-auto max-w-[220px] object-cover"} block bg-panel`} />
          </button>
          <figcaption className="mt-0.5 max-w-[220px] truncate text-[11px] text-muted">{m.caption}</figcaption>
        </figure>
      ))}
    </div>
  );
}

export function Trajectory({ run, title, compact = false }: { run: RunState; title?: string; compact?: boolean }) {
  const steps = useMemo(() => buildSteps(run.events), [run.events]);
  const { sel } = useTrace();
  const end = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState<Media | null>(null);
  const running = run.status === "running" || run.status === "starting";
  const mediaCount = steps.reduce((n, st) => n + st.media.length, 0);
  useEffect(() => { if (running && !compact) end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [steps.length, mediaCount, running, compact]);
  useEffect(() => {
    if (!zoom) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setZoom(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [zoom]);
  return (
    <div className="space-y-4">
      {title && (
        <div className="flex items-center gap-3">
          {running && <Spinner className="h-4 w-4" />}
          <div>
            <div className="font-display text-xl text-ink">{title}</div>
            <div className="text-sm text-muted">{running ? "The agent is working" : "Finished"} · {steps.length} steps</div>
          </div>
        </div>
      )}
      <ol className="relative space-y-1 border-l-2 border-rule pl-5">
        {steps.map((st, i) => {
          const hl = !!sel?.callIds.some((c) => st.callIds.includes(c));
          const tag = SOURCE_TAG[st.name];
          return (
            <li key={st.id} className={`fade-up relative py-1.5 pr-2 text-sm ${hl ? "bg-panel2" : ""}`}
              style={{ animationDelay: `${Math.min(i * 10, 80)}ms` }}>
              <span className="absolute -left-[27px] top-2 flex h-4 w-4 items-center justify-center bg-page">
                <Icon status={st.status} />
              </span>
              <div className="flex flex-wrap items-baseline gap-x-2">
                <span className={st.status === "running" ? "font-bold text-ink" : "text-ink"}>{st.label}</span>
                {tag && <span className="text-[10px] font-bold uppercase tracking-wide text-muted">{tag}</span>}
                {st.status === "data_gap" && <span className="text-[11px] font-semibold text-alert-amber">data gap</span>}
              </div>
              <MediaStrip media={st.media} onOpen={setZoom} />
            </li>
          );
        })}
        {running && steps.length === 0 && <li className="py-1.5 text-sm text-muted">Starting…</li>}
      </ol>
      <div ref={end} />
      {zoom && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-2 bg-black/80 p-6" onClick={() => setZoom(null)}
          role="dialog" aria-modal="true" aria-label={zoom.caption}>
          <img src={zoom.src} alt={zoom.caption} className="max-h-[85vh] max-w-full border border-rule bg-panel" />
          <div className="text-sm text-ink">{zoom.caption} · click or press Esc to close</div>
        </div>
      )}
    </div>
  );
}
