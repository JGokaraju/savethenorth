import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { AvailabilityChips, LocationSearch } from "../components/FacilityPanel";
import { Footer, TopBar, useHealth } from "../components/Header";
import { Summary } from "../components/Summary";
import { useToast } from "../components/Toasts";
import { Trajectory } from "../components/Trajectory";
import { Card, ModeToggle, Spinner } from "../components/ui";
import { api, Facility } from "../lib/api";
import { RunMode, useRunMode } from "../lib/mode";
import { TraceProvider } from "../lib/trace";
import { useRun } from "../lib/useRun";

export default function Workspace() {
  const { facilityId = "tx-lenorah-redlake" } = useParams();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const toast = useToast();
  const health = useHealth();
  const { mode, setMode } = useRunMode(health?.live_available);
  const [date, setDate] = useState(params.get("date") ?? "2025-08-08");
  const [f, setF] = useState<Facility | null>(null);
  const { state: run, start } = useRun(toast);
  const autoStarted = useRef<string | null>(null);

  useEffect(() => {
    setF(null);
    api.facility(facilityId).then(setF).catch((e) => toast(`Unknown facility: ${e.message}`, "error"));
  }, [facilityId, toast]);

  const assess = useCallback(() => { if (f) start(f.facility_id, date, mode); }, [f, date, mode, start]);

  useEffect(() => { // auto-start once when arriving from the landing page
    if (!f || !health || params.get("autostart") === "0" || autoStarted.current === f.facility_id) return;
    autoStarted.current = f.facility_id;
    const requested = (params.get("mode") as RunMode) || mode;
    start(f.facility_id, date, requested === "live" && health.live_available ? "live" : "demo");
  }, [f, health, params, date, mode, start]);

  const busy = run.status === "starting" || run.status === "running";
  const done = run.status === "finished" && run.verdict;

  return (
    <TraceProvider>
      <div className="flex min-h-screen flex-col">
        <TopBar right={<ModeToggle mode={mode} setMode={setMode} liveAvailable={health?.live_available} />}>
          <LocationSearch className="w-full max-w-sm" initial={f?.name}
            onPick={(r) => { const id = r.facility_id ?? r.nearest_facility?.facility_id; if (id) nav(`/assess/${id}?date=${date}&autostart=0`); }} />
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="input w-auto" aria-label="Event date (UTC)" />
          <button className="btn-dark" onClick={assess} disabled={!f || busy}>{busy ? <><Spinner className="border-slate-500 border-t-white" /> Assessing</> : "Assess"}</button>
        </TopBar>

        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">
          {done ? (
            <Summary run={run} f={f} />
          ) : (
            <div className="mx-auto max-w-2xl space-y-4">
              {f && (
                <Card>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="label">Facility</div>
                      <div className="mt-1 text-lg font-semibold text-slate-900">{f.name}</div>
                      <div className="text-sm text-slate-500">{f.county} County, {f.state} · {f.operator?.split(" — ")[0] ?? "Operator unknown"}</div>
                    </div>
                    <div className="text-right text-xs text-slate-400">Event date<div className="text-sm font-medium text-slate-700">{date}</div></div>
                  </div>
                  <div className="mt-4"><AvailabilityChips f={f} /></div>
                </Card>
              )}
              {run.status === "idle" && f && (
                <Card><p className="text-sm text-slate-500">Press <b className="text-slate-800">Assess</b> to start the verification agent.</p></Card>
              )}
              {(busy || run.status === "finished") && (
                <Card className="fade-up"><Trajectory run={run} title={f ? `Verifying ${f.name}` : "Verifying"} /></Card>
              )}
              {run.status === "error" && (
                <Card>
                  <p className="text-sm text-red-700">{run.error ?? "The assessment stopped unexpectedly."}</p>
                  <button className="btn-dark mt-3" onClick={assess}>Try again</button>
                </Card>
              )}
            </div>
          )}
        </main>
        <Footer />
      </div>
    </TraceProvider>
  );
}
