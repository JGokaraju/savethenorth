"""Fetch high-resolution basemap imagery of the site (Esri World Imagery export) for display.

Writes assets/site_imagery/<facility_id>_site.jpg (plant close-up, ~1.7 m/px) and
<facility_id>_region.jpg (the ±6 km EMIT analysis window, for the plume overlay), each with a
bounds JSON. Display only — no measurements are derived from these images.
Imagery: Esri, Maxar, Earthstar Geographics, and the GIS User Community (attribution required).
Usage: python scripts/fetch_site_imagery.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.settings import cfg, facility  # noqa: E402

URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export"
OUT = ROOT / "assets" / "site_imagery"


def fetch(name: str, clat: float, clon: float, half_x_km: float, half_y_km: float, w: int, h: int) -> None:
    dlat = half_y_km / 110.54
    dlon = half_x_km / (111.32 * math.cos(math.radians(clat)))
    b = {"west": clon - dlon, "south": clat - dlat, "east": clon + dlon, "north": clat + dlat}
    r = httpx.get(URL, params={"bbox": f"{b['west']},{b['south']},{b['east']},{b['north']}", "bboxSR": 4326,
                               "imageSR": 4326, "size": f"{w},{h}", "format": "jpg", "f": "image"}, timeout=90)
    r.raise_for_status()
    if not r.headers.get("content-type", "").startswith("image"):
        raise RuntimeError(f"unexpected response: {r.text[:200]}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.jpg").write_bytes(r.content)
    (OUT / f"{name}.json").write_text(json.dumps({**b, "source": "Esri World Imagery",
                                                   "attribution": "Esri, Maxar, Earthstar Geographics, and the GIS User Community"},
                                                  indent=1), encoding="utf-8")
    print(f"{name}.jpg  {len(r.content) // 1024} KB  {b}")


def main() -> None:
    f = facility("tx-lenorah-redlake")
    fetch(f"{f['facility_id']}_site", f["lat"], f["lon"], 1.6, 1.0, 1920, 1200)
    src = f["plume_source_hint"]
    half = cfg("emit", "crop_half_width_km")
    fetch(f"{f['facility_id']}_region", src["lat"], src["lon"], half, half, 1400, 1400)


if __name__ == "__main__":
    main()
