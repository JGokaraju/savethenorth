import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Globe, { GlobeMethods } from "react-globe.gl";
import { useNavigate } from "react-router-dom";
import { AvailabilityChips, LocationSearch } from "../components/FacilityPanel";
import { Footer, SiteHeader, useHealth } from "../components/Header";
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

const DATA_BULLETS: { title: string; line: string }[] = [
  { title: "Methane", line: "NASA EMIT imaging spectrometer, 60 m methane enhancement" },
  { title: "Heat and flares", line: "NASA VIIRS thermal detections: fire radiative power, brightness temperature" },
  { title: "Imagery", line: "Copernicus Sentinel-2 true colour and shortwave infrared; high-resolution site imagery" },
  { title: "Weather and wind", line: "ERA5 reanalysis: 10 m wind speed and direction, temperature, pressure" },
  { title: "Technical reports", line: "TCEQ Title V permit (Statement of Basis) and emissions-event reports" },
  { title: "Cross-check", line: "Carbon Mapper plume records" },
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose} role="dialog" aria-modal="true" aria-label="Source datasets">
      <div className="max-h-[85vh] w-full max-w-4xl overflow-auto border border-rule bg-white" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-rule bg-paper px-5 py-3">
          <h2 className="text-lg font-bold text-ink">Source datasets</h2>
          <button onClick={onClose} className="btn-light px-3 py-1" aria-label="Close">Close</button>
        </div>
        {!ds ? <div className="p-5"><Spinner /></div> : (
          <table className="w-full text-sm">
            <thead className="bg-paper text-left text-xs uppercase tracking-wide text-muted">
              <tr><th className="px-4 py-2">Dataset</th><th className="px-4 py-2">Status</th><th className="px-4 py-2">Coverage</th><th className="px-4 py-2">Integrity</th></tr>
            </thead>
            <tbody>
              {ds.map((d) => (
                <tr key={d.slot_id} className="border-t border-rule align-top">
                  <td className="px-4 py-2.5">
                    <div className="font-semibold text-ink">{d.source_name}</div>
                    <div className="text-xs text-muted">{d.citation}</div>
                    {d.source_url && <a href={d.source_url} target="_blank" rel="noreferrer" className="link text-xs">Source</a>}
                  </td>
                  <td className="px-4 py-2.5 text-xs">{d.status !== "present" ? "Missing" : d.synthetic ? "Placeholder" : d.quality === "low" ? "Low quality" : "Available"}</td>
                  <td className="px-4 py-2.5 text-xs text-muted">{d.date_coverage}</td>
                  <td className="px-4 py-2.5"><ShortHash hash={d.sha256} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function Hero() {
  return (
    <section className="relative flex min-h-[calc(100vh-64px)] flex-col items-center justify-center overflow-hidden px-6 text-center">
      <img src="/landing-bg.jpg" alt="" aria-hidden className="absolute inset-0 h-full w-full object-cover" />
      <div className="absolute inset-0 bg-[#0b1a2e]/55" aria-hidden />
      <div className="relative flex flex-col items-center">
        <div className="fade-in"><Logo size={128} speed={30} /></div>
        <h1 className="fade-in mt-6 text-5xl font-extrabold tracking-tight text-white sm:text-7xl" style={{ animationDelay: "0.3s" }}>Save the North</h1>
        <p className="fade-in mt-3 max-w-xl text-lg text-[#e6ebf0]" style={{ animationDelay: "0.7s" }}>
          Independent satellite verification of methane emissions from industrial facilities.
        </p>
      </div>
      <button onClick={() => document.getElementById("data")?.scrollIntoView({ behavior: "smooth" })}
        className="fade-in absolute bottom-8 text-white/80 hover:text-white" style={{ animationDelay: "1.2s" }} aria-label="Scroll down">
        <svg viewBox="0 0 24 24" className="nudge h-8 w-8"><path fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="square" d="M6 9l6 6 6-6" /></svg>
      </button>
    </section>
  );
}

function DataSection() {
  const { ref, inView } = useInView<HTMLDivElement>(0.25);
  return (
    <section id="data" className="border-b border-rule bg-paper">
      <div ref={ref} className={`reveal mx-auto max-w-6xl px-4 py-12 ${inView ? "in" : ""}`}>
        <h2 className="h2">How the data is collected</h2>
        <ul className="mt-5 grid list-disc gap-x-12 gap-y-2 pl-5 text-[15px] leading-relaxed text-ink sm:grid-cols-2">
          {DATA_BULLETS.map((d) => <li key={d.title}><b>{d.title}:</b> <span className="text-muted">{d.line}</span></li>)}
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
  const { ref: globeSection, inView: globeVisible } = useInView<HTMLElement>(0.3);
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
    ...f, color: f.data_status === "cached" ? "#b50909" : "#ffffff", size: 0.012,
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
      <SiteHeader right={<button onClick={() => setShowDs(true)} className="font-semibold text-white underline underline-offset-2">Data sources</button>} />
      <Hero />
      <DataSection />

      <section ref={globeSection} className="mx-auto max-w-6xl px-4 py-12">
        <h2 className="h2">Assess a facility</h2>
        {/* the search form sits above the globe, never on top of it */}
        <div className="mt-5 grid gap-4 sm:grid-cols-[1fr_auto_auto] sm:items-end">
          <div>
            <span className="mb-1 block text-sm font-bold text-ink">Facility or location</span>
            <LocationSearch initial={DEFAULT_QUERY} onPick={onPick} />
          </div>
          <label className="block">
            <span className="mb-1 block text-sm font-bold text-ink">Event date (UTC)</span>
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="input w-auto" />
          </label>
          <button disabled={!sel} className="btn-dark h-[42px]" onClick={assess}>Assess facility</button>
        </div>
        <div className="mt-3"><ModeToggle mode={mode} setMode={setMode} liveAvailable={health?.live_available} /></div>

        <table className="mt-6 w-full border border-rule text-sm">
          <caption className="sr-only">Monitored facilities</caption>
          <thead className="bg-paper text-left text-xs uppercase tracking-wide text-muted">
            <tr><th className="px-4 py-2">Facility</th><th className="px-4 py-2">Location</th><th className="hidden px-4 py-2 md:table-cell">Operator</th><th className="px-4 py-2">Satellite data</th></tr>
          </thead>
          <tbody>
            {facilities.map((f) => (
              <tr key={f.facility_id} onClick={() => selectFacility(f.facility_id)}
                className={`cursor-pointer border-t border-rule ${sel?.facility_id === f.facility_id ? "bg-[#e7f2f8]" : "hover:bg-paper"}`}>
                <td className="px-4 py-2.5 font-semibold text-primary">
                  <button className="text-left underline-offset-2 hover:underline">{f.name}</button>
                </td>
                <td className="px-4 py-2.5 text-muted">{f.county} County, {f.state}</td>
                <td className="hidden px-4 py-2.5 text-muted md:table-cell">{f.operator?.split(" — ")[0] ?? "—"}</td>
                <td className="px-4 py-2.5">
                  {f.data_status === "cached"
                    ? <span className="font-semibold text-alert-red">Methane plume detected</span>
                    : <span className="text-muted">No observations</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {sel && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
            <span className="font-bold text-ink">Data available for {sel.name}:</span><AvailabilityChips f={sel} />
          </div>
        )}

        <div ref={box.ref} className="relative mt-8 h-[70vh] min-h-[460px] w-full border border-rule bg-[#f7f9fa] [&_canvas]:[filter:brightness(1.12)_saturate(0.85)]">
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
              atmosphereAltitude={0.15}
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
              pointLabel={(d: any) => `<div style="padding:6px 8px;background:#fff;border:1px solid #dfe1e2;font:13px 'Public Sans',Arial;color:#1b1b1b"><b>${d.name}</b><br/><span style="color:#565c65">${d.label}</span></div>`}
              onPointClick={(d: any) => selectFacility(d.facility_id)}
              onPointHover={(d: any) => { if (d) { window.clearTimeout(resumeTimer.current); setRotate(false); } else if (!userLocked.current) pauseThenResume(); }}
              ringsData={rings}
              ringColor={(d: any) => (t: number) => d.hot ? `rgba(181,9,9,${1 - t})` : `rgba(255,255,255,${0.9 * (1 - t)})`}
              ringMaxRadius={(d: any) => (d.hot ? 4.5 : 1.8)}
              ringPropagationSpeed={reduced ? 0 : 1.4}
              ringRepeatPeriod={(d: any) => (d.hot ? 1100 : 2200)}
            />
          )}
        </div>
        <p className="mt-2 text-right text-[11px] text-muted">Earth imagery: NASA Blue Marble</p>
      </section>
      <Footer />
      {showDs && <DatasetsModal onClose={() => setShowDs(false)} />}
    </div>
  );
}
