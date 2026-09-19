---
name: flare-and-cause-analysis
description: Assess flare activity (FIRMS), plant physics bounds and permit context to judge the likely cause of the plume.
---
# Flare and cause analysis

## Tool order
1. `flare_activity(facility_id, "2025-08-01", "2025-08-15")`
2. `analyze_chart("flare_timeline", "Were flares detected near the facility around the EMIT overpass, and how does activity vary over the period?")`
3. `analyze_image("s2_swir", "Are there bright SWIR hot spots consistent with active flares?")`
4. `read_document("tceq_sob", "Extract processing capacity, flare IDs, and applicable federal rules as JSON")`
5. `physics_bounds(facility_id)`: uses this run's median by default.

## Reading FIRMS
- VIIRS 375 m detections within **1.5 km** are attributed to the plant. FRP (MW) is **qualitative**: it says a flare was
  burning. It does not say how much gas was flared.
- A detection within ±36 h of the overpass → "a flare was observed burning around the time of the overpass".
- No detection ≠ no flaring (clouds, detection limits, overpass timing). Say so.

## Physics bound
- Plant CH₄ throughput ceiling ≈ capacity (500 MMscfd) × CH₄ fraction (0.75, verify) × 19.2 g/scf ÷ 24 → ~300 t/h.
- A lit flare at ~98% combustion efficiency slips ~2% of what it burns. To explain Q as slip you would need Q/(1−CE)
  flared.
  - `flare_slip_implausible`: that exceeds the whole plant's throughput → a normally operating lit flare is *not* a
    plausible sole source.
  - `estimate_physically_implausible`: Q itself exceeds the ceiling → data-quality flag. Distrust the estimate.
  - `flare_slip_possible`: slip cannot be ruled out.

## Plausible causes at a cryogenic gas plant (rank them)
1. **Unlit / malfunctioning flare** (pilot out, snuffed flame) venting uncombusted gas. The flare's flash-gas
   routing (amine and TEG flash drums go to flare per the Statement of Basis) makes this plausible.
2. **Compressor or blowdown venting** (inlet/residue compression, pressure relief).
3. **Dehydrator / amine flash vents** bypassing control.
4. **Tank or condensate flashing** (smaller; unlikely at tens of t/h).
Use at least **two independent evidence lines** (plume origin at the processing area; flare status from FIRMS; physics
bound; permit equipment list) before giving a cause. Keep confidence **low–medium** unless operator records confirm it.

## OMNI evidence
- OMNI's SWIR and true-colour interpretations are **supporting, not decisive**, especially with the 2026-09-18
  regional screenshots. If OMNI says the image cannot resolve the plant, report that limitation.
- OMNI's document extraction (capacity, flare IDs FL-3501/3502/3504, Subpart OOOOb/KKKK) should agree with facility
  metadata. Note any disagreement as a conflict.

## Language
"likely", "consistent with", "cannot be ruled out". Never assert a cause as fact.
