import sys
from pathlib import Path

import numpy as np
import pytest
from rasterio.transform import from_origin

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.science.emit import EmitCrop, pixel_geometry  # noqa: E402

SRC_LAT, SRC_LON = 32.3259, -101.82905
RES = 0.000542232520256367


def make_crop(enh: np.ndarray, uncert=None) -> EmitCrop:
    h, w = enh.shape
    tr = from_origin(SRC_LON - RES * w / 2, SRC_LAT + RES * h / 2, RES, RES)
    lon = tr.c + (np.arange(w) + 0.5) * tr.a
    lat = tr.f + (np.arange(h) + 0.5) * tr.e
    dx, dy, area = pixel_geometry(tr, SRC_LAT)
    LON, LAT = np.meshgrid(lon, lat)
    dist = np.hypot((LON - SRC_LON) * 111.32 * np.cos(np.radians(SRC_LAT)), (LAT - SRC_LAT) * 110.54)
    return EmitCrop(enh.astype(float), uncert, None, lon, lat, tr, "EPSG:4326", area, dx, dy, SRC_LAT, SRC_LON, dist)


@pytest.fixture
def crop_factory():
    return make_crop
