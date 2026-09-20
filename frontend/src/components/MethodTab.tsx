import katex from "katex";
import "katex/dist/katex.min.css";
import { RunState } from "../lib/useRun";

function TeX({ children, block = false }: { children: string; block?: boolean }) {
  return <span className={block ? "block overflow-x-auto py-1" : ""}
    dangerouslySetInnerHTML={{ __html: katex.renderToString(children, { displayMode: block, throwOnError: false }) }} />;
}

const data = (run: RunState, name: string): any =>
  [...run.events].reverse().find((e) => e.type === "tool_result" && e.name === name && e.status === "ok")?.data ?? {};

const n = (v: any, d = 0) => (typeof v === "number" ? v.toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d }) : "—");

export function MethodTab({ run }: { run: RunState }) {
  const pm = data(run, "plume_map");
  const w = data(run, "get_wind");
  const em = data(run, "compute_emission_rate");
  const ph = data(run, "physics_bounds");
  const det = em.deterministic ?? {};
  return (
    <div className="space-y-5 text-sm leading-relaxed text-muted">
      <section>
        <h4 className="mb-1 text-base font-bold text-ink">1 · Plume mask</h4>
        <p>EMIT L2B CH4ENH (matched-filter enhancement, ppm·m, ~60 m) is cropped ±6 km around the plume source. A robust background
          (median, MAD·1.4826) comes from a 2.5–4 km annulus with the plume excluded: μ = {n(pm.background_mu_ppm_m, 1)}, σ = {n(pm.background_sigma_ppm_m, 1)} ppm·m.
          Pixels above <TeX>{"\\mu + k\\sigma"}</TeX> (k = {pm.k_default ?? 2.5}) are opened with a 3×3 kernel, and components within 1 km of the source are kept:
          {" "}<b>{n(pm.n_pixels)}</b> pixels, area {n((pm.area_m2 ?? 0) / 1e6, 2)} km².</p>
      </section>
      <section>
        <h4 className="mb-1 text-base font-bold text-ink">2 · Integrated mass enhancement (Varon et al., 2018)</h4>
        <TeX block>{"\\Delta\\Omega_i = (\\mathrm{enh}_i - \\mu)\\,10^{-6}\\, n_{air}\\, M_{CH_4},\\quad n_{air} = \\frac{P}{R\\,T}"}</TeX>
        <TeX block>{`n_{air} = \\frac{${n(w.pressure_pa)}\\,\\mathrm{Pa}}{8.314 \\times ${n(w.temperature_k, 1)}\\,\\mathrm{K}} = ${n(w.n_air_mol_m3, 2)}\\ \\mathrm{mol\\,m^{-3}}`}</TeX>
        <TeX block>{`\\mathrm{IME} = \\sum_{i \\in \\mathrm{mask}} \\Delta\\Omega_i\\,A_{pix} = ${n(det.ime_kg)}\\ \\mathrm{kg}\\quad (A_{pix} = ${n(em.pixel_area_m2)}\\ \\mathrm{m^2})`}</TeX>
        <TeX block>{`U_{eff} = \\alpha \\ln U_{10} + \\beta = 1.1 \\ln(${n(det.u10_m_s, 2)}) + 0.6 = ${n(det.ueff_m_s, 2)}\\ \\mathrm{m\\,s^{-1}}`}</TeX>
        <TeX block>{`Q = \\frac{U_{eff}\\,\\mathrm{IME}}{L},\\ L = \\sqrt{A_{mask}} = ${n(det.length_m)}\\ \\mathrm{m} \\;\\Rightarrow\\; Q = ${n(det.q_kg_h)}\\ \\mathrm{kg\\,h^{-1}}`}</TeX>
        <p className="text-xs text-alert-amber">α, β are flagged "needs verification" (instrument-specific calibration; EMIT-specific values should be confirmed).</p>
      </section>
      <section>
        <h4 className="mb-1 text-base font-bold text-ink">3 · Monte Carlo uncertainty</h4>
        <p>N = {n(em.n_draws)} draws with a fixed seed. Each draw samples U10 ~ N({n(w.u10_m_s, 2)}, {n(w.sigma_u_m_s, 2)}) m/s (truncated ≥ 0.5),
          k uniformly from {"{1.5, 2, 2.5, 3, 4}"}, per-pixel noise from the EMIT uncertainty layer, and α, β ± 20%.
          Result: median <b>{n(em.median_kg_h)}</b> kg/h, p5–p95 {n(em.p5_kg_h)}–{n(em.p95_kg_h)} kg/h.</p>
      </section>
      <section>
        <h4 className="mb-1 text-base font-bold text-ink">4 · Physics bound</h4>
        <TeX block>{`Q_{max} = \\frac{500\\,\\mathrm{MMscfd} \\times 10^6 \\times f_{CH_4} \\times 19.2\\,\\mathrm{g/scf}}{24 \\times 10^6} = ${n(ph.ceiling_t_h)}\\ \\mathrm{t\\,h^{-1}}\\ (f_{CH_4}=0.75)`}</TeX>
        <TeX block>{`Q_{flared} = \\frac{Q}{1-\\mathrm{CE}} = \\frac{${n(ph.q_t_h, 1)}}{1-${ph.combustion_efficiency ?? 0.98}} = ${n(ph.required_flared_ch4_t_h)}\\ \\mathrm{t\\,h^{-1}}`}</TeX>
        <p>Classification: <code>{ph.classification ?? "—"}</code>. {ph.interpretation}</p>
      </section>
      <section>
        <h4 className="mb-1 text-base font-bold text-ink">5 · Regulatory screening rules</h4>
        <ul className="list-disc space-y-1 pl-5 text-xs">
          <li><b>US_SUPER_EMITTER</b> (40 CFR 60.5371a/b): p5 &gt; 100 kg/h → EXCEEDS; p95 &lt; 100 → BELOW; otherwise INCONCLUSIVE. Program compliance date Jan 22, 2027; under EPA reconsideration.</li>
          <li><b>TX_EMISSIONS_EVENT_REPORTING</b> (30 TAC 101.201; RQ per 30 TAC 101.1(89)): mass in a ≥1 h event at the median rate vs the 5,000 lb RQ (verify); STEERS events matched within ±1 day.</li>
          <li><b>PLANT_PHYSICS_CEILING</b>: estimate vs plant throughput.</li>
          <li><b>NOX_PERMIT_LIMITS</b>, <b>GHGRP_REPORTED</b>: not assessed (data not ingested).</li>
        </ul>
      </section>
      <p className="border-l-2 border-accent/60 bg-panel2 p-3 text-xs text-ink">All results are satellite-based screening estimates, not enforcement determinations.</p>
    </div>
  );
}
