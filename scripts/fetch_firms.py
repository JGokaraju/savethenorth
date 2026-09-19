"""Re-download NASA FIRMS VIIRS detections for the case window in <=5-day chunks.

The FIRMS area API accepts DAY_RANGE 1..5 per request, so Aug 1-15 needs 3 calls per
satellite. Writes NEW files into assets/ (never overwrites existing ones):
    assets/firms/firms_<SOURCE>_<start>.csv
Usage:  FIRMS_MAP_KEY=... python scripts/fetch_firms.py
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx

KEY = os.getenv("FIRMS_MAP_KEY", "").strip()
BBOX = "-101.95,32.20,-101.70,32.45"  # west,south,east,north
SOURCES = ["VIIRS_NOAA20_SP", "VIIRS_NOAA21_SP", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "VIIRS_SNPP_SP"]
START, DAYS, CHUNK = date(2025, 8, 1), 15, 5
OUT = Path(__file__).resolve().parent.parent / "assets" / "firms"


def main() -> int:
    if not KEY:
        print("Set FIRMS_MAP_KEY (https://firms.modaps.eosdis.nasa.gov/api/map_key/)")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    for src in SOURCES:
        for off in range(0, DAYS, CHUNK):
            d0 = START + timedelta(days=off)
            url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{KEY}/{src}/{BBOX}/{min(CHUNK, DAYS - off)}/{d0}"
            r = httpx.get(url, timeout=60)
            text = r.text.strip()
            if r.status_code != 200 or not text.lower().startswith("latitude"):
                print(f"{src} {d0}: skipped ({r.status_code}: {text[:80]})")
                continue
            dst = OUT / f"firms_{src}_{d0}.csv"
            if dst.exists():
                print(f"{dst.name} exists, not overwriting")
                continue
            dst.write_text(text + "\n", encoding="utf-8")
            print(f"{src} {d0}: {len(text.splitlines()) - 1} rows -> {dst.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
