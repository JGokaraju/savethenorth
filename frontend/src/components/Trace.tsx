import { useEffect, useMemo, useRef, useState } from "react";
import { RunEvent } from "../lib/api";
import { useTrace } from "../lib/trace";
import { RunState } from "../lib/useRun";
import { Plot } from "./Plot";
import { Chip, Skeleton, Spinner } from "./ui";

type Item =
  | { kind: "note"; ev: RunEvent }
  | { kind: "skill"; ev: RunEvent }
  | { kind: "error"; ev: RunEvent }
  | { kind: "start"; ev: RunEvent }
  | { kind: "verdict"; ev: RunEvent }
  | { kind: "call"; call: RunEvent; result?: RunEvent; charts: RunEvent[]; omni: RunEvent[] };

function buildItems(events: RunEvent[]): Item[] {
  const items: Item[] = [];
  const byCall: Record<string, Extract<Item, { kind: "call" }>> = {};
  let current: Extract<Item, { kind: "call" }> | null = null;
  for (const ev of events) {
    switch (ev.type) {
      case "run_started": items.push({ kind: "start", ev }); break;
      case "assistant_message": items.push({ kind: "note", ev }); break;
      case "skill_loaded": items.push({ kind: "skill", ev }); break;
      case "error": items.push({ kind: "error", ev }); break;
      case "verdict": items.push({ kind: "verdict", ev }); break;
      case "tool_call": {
        if (ev.name === "load_skill") { current = null; break; } // shown as a skill chip instead
        const it = { kind: "call" as const, call: ev, charts: [], omni: [] };
        byCall[ev.call_id] = it; current = it; items.push(it); break;
      }
      case "tool_result": if (byCall[ev.call_id]) byCall[ev.call_id].result = ev; break;
      case "chart": (byCall[ev.call_id] ?? current)?.charts.push(ev); break;
      case "omni_analysis": current?.omni.push(ev); break;
    }
  }
  return items;
}

const TOOL_LABEL: Record<string, string> = {
  analyze_chart: "Huawei OMNI · chart analysis", analyze_image: "Huawei OMNI · image analysis", read_document: "Huawei OMNI · document reading",
};

function OmniCard({ ev }: { ev: RunEvent }) {
  const [zoom, setZoom] = useState(false);
  return (
    <div className="mt-2 rounded-lg border border-violet-500/30 bg-violet-950/20 p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <Chip tone="violet">Huawei OMNI</Chip>
        <span className="text-[11px] text-slate-400">{ev.model}</span>
        <Chip tone={ev.mode === "LIVE" ? "emerald" : ev.mode === "CACHED" ? "sky" : "amber"}>{ev.mode}</Chip>
      </div>
      <div className="flex gap-3">
        {ev.thumbnail_url && (
          <img src={ev.thumbnail_url} alt={`input sent to OMNI: ${ev.target_id}`} onClick={() => setZoom(true)}
            className="h-20 w-28 flex-none cursor-zoom-in rounded border border-slate-700 bg-slate-950 object-cover" />
        )}
        <div className="min-w-0 text-xs">
          <div className="text-slate-400"><span className="text-slate-500">Q:</span> {ev.question}</div>
          <div className="mt-1 whitespace-pre-wrap break-words text-slate-200">{ev.answer}</div>
        </div>
      </div>
      {zoom && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-6" onClick={() => setZoom(false)}>
          <img src={ev.thumbnail_url} className="max-h-full max-w-full rounded" alt="" />
        </div>
      )}
    </div>
  );
}

