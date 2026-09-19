import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Globe, { GlobeMethods } from "react-globe.gl";
import { useNavigate } from "react-router-dom";
import { AvailabilityChips, LocationSearch } from "../components/FacilityPanel";
import { useHealth } from "../components/Header";
import { useToast } from "../components/Toasts";
import { Logo, ModeToggle, ShortHash, Spinner } from "../components/ui";
import { api, Dataset, Facility, GeoResult } from "../lib/api";
import { useRunMode } from "../lib/mode";

const DEFAULT_ID = "tx-lenorah-redlake";
const DEFAULT_QUERY = "Lenorah Gas Plant, Stanton, Texas";
const TEX = "/textures/earth-blue-marble.jpg";
const BUMP = "/textures/earth-topology.png";
const RESUME_MS = 5000;

const KEY_DATA: { title: string; detail: string; color: string }[] = [
  { title: "Methane", detail: "NASA EMIT imaging spectrometer — CH₄ enhancement at 60 m", color: "#2a78d6" },
  { title: "Heat and flares", detail: "NASA VIIRS thermal detections — fire radiative power and brightness temperature", color: "#eb6834" },
  { title: "Optical and shortwave-infrared imagery", detail: "Copernicus Sentinel-2 — true colour and SWIR", color: "#1baf7a" },
  { title: "Weather and wind", detail: "ERA5 reanalysis via Open-Meteo — wind speed and direction, temperature, pressure", color: "#4a3aa7" },
  { title: "Technical reports", detail: "TCEQ Title V permit (Statement of Basis) and STEERS emissions-event reports", color: "#52514e" },
  { title: "Independent plume records", detail: "Carbon Mapper — cross-check of the satellite estimate", color: "#a3a29c" },
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

function useWindowSize() {
  const [s, setS] = useState({ w: window.innerWidth, h: window.innerHeight });
  useEffect(() => {
    const on = () => setS({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return s;
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

export default function Landing() {
  const nav = useNavigate();
  const toast = useToast();
  const health = useHealth(10000);
  const { mode, setMode } = useRunMode(health?.live_available);
  const globe = useRef<GlobeMethods>();
  const { w, h } = useWindowSize();
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
    if (c) { c.autoRotate = on && !reduced && !userLocked.current; c.autoRotateSpeed = 2.5; /* ≈0.25–0.3°/frame at 60 fps */ }
  }, [reduced]);

  const pauseThenResume = useCallback(() => {
    setRotate(false);
    window.clearTimeout(resumeTimer.current);
    resumeTimer.current = window.setTimeout(() => setRotate(true), RESUME_MS);
  }, [setRotate]);

  const flyTo = useCallback((lat: number, lng: number, altitude = 1.75, ms = 2000) => {
    userLocked.current = true;
    setRotate(false);
    globe.current?.pointOfView({ lat, lng: lng - 12, altitude }, reduced ? 0 : ms); // offset so the site sits right of the cards
  }, [setRotate, reduced]);

  const selectFacility = useCallback((id: string, fly = true) => {
    const f = facilities.find((x) => x.facility_id === id);
    if (!f) return;
    setSel(f);
    if (fly) flyTo(f.lat, f.lon);
  }, [facilities, flyTo]);

  const onReady = useCallback(() => {
    const g = globe.current;
    if (!g) return;
    g.renderer().setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    const c = g.controls() as any;
    c.enableDamping = true;
    c.addEventListener("start", () => { window.clearTimeout(resumeTimer.current); setRotate(false); });
    c.addEventListener("end", () => { if (!userLocked.current) pauseThenResume(); });
    g.pointOfView({ lat: 25, lng: -40, altitude: 2.3 }, 0);
    setRotate(true);
  }, [setRotate, pauseThenResume]);

  useEffect(() => { // spin ~2 s, then fly to the default case
    if (!facilities.length) return;
    const d = facilities.find((f) => f.facility_id === DEFAULT_ID);
    if (!d) return;
    setSel(d);
    const t = window.setTimeout(() => flyTo(d.lat, d.lon, 1.75, 2600), reduced ? 0 : 2000);
    return () => window.clearTimeout(t);
  }, [facilities, flyTo, reduced]);

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

  return (
    <div className="relative h-screen w-screen overflow-hidden">
      {/* soften the satellite texture toward the pastel relief look of the design */}
      <div className="absolute inset-0 [&_canvas]:[filter:brightness(1.18)_saturate(0.8)_contrast(0.92)]" aria-hidden>
        <Globe
          ref={globe}
          width={w}
          height={h}
          onGlobeReady={onReady}
          backgroundColor="rgba(0,0,0,0)"
          globeImageUrl={tex.earth ?? undefined}
          bumpImageUrl={tex.bump ?? undefined}
          showAtmosphere
          atmosphereColor="#ffffff"
          atmosphereAltitude={0.22}
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
      </div>

      <div className="absolute right-4 top-4 z-10">
        <div className="glass px-2 py-1.5"><ModeToggle mode={mode} setMode={setMode} liveAvailable={health?.live_available} /></div>
      </div>

      <div className="absolute inset-x-4 bottom-4 z-10 max-h-[70vh] space-y-3 overflow-y-auto sm:inset-x-auto sm:left-4 sm:top-4 sm:max-h-none sm:w-[400px]">
        <div className="glass flex items-center gap-3 px-5 py-4">
          <Logo size={44} />
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-slate-900">Save the North</h1>
            <p className="text-[13px] text-slate-500">Satellite verification of industrial emissions for regulators.</p>
          </div>
        </div>

        <div className="glass space-y-4 p-5">
          <div className="space-y-2">
            <span className="label">Location</span>
            <LocationSearch initial={DEFAULT_QUERY} onPick={onPick} />
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="input" aria-label="Event date (UTC)" />
          </div>
          {sel && (
            <div className="space-y-2 rounded-2xl border border-slate-200/80 bg-white/80 p-4">
              <div className="text-[15px] font-semibold text-slate-900">{sel.name}</div>
              <div className="text-xs text-slate-500">{sel.operator ? sel.operator.split(" — ")[0] + " — potentially responsible operator" : "Operator unknown"}</div>
              <div className="text-[11px] text-slate-400">
                {sel.lat.toFixed(4)}, {sel.lon.toFixed(4)} · {sel.county} County, {sel.state}
                {sel.title_v_permit && <> · Title V {sel.title_v_permit}</>}{sel.nsr_authorization && <> · NSR {sel.nsr_authorization}</>}
              </div>
              <AvailabilityChips f={sel} />
            </div>
          )}
          <div className="flex items-center justify-between gap-3">
            <button onClick={() => setShowDs(true)} className="text-xs font-medium text-slate-500 hover:text-slate-900">View source datasets</button>
            <button disabled={!sel} className="btn-dark" onClick={() => sel && nav(`/assess/${sel.facility_id}?date=${date}&mode=${mode}`)}>
              Assess facility
            </button>
          </div>
        </div>

        <div className="glass p-5">
          <div className="label mb-3">Key data used</div>
          <ul className="space-y-3">
            {KEY_DATA.map((k) => (
              <li key={k.title} className="flex gap-3">
                <span className="mt-1.5 h-2.5 w-2.5 flex-none rounded-full" style={{ background: k.color }} />
                <div>
                  <div className="text-[13px] font-medium text-slate-800">{k.title}</div>
                  <div className="text-xs leading-snug text-slate-500">{k.detail}</div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="absolute right-4 top-20 z-10 hidden w-[340px] lg:block">
        <div className="glass p-2">
          <div className="label px-3 pb-1 pt-3">Monitored facilities</div>
          <ul>
            {facilities.map((f) => (
              <li key={f.facility_id}>
                <button onClick={() => selectFacility(f.facility_id)}
                  className={`w-full rounded-2xl px-3 py-3 text-left transition ${sel?.facility_id === f.facility_id ? "bg-white shadow-sm" : "hover:bg-white/60"}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold text-slate-800">{f.name}</span>
                    <span className="flex items-center gap-1.5 whitespace-nowrap text-[11px] text-slate-500">
                      <span className={`h-2 w-2 rounded-full ${f.data_status === "cached" ? "bg-red-500" : "bg-slate-300"}`} />
                      {f.data_status === "cached" ? "Plume detected" : "No observations"}
                    </span>
                  </div>
                  <div className="mt-0.5 text-xs text-slate-400">{f.county} County, {f.state}</div>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="pointer-events-none absolute bottom-3 right-4 hidden text-[10px] text-slate-500 sm:block">Earth imagery: NASA Blue Marble · screening estimates only</div>
      {showDs && <DatasetsModal onClose={() => setShowDs(false)} />}
    </div>
  );
}
