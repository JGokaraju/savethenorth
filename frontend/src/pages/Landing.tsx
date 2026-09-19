import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Globe, { GlobeMethods } from "react-globe.gl";
import { useNavigate } from "react-router-dom";
import { AvailabilityChips, LocationSearch } from "../components/FacilityPanel";
import { Footer, useHealth } from "../components/Header";
import { useToast } from "../components/Toasts";
import { Logo, ModeToggle, ShortHash, Spinner } from "../components/ui";
import { api, Dataset, Facility, GeoResult } from "../lib/api";
import { useElementSize, useInView } from "../lib/hooks";
import { useRunMode } from "../lib/mode";

const DEFAULT_ID = "tx-lenorah-redlake";
const DEFAULT_QUERY = "Lenorah Gas Plant, Stanton, Texas";
const TEX = "/textures/earth-blue-marble.jpg";
const BUMP = "/textures/earth-topology.png";
const RESUME_MS = 5000;

const DATA_BULLETS: { title: string; line: string; color: string }[] = [
  { title: "Methane", line: "NASA EMIT spectrometer, 60 m", color: "#2a78d6" },
  { title: "Heat and flares", line: "NASA VIIRS fire power and brightness temperature", color: "#eb6834" },
  { title: "Imagery", line: "Sentinel-2 true colour and shortwave infrared", color: "#1baf7a" },
  { title: "Weather and wind", line: "ERA5 wind, temperature, pressure", color: "#4a3aa7" },
  { title: "Technical reports", line: "TCEQ permit and emissions-event reports", color: "#52514e" },
  { title: "Cross-check", line: "Carbon Mapper plume records", color: "#a3a29c" },
];

