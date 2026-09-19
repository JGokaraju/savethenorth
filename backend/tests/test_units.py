import numpy as np
from rasterio.transform import from_origin

from backend.science.emit import pixel_geometry
from backend.science.ime import ppm_m_to_kg_m2
from backend.science.physics import ceiling_t_h


def test_ppm_m_to_kg_m2_hand_calc():
    # 1000 ppm·m at P=92000 Pa, T=305 K: n_air = 92000/(8.314*305) = 36.281 mol/m³
    n_air = 92000 / (8.314 * 305)
    expected = 1000 * 1e-6 * 36.2811 * 0.01604  # = 5.8195e-4 kg/m²
    assert abs(ppm_m_to_kg_m2(1000, n_air) - expected) / expected < 1e-4


def test_pixel_area_in_expected_range():
    tr = from_origin(-102.18, 33.37, 0.000542232520256367, 0.000542232520256367)
    dx, dy, area = pixel_geometry(tr, 32.3259)
    assert 45 < dx < 60 and 55 < dy < 65
    assert 2000 < area < 5500


def test_kmh_to_ms():
    assert abs(36 / 3.6 - 10.0) < 1e-12


def test_plant_ceiling_about_300_t_h():
    assert abs(ceiling_t_h(500) - 300) < 1.0
    assert np.isclose(ceiling_t_h(500, 0.65), 500e6 * 0.65 * 19.2 / 24 / 1e6)
