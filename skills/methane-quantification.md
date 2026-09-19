---
name: methane-quantification
description: Quantify the plume with the IME method from EMIT enhancement data, including wind and Monte Carlo uncertainty.
---
# Methane quantification (EMIT L2B CH4ENH + IME)

## What the data is
EMIT's L2B product is a matched-filter **methane enhancement in ppm·m**: the excess CH₄ column above the local
background, integrated along the light path, on a ~60 m (0.000542°) geographic grid. Values are noisy (per-pixel 1σ is
several hundred ppm·m), so a single bright pixel means nothing. A coherent, wind-aligned plume does.

## Tool order
1. `plume_map(facility_id, date)`: crops ±6 km around the source hint, estimates the background from a 2.5–4 km annulus
   (excluding the plume), thresholds at μ + k·σ, applies a 3×3 opening, and keeps components within 1 km of the source.
2. `analyze_chart("plume_map", "Where does the plume originate relative to the facility marker, and which direction does it extend?")`
3. `analyze_image("s2_truecolor", "Identify the gas processing plant footprint and infrastructure near the marked location.")`
   Expect the answer to be limited by the image's date and scale. Report that honestly.
4. `get_wind(facility_id)`: U10, direction, σ_U at the overpass.
5. `compute_emission_rate(facility_id, date)`: IME + Monte Carlo (N = 2000).
6. `analyze_chart("emission_distribution", "Describe the distribution relative to the 100 kg/h threshold line and the Carbon Mapper line.")`
7. `compare_estimates(facility_id, date)`

## The IME method (Varon et al., 2018)
- ΔΩ [kg/m²] = (enh − μ_bg) × 10⁻⁶ × n_air × M_CH₄, with n_air = P/(R·T)
- IME [kg] = Σ ΔΩ · A_pixel over the plume mask
- L = √(mask area); U_eff = α·ln(U10) + β (α = 1.1, β = 0.6, **flagged verify**)
- Q = U_eff · IME / L → kg/s × 3600 = kg/h

## How to read the results
- **Mask slider (k = 1.5 … 4)**: a robust plume gives similar Q across k. Large swings mean the mask is noise-driven.
- **Wind dominates uncertainty.** Q scales roughly with U_eff. Use `wind_sensitivity`: if the whole curve stays above
  the threshold for 1–12 m/s, the threshold conclusion is robust to wind error.
- **Distribution**: report the median and the p5–p95 range. Never report more precision than two significant figures in prose.
- If `plume_map` warns that the plume reaches the crop edge, say the IME may be an underestimate.

## Cross-check with Carbon Mapper
- The Carbon Mapper record uses the **same EMIT radiances** with an independent retrieval and quantification pipeline. It is
  *not* a fully independent measurement. Say so.
- Ratio 0.5–2 with overlapping intervals → "consistent". Otherwise → report a **conflict**, and explain which estimate
  you trust more and why (e.g., wind source, mask choice).
- If the Carbon Mapper slot is **SYNTHETIC**, state that the cross-check is illustrative only and provides no corroboration.

## Language
"Estimated emission rate", "screening estimate", "consistent with". Never "measured leak rate" or "confirmed".
