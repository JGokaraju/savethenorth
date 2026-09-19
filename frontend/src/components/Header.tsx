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

/** Site header: solid navy bar with the service name. */
export function SiteHeader({ right }: { right?: ReactNode }) {
  return (
    <header className="sticky top-0 z-30 bg-primary-darker text-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
        <Link to="/" className="group flex items-center gap-3" aria-label="Save the North — home">
          <Logo size={36} />
          <span className="leading-none">
            <span className="wordmark block text-[19px] font-extrabold uppercase">Save the North</span>
            <span className="mt-1 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.2em]">
              <span className="tagline-accent">Methane watch from orbit</span>
              <span className="hidden h-3 w-px bg-white/30 sm:block" aria-hidden />
              <span className="hidden text-[#a9c7e3] sm:block">EMIT · VIIRS · ERA5</span>
            </span>
          </span>
        </Link>
        {right && <div className="flex items-center gap-4 text-sm">{right}</div>}
      </div>
    </header>
  );
}

/** Kept for existing imports: a compact bar with inline controls under the site header. */
export function TopBar({ children, right }: { children?: ReactNode; right?: ReactNode }) {
  return (
    <>
      <SiteHeader />
      <div className="border-b border-rule bg-paper">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3 px-4 py-3">
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">{children}</div>
          {right}
        </div>
      </div>
    </>
  );
}

export function Brand() {
  return <Link to="/" className="font-bold text-ink">Save the North</Link>;
}

export function Footer() {
  return (
    <footer className="mt-10 border-t border-rule bg-paper">
      <div className="mx-auto max-w-6xl space-y-2 px-4 py-6 text-xs leading-relaxed text-muted">
        <p className="font-bold text-ink">Data sources</p>
        <ul className="list-disc space-y-0.5 pl-5">
          <li>NASA EMIT L2B Methane Enhancement v002 (doi:10.5067/EMIT/EMITL2BCH4ENH.002)</li>
          <li>NASA FIRMS VIIRS active fire detections</li>
          <li>Copernicus Sentinel-2 (modified Copernicus Sentinel data 2026); site imagery: Esri, Maxar, Earthstar Geographics</li>
          <li>Open-Meteo historical weather (ERA5)</li>
          <li>TCEQ Statement of Basis FOP O4734 and STEERS emissions-event reports</li>
          <li>Carbon Mapper plume records (placeholder values in this build)</li>
        </ul>
        <p>Method: Varon et al. (2018). Rules: 40 CFR 60.5371a/b; 30 TAC 101.201, 101.1.</p>
        <p className="font-semibold text-ink">Screening estimates only — not enforcement determinations. This is an independent prototype, not an official government service.</p>
        <p className="flex items-center gap-2 pt-1"><img src="/logo.png" alt="" width={18} height={18} /> Built at Hack the North.</p>
      </div>
    </footer>
  );
}
