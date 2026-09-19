import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { LocationSearch } from "../components/FacilityPanel";
import { Footer, TopBar, useHealth } from "../components/Header";
import { Report } from "../components/Report";
import { useToast } from "../components/Toasts";
import { Trajectory } from "../components/Trajectory";
import { ModeToggle, Spinner } from "../components/ui";
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
  const { state: run, start, attach } = useRun(toast);
  const autoStarted = useRef<string | null>(null);
  const runParam = params.get("run");

  useEffect(() => {
    setF(null);
    api.facility(facilityId).then(setF).catch((e) => toast(`Unknown facility: ${e.message}`, "error"));
  }, [facilityId, toast]);

  // Record the run id in the URL so a reload or shared link re-attaches instead of starting (and paying for) a new run.
  const launch = useCallback(async (m: RunMode) => {
    if (!f) return;
    const id = await start(f.facility_id, date, m);
    if (id) {
      autoStarted.current = id;
      nav(`/assess/${f.facility_id}?date=${date}&run=${id}`, { replace: true });
    }
  }, [f, date, start, nav]);
  const assess = useCallback(() => { launch(mode); }, [launch, mode]);

  useEffect(() => { // existing run in the URL: re-attach
    if (runParam && autoStarted.current !== runParam && run.runId !== runParam) {
      autoStarted.current = runParam;
      attach(runParam);
    }
  }, [runParam, run.runId, attach]);

  useEffect(() => { // no run yet: auto-start once when arriving from the landing page
    if (runParam || !f || !health || params.get("autostart") === "0" || autoStarted.current) return;
    autoStarted.current = "starting";
    const requested = (params.get("mode") as RunMode) || mode;
    launch(requested === "live" && health.live_available ? "live" : "demo");
  }, [runParam, f, health, params, mode, launch]);

  const busy = run.status === "starting" || run.status === "running";
  const done = run.status === "finished" && !!run.verdict;
  useEffect(() => { if (done) window.scrollTo(0, 0); }, [done]); // the report opens on its hero image

  if (done) {
    return (
      <TraceProvider>
        <Report run={run} f={f} />
        <Footer />
      </TraceProvider>
    );
  }

  return (
    <TraceProvider>
      <div className="flex min-h-screen flex-col">
        <TopBar right={<ModeToggle mode={mode} setMode={setMode} liveAvailable={health?.live_available} />}>
          <LocationSearch className="w-full max-w-sm" initial={f?.name}
            onPick={(r) => { const id = r.facility_id ?? r.nearest_facility?.facility_id; if (id) nav(`/assess/${id}?date=${date}&autostart=0`); }} />
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="input w-auto" aria-label="Event date (UTC)" />
          <button className="btn-dark" onClick={assess} disabled={!f || busy}>{busy ? <><Spinner className="border-white/40 border-t-white" /> Assessing</> : "Assess"}</button>
        </TopBar>

        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">
          <nav className="text-sm text-muted" aria-label="Breadcrumb"><a href="/" className="link">Home</a> <span aria-hidden>›</span> Assessment</nav>
          <div className="mt-2 flex flex-wrap items-end justify-between gap-3 border-b border-rule pb-4">
            <div>
              <h1 className="text-3xl font-extrabold text-ink">{f?.name ?? "Loading…"}</h1>
              {f && <p className="mt-1 text-muted">{f.county} County, {f.state} · event date {date}</p>}
            </div>
            <span className={`px-2 py-0.5 text-xs font-bold uppercase tracking-wide ${busy ? "bg-primary text-white" : run.status === "error" ? "bg-alert-red text-white" : "bg-rule text-ink"}`}>
              {busy ? "In progress" : run.status === "error" ? "Stopped" : run.status === "finished" ? "Complete" : "Not started"}
            </span>
          </div>
          <div className="mt-6 max-w-2xl">
            {run.status === "idle" && f && <p className="text-muted">Select <b className="text-ink">Assess</b> to start the verification.</p>}
            {(busy || run.status === "finished") && <Trajectory run={run} title="Verification steps" />}
            {run.status === "error" && (
              <div className="border-l-4 border-alert-red bg-[#f4e3db] px-4 py-3">
                <p className="font-bold text-ink">The assessment stopped</p>
                <p className="text-sm text-ink">{run.error ?? "An unexpected error occurred."}</p>
                <button className="btn-dark mt-3" onClick={assess}>Try again</button>
              </div>
            )}
          </div>
        </main>
        <Footer />
      </div>
    </TraceProvider>
  );
}
