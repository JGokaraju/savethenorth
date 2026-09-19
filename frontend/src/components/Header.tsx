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

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link to="/" className="flex items-center gap-2.5">
      <Logo size={compact ? 28 : 34} />
      <span className={`font-semibold tracking-tight text-slate-900 ${compact ? "text-base" : "text-lg"}`}>Save the North</span>
    </Link>
  );
}

export function TopBar({ children, right }: { children?: ReactNode; right?: ReactNode }) {
  return (
    <header className="sticky top-0 z-30 px-4 pt-4">
      <div className="glass flex flex-wrap items-center gap-3 px-4 py-3">
        <Brand compact />
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">{children}</div>
        <div className="flex items-center gap-2">{right}</div>
      </div>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="px-6 pb-6 pt-2 text-[11px] leading-relaxed text-slate-400">
      Data: NASA EMIT L2B Methane Enhancement v002 (doi:10.5067/EMIT/EMITL2BCH4ENH.002) · NASA FIRMS VIIRS active fire ·
      Copernicus Sentinel-2 (modified Copernicus Sentinel data 2026) · Open-Meteo / ERA5 weather · TCEQ Statement of Basis FOP O4734 and
      STEERS emissions-event reports · Carbon Mapper (placeholder values in this build) · Method: Varon et al. (2018) · Rules: 40 CFR 60.5371a/b;
      30 TAC 101.201, 101.1. Screening estimates only — not enforcement determinations.
    </footer>
  );
}
