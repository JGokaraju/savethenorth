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
// 2x2 solid navy: the sphere reads as the page, so only the country outlines show
const SPHERE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEElEQVR42mMQ0wsEIgYIBQAPbgJVflHuUgAAAABJRU5ErkJggg==";
const IDLE_SPIN_MS = 5000;
const REVEAL_MARGIN = "0px 0px -30% 0px"; // reveal as the section arrives, not while it is still below the fold

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

/** Country outlines for the wireframe globe. */
function useCountries() {
  const [countries, setCountries] = useState<any[]>([]);
  useEffect(() => {
    fetch("/geo/countries.geojson").then((r) => r.json()).then((j) => setCountries(j.features)).catch(() => setCountries([]));
  }, []);
  return countries;
}

/** Hero globe: a dark sphere with country outlines only, the monitored sites marked on it.
 *  It idles with a slow spin, follows whichever site the list points at, and a marker click
 *  starts that site's assessment — the globe is the call to action. */
function HeroGlobe({ facilities, focus, onPick, onHover, reduced }: {
  facilities: Facility[]; focus: Facility | null; onPick: (id: string) => void;
  onHover: (id: string | null) => void; reduced: boolean;
}) {
  const globe = useRef<GlobeMethods>();
  const box = useElementSize<HTMLDivElement>();
  const countries = useCountries();
  const idle = useRef<number>();

  const spin = useCallback((on: boolean) => {
    const c = globe.current?.controls() as any;
    if (c) { c.autoRotate = on && !reduced; c.autoRotateSpeed = 0.5; }
  }, [reduced]);

  const spinLater = useCallback(() => {
    window.clearTimeout(idle.current);
    idle.current = window.setTimeout(() => spin(true), IDLE_SPIN_MS);
  }, [spin]);

  const onReady = useCallback(() => {
    const g = globe.current;
    if (!g) return;
    g.renderer().setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    const c = g.controls() as any;
    c.enableDamping = true;
    c.enableZoom = false; // the page scrolls; the globe must not capture the wheel
    c.addEventListener("start", () => { window.clearTimeout(idle.current); spin(false); });
    c.addEventListener("end", spinLater);
    g.pointOfView({ lat: 24, lng: -55, altitude: 2.4 }, 0);
    spin(true);
  }, [spin, spinLater]);

  useEffect(() => { // follow the site the list (or a marker hover) points at
    if (!focus) return;
    spin(false);
    globe.current?.pointOfView({ lat: focus.lat, lng: focus.lon, altitude: 1.6 }, reduced ? 0 : 1100);
    spinLater();
  }, [focus, spin, spinLater, reduced]);

  const points = useMemo(() => facilities.map((f) => ({
    ...f, hot: f.data_status === "cached", active: focus?.facility_id === f.facility_id,
  })), [facilities, focus]);

  return (
    <div ref={box.ref} className="relative aspect-square w-full [&_canvas]:cursor-grab [&_canvas]:active:cursor-grabbing">
      {box.w > 0 && (
        <Globe
          ref={globe}
          width={box.w}
          height={box.h}
          onGlobeReady={onReady}
          backgroundColor="rgba(0,0,0,0)"
          globeImageUrl={SPHERE}
          showAtmosphere
          atmosphereColor="#9ec5f2"
          atmosphereAltitude={0.13}
          polygonsData={countries}
          polygonCapColor={() => "rgba(255,255,255,0.05)"}
          polygonSideColor={() => "rgba(0,0,0,0)"}
          polygonStrokeColor={() => "rgba(255,255,255,0.8)"}
          polygonAltitude={0.006}
          pointsData={points}
          pointLat="lat"
          pointLng="lon"
          pointColor={(d: any) => (d.active ? "#ffffff" : d.hot ? "#ff6b57" : "rgba(255,255,255,0.7)")}
          pointAltitude={(d: any) => (d.active ? 0.09 : 0.03)}
          pointRadius={(d: any) => (d.active ? 0.55 : 0.35)}
          pointLabel={(d: any) => `<div style="padding:5px 8px;background:#162e51;border:1px solid rgba(255,255,255,.35);font:12px 'Public Sans',Arial;color:#fff"><b>${d.name}</b><br/><span style="opacity:.75">Click to assess</span></div>`}
          onPointClick={(d: any) => onPick(d.facility_id)}
          onPointHover={(d: any) => onHover(d ? d.facility_id : null)}
          ringsData={points.filter((d: any) => d.hot)}
          ringLat="lat"
          ringLng="lon"
          ringColor={() => (t: number) => `rgba(255,107,87,${1 - t})`}
          ringMaxRadius={4}
          ringPropagationSpeed={reduced ? 0 : 1.5}
          ringRepeatPeriod={1400}
        />
      )}
    </div>
  );
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose} role="dialog" aria-modal="true" aria-label="Source datasets">
      <div className="panel max-h-[85vh] w-full max-w-4xl overflow-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-rule px-6 py-4">
          <h2 className="text-xl font-bold text-ink">Source datasets</h2>
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
    <div className="border-b border-rule pb-4">
      <Eyebrow>{num} · {eyebrow}</Eyebrow>
      <h2 className="h2 mt-2">{title}</h2>
      {children}
    </div>
  );
}

