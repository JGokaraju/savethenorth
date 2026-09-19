"""A synthetic plume with a known IME and wind: Q must be recovered within 1%."""
import numpy as np

from backend.science import ime, mask


def test_q_recovered_within_1pct(crop_factory):
    rng = np.random.default_rng(0)
    h = w = 201
    bg_level, noise = 20.0, 5.0
    enh = bg_level + rng.normal(0, noise, (h, w))
    # rectangular plume starting at the source (centre) and extending north, 3000 ppm·m above background
    plume = np.zeros((h, w), bool)
    plume[60:101, 97:104] = True
    enh[plume] += 3000.0
    crop = crop_factory(enh)
    bg = mask.background(crop)
    m = mask.plume_mask(crop, bg, 2.5)
    assert m.n_pixels == plume.sum()

    n_air = 92000 / (8.314 * 305)
    u10 = 4.0
    expected_ime = ime.ppm_m_to_kg_m2(3000.0, n_air) * plume.sum() * crop.pixel_area_m2
    L = np.sqrt(plume.sum() * crop.pixel_area_m2)
    expected_q = float(ime.u_eff(u10)) * expected_ime / L
    det = ime.deterministic(crop, bg, m, u10, n_air)
    assert abs(det.ime_kg - expected_ime) / expected_ime < 0.01
    assert abs(det.q_kg_s - expected_q) / expected_q < 0.01


def test_ueff_log_form_and_clamp():
    assert np.isclose(ime.u_eff(np.e, 1.1, 0.6, "log"), 1.7)
    assert ime.u_eff(0.1, 1.1, 0.6, "log") == 0.5  # clamped


def test_monte_carlo_deterministic_seed(crop_factory):
    rng = np.random.default_rng(1)
    enh = rng.normal(0, 10, (151, 151))
    enh[50:76, 73:78] += 2000
    crop = crop_factory(enh, uncert=np.full(enh.shape, 10.0))
    bg = mask.background(crop)
    ms = mask.all_masks(crop, bg)
    a = ime.monte_carlo(crop, bg, ms, 4.0, 1.2, 36.0, n=500, seed=7)
    b = ime.monte_carlo(crop, bg, ms, 4.0, 1.2, 36.0, n=500, seed=7)
    assert a["median_kg_h"] == b["median_kg_h"]
    assert a["p5_kg_h"] < a["median_kg_h"] < a["p95_kg_h"]
