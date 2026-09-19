"""With real assets, the median Q must be within a factor of 3 of the Carbon Mapper rate.

Fails LOUDLY with diagnostics otherwise — do not tune constants to force agreement.
Skipped when assets are missing. Note: if the Carbon Mapper slot is the SYNTHETIC placeholder, this
test only checks internal plausibility against the team-recalled value, not real corroboration.
"""
import pytest

from backend.science import carbonmapper, emit, ime, mask, wind
from backend.science.common import slot_present
from backend.settings import cfg, facility


@pytest.mark.skipif(not all(slot_present(s) for s in ("emit_ch4enh", "wind", "carbonmapper")),
                    reason="real assets (EMIT, wind, Carbon Mapper) not all present")
def test_median_within_factor_3_of_carbon_mapper():
    f = facility("tx-lenorah-redlake")
    h = f["plume_source_hint"]
    crop = emit.load_crop(h["lat"], h["lon"])
    bg = mask.background(crop)
    masks = mask.all_masks(crop, bg)
    w = wind.at()
    mc = ime.monte_carlo(crop, bg, masks, w.u10, w.sigma_u, w.n_air_mol_m3)
    c = carbonmapper.compare(mc, cfg("case", "event_date_utc"), cfg("case", "known_plume_id"))
    m = masks[cfg("mask", "k_default")]
    det = ime.deterministic(crop, bg, m, w.u10, w.n_air_mol_m3)
    diag = (f"\nratio={c['ratio']:.2f} ours={mc['median_kg_h']:.0f} kg/h theirs={c['their_kg_h']:.0f} kg/h"
            f" (synthetic={c['synthetic']})\n mask={m.n_pixels} px area={m.area_m2:.0f} m² L={m.length_m:.0f} m"
            f"\n U10={w.u10:.2f} m/s Ueff={det.ueff:.2f} n_air={w.n_air_mol_m3:.2f} mol/m³ IME={det.ime_kg:.0f} kg"
            f"\n bg μ={bg.mu:.1f} σ={bg.sigma:.1f} ppm·m")
    assert 1 / 3 <= c["ratio"] <= 3, "Estimate disagrees with Carbon Mapper by >3x:" + diag
