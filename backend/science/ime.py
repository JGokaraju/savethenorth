"""§6.3 Integrated Mass Enhancement (Varon et al. 2018) and §6.4 Monte Carlo uncertainty."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from backend.science.emit import EmitCrop
from backend.science.mask import Background, PlumeMask
from backend.settings import cfg


def ppm_m_to_kg_m2(delta_ppm_m, n_air_mol_m3: float):
    """ΔΩ [kg/m²] = Δ[ppm·m] × 1e-6 × n_air [mol/m³] × M_CH4 [kg/mol]."""
    return np.asarray(delta_ppm_m) * 1e-6 * n_air_mol_m3 * cfg("physics_constants", "M_CH4")


def u_eff(u10, alpha: float | None = None, beta: float | None = None, model: str | None = None):
    model = model or cfg("wind", "ueff_model")
    u10 = np.maximum(np.asarray(u10, float), 1e-6)
    if model == "linear":
        a = cfg("wind", "linear_a") if alpha is None else alpha
        b = cfg("wind", "linear_b") if beta is None else beta
        ue = a * u10 + b
    else:
        a = cfg("wind", "alpha") if alpha is None else alpha
        b = cfg("wind", "beta") if beta is None else beta
        ue = a * np.log(u10) + b
    return np.maximum(ue, cfg("wind", "ueff_min"))


def ime_kg(enh_ppm_m: np.ndarray, mask: np.ndarray, mu_bg: float, area_m2: float, n_air: float) -> float:
    delta = np.where(mask, enh_ppm_m - mu_bg, 0.0)
    return float(np.nansum(ppm_m_to_kg_m2(delta, n_air)) * area_m2)


def q_kg_s(ime: float, length_m: float, ueff: float) -> float:
    return float(ueff * ime / length_m)


@dataclass
class Deterministic:
    k: float
    ime_kg: float
    length_m: float
    u10: float
    ueff: float
    q_kg_s: float

    @property
    def q_kg_h(self) -> float:
        return self.q_kg_s * 3600.0


def deterministic(crop: EmitCrop, bg: Background, m: PlumeMask, u10: float, n_air: float) -> Deterministic:
    ime = ime_kg(crop.enh, m.mask, bg.mu, crop.pixel_area_m2, n_air)
    ue = float(u_eff(u10))
    return Deterministic(m.k, ime, m.length_m, u10, ue, q_kg_s(ime, m.length_m, ue))


def pixel_sigma(crop: EmitCrop, bg: Background) -> np.ndarray:
    if crop.uncert is not None:
        s = np.where(np.isfinite(crop.uncert), crop.uncert, bg.sigma)
    else:
        s = cfg("emit", "fallback_uncert_frac") * np.abs(np.nan_to_num(crop.enh)) + bg.sigma
    return s


def monte_carlo(crop: EmitCrop, bg: Background, masks: dict[float, PlumeMask], u10: float, sigma_u: float,
                n_air: float, n: int | None = None, seed: int | None = None) -> dict:
    """Each draw: U10 ~ N(U10, σ_U) truncated; k ~ U(slider set); per-pixel noise ~ N(0, σ_pix);
    α, β ~ U(±20%). The mask for each k is fixed (computed from observed data); noise perturbs the
    integrated enhancement inside it."""
    n = n or cfg("monte_carlo", "n")
    rng = np.random.default_rng(seed if seed is not None else cfg("monte_carlo", "seed"))
    ks = sorted(masks)
    sig = pixel_sigma(crop, bg)
    # precompute per-k sums: Σ(enh-μ) and Σσ² inside mask, so the per-pixel noise sum is N(0, sqrt(Σσ²))
    pre = {}
    for k in ks:
        mk = masks[k].mask
        pre[k] = (float(np.nansum(crop.enh[mk] - bg.mu)), float(np.sqrt(np.nansum(sig[mk] ** 2))),
                  masks[k].length_m)
    model = cfg("wind", "ueff_model")
    a0 = cfg("wind", "linear_a" if model == "linear" else "alpha")
    b0 = cfg("wind", "linear_b" if model == "linear" else "beta")
    f = cfg("monte_carlo", "coef_perturb_frac")
    umin = cfg("monte_carlo", "u10_min")

    u = rng.normal(u10, sigma_u, n)
    bad = u < umin
    while bad.any():  # truncate by resampling
        u[bad] = rng.normal(u10, sigma_u, bad.sum())
        bad = u < umin
    kk = rng.choice(ks, n)
    alpha = a0 * rng.uniform(1 - f, 1 + f, n)
    beta = b0 * rng.uniform(1 - f, 1 + f, n)
    noise = rng.standard_normal(n)
    sums = np.array([pre[k][0] for k in kk]) + noise * np.array([pre[k][1] for k in kk])
    L = np.array([pre[k][2] for k in kk])
    ime = ppm_m_to_kg_m2(sums, n_air) * crop.pixel_area_m2
    q = u_eff(u, alpha, beta, model) * ime / L * 3600.0
    pct = {p: float(np.percentile(q, p)) for p in (5, 25, 50, 75, 95)}
    hist_counts, edges = np.histogram(np.log10(np.clip(q, 1, None)), bins=40)
    return {"n": n, "median_kg_h": pct[50], "p5_kg_h": pct[5], "p25_kg_h": pct[25], "p75_kg_h": pct[75],
            "p95_kg_h": pct[95], "mean_kg_h": float(q.mean()), "samples_kg_h": q,
            "hist": {"log10_edges": edges.tolist(), "counts": hist_counts.tolist()},
            "inputs": {"u10": u10, "sigma_u": sigma_u, "k_values": ks, "alpha0": a0, "beta0": b0,
                       "coef_perturb_frac": f, "ueff_model": model}}


def sensitivity_curve(ime: float, length_m: float, u_min=1.0, u_max=12.0, n=45) -> dict:
    u = np.linspace(u_min, u_max, n)
    model = cfg("wind", "ueff_model")
    a0 = cfg("wind", "linear_a" if model == "linear" else "alpha")
    b0 = cfg("wind", "linear_b" if model == "linear" else "beta")
    f = cfg("monte_carlo", "coef_perturb_frac")
    q = u_eff(u) * ime / length_m * 3600
    lo = u_eff(u, a0 * (1 - f), b0 * (1 - f), model) * ime / length_m * 3600
    hi = u_eff(u, a0 * (1 + f), b0 * (1 + f), model) * ime / length_m * 3600
    return {"u10": u.tolist(), "q_kg_h": q.tolist(), "q_lo_kg_h": lo.tolist(), "q_hi_kg_h": hi.tolist()}