function CallCard({ it, highlighted }: { it: Extract<Item, { kind: "call" }>; highlighted: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const r = it.result;
  const status = r?.status;
  useEffect(() => { if (highlighted) { setOpen(true); ref.current?.scrollIntoView({ behavior: "smooth", block: "center" }); } }, [highlighted]);
  const dot = !r ? "bg-slate-500 animate-pulse" : status === "ok" ? "bg-emerald-400" : status === "data_gap" ? "bg-amber-400" : "bg-red-400";
  return (
    <div ref={ref} id={it.call.call_id}
      className={`rounded-lg border bg-slate-900/70 transition ${highlighted ? "border-sky-400 ring-2 ring-sky-400/40" : "border-slate-800"}`}>
      <button onClick={() => setOpen((o) => !o)} className="flex w-full items-start gap-2 px-3 py-2 text-left">
        <span className={`mt-1.5 h-2 w-2 flex-none rounded-full ${dot}`} />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <code className="text-xs font-semibold text-sky-300">{it.call.name}</code>
            {TOOL_LABEL[it.call.name] && <span className="text-[10px] uppercase tracking-wide text-violet-300">{TOOL_LABEL[it.call.name]}</span>}
            {status === "data_gap" && <Chip tone="amber">data gap</Chip>}
            {status === "error" && <Chip tone="red">error</Chip>}
            {!r && <Spinner />}
          </span>
          {r && <span className="mt-0.5 block text-xs text-slate-400">{r.summary}</span>}
        </span>
        <span className="text-xs text-slate-600">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="space-y-2 border-t border-slate-800 px-3 py-2 text-xs">
          <div><span className="text-slate-500">args </span><code className="break-all text-slate-300">{JSON.stringify(it.call.args)}</code></div>
          {(r?.warnings?.length ?? 0) > 0 && r && <ul className="list-disc pl-5 text-amber-300/90">{r.warnings.map((w: string, i: number) => <li key={i}>{w}</li>)}</ul>}
          {(r?.evidence_ids?.length ?? 0) > 0 && r && (
            <div className="flex flex-wrap gap-1">{r.evidence_ids.map((e: string) => <Chip key={e}>{e}</Chip>)}</div>
          )}
        </div>
      )}
      {it.omni.map((o, i) => <div key={i} className="px-3 pb-3"><OmniCard ev={o} /></div>)}
      {it.charts.map((c) => (
        <div key={c.chart_id} className="border-t border-slate-800 px-1 pb-1">
          <Plot figure={c.figure_json} height={c.chart_id === "plume_map" ? 560 : 420} />
        </div>
      ))}
    </div>
  );
}

export function Trace({ run }: { run: RunState }) {
  const items = useMemo(() => buildItems(run.events), [run.events]);
  const { sel } = useTrace();
  const bottom = useRef<HTMLDivElement>(null);
  const [follow, setFollow] = useState(true);
  useEffect(() => { if (follow && run.status === "running") bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [items.length, follow, run.status]);

  if (run.status === "idle") return <div className="rounded-xl border border-dashed border-slate-800 p-8 text-center text-sm text-slate-500">Press <b>Assess</b> to start the agent.</div>;
  if (!items.length) return <div className="space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-14" />)}</div>;
  return (
    <div className="space-y-2">
      <label className="flex items-center justify-end gap-1 text-[11px] text-slate-500">
        <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> follow live
      </label>
      {items.map((it, i) => {
        switch (it.kind) {
          case "start":
            return <div key={i} className="text-[11px] uppercase tracking-wide text-slate-500">Run {it.ev.run_id} · {it.ev.mode}{it.ev.replay_of ? ` (replay of ${it.ev.replay_of})` : ""}</div>;
          case "skill":
            return <div key={i}><Chip tone="sky" title={it.ev.description}>📘 Loaded skill: {it.ev.name}</Chip></div>;
          case "note":
            return <p key={i} className="border-l-2 border-slate-700 pl-3 text-sm italic text-slate-300">{it.ev.text}{it.ev.source === "scripted" && <span className="ml-2 text-[10px] not-italic text-slate-600">(scripted agent)</span>}</p>;
          case "error":
            return <div key={i} className={`rounded-lg border px-3 py-2 text-xs ${it.ev.recoverable ? "border-amber-600/50 bg-amber-950/30 text-amber-200" : "border-red-600/50 bg-red-950/30 text-red-200"}`}>{it.ev.message}</div>;
          case "verdict":
            return <div key={i} className="rounded-lg border border-emerald-600/40 bg-emerald-950/20 px-3 py-2 text-xs text-emerald-200">✓ Verdict submitted and validated against computed results.</div>;
          case "call":
            return <CallCard key={it.call.call_id} it={it} highlighted={!!sel?.callIds.includes(it.call.call_id)} />;
        }
      })}
      {(run.status === "running" || run.status === "starting") && <div className="flex items-center gap-2 text-xs text-slate-500"><Spinner /> agent working…</div>}
      <div ref={bottom} />
    </div>
  );
}
