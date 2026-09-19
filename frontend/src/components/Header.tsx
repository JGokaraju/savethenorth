import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Health } from "../lib/api";
import { ModeBadge } from "./ui";

export function useHealth(pollMs = 5000) {
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

export function Header({ runMode }: { runMode?: string | null }) {
  const h = useHealth();
  const oc = h?.omni_calls;
  return (
    <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-slate-800 bg-slate-950/90 px-4 py-2.5 backdrop-blur">
      <Link to="/" className="flex items-center gap-2">
        <span className="text-lg" aria-hidden>🛰️</span>
        <span className="font-semibold text-slate-100">Plumewatch</span>
        <span className="hidden text-sm text-slate-400 sm:inline">— Satellite Emissions Verification</span>
      </Link>
      <div className="flex items-center gap-3 text-xs text-slate-400">
        <ModeBadge mode={runMode ?? h?.mode.label} />
        {oc && <span title="Huawei OMNI calls: live / cached / mock (sponsor credit is limited)">OMNI calls: <b className="text-slate-200">{oc.live_calls}</b> live · {oc.cached} cached · {oc.mock} mock</span>}
      </div>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="border-t border-slate-800 px-4 py-3 text-[11px] leading-relaxed text-slate-500">
      Data: NASA EMIT L2B Methane Enhancement v002 (Green et al., NASA LP DAAC, doi:10.5067/EMIT/EMITL2BCH4ENH.002) · Carbon Mapper
      (data.carbonmapper.org; <b className="text-violet-300">this demo uses a SYNTHETIC placeholder</b>) · NASA FIRMS VIIRS active fire · Contains modified
      Copernicus Sentinel data 2026 · Open-Meteo historical weather (ERA5) · TCEQ Statement of Basis FOP O4734 and STEERS emissions-event reports ·
      Method: Varon et al. (2018), AMT · Rules: 40 CFR 60.5371a/b; 30 TAC 101.201, 101.1. Screening estimates only — not enforcement determinations.
    </footer>
  );
}
