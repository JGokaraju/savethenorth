import { useMemo } from "react";
import { fmtDuration, useElapsed } from "../lib/hooks";
import { RunState } from "../lib/useRun";
import { Spinner } from "./ui";

const PHASES = ["Data discovery", "Quantification", "Cause", "Regulatory", "Verdict"] as const;

/** Which phase a tool belongs to (the skills drive the same order). */
const PHASE_OF: Record<string, number> = {
  list_skills: 0, find_facility: 0, list_available_data: 0, describe_dataset: 0,
  plume_map: 1, get_wind: 1, compute_emission_rate: 1, compare_estimates: 1,
  flare_activity: 2, physics_bounds: 2, annualize: 2,
  reporting_timeline: 3, check_regulations: 3,
  rank_evidence: 4, show_chart: 4, submit_verdict: 4,
};
const SKILL_PHASE: Record<string, number> = {
  "data-discovery": 0, "methane-quantification": 1, "flare-and-cause-analysis": 2, "texas-regulatory-check": 3, "verdict-report": 4,
};

export function RunProgress({ run }: { run: RunState }) {
  const live = run.status === "running" || run.status === "starting";
  const started = run.events[0]?.ts;
  const elapsed = useElapsed(started, live);

  const { phase, steps, reads, datasets } = useMemo(() => {
    let phase = 0, steps = 0, reads = 0;
    for (const e of run.events) {
      if (e.type === "tool_call") {
        steps++;
        const p = e.name === "load_skill" ? SKILL_PHASE[e.args?.name] : PHASE_OF[e.name];
        if (p != null) phase = Math.max(phase, p);
      }
      if (e.type === "omni_analysis") reads++;
    }
    return { phase, steps, reads, datasets: run.ledger.filter((r) => r.type === "data").length };
  }, [run.events, run.ledger]);

  const done = run.status === "finished";
  const pct = done ? 100 : Math.min(96, (phase / PHASES.length) * 100 + 8);

  return (
    <div className="border border-rule">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-rule bg-panel2 px-4 py-3">
        <div className="flex items-center gap-2.5">
          {live ? <Spinner className="h-4 w-4" /> : null}
          <span className="font-display text-lg text-ink">{done ? "Verification complete" : PHASES[phase]}</span>
          <span className="font-mono text-sm tabular-nums text-muted">{fmtDuration(elapsed)}</span>
        </div>
        <div className="flex gap-5 text-xs text-muted">
          <span><b className="font-mono text-sm text-ink">{steps}</b> steps</span>
          <span><b className="font-mono text-sm text-ink">{datasets}</b> datasets</span>
          <span><b className="font-mono text-sm text-ink">{reads}</b> AI readings</span>
        </div>
      </div>
      <div className="h-1 w-full bg-rule">
        <div className="h-1 bg-gold transition-[width] duration-700 ease-out" style={{ width: `${pct}%` }} />
      </div>
      <ol className="grid grid-cols-2 divide-y divide-rule sm:grid-cols-5 sm:divide-y-0">
        {PHASES.map((p, i) => {
          const state = done || i < phase ? "done" : i === phase ? "active" : "todo";
          return (
            <li key={p} className={`flex items-center gap-2 px-4 py-2.5 text-xs sm:border-l sm:border-rule sm:first:border-l-0 ${state === "active" ? "bg-panel2" : ""}`}>
              <span className={`flex h-4 w-4 flex-none items-center justify-center text-[10px] font-bold ${
                state === "done" ? "bg-[#008817] text-white" : state === "active" ? "bg-primary text-white" : "bg-rule text-muted"}`}>
                {state === "done" ? "✓" : i + 1}
              </span>
              <span className={state === "todo" ? "text-muted" : "font-semibold text-ink"}>{p}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
