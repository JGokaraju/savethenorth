import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { FacilityPanel } from "../components/FacilityPanel";
import { Footer, Header } from "../components/Header";
import { useToast } from "../components/Toasts";
import { Trace } from "../components/Trace";
import { Card } from "../components/ui";
import { VerdictPanel } from "../components/VerdictPanel";
import { api, Facility } from "../lib/api";
import { TraceProvider } from "../lib/trace";
import { useRun } from "../lib/useRun";

export default function Workspace() {
  const { facilityId = "tx-lenorah-redlake" } = useParams();
  const [params] = useSearchParams();
  const nav = useNavigate();
  const toast = useToast();
  const [date, setDate] = useState(params.get("date") ?? "2025-08-08");
  const [f, setF] = useState<Facility | null>(null);
  const { state: run, start } = useRun(toast);
  const autoStarted = useRef<string | null>(null);

  useEffect(() => {
    setF(null);
    api.facility(facilityId).then(setF).catch((e) => toast(`Unknown facility: ${e.message}`, "error"));
  }, [facilityId, toast]);

  const assess = useCallback(() => { if (f) start(f.facility_id, date); }, [f, date, start]);

  useEffect(() => {  // auto-start once per facility when arriving from the landing page
    if (f && params.get("autostart") !== "0" && autoStarted.current !== f.facility_id) {
      autoStarted.current = f.facility_id;
      start(f.facility_id, date);
    }
  }, [f, params, date, start]);

  return (
    <TraceProvider>
      <div className="flex min-h-screen flex-col bg-slate-950">
        <Header runMode={run.mode} />
        <main className="grid flex-1 grid-cols-1 gap-4 p-4 lg:grid-cols-[320px,minmax(0,1fr)] xl:grid-cols-[320px,minmax(0,1fr),minmax(0,480px)]">
          <aside className="space-y-4">
            <FacilityPanel f={f} date={date} setDate={setDate} onAssess={assess} run={run}
              onPickFacility={(id) => nav(`/assess/${id}?date=${date}&autostart=0`)} />
          </aside>
          <section className="min-w-0">
            <Card title="Agent trace" right={<span className="text-[11px] text-slate-500">{run.events.filter((e) => e.type === "tool_call").length} tool calls</span>}>
              <Trace run={run} />
            </Card>
          </section>
          <section className="min-w-0 lg:col-span-2 xl:col-span-1">
            <div className="xl:sticky xl:top-16"><VerdictPanel run={run} /></div>
          </section>
        </main>
        <Footer />
      </div>
    </TraceProvider>
  );
}
