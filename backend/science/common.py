"""Shared helpers for the science modules."""
from __future__ import annotations

import datetime as dt
import math

import numpy as np

from backend.settings import ROOT, load_manifest

EARTH_R_KM = 6371.0


class DataGap(Exception):
    """Raised when required data is missing or unusable. Tools turn this into status=data_gap."""


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * EARTH_R_KM * np.arcsin(np.sqrt(a))


def slot(slot_id: str) -> dict:
    """Manifest record for a slot; raises DataGap when absent."""
    rec = load_manifest().get("slots", {}).get(slot_id)
    if not rec or rec.get("status") != "present" or not rec.get("normalized"):
        reason = (rec or {}).get("reason", "slot not in manifest (run `python tasks.py prep`)")
        raise DataGap(f"{slot_id}: {reason}")
    path = ROOT / rec["normalized"]
    if not path.exists():
        raise DataGap(f"{slot_id}: normalized file {rec['normalized']} not found (run `python tasks.py prep`)")
    return {**rec, "path": path}


def slot_present(slot_id: str) -> bool:
    try:
        slot(slot_id)
        return True
    except DataGap:
        return False


def parse_utc(s: str) -> dt.datetime:
    s = s.strip().replace("Z", "+00:00")
    t = dt.datetime.fromisoformat(s)
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def finite(x):
    """JSON-safe float (None for NaN/inf)."""
    if x is None:
        return None
    x = float(x)
    return x if math.isfinite(x) else None


def robust_stats(v: np.ndarray) -> tuple[float, float]:
    """Median and MAD-based std."""
    v = v[np.isfinite(v)]
    if v.size == 0:
        return float("nan"), float("nan")
    med = float(np.median(v))
    return med, float(1.4826 * np.median(np.abs(v - med)))
