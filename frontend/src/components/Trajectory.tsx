import { useEffect, useMemo, useRef } from "react";
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
    case "load_skill": return `Reading playbook · ${titleCase(args.name ?? "")}`;
    case "find_facility": return "Looking up the facility";
    case "list_available_data": return "Inventorying available data";
    case "describe_dataset": return `Inspecting dataset · ${args.slot_id}`;
    case "plume_map": return "Mapping the methane plume · NASA EMIT";
    case "get_wind": return "Retrieving wind at the satellite overpass";
    case "compute_emission_rate": return "Estimating the emission rate · Monte Carlo";
    case "compare_estimates": return "Cross-checking against Carbon Mapper";
    case "flare_activity": return "Checking flare heat signatures · NASA VIIRS";
    case "physics_bounds": return "Testing against plant capacity";
    case "annualize": return "Projecting annual emissions";
    case "reporting_timeline": return "Matching against TCEQ emissions-event reports";
    case "check_regulations": return "Screening against federal and Texas rules";
    case "analyze_chart": return `Huawei OMNI · reading the ${CHART_NAMES[args.chart_id] ?? args.chart_id}`;
    case "analyze_image": return `Huawei OMNI · inspecting the ${IMAGES[args.image_id] ?? args.image_id}`;
    case "read_document": return `Huawei OMNI · reading ${DOCS[args.doc_id] ?? args.doc_id}`;
    case "show_chart": return "Preparing figures";
    case "submit_verdict": return "Writing the verdict";
    default: return titleCase(name);
  }
}

type Step = { id: string; label: string; status: "running" | "ok" | "data_gap" | "error"; callIds: string[] };

function buildSteps(events: RunEvent[]): Step[] {
  const steps: Step[] = [];
  const byCall: Record<string, Step> = {};
  for (const ev of events) {
    if (ev.type === "tool_call") {
      const label = stepLabel(ev.name, ev.args);
      const last = steps[steps.length - 1];
      if (ev.name === "show_chart" && last?.label === label) { // collapse repeated figure selection
        last.callIds.push(ev.call_id); byCall[ev.call_id] = last; last.status = "running"; continue;
      }
      const s: Step = { id: ev.call_id, label, status: "running", callIds: [ev.call_id] };
      byCall[ev.call_id] = s; steps.push(s);
    } else if (ev.type === "tool_result" && byCall[ev.call_id]) {
      const s = byCall[ev.call_id];
      s.status = ev.status === "ok" ? "ok" : ev.status === "data_gap" ? "data_gap" : ev.name === "submit_verdict" ? "running" : "error";
    }
  }
  return steps;
}

function Icon({ status }: { status: Step["status"] }) {
  if (status === "running") return <Spinner />;
  if (status === "ok") return (
    <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 text-emerald-600" aria-label="done"><path fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d="M3.5 8.5l3 3 6-7" /></svg>
  );
  if (status === "data_gap") return <span className="block h-2 w-2 rounded-full bg-amber-500" aria-label="data gap" />;
  return <span className="block h-2 w-2 rounded-full bg-red-500" aria-label="error" />;
}

export function Trajectory({ run, title, compact = false }: { run: RunState; title?: string; compact?: boolean }) {
  const steps = useMemo(() => buildSteps(run.events), [run.events]);
  const { sel } = useTrace();
  const end = useRef<HTMLDivElement>(null);
  const running = run.status === "running" || run.status === "starting";
  useEffect(() => { if (running && !compact) end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [steps.length, running, compact]);
  return (
    <div className="space-y-4">
      {title && (
        <div className="flex items-center gap-3">
          {running && <Spinner className="h-4 w-4" />}
          <div>
            <div className="text-[15px] font-semibold text-slate-800">{title}</div>
            <div className="text-xs text-slate-400">{running ? "The agent is working" : "Finished"} · {steps.length} steps</div>
          </div>
        </div>
      )}
      <ol className="relative space-y-0.5 border-l border-slate-200 pl-5">
        {steps.map((s, i) => {
          const hl = !!sel?.callIds.some((c) => s.callIds.includes(c));
          return (
            <li key={s.id} className={`fade-up relative flex items-center gap-3 rounded-lg py-1.5 pr-2 text-sm ${hl ? "bg-sky-50" : ""}`}
              style={{ animationDelay: `${Math.min(i * 10, 80)}ms` }}>
              <span className="absolute -left-[27px] flex h-4 w-4 items-center justify-center rounded-full bg-white">
                <Icon status={s.status} />
              </span>
              <span className={s.status === "running" ? "font-medium text-slate-900" : "text-slate-600"}>{s.label}</span>
              {s.status === "data_gap" && <span className="text-[11px] text-amber-700">data gap</span>}
            </li>
          );
        })}
        {running && steps.length === 0 && <li className="py-1.5 text-sm text-slate-400">Starting…</li>}
      </ol>
      <div ref={end} />
    </div>
  );
}