const OUTCOME_CLS: Record<string, string> = {
  FAILED: "border-alert-red/60 bg-alert-red/15 text-alert-red", ACCEPTED: "border-alert-green/60 bg-alert-green/15 text-alert-green",
  INCONCLUSIVE: "border-alert-amber/60 bg-alert-amber/15 text-alert-amber", NOT_ASSESSED: "border-rule text-muted",
};

function RecentRuns({ runs }: { runs: RecentRun[] }) {
  const { ref, inView } = useInView<HTMLDivElement>(0, REVEAL_MARGIN);
  if (!runs.length) return null;
  return (
    <section id="recent" className="mx-auto max-w-6xl scroll-mt-24 px-6 py-16">
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
                  <a className="text-base font-bold text-ink hover:text-accent" href={`/assess/${r.facility_id}?date=${r.date}&run=${r.run_id}`}>
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
  const { ref: dataRef, inView: dataIn } = useInView<HTMLDivElement>(0, REVEAL_MARGIN);
  const reduced = useReducedMotion();
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [sel, setSel] = useState<Facility | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [date, setDate] = useState("2025-08-08");
  const [showDs, setShowDs] = useState(false);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [recent, setRecent] = useState<RecentRun[]>([]);

  useEffect(() => { api.facilities().then(setFacilities).catch((e) => toast(`Backend not reachable: ${e.message}`, "error")); }, [toast]);
  useEffect(() => { api.datasets().then(setDatasets).catch(() => setDatasets([])); }, []);
  useEffect(() => { api.recentRuns(5).then(setRecent).catch(() => setRecent([])); }, []);

  const selectFacility = useCallback((id: string) => {
    const f = facilities.find((x) => x.facility_id === id);
    if (f) setSel(f);
  }, [facilities]);

  useEffect(() => { // preselect the default case
    if (!facilities.length || sel) return;
    setSel(facilities.find((f) => f.facility_id === DEFAULT_ID) ?? null);
  }, [facilities, sel]);

  // the globe follows the row under the cursor, falling back to the selected site
  const focus = useMemo(() => facilities.find((f) => f.facility_id === (hover ?? sel?.facility_id)) ?? null,
                        [facilities, hover, sel]);

  const onPick = (r: GeoResult) => {
    const id = r.facility_id ?? r.nearest_facility?.facility_id;
    if (id) selectFacility(id);
    else { setSel(null); toast(`No monitored facility within 25 km of ${r.label}.`, "info"); }
  };
  const assess = (f?: Facility) => {
    const t = f ?? sel;
    if (t) nav(`/assess/${t.facility_id}?date=${date}&mode=${mode}`);
  };
  const counts = datasets.length ? datasetCounts(datasets) : [];

  return (
    <div>
      {/* ------------------------------------------------------------------ hero */}
      <section id="hero" className="relative flex min-h-[calc(100vh-40px)] flex-col justify-center overflow-hidden">
        <img src="/landing-bg.jpg" alt="" aria-hidden className="slow-zoom absolute inset-0 h-full w-full object-cover" />
        <div className="absolute inset-0 bg-primary-darker/90" aria-hidden />
        <SiteHeader overlay hideWordmark right={<button onClick={() => setShowDs(true)} className="underline underline-offset-2 hover:text-white">Data sources</button>} />

        <div className="relative mx-auto grid w-full max-w-6xl items-center gap-8 px-6 py-14 lg:grid-cols-[minmax(0,1fr)_minmax(0,560px)] lg:gap-12">
          <div>
            <h1 className="fade-in text-6xl font-bold leading-[0.92] tracking-tight text-white sm:text-8xl">
              Save the<br />North
            </h1>
            <p className="fade-in mt-5 max-w-md text-lg leading-snug text-white/75 sm:text-xl" style={{ animationDelay: "0.2s" }}>
              Agentic analysis of factory emissions
            </p>

            {/* the site list is the call to action: it steers the globe and starts the assessment */}
            <div className="fade-in mt-10" style={{ animationDelay: "0.4s" }}>
              <p className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.16em] text-white/50">
                <span className="block h-px w-6 bg-white/40" aria-hidden />
                Monitored sites — select one to assess
              </p>
              <ul className="mt-3 border-t border-white/15">
                {facilities.map((f) => (
                  <li key={f.facility_id}>
                    <button
                      onMouseEnter={() => setHover(f.facility_id)}
                      onFocus={() => setHover(f.facility_id)}
                      onMouseLeave={() => setHover(null)}
                      onBlur={() => setHover(null)}
                      onClick={() => assess(f)}
                      className="group flex w-full items-center gap-3 border-b border-white/15 py-3 text-left transition-colors hover:bg-white/[0.07] focus:bg-white/[0.07] focus:outline-none">
                      <span aria-hidden className={`h-2 w-2 flex-none ${f.data_status === "cached" ? "bg-[#ff6b57]" : "bg-white/50"}`} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[17px] font-semibold text-white">{f.name}</span>
                        <span className="block truncate text-[13px] text-white/55">
                          {f.county} County, {f.state}
                          {f.data_status === "cached" ? " · methane plume on record" : " · no observations yet"}
                        </span>
                      </span>
                      <span className="flex-none text-[12px] font-bold uppercase tracking-[0.12em] text-transparent transition-colors group-hover:text-white group-focus:text-white">
                        Assess →
                      </span>
                    </button>
                  </li>
                ))}
                {!facilities.length && <li className="border-b border-white/15 py-3 text-white/60">Loading sites…</li>}
              </ul>
              <button onClick={() => document.getElementById("data")?.scrollIntoView({ behavior: "smooth" })}
                className="mt-6 flex items-center gap-2 text-[12px] font-bold uppercase tracking-[0.14em] text-white/70 hover:text-white">
                How the data is collected
                <svg viewBox="0 0 24 24" className="nudge h-4 w-4"><path fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="square" d="M12 4v16M6 14l6 6 6-6" /></svg>
              </button>
            </div>
          </div>

          <div className="fade-in order-first lg:order-none" style={{ animationDelay: "0.3s" }}>
            <HeroGlobe facilities={facilities} focus={focus} reduced={reduced}
              onPick={(id) => assess(facilities.find((x) => x.facility_id === id))}
              onHover={setHover} />
            <p className="mt-1 text-right text-[10px] uppercase tracking-[0.14em] text-white/40">Drag to rotate · click a site to assess</p>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------- 01 the data */}
      <section id="data" className="mx-auto max-w-6xl scroll-mt-24 px-6 py-16">
        <div ref={dataRef} className={`reveal ${dataIn ? "in" : ""}`}>
          <SectionHead num="01" eyebrow="Where it looks" title="How the data is collected" />
          <div className="mt-8 grid gap-x-12 gap-y-6 lg:grid-cols-2">
            {[DATA_BULLETS.slice(0, 3), DATA_BULLETS.slice(3)].map((col, i) => (
              <ul key={i} className="space-y-5">
                {col.map((d) => (
                  <li key={d.title} className="border-l-[3px] border-accent pl-4">
                    <div className="font-bold text-ink">{d.title}</div>
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
                  <dd className="text-2xl font-bold tabular-nums text-ink">{c.value}</dd>
                  <dt className="mt-1 text-[10px] uppercase tracking-[0.16em] text-muted">{c.label}</dt>
                </div>
              ))}
            </dl>
          )}

          <p className="label mt-12">What the agent does with it</p>
          <ol className="mt-4 grid gap-px border border-rule bg-rule sm:grid-cols-5">
            {PIPELINE.map((s) => (
              <li key={s.n} className="bg-page px-4 py-5">
                <span className="text-xl font-bold text-accent">{String(s.n).padStart(2, "0")}</span>
                <div className="mt-1 text-ink">{s.t}</div>
                <p className="mt-1 text-xs leading-snug text-muted">{s.d}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ----------------------------------------------------------- 02 assessment */}
      <section id="assess" className="scroll-mt-24 border-t border-rule bg-panel py-16">
        <div className="mx-auto max-w-6xl px-6">
          <SectionHead num="02" eyebrow="Run an assessment" title="Assess a facility" />

          <div className="mt-8 grid gap-4 sm:grid-cols-[1fr_auto_auto] sm:items-end">
            <div>
              <span className="label mb-2 block">Facility or location</span>
              <LocationSearch initial={DEFAULT_QUERY} onPick={onPick} />
            </div>
            <label className="block">
              <span className="label mb-2 block">Event date (UTC)</span>
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="input w-auto [color-scheme:dark]" />
            </label>
            <button disabled={!sel} className="btn-dark h-[46px]" onClick={() => assess()}>Assess facility</button>
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
                    <button className={`text-left text-[15px] font-bold ${sel?.facility_id === f.facility_id ? "text-accent" : "text-ink"}`}>{f.name}</button>
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

        </div>
      </section>

      {/* ------------------------------------------------------------- 03 previous */}
      <RecentRuns runs={recent} />
      <Footer />
      {showDs && <DatasetsModal onClose={() => setShowDs(false)} />}
    </div>
  );
}
