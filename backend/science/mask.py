"""§6.2 Plume mask: robust background from an annulus, k·σ threshold, opening, attribution."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from backend.science.common import DataGap, robust_stats
from backend.science.emit import EmitCrop
from backend.settings import cfg


@dataclass
class Background:
    mu: float
    sigma: float
    n_pixels: int
    excluded_plume_pixels: int


@dataclass
class PlumeMask:
    k: float
    mask: np.ndarray
    n_pixels: int
    area_m2: float
    length_m: float
    max_enh: float
    max_lat: float
    max_lon: float
    threshold: float
    n_components: int


def _candidate(crop: EmitCrop, mu: float, sigma: float, k: float) -> tuple[np.ndarray, int]:
    enh = crop.enh
    cand = np.isfinite(enh) & (enh > mu + k * sigma)
    cand = ndimage.binary_opening(cand, structure=np.ones((3, 3), bool))
    lab, n = ndimage.label(cand, structure=np.ones((3, 3), bool))
    r = cfg("mask", "attribution_radius_km")
    near = np.unique(lab[(crop.dist_km <= r) & (lab > 0)])
    return np.isin(lab, near[near > 0]), len(near[near > 0])


def background(crop: EmitCrop) -> Background:
    r0, r1 = cfg("mask", "bg_annulus_inner_km"), cfg("mask", "bg_annulus_outer_km")
    ann = (crop.dist_km >= r0) & (crop.dist_km <= r1) & np.isfinite(crop.enh)
    if ann.sum() < 50:
        raise DataGap(f"background annulus has only {int(ann.sum())} valid pixels")
    mu, sd = robust_stats(crop.enh[ann])
    excluded = 0
    if cfg("mask", "bg_exclude_plume"):
        first, _ = _candidate(crop, mu, sd, cfg("mask", "k_default"))
        dil = ndimage.binary_dilation(first, iterations=2)
        excluded = int((ann & dil).sum())
        ann2 = ann & ~dil
        if ann2.sum() >= 50:
            mu, sd = robust_stats(crop.enh[ann2])
            ann = ann2
    return Background(mu, sd, int(ann.sum()), excluded)


def plume_mask(crop: EmitCrop, bg: Background, k: float) -> PlumeMask:
    m, ncomp = _candidate(crop, bg.mu, bg.sigma, k)
    n = int(m.sum())
    if n == 0:
        raise DataGap(f"no plume attributable within {cfg('mask', 'attribution_radius_km')} km (k={k})")
    vals = np.where(m, crop.enh, -np.inf)
    iy, ix = np.unravel_index(np.argmax(vals), vals.shape)
    area = n * crop.pixel_area_m2
    return PlumeMask(k, m, n, area, float(np.sqrt(area)), float(crop.enh[iy, ix]),
                     float(crop.lat[iy]), float(crop.lon[ix]), bg.mu + k * bg.sigma, ncomp)


def all_masks(crop: EmitCrop, bg: Background) -> dict[float, PlumeMask]:
    out = {}
    for k in cfg("mask", "k_values"):
        try:
            out[float(k)] = plume_mask(crop, bg, float(k))
        except DataGap:
            pass
    return out
