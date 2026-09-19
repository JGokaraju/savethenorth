import { ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Globe, { GlobeMethods } from "react-globe.gl";
import { useNavigate } from "react-router-dom";
import { AvailabilityChips, LocationSearch } from "../components/FacilityPanel";
import { Footer, SiteHeader, useHealth } from "../components/Header";
import { useToast } from "../components/Toasts";
import { Eyebrow, ModeToggle, ShortHash, Spinner } from "../components/ui";
import { api, Dataset, Facility, GeoResult, RecentRun } from "../lib/api";
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

const PIPELINE = [
  { n: 1, t: "Discover", d: "Inventory the data and its gaps" },
  { n: 2, t: "Quantify", d: "Plume mask, mass, wind, uncertainty" },
  { n: 3, t: "Explain", d: "Flares, imagery, permit, physics" },
  { n: 4, t: "Screen", d: "Federal and Texas rules" },
  { n: 5, t: "Rank", d: "Hybrid search and rerank, then verdict" },
];

const SECTIONS = [
  { id: "hero", label: "Start" },
  { id: "data", label: "01" },
  { id: "assess", label: "02" },
  { id: "recent", label: "03" },
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose} role="dialog" aria-modal="true" aria-label="Source datasets">
      <div className="panel max-h-[85vh] w-full max-w-4xl overflow-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-rule px-6 py-4">
          <h2 className="font-display text-2xl text-ink">Source datasets</h2>
          <button onClick={onClose} className="read-more" aria-label="Close">Close</button>
        </div>
        {!ds ? <div className="p-6"><Spinner /></div> : (
          <table className="w-full text-sm">
            <thead className="border-b border-rule text-left text-[11px] uppercase tracking-[0.16em] text-muted">
              <tr><th className="px-6 py-3">Dataset</th><th className="px-6 py-3">Status</th><th className="px-6 py-3">Coverage</th><th className="px-6 py-3">Integrity</th></tr>
            </thead>
            <tbody>
              {ds.map((d) => (
                <tr key={d.slot_id} className="border-b border-rule/60 align-top">
                  <td className="px-6 py-3">
                    <div className="text-ink">{d.source_name}</div>
                    <div className="text-xs text-muted">{d.citation}</div>
                    {d.source_url && <a href={d.source_url} target="_blank" rel="noreferrer" className="link text-xs">Source</a>}
                  </td>
                  <td className="px-6 py-3 text-xs text-muted">{d.status !== "present" ? "Missing" : d.synthetic ? "Placeholder" : d.quality === "low" ? "Low quality" : "Available"}</td>
                  <td className="px-6 py-3 text-xs text-muted">{d.date_coverage}</td>
                  <td className="px-6 py-3"><ShortHash hash={d.sha256} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

/** Live counts from the manifest, so the landing page shows the real corpus size. */
function datasetCounts(ds: Dataset[]): { label: string; value: string }[] {
  const by = Object.fromEntries(ds.map((d) => [d.slot_id, d])) as Record<string, any>;
  const n = (v: any) => (typeof v === "number" ? v.toLocaleString() : null);
  const rows: [string, string | null][] = [
    ["EMIT pixels analysed", n(by.emit_ch4enh?.stats?.valid_pixels)],
    ["VIIRS detections", n(by.firms?.stats?.rows)],
    ["Hourly wind records", n(by.wind?.stats?.n_hours)],
    ["Permit pages", n(by.tceq_sob?.stats?.pages)],
    ["Emissions-event rows", n(by.tceq_steers?.stats?.rows)],
    ["Datasets tracked", String(ds.filter((d) => d.status === "present").length)],
  ];
  return rows.filter(([, v]) => v).map(([label, value]) => ({ label, value: value as string }));
}

function SectionHead({ num, eyebrow, title, children }: { num: string; eyebrow: string; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end gap-x-8 gap-y-2">
      <span className="numeral">{num}</span>
      <div className="min-w-0 flex-1">
        <Eyebrow>{eyebrow}</Eyebrow>
        <h2 className="h2 mt-3">{title}</h2>
        {children}
      </div>
    </div>
  );
}

const OUTCOME_CLS: Record<string, string> = {
  FAILED: "border-alert-red/60 bg-alert-red/15 text-alert-red", ACCEPTED: "border-alert-green/60 bg-alert-green/15 text-alert-green",
  INCONCLUSIVE: "border-alert-amber/60 bg-alert-amber/15 text-alert-amber", NOT_ASSESSED: "border-rule text-muted",
};

function RecentRuns({ runs }: { runs: RecentRun[] }) {
  const { ref, inView } = useInView<HTMLDivElement>(0.15);
  if (!runs.length) return null;
  return (
    <section id="recent" className="mx-auto max-w-6xl scroll-mt-24 px-6 py-20">
      <div ref={ref} className={`reveal ${inView ? "in" : ""}`}>
        <SectionHead num="03" eyebrow="Previous work" title="Recent assessments" />
        <table className="mt-8 w-full border-t border-rule text-sm">
          <thead className="text-left text-[11px] uppercase tracking-[0.16em] text-muted">
            <tr><th className="py-3 pr-4">Facility</th><th className="py-3 pr-4">Event date</th><th className="py-3 pr-4">Mode</th>
              <th className="py-3 pr-4">Rate</th><th className="py-3">Outcome</th></tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.run_id} className="border-t border-rule/60 transition-colors hover:bg-panel">
                <td className="py-4 pr-4">
                  <a className="font-display text-lg text-ink hover:text-gold" href={`/assess/${r.facility_id}?date=${r.date}&run=${r.run_id}`}>
                    {r.facility_name ?? r.facility_id}
                  </a>
                </td>
                <td className="py-4 pr-4 text-muted">{r.date}</td>
                <td className="py-4 pr-4 text-muted">{r.mode === "LIVE" ? "Live" : r.mode === "REPLAY" ? "Replay" : "Demo"}</td>
                <td className="py-4 pr-4 font-mono tabular-nums text-ink">{r.median_kg_h ? `${(r.median_kg_h / 1000).toFixed(1)} t/h` : "—"}</td>
                <td className="py-4">
                  {r.finished && r.outcome
                    ? <span className={`border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] ${OUTCOME_CLS[r.outcome] ?? OUTCOME_CLS.NOT_ASSESSED}`}>{r.outcome.replace("_", " ")}</span>
                    : <span className="text-xs text-muted">in progress</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
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
  const { ref: globeSection, inView: globeVisible } = useInView<HTMLDivElement>(0.3);
  const { ref: dataRef, inView: dataIn } = useInView<HTMLDivElement>(0.2);
  const reduced = useReducedMotion();
  const tex = useTextures();
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [sel, setSel] = useState<Facility | null>(null);
  const [date, setDate] = useState("2025-08-08");
  const [showDs, setShowDs] = useState(false);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [recent, setRecent] = useState<RecentRun[]>([]);
  const resumeTimer = useRef<number>();
  const userLocked = useRef(false); // stop auto-rotation once a location is chosen

  useEffect(() => { api.facilities().then(setFacilities).catch((e) => toast(`Backend not reachable: ${e.message}`, "error")); }, [toast]);
  useEffect(() => { api.datasets().then(setDatasets).catch(() => setDatasets([])); }, []);
  useEffect(() => { api.recentRuns(5).then(setRecent).catch(() => setRecent([])); }, []);

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
    ...f, color: f.data_status === "cached" ? "#e05c4b" : "#f3f1ea", size: 0.012,
    label: f.data_status === "cached" ? "Methane plume detected" : "No cached observations",
  })), [facilities]);
  const rings = useMemo(() => facilities.map((f) => ({ lat: f.lat, lng: f.lon, hot: f.data_status === "cached" })), [facilities]);

  const onPick = (r: GeoResult) => {
    const id = r.facility_id ?? r.nearest_facility?.facility_id;
    if (id) selectFacility(id);
    else { setSel(null); flyTo(r.lat, r.lon); toast(`No monitored facility within 25 km of ${r.label}.`, "info"); }
  };
  const assess = () => sel && nav(`/assess/${sel.facility_id}?date=${date}&mode=${mode}`);
  const counts = datasets.length ? datasetCounts(datasets) : [];

  return (
    <div>
      {/* ------------------------------------------------------------------ hero */}
      <section id="hero" className="relative flex min-h-screen flex-col justify-center overflow-hidden">
        <img src="/landing-bg.jpg" alt="" aria-hidden className="slow-zoom absolute inset-0 h-full w-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-b from-page/85 via-page/60 to-page" aria-hidden />
        <SiteHeader overlay right={<button onClick={() => setShowDs(true)} className="hover:text-gold">Data sources</button>} />

        {/* instrument rail */}
        <div className="pointer-events-none absolute bottom-28 left-7 hidden lg:block">
          <span className="block origin-bottom-left -rotate-90 whitespace-nowrap text-[11px] font-semibold uppercase tracking-[0.3em] text-muted">
            EMIT · VIIRS · Sentinel-2 · ERA5
          </span>
        </div>
        {/* section index */}
        <nav className="absolute right-8 top-1/2 hidden -translate-y-1/2 flex-col items-end gap-3 text-[11px] font-semibold uppercase tracking-[0.2em] lg:flex" aria-label="Sections">
          {SECTIONS.map((s, i) => (
            <button key={s.id} onClick={() => document.getElementById(s.id)?.scrollIntoView({ behavior: "smooth" })}
              className={i === 0 ? "text-gold" : "text-muted hover:text-ink"}>{s.label}</button>
          ))}
        </nav>

        <div className="relative mx-auto w-full max-w-6xl px-6">
          <div className="max-w-2xl">
            <Eyebrow className="fade-in">Satellite emissions verification</Eyebrow>
            <h1 className="fade-in mt-6 font-display text-5xl leading-[1.05] text-ink sm:text-7xl" style={{ animationDelay: "0.25s" }}>
              Watching methane<br />from orbit
            </h1>
            <p className="fade-in mt-6 max-w-xl text-[17px] leading-relaxed text-muted" style={{ animationDelay: "0.6s" }}>
              An agent that measures industrial methane plumes from satellite data, checks them against the operator&rsquo;s own
              filings, and shows the source of every number.
            </p>
            <button onClick={() => document.getElementById("data")?.scrollIntoView({ behavior: "smooth" })}
              className="fade-in mt-10 flex items-center gap-3 text-[12px] font-semibold uppercase tracking-[0.2em] text-ink hover:text-gold"
              style={{ animationDelay: "0.9s" }}>
              Scroll down
              <svg viewBox="0 0 24 24" className="nudge h-5 w-5"><path fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="square" d="M12 4v16M6 14l6 6 6-6" /></svg>
            </button>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------- 01 the data */}
      <section id="data" className="mx-auto max-w-6xl scroll-mt-24 px-6 py-20">
        <div ref={dataRef} className={`reveal ${dataIn ? "in" : ""}`}>
          <SectionHead num="01" eyebrow="Where it looks" title="How the data is collected" />
          <div className="mt-8 grid gap-x-12 gap-y-6 lg:grid-cols-2">
            {[DATA_BULLETS.slice(0, 3), DATA_BULLETS.slice(3)].map((col, i) => (
              <ul key={i} className="space-y-5">
                {col.map((d) => (
                  <li key={d.title} className="border-l border-gold/50 pl-4">
                    <div className="text-ink">{d.title}</div>
                    <div className="text-sm leading-relaxed text-muted">{d.line}</div>
                  </li>
                ))}
              </ul>
            ))}
          </div>

          {counts.length > 0 && (
            <dl className="mt-12 grid grid-cols-2 gap-px border border-rule bg-rule sm:grid-cols-3 lg:grid-cols-6">
              {counts.map((c) => (
                <div key={c.label} className="bg-page px-4 py-5">
                  <dd className="font-display text-3xl text-ink">{c.value}</dd>
                  <dt className="mt-1 text-[10px] uppercase tracking-[0.16em] text-muted">{c.label}</dt>
                </div>
              ))}
            </dl>
          )}

          <p className="label mt-12">What the agent does with it</p>
          <ol className="mt-4 grid gap-px border border-rule bg-rule sm:grid-cols-5">
            {PIPELINE.map((s) => (
              <li key={s.n} className="bg-page px-4 py-5">
                <span className="font-display text-2xl text-gold">{String(s.n).padStart(2, "0")}</span>
                <div className="mt-1 text-ink">{s.t}</div>
                <p className="mt-1 text-xs leading-snug text-muted">{s.d}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ----------------------------------------------------------- 02 assessment */}
      <section id="assess" className="scroll-mt-24 border-t border-rule bg-panel/40 py-20">
        <div ref={globeSection} className="mx-auto max-w-6xl px-6">
          <SectionHead num="02" eyebrow="Run an assessment" title="Assess a facility" />

          {/* the search form sits above the globe, never on top of it */}
          <div className="mt-8 grid gap-4 sm:grid-cols-[1fr_auto_auto] sm:items-end">
            <div>
              <span className="label mb-2 block">Facility or location</span>
              <LocationSearch initial={DEFAULT_QUERY} onPick={onPick} />
            </div>
            <label className="block">
              <span className="label mb-2 block">Event date (UTC)</span>
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="input w-auto [color-scheme:dark]" />
            </label>
            <button disabled={!sel} className="btn-dark h-[46px]" onClick={assess}>Assess facility</button>
          </div>
          <div className="mt-4"><ModeToggle mode={mode} setMode={setMode} liveAvailable={health?.live_available} /></div>

          <table className="mt-10 w-full border-t border-rule text-sm">
            <caption className="sr-only">Monitored facilities</caption>
            <thead className="text-left text-[11px] uppercase tracking-[0.16em] text-muted">
              <tr><th className="py-3 pr-4">Facility</th><th className="py-3 pr-4">Location</th>
                <th className="hidden py-3 pr-4 md:table-cell">Operator</th><th className="py-3">Satellite data</th></tr>
            </thead>
            <tbody>
              {facilities.map((f) => (
                <tr key={f.facility_id} onClick={() => selectFacility(f.facility_id)}
                  className={`cursor-pointer border-t border-rule/60 transition-colors ${sel?.facility_id === f.facility_id ? "bg-panel2" : "hover:bg-panel"}`}>
                  <td className="py-4 pr-4">
                    <button className={`text-left font-display text-lg ${sel?.facility_id === f.facility_id ? "text-gold" : "text-ink"}`}>{f.name}</button>
                  </td>
                  <td className="py-4 pr-4 text-muted">{f.county} County, {f.state}</td>
                  <td className="hidden py-4 pr-4 text-muted md:table-cell">{f.operator?.split(" — ")[0] ?? "—"}</td>
                  <td className="py-4">
                    {f.data_status === "cached"
                      ? <span className="text-alert-red">Methane plume detected</span>
                      : <span className="text-muted">No observations</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {sel && (
            <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
              <span className="label">Data available for {sel.name}</span><AvailabilityChips f={sel} />
            </div>
          )}

          <div ref={box.ref} className="relative mt-10 h-[70vh] min-h-[460px] w-full border border-rule bg-page">
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
                atmosphereColor="#9bd3ff"
                atmosphereAltitude={0.18}
                polygonsData={tex.earth ? [] : tex.countries}
                polygonCapColor={() => "rgba(36,57,60,0.9)"}
                polygonSideColor={() => "rgba(0,0,0,0)"}
                polygonStrokeColor={() => "#4a6b6d"}
                pointsData={points}
                pointLat="lat"
                pointLng="lon"
                pointColor="color"
                pointAltitude="size"
                pointRadius={0.35}
                pointLabel={(d: any) => `<div style="padding:6px 8px;background:#102124;border:1px solid #24393c;font:13px 'Public Sans',Arial;color:#f3f1ea"><b>${d.name}</b><br/><span style="color:#9bacab">${d.label}</span></div>`}
                onPointClick={(d: any) => selectFacility(d.facility_id)}
                onPointHover={(d: any) => { if (d) { window.clearTimeout(resumeTimer.current); setRotate(false); } else if (!userLocked.current) pauseThenResume(); }}
                ringsData={rings}
                ringColor={(d: any) => (t: number) => d.hot ? `rgba(224,92,75,${1 - t})` : `rgba(243,241,234,${0.8 * (1 - t)})`}
                ringMaxRadius={(d: any) => (d.hot ? 4.5 : 1.8)}
                ringPropagationSpeed={reduced ? 0 : 1.4}
                ringRepeatPeriod={(d: any) => (d.hot ? 1100 : 2200)}
              />
            )}
          </div>
          <p className="mt-2 text-right text-[10px] uppercase tracking-[0.16em] text-muted">Earth imagery: NASA Blue Marble</p>
        </div>
      </section>

      {/* ------------------------------------------------------------- 03 previous */}
      <RecentRuns runs={recent} />
      <Footer />
      {showDs && <DatasetsModal onClose={() => setShowDs(false)} />}
    </div>
  );
}
