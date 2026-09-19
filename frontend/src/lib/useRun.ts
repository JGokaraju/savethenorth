import { useCallback, useEffect, useRef, useState } from "react";
import { api, LedgerRecord, RunEvent, Verdict } from "./api";

export interface ChartEvent {
  chart_id: string;
  title: string;
  figure_json: any;
  call_id?: string;
}

export interface RunState {
  runId: string | null;
  mode: string | null;
  events: RunEvent[];
  charts: Record<string, ChartEvent>;
  verdict: Verdict | null;
  shownCharts: { chart_id: string; caption: string; title: string }[];
  ledger: LedgerRecord[];
  omniCalls: LedgerRecord[];
  status: "idle" | "starting" | "running" | "finished" | "error";
  error: string | null;
}

const EVENT_TYPES = ["run_started", "skill_loaded", "tool_call", "tool_result", "chart", "omni_analysis",
  "assistant_message", "verdict", "error", "run_finished"];

const empty: RunState = {
  runId: null, mode: null, events: [], charts: {}, verdict: null, shownCharts: [], ledger: [], omniCalls: [],
  status: "idle", error: null,
};

export function useRun(onToast?: (msg: string, kind?: "error" | "info") => void) {
  const [state, setState] = useState<RunState>(empty);
  const esRef = useRef<EventSource | null>(null);

  const refreshEvidence = useCallback(async (runId: string) => {
    try {
      const ev = await api.evidence(runId);
      setState((s) => (s.runId === runId ? { ...s, ledger: ev.ledger, omniCalls: ev.omni_calls } : s));
    } catch {
      /* evidence is best-effort while running */
    }
  }, []);

  const subscribe = useCallback((runId: string) => {
    esRef.current?.close();
    const es = new EventSource(`/api/runs/${runId}/events`);
    esRef.current = es;
    let finished = false;
    const handle = (e: MessageEvent) => {
      const ev: RunEvent = JSON.parse(e.data);
      setState((s) => {
        if (s.runId !== runId) return s;
        const next: RunState = { ...s, events: [...s.events, ev], status: s.status === "starting" ? "running" : s.status };
        if (ev.type === "run_started") next.mode = ev.mode;
        if (ev.type === "chart") next.charts = { ...s.charts, [ev.chart_id]: ev as unknown as ChartEvent };
        if (ev.type === "verdict") {
          next.verdict = ev.verdict;
          next.shownCharts = ev.shown_charts ?? [];
        }
        if (ev.type === "error" && !ev.recoverable) next.error = ev.message;
        if (ev.type === "run_finished") next.status = ev.ok ? "finished" : "error";
        return next;
      });
      if (ev.type === "error") onToast?.(ev.message, ev.recoverable ? "info" : "error");
      if (ev.type === "tool_result" || ev.type === "omni_analysis") refreshEvidence(runId);
      if (ev.type === "run_finished") {
        finished = true;
        es.close();
        refreshEvidence(runId);
      }
    };
    EVENT_TYPES.forEach((t) => es.addEventListener(t, handle as EventListener));
    es.onerror = () => {
      if (!finished) {
        es.close();
        setState((s) => (s.runId === runId && s.status !== "finished" ? { ...s, status: "error", error: "Lost connection to the event stream" } : s));
        onToast?.("Lost connection to the event stream", "error");
      }
    };
  }, [onToast, refreshEvidence]);

  const start = useCallback(async (facilityId: string, date: string, mode: "demo" | "live" = "demo"): Promise<string | null> => {
    esRef.current?.close();
    setState({ ...empty, status: "starting" });
    try {
      const r = await api.startRun(facilityId, date, mode);
      setState({ ...empty, runId: r.run_id, mode: r.mode, status: "starting" });
      subscribe(r.run_id);
      return r.run_id;
    } catch (e: any) {
      setState({ ...empty, status: "error", error: String(e.message ?? e) });
      onToast?.(`Could not start the run: ${e.message ?? e}`, "error");
      return null;
    }
  }, [subscribe, onToast]);

  /** Re-attach to an existing run (page reload / shared link): replays its events, never starts a new run. */
  const attach = useCallback((runId: string) => {
    esRef.current?.close();
    setState({ ...empty, runId, status: "starting" });
    subscribe(runId);
  }, [subscribe]);

  useEffect(() => () => esRef.current?.close(), []);
  return { state, start, attach };
}