function useReducedMotion() {
  const [r, setR] = useState(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
  useEffect(() => {
    const m = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const on = () => setR(m.matches);
    m?.addEventListener?.("change", on);
    return () => m?.removeEventListener?.("change", on);
  }, []);
  return r;
}

/** Texture if it loads (bundled by setup, works offline); otherwise a plain sphere with country outlines. */
function useTextures() {
  const [state, setState] = useState<{ earth: string | null; bump: string | null; countries: any[] }>({ earth: null, bump: null, countries: [] });
  useEffect(() => {
    const probe = (url: string) => new Promise<boolean>((res) => { const i = new Image(); i.onload = () => res(true); i.onerror = () => res(false); i.src = url; });
    Promise.all([probe(TEX), probe(BUMP)]).then(async ([e, b]) => {
      let countries: any[] = [];
      if (!e) {
        try { countries = (await (await fetch("/geo/countries.geojson")).json()).features; } catch { /* plain sphere */ }
      }
      setState({ earth: e ? TEX : null, bump: b ? BUMP : null, countries });
    });
  }, []);
  return state;
}

function DatasetsModal({ onClose }: { onClose: () => void }) {
  const [ds, setDs] = useState<Dataset[] | null>(null);
  useEffect(() => { api.datasets().then(setDs).catch(() => setDs([])); }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/20 p-4 backdrop-blur-sm" onClick={onClose} role="dialog" aria-modal="true" aria-label="Source datasets">
      <div className="glass max-h-[85vh] w-full max-w-4xl overflow-auto bg-white/95 p-6" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900">Source datasets</h2>
          <button onClick={onClose} className="btn-light px-3 py-1.5" aria-label="Close">Close</button>
        </div>
        {!ds ? <Spinner /> : (
          <div className="space-y-2">
            {ds.map((d) => (
              <div key={d.slot_id} className="rounded-2xl border border-slate-200 bg-white p-4 text-xs">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-slate-800">{d.source_name}</span>
                  {d.status !== "present" && <span className="rounded-full bg-red-50 px-2 text-[10px] text-red-700 ring-1 ring-red-200">missing</span>}
                  {d.synthetic && <span className="rounded-full bg-violet-50 px-2 text-[10px] text-violet-700 ring-1 ring-violet-200">placeholder</span>}
                  {d.quality === "low" && <span className="rounded-full bg-amber-50 px-2 text-[10px] text-amber-800 ring-1 ring-amber-200">low quality</span>}
                </div>
                <div className="mt-1 text-slate-500">{d.citation}</div>
                <div className="mt-1.5 flex flex-wrap gap-3 text-slate-400">
                  <span>{d.file ?? d.reason}</span><ShortHash hash={d.sha256} />
                  {d.size_bytes != null && <span>{d.size_bytes >= 1e6 ? `${(d.size_bytes / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(d.size_bytes / 1e3))} KB`}</span>}
                  {d.date_coverage && <span>{d.date_coverage}</span>}
                  {d.source_url && <a href={d.source_url} target="_blank" rel="noreferrer" className="text-sky-700 hover:underline">source</a>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Hero() {
  return (
    <section className="relative flex h-screen flex-col items-center justify-center px-6 text-center">
      <div className="fade-in"><Logo size={132} /></div>
      <h1 className="fade-in mt-8 text-5xl font-semibold tracking-tight text-slate-900 sm:text-7xl" style={{ animationDelay: "0.35s" }}>Save the North</h1>
      <p className="fade-in mt-4 text-base text-slate-500 sm:text-lg" style={{ animationDelay: "0.8s" }}>Satellite verification of industrial emissions.</p>
      <button onClick={() => document.getElementById("data")?.scrollIntoView({ behavior: "smooth" })}
        className="fade-in absolute bottom-10 flex flex-col items-center gap-1 text-xs text-slate-400 hover:text-slate-700" style={{ animationDelay: "1.4s" }} aria-label="Scroll down">
        <svg viewBox="0 0 24 24" className="nudge h-6 w-6"><path fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" d="M6 9l6 6 6-6" /></svg>
      </button>
    </section>
  );
}

function DataSection() {
  const { ref, inView } = useInView<HTMLDivElement>(0.25);
  return (
    <section id="data" className="mx-auto max-w-5xl px-6 py-20">
      <div ref={ref} className={`reveal ${inView ? "in" : ""}`}>
        <div className="label mb-6 text-center">How the data is collected</div>
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {DATA_BULLETS.map((d) => (
            <li key={d.title} className="glass flex items-center gap-3 px-5 py-4">
              <span className="h-2.5 w-2.5 flex-none rounded-full" style={{ background: d.color }} />
              <div className="min-w-0">
                <div className="text-sm font-semibold text-slate-800">{d.title}</div>
                <div className="truncate text-xs text-slate-500">{d.line}</div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

export default function Landing() {
  const nav = useNavigate();
  const toast = useToast();
  const health = useHealth(10000);
  const { mode, setMode } = useRunMode(health?.live_available);
  const globe = useRef<GlobeMethods>();
  const box = useElementSize<HTMLDivElement>();
  const { ref: globeSection, inView: globeVisible } = useInView<HTMLElement>(0.35);
  const reduced = useReducedMotion();
  const tex = useTextures();
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [sel, setSel] = useState<Facility | null>(null);
  const [date, setDate] = useState("2025-08-08");
  const [showDs, setShowDs] = useState(false);
  const resumeTimer = useRef<number>();
  const userLocked = useRef(false); // stop auto-rotation once a location is chosen

  useEffect(() => { api.facilities().then(setFacilities).catch((e) => toast(`Backend not reachable: ${e.message}`, "error")); }, [toast]);

  const setRotate = useCallback((on: boolean) => {
    const c = globe.current?.controls() as any;
    if (c) { c.autoRotate = on && !reduced && !userLocked.current; c.autoRotateSpeed = 2.5; }
  }, [reduced]);

  const pauseThenResume = useCallback(() => {
    setRotate(false);
    window.clearTimeout(resumeTimer.current);
    resumeTimer.current = window.setTimeout(() => setRotate(true), RESUME_MS);
  }, [setRotate]);

  const flyTo = useCallback((lat: number, lng: number, altitude = 1.6, ms = 2000) => {
    userLocked.current = true;
    setRotate(false);
    globe.current?.pointOfView({ lat, lng, altitude }, reduced ? 0 : ms);
  }, [setRotate, reduced]);

  const selectFacility = useCallback((id: string) => {
    const f = facilities.find((x) => x.facility_id === id);
    if (!f) return;
    setSel(f);
    flyTo(f.lat, f.lon);
  }, [facilities, flyTo]);

  const onReady = useCallback(() => {
    const g = globe.current;
    if (!g) return;
    g.renderer().setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    const c = g.controls() as any;
    c.enableDamping = true;
    c.enableZoom = false; // the page scrolls; the globe must not capture the wheel
    c.addEventListener("start", () => { window.clearTimeout(resumeTimer.current); setRotate(false); });
    c.addEventListener("end", () => { if (!userLocked.current) pauseThenResume(); });
    g.pointOfView({ lat: 25, lng: -40, altitude: 2.2 }, 0);
    setRotate(true);
  }, [setRotate, pauseThenResume]);

  useEffect(() => { // preselect the default case
    if (!facilities.length || sel) return;
    setSel(facilities.find((f) => f.facility_id === DEFAULT_ID) ?? null);
  }, [facilities, sel]);

  useEffect(() => { // once the globe scrolls into view: spin ~2 s, then fly to the selected site
    if (!globeVisible || !sel || userLocked.current) return;
    const t = window.setTimeout(() => flyTo(sel.lat, sel.lon, 1.6, 2600), reduced ? 0 : 2000);
    return () => window.clearTimeout(t);
  }, [globeVisible, sel, flyTo, reduced]);

  const points = useMemo(() => facilities.map((f) => ({
    ...f, color: f.data_status === "cached" ? "#dc2626" : "#ffffff", size: 0.012,
    label: f.data_status === "cached" ? "Methane plume detected" : "No cached observations",
  })), [facilities]);
  const rings = useMemo(() => facilities.map((f) => ({ lat: f.lat, lng: f.lon, hot: f.data_status === "cached" })), [facilities]);

  const onPick = (r: GeoResult) => {
    const id = r.facility_id ?? r.nearest_facility?.facility_id;
    if (id) selectFacility(id);
    else { setSel(null); flyTo(r.lat, r.lon); toast(`No monitored facility within 25 km of ${r.label}.`, "info"); }
  };
  const assess = () => sel && nav(`/assess/${sel.facility_id}?date=${date}&mode=${mode}`);

  return (
    <div>
      <Hero />
      <DataSection />

      <section ref={globeSection} className="mx-auto max-w-6xl px-4 pb-10 pt-6">
        {/* search sits above the globe, never on top of it */}
        <div className="glass relative z-20 space-y-3 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <LocationSearch className="min-w-[240px] flex-1" initial={DEFAULT_QUERY} onPick={onPick} />
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="input w-auto" aria-label="Event date (UTC)" />
            <ModeToggle mode={mode} setMode={setMode} liveAvailable={health?.live_available} />
            <button disabled={!sel} className="btn-dark" onClick={assess}>Assess facility</button>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {facilities.map((f) => (
              <button key={f.facility_id} onClick={() => selectFacility(f.facility_id)}
                className={`flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium transition ${sel?.facility_id === f.facility_id ? "bg-[#2b2f33] text-white" : "bg-white/80 text-slate-600 hover:bg-white"}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${f.data_status === "cached" ? "bg-red-500" : "bg-slate-300"}`} />{f.name}
              </button>
            ))}
            <button onClick={() => setShowDs(true)} className="ml-auto text-xs font-medium text-slate-500 hover:text-slate-900">Source datasets</button>
          </div>
          {sel && (
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200/70 pt-3">
              <div className="text-sm"><span className="font-semibold text-slate-900">{sel.name}</span>
                <span className="text-slate-400"> · {sel.county} County, {sel.state}{sel.operator ? ` · ${sel.operator.split(" — ")[0]}` : ""}</span></div>
              <AvailabilityChips f={sel} />
            </div>
          )}
        </div>

        <div ref={box.ref} className="relative mt-4 h-[78vh] min-h-[480px] w-full [&_canvas]:[filter:brightness(1.18)_saturate(0.8)_contrast(0.92)]">
          {box.w > 0 && (
            <Globe
              ref={globe}
              width={box.w}
              height={box.h}
              onGlobeReady={onReady}
              backgroundColor="rgba(0,0,0,0)"
              globeImageUrl={tex.earth ?? undefined}
              bumpImageUrl={tex.bump ?? undefined}
              showAtmosphere
              atmosphereColor="#ffffff"
              atmosphereAltitude={0.2}
              polygonsData={tex.earth ? [] : tex.countries}
              polygonCapColor={() => "rgba(214,205,183,0.9)"}
              polygonSideColor={() => "rgba(0,0,0,0)"}
              polygonStrokeColor={() => "#b9b1a0"}
              pointsData={points}
              pointLat="lat"
              pointLng="lon"
              pointColor="color"
              pointAltitude="size"
              pointRadius={0.35}
              pointLabel={(d: any) => `<div style="padding:6px 8px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;font:12px Inter,system-ui;color:#1f2937;box-shadow:0 6px 20px rgba(15,23,42,.12)"><b>${d.name}</b><br/><span style="color:#64748b">${d.label}</span></div>`}
              onPointClick={(d: any) => selectFacility(d.facility_id)}
              onPointHover={(d: any) => { if (d) { window.clearTimeout(resumeTimer.current); setRotate(false); } else if (!userLocked.current) pauseThenResume(); }}
              ringsData={rings}
              ringColor={(d: any) => (t: number) => d.hot ? `rgba(220,38,38,${1 - t})` : `rgba(255,255,255,${0.9 * (1 - t)})`}
              ringMaxRadius={(d: any) => (d.hot ? 4.5 : 1.8)}
              ringPropagationSpeed={reduced ? 0 : 1.4}
              ringRepeatPeriod={(d: any) => (d.hot ? 1100 : 2200)}
            />
          )}
        </div>
        <div className="mt-2 text-right text-[10px] text-slate-400">Earth imagery: NASA Blue Marble</div>
      </section>
      <Footer />
      {showDs && <DatasetsModal onClose={() => setShowDs(false)} />}
    </div>
  );
}
