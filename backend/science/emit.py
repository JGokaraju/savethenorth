"""§6.1 Load and crop the EMIT L2B CH4 enhancement (+ uncertainty / sensitivity) around the source."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import rasterio
from rasterio.windows import from_bounds

from backend.science.common import DataGap, slot
from backend.settings import cfg


@dataclass
class EmitCrop:
    enh: np.ndarray          # ppm·m, NaN where invalid
    uncert: np.ndarray | None
    sens: np.ndarray | None
    lon: np.ndarray          # 1-D pixel-centre longitudes (columns)
    lat: np.ndarray          # 1-D pixel-centre latitudes (rows, north->south)
    transform: object
    crs: str
    pixel_area_m2: float
    dx_m: float
    dy_m: float
    src_lat: float
    src_lon: float
    dist_km: np.ndarray      # distance of each pixel from the source hint
    evidence: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    files: dict = field(default_factory=dict)

    @property
    def n_valid(self) -> int:
        return int(np.isfinite(self.enh).sum())


def pixel_geometry(transform, lat: float) -> tuple[float, float, float]:
    dx = abs(transform.a) * 111320.0 * np.cos(np.radians(lat))
    dy = abs(transform.e) * 110540.0
    return float(dx), float(dy), float(dx * dy)


def _read(path, bounds):
    with rasterio.open(path) as ds:
        win = from_bounds(*bounds, ds.transform).round_offsets().round_lengths()
        arr = ds.read(1, window=win, boundless=True, fill_value=-9999).astype(np.float64)
        tr = ds.window_transform(win)
        crs = str(ds.crs)
    thr = cfg("emit", "nodata_threshold")
    arr[(arr <= thr) | ~np.isfinite(arr)] = np.nan
    return arr, tr, crs


def load_crop(src_lat: float, src_lon: float, half_km: float | None = None) -> EmitCrop:
    half_km = half_km or cfg("emit", "crop_half_width_km")
    enh_rec = slot("emit_ch4enh")
    dlat = half_km / 110.54
    dlon = half_km / (111.32 * np.cos(np.radians(src_lat)))
    bounds = (src_lon - dlon, src_lat - dlat, src_lon + dlon, src_lat + dlat)
    enh, tr, crs = _read(enh_rec["path"], bounds)
    if not np.isfinite(enh).any():
        raise DataGap("EMIT crop around the source hint contains no valid pixels")
    evidence, assumptions, files = ["emit_ch4enh"], [], {"emit_ch4enh": enh_rec}
    uncert = sens = None
    try:
        u_rec = slot("emit_ch4uncert")
        uncert, _, _ = _read(u_rec["path"], bounds)
        evidence.append("emit_ch4uncert"); files["emit_ch4uncert"] = u_rec
    except DataGap:
        assumptions.append("No EMIT uncertainty layer: pixel noise = 15% |enhancement| + background std")
    try:
        s_rec = slot("emit_ch4sens")
        sens, _, _ = _read(s_rec["path"], bounds)
        files["emit_ch4sens"] = s_rec
    except DataGap:
        pass
    h, w = enh.shape
    lon = tr.c + (np.arange(w) + 0.5) * tr.a
    lat = tr.f + (np.arange(h) + 0.5) * tr.e
    dx, dy, area = pixel_geometry(tr, src_lat)
    lo, hi = cfg("emit", "pixel_area_min_m2"), cfg("emit", "pixel_area_max_m2")
    if not lo <= area <= hi:
        raise DataGap(f"pixel area {area:.0f} m² outside sanity range {lo}-{hi} m² — grid not as expected")
    LON, LAT = np.meshgrid(lon, lat)
    dist = np.hypot((LON - src_lon) * 111.32 * np.cos(np.radians(src_lat)), (LAT - src_lat) * 110.54)
    return EmitCrop(enh, uncert, sens, lon, lat, tr, crs, area, dx, dy, src_lat, src_lon, dist,
                    evidence, assumptions, files)
