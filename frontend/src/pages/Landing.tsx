import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Globe, { GlobeMethods } from "react-globe.gl";
import { useNavigate } from "react-router-dom";
import { AvailabilityChips, LocationSearch } from "../components/FacilityPanel";
import { useHealth } from "../components/Header";
import { useToast } from "../components/Toasts";
import { ModeBadge, ShortHash, Spinner } from "../components/ui";
import { api, Dataset, Facility, GeoResult } from "../lib/api";

const DEFAULT_ID = "tx-lenorah-redlake";
const DEFAULT_QUERY = "Lenorah Gas Plant, Stanton, Texas";
const TEX = "/textures/earth-blue-marble.jpg";
const SKY = "/textures/night-sky.png";
const RESUME_MS = 5000;

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

function useWindowSize() {
  const [s, setS] = useState({ w: window.innerWidth, h: window.innerHeight });
  useEffect(() => {
    const on = () => setS({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return s;
}

/** Texture if it loads (offline-capable, bundled by setup); otherwise solid sphere + country outlines. */
function useTextures() {
  const [state, setState] = useState<{ earth: string | null; sky: string | null; countries: any[] }>({ earth: null, sky: null, countries: [] });
  useEffect(() => {
    const probe = (url: string) => new Promise<boolean>((res) => { const i = new Image(); i.onload = () => res(true); i.onerror = () => res(false); i.src = url; });
    Promise.all([probe(TEX), probe(SKY)]).then(async ([e, s]) => {
      let countries: any[] = [];
      if (!e) {
        try { countries = (await (await fetch("/geo/countries.geojson")).json()).features; } catch { /* plain sphere */ }
      }
      setState({ earth: e ? TEX : null, sky: s ? SKY : null, countries });
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose} role="dialog" aria-modal="true" aria-label="Source datasets">
      <div className="max-h-[85vh] w-full max-w-4xl overflow-auto rounded-xl border border-slate-700 bg-slate-900 p-5" onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-100">Source datasets (Lenorah / Red Lake case)</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white" aria-label="Close">✕</button>
        </div>
        {!ds ? <Spinner /> : (
          <div className="space-y-2">
            {ds.map((d) => (
              <div key={d.slot_id} className="rounded-lg border border-slate-800 p-3 text-xs">
                <div className="flex flex-wrap items-center gap-2">
                  <code className="text-sky-300">{d.slot_id}</code>
                  <span className={`rounded px-1.5 text-[10px] ${d.status === "present" ? "bg-emerald-500/15 text-emerald-300" : "bg-red-500/15 text-red-300"}`}>{d.status}</span>
                  {d.synthetic && <span className="rounded bg-violet-500/15 px-1.5 text-[10px] text-violet-300">SYNTHETIC</span>}
                  {d.quality === "low" && <span className="rounded bg-amber-500/15 px-1.5 text-[10px] text-amber-300">low quality</span>}
                  <span className="text-slate-200">{d.source_name}</span>
                </div>
                <div className="mt-1 text-slate-400">{d.citation}</div>
                <div className="mt-1 flex flex-wrap gap-3 text-slate-500">
                  <span>{d.file ?? d.reason}</span><ShortHash hash={d.sha256} />
                  {d.size_bytes != null && <span>{d.size_bytes >= 1e6 ? `${(d.size_bytes / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(d.size_bytes / 1e3))} KB`}</span>}
                  {d.date_coverage && <span>{d.date_coverage}</span>}
                  {d.source_url && <a href={d.source_url} target="_blank" rel="noreferrer" className="text-sky-400 hover:underline">source</a>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function Landing() {
  const nav = useNavigate();
  const toast = useToast();
  const health = useHealth(10000);
  const globe = useRef<GlobeMethods>();
  const { w, h } = useWindowSize();
  const reduced = useReducedMotion();
  const tex = useTextures();
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [sel, setSel] = useState<Facility | null>(null);
  const [date, setDate] = useState("2025-08-08");
  const [showDs, setShowDs] = useState(false);
  const resumeTimer = useRef<number>();
  const userLocked = useRef(false); // stop auto-rotation for good once a location is chosen

  useEffect(() => { api.facilities().then(setFacilities).catch((e) => toast(`Backend not reachable: ${e.message}`, "error")); }, [toast]);

  const setRotate = useCallback((on: boolean) => {
    const c = globe.current?.controls() as any;
    if (c) { c.autoRotate = on && !reduced && !userLocked.current; c.autoRotateSpeed = 2.5; /* ≈0.25–0.3°/frame at 60 fps */ }
  }, [reduced]);

  const pauseThenResume = useCallback(() => {
    setRotate(false);
    window.clearTimeout(resumeTimer.current);
    resumeTimer.current = window.setTimeout(() => setRotate(true), RESUME_MS);
  }, [setRotate]);

  const flyTo = useCallback((lat: number, lng: number, altitude = 0.4, ms = 2000) => {
    userLocked.current = true;
    setRotate(false);
    globe.current?.pointOfView({ lat, lng, altitude }, reduced ? 0 : ms);
  }, [setRotate, reduced]);

  const selectFacility = useCallback((id: string, fly = true) => {
    const f = facilities.find((x) => x.facility_id === id);
    if (!f) return;
    setSel(f);
    if (fly) flyTo(f.lat, f.lon);
  }, [facilities, flyTo]);

  // globe setup: pixel-ratio cap, controls, initial tilt; spin ~2 s then fly to the default case
  const onReady = useCallback(() => {
    const g = globe.current;
    if (!g) return;
    g.renderer().setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    const c = g.controls() as any;
    c.enableDamping = true;
    c.addEventListener("start", () => { window.clearTimeout(resumeTimer.current); setRotate(false); });
    c.addEventListener("end", () => { if (!userLocked.current) pauseThenResume(); });
    g.pointOfView({ lat: 25, lng: -60, altitude: 2.4 }, 0);
    setRotate(true);
  }, [setRotate, pauseThenResume]);

  useEffect(() => {
    if (!facilities.length) return;
    const d = facilities.find((f) => f.facility_id === DEFAULT_ID);
    if (!d) return;
    setSel(d);
    const t = window.setTimeout(() => flyTo(d.lat, d.lon, 0.4, 2600), reduced ? 0 : 2000);
    return () => window.clearTimeout(t);
  }, [facilities, flyTo, reduced]);

  const points = useMemo(() => facilities.map((f) => ({
    ...f, color: f.data_status === "cached" ? "#ef4444" : "#94a3b8", size: f.data_status === "cached" ? 0.02 : 0.01,
    label: f.data_status === "cached" ? "Methane plume detected" : "No cached observations",
  })), [facilities]);
  const rings = useMemo(() => facilities.filter((f) => f.data_status === "cached").map((f) => ({ lat: f.lat, lng: f.lon })), [facilities]);

  const onPick = (r: GeoResult) => {
    const id = r.facility_id ?? r.nearest_facility?.facility_id;
    if (id) selectFacility(id);
    else { setSel(null); flyTo(r.lat, r.lon, 0.8); toast(`No monitored facility within 25 km of ${r.label}.`, "info"); }
  };

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-black">
      <div className="absolute inset-0" aria-hidden>
        <Globe
          ref={globe}
          width={w}
          height={h}
          onGlobeReady={onReady}
          globeImageUrl={tex.earth ?? undefined}
          backgroundImageUrl={tex.sky ?? undefined}
          backgroundColor="#000005"
          showAtmosphere
          atmosphereColor="#5aa9ff"
          atmosphereAltitude={0.18}
          polygonsData={tex.earth ? [] : tex.countries}
          polygonCapColor={() => "rgba(30,64,120,0.55)"}
          polygonSideColor={() => "rgba(0,0,0,0)"}
          polygonStrokeColor={() => "#6b8fc9"}
          pointsData={points}
          pointLat="lat"
          pointLng="lon"
          pointColor="color"
          pointAltitude="size"
          pointRadius={0.09}
          pointLabel={(d: any) => `<div style="padding:4px 6px;background:#0f172a;border:1px solid #334155;border-radius:6px;font:12px system-ui;color:#e2e8f0"><b>${d.name}</b><br/>${d.label}</div>`}
          onPointClick={(d: any) => selectFacility(d.facility_id)}
          onPointHover={(d: any) => { if (d) { window.clearTimeout(resumeTimer.current); setRotate(false); } else if (!userLocked.current) pauseThenResume(); }}
          ringsData={rings}
          ringColor={() => (t: number) => `rgba(239,68,68,${1 - t})`}
          ringMaxRadius={3.2}
          ringPropagationSpeed={reduced ? 0 : 1.6}
          ringRepeatPeriod={1100}
          labelsData={facilities.filter((f) => f.data_status === "cached")}
          labelLat="lat"
          labelLng="lon"
          labelText={() => "Methane plume detected"}
          labelColor={() => "#fca5a5"}
          labelSize={0.2}
          labelDotRadius={0.04}
          labelAltitude={0.012}
        />
      </div>

      <div className="pointer-events-none absolute left-0 right-0 top-0 flex items-center justify-between p-4">
        <div className="pointer-events-auto flex items-center gap-2 text-slate-100"><span aria-hidden>🛰️</span><b>Plumewatch</b></div>
        <div className="pointer-events-auto"><ModeBadge mode={health?.mode.label} /></div>
      </div>

      <div className="absolute bottom-4 left-4 right-4 sm:bottom-auto sm:right-auto sm:top-1/2 sm:w-[420px] sm:-translate-y-1/2">
        <div className="space-y-4 rounded-2xl border border-white/10 bg-slate-900/55 p-5 shadow-2xl backdrop-blur-xl">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-white">Plumewatch</h1>
            <p className="text-sm text-slate-300">Satellite verification of industrial emissions for regulators.</p>
          </div>
          <div className="space-y-2">
            <LocationSearch initial={DEFAULT_QUERY} onPick={onPick} />
            <label className="block text-xs text-slate-400">
              Event date (UTC)
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-slate-100 [color-scheme:dark]" />
            </label>
          </div>
          {sel && (
            <div className="space-y-2 rounded-xl border border-white/10 bg-slate-950/50 p-3">
              <div className="text-sm font-semibold text-slate-100">{sel.name}</div>
              <div className="text-xs text-slate-400">{sel.operator ?? "Operator unknown"}{sel.operator && !sel.operator.includes("potentially") ? " — potentially responsible operator" : ""}</div>
              <div className="text-[11px] text-slate-500">
                {sel.lat.toFixed(4)}, {sel.lon.toFixed(4)} · {sel.county} County, {sel.state}
                {sel.title_v_permit && <> · Title V {sel.title_v_permit}</>}{sel.nsr_authorization && <> · NSR {sel.nsr_authorization}</>}
              </div>
              <AvailabilityChips f={sel} />
            </div>
          )}
          <div className="flex items-center justify-between gap-3">
            <button onClick={() => setShowDs(true)} className="text-xs text-sky-300 hover:underline">View source datasets</button>
            <button disabled={!sel} onClick={() => sel && nav(`/assess/${sel.facility_id}?date=${date}`)}
              className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white shadow-lg hover:bg-sky-500 disabled:opacity-50">
              Assess facility →
            </button>
          </div>
        </div>
      </div>
      <div className="pointer-events-none absolute bottom-2 right-3 hidden text-[10px] text-slate-500 sm:block">Earth imagery: NASA Blue Marble · screening estimates only</div>
      {showDs && <DatasetsModal onClose={() => setShowDs(false)} />}
    </div>
  );
}
