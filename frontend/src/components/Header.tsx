import { ReactNode, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Health } from "../lib/api";
import { Logo } from "./ui";

export function useHealth(pollMs = 8000) {
  const [h, setH] = useState<Health | null>(null);
  useEffect(() => {
    let alive = true;
    const tick = () => api.health().then((x) => alive && setH(x)).catch(() => alive && setH(null));
    tick();
    const t = setInterval(tick, pollMs);
    return () => { alive = false; clearInterval(t); };
  }, [pollMs]);
  return h;
}

/** Slim band above the header, in the manner of a public-agency site. */
function DisclosureStrip() {
  return (
    <div className="bg-primary-darker text-white">
      <div className="mx-auto flex max-w-6xl items-center gap-2 px-6 py-1.5 text-[12px] leading-tight">
        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 flex-none" aria-hidden>
          <path fill="currentColor" d="M8 1l6 3v4c0 3.3-2.5 6.2-6 7-3.5-.8-6-3.7-6-7V4l6-3z" />
        </svg>
        <span>Independent screening prototype — not an official government service.</span>
      </div>
    </div>
  );
}

/** Site header. `overlay` floats it above a hero image; otherwise it sits on the page background. */
export function SiteHeader({ right, overlay = false }: { right?: ReactNode; overlay?: boolean }) {
  return (
    <div className={overlay ? "absolute inset-x-0 top-0 z-30" : "sticky top-0 z-30 bg-page"}>
      <DisclosureStrip />
      <header className={overlay ? "border-b border-white/25" : "border-b-[3px] border-primary-dark bg-page"}>
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-6 py-3">
          <Link to="/" className={`flex items-center gap-3 ${overlay ? "text-white" : "text-ink"}`} aria-label="Save the North — home">
            <Logo size={34} />
            <span className="leading-none">
              <span className="block text-xl font-bold tracking-tight">Save the North</span>
              <span className={`mt-1 block text-[11px] font-semibold uppercase tracking-[0.12em] ${overlay ? "text-white/75" : "text-muted"}`}>
                Satellite methane verification
              </span>
            </span>
          </Link>
          <div className={`flex items-center gap-5 text-[14px] font-semibold ${overlay ? "text-white/90" : "text-accent"}`}>{right}</div>
        </div>
      </header>
    </div>
  );
}

/** Compact controls bar under the header (assessment workspace). */
export function TopBar({ children, right }: { children?: ReactNode; right?: ReactNode }) {
  return (
    <>
      <SiteHeader />
      <div className="border-b border-rule bg-panel">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3 px-6 py-4">
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3">{children}</div>
          {right}
        </div>
      </div>
    </>
  );
}

export function Footer() {
  return (
    <footer className="mt-16 border-t-[6px] border-primary-dark bg-primary-darker text-white">
      <div className="mx-auto grid max-w-6xl gap-8 px-6 py-12 text-[13px] leading-relaxed text-white/80 sm:grid-cols-3">
        <div>
          <p className="mb-3 text-[13px] font-bold uppercase tracking-[0.08em] text-white">Data sources</p>
          <ul className="space-y-1">
            <li>NASA EMIT L2B methane enhancement v002</li>
            <li>NASA FIRMS VIIRS active fire</li>
            <li>Copernicus Sentinel-2; site imagery by Esri, Maxar</li>
            <li>Open-Meteo / ERA5 weather</li>
            <li>TCEQ permit and emissions-event reports</li>
            <li>Carbon Mapper (placeholder values in this build)</li>
          </ul>
        </div>
        <div>
          <p className="mb-3 text-[13px] font-bold uppercase tracking-[0.08em] text-white">Method and rules</p>
          <ul className="space-y-1">
            <li>Varon et al. (2018), integrated mass enhancement</li>
            <li>40 CFR 60.5371a/b — super-emitter programme</li>
            <li>30 TAC 101.201 and 101.1 — emissions events</li>
            <li>doi:10.5067/EMIT/EMITL2BCH4ENH.002</li>
          </ul>
        </div>
        <div>
          <p className="mb-3 text-[13px] font-bold uppercase tracking-[0.08em] text-white">About</p>
          <p>Screening estimates only — not enforcement determinations. An independent prototype, not an official government service.</p>
          <p className="mt-3 flex items-center gap-2"><img src="/logo.png" alt="" width={18} height={18} /> Built at Hack the North.</p>
        </div>
      </div>
    </footer>
  );
}

export function Brand() {
  return <Link to="/" className="font-bold text-ink">Save the North</Link>;
}
