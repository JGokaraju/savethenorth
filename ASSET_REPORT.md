# Asset Report

Generated 2026-09-19T22:59:30+00:00 by `python -m backend.scripts.inventory`. Originals in `assets/` are never modified; normalized copies live in `data/normalized/`. Machine-readable version: `data/manifest.yaml`.

## Slot summary

| Slot | Status | Source file | Normalized | Notes |
|---|---|---|---|---|
| `emit_ch4enh` | PRESENT | `assets/emit_data/EMIT_L2B_CH4ENH_002_20250808T144501_2522010_004.tif` | `data/normalized/emit_ch4enh.tif` | 2025-08-08T14:45:01Z (scene start from filename) |
| `emit_ch4uncert` | PRESENT | `assets/emit_data/EMIT_L2B_CH4UNCERT_002_20250808T144501_2522010_004.tif` | `data/normalized/emit_ch4uncert.tif` | 2025-08-08T14:45:01Z (scene start from filename) |
| `emit_ch4sens` | PRESENT | `assets/emit_data/EMIT_L2B_CH4SENS_002_20250808T144501_2522010_004.tif` | `data/normalized/emit_ch4sens.tif` | 2025-08-08T14:45:01Z (scene start from filename) |
| `carbonmapper` | PRESENT (SYNTHETIC) | `data/synthetic/carbonmapper_plumes_SYNTHETIC.csv` | `data/normalized/carbonmapper_plumes.csv` | SYNTHETIC placeholder — not real Carbon Mapper data |
| `wind` | PRESENT | `assets/wind.json` | `data/normalized/wind.json` | 2025-08-08T00:00 .. 2025-08-08T23:00 UTC |
| `firms` | PRESENT | `assets/firms/` | `data/normalized/firms_viirs.csv` | 2025-08-01 .. 2025-08-15 |
| `s2_truecolor` | PRESENT (low quality) | `assets/s2_truecolor.jpg` | `data/normalized/s2_truecolor.jpg` | image date 2026-09-18 does not match the 2025-08-08 event; regional (~200 km) screenshot; the plant spans only ~1–3 px |
| `s2_swir` | PRESENT (low quality) | `assets/s2_swir.jpg` | `data/normalized/s2_swir.jpg` | image date 2026-09-18 does not match the 2025-08-08 event; regional (~200 km) screenshot; the plant spans only ~1–3 px |
| `tceq_sob` | PRESENT | `assets/tceq_sob_lenorah.pdf` | `data/normalized/tceq_sob.pdf` | prepared March 6, 2026 |
| `site_imagery` | PRESENT | `assets/site_imagery/tx-lenorah-redlake_region.jpg` | `data/normalized/site_imagery_region.jpg` | basemap imagery date is not the event date; display only |
| `tceq_steers` | PRESENT | `assets/Air Emission Event Report Database Incident 441788.xls` | `data/normalized/steers_emission_points.csv` | 2025-06-08 .. 2026-01-24 |

## Decisions

- `emit_ch4enh` ← `assets/emit_data/EMIT_L2B_CH4ENH_002_20250808T144501_2522010_004.tif` (granule `20250808T144501_2522010_004` contains valid data at the plume source hint; tag description = 'Methane Enhancement Values'). Normalized to `data/normalized/emit_ch4enh.tif` cropped to ±0.15° around the hint (553×553 px).
- `emit_ch4enh`: ignored `assets/emit_data/EMIT_L2B_CH4ENH_002_20250808T144449_2522010_003.tif` — source hint pixel is nodata in this granule (adjacent granule of the same overpass).
- `emit_ch4uncert` ← `assets/emit_data/EMIT_L2B_CH4UNCERT_002_20250808T144501_2522010_004.tif` (granule `20250808T144501_2522010_004` contains valid data at the plume source hint; tag description = 'Methane Enhancement Uncertainty Values'). Normalized to `data/normalized/emit_ch4uncert.tif` cropped to ±0.15° around the hint (553×553 px).
- `emit_ch4uncert`: ignored `assets/emit_data/EMIT_L2B_CH4UNCERT_002_20250808T144449_2522010_003.tif` — source hint pixel is nodata in this granule (adjacent granule of the same overpass).
- `emit_ch4sens` ← `assets/emit_data/EMIT_L2B_CH4SENS_002_20250808T144501_2522010_004.tif` (granule `20250808T144501_2522010_004` contains valid data at the plume source hint; tag description = 'Methane Enhancement Sensitivity Values'). Normalized to `data/normalized/emit_ch4sens.tif` cropped to ±0.15° around the hint (553×553 px).
- `emit_ch4sens`: ignored `assets/emit_data/EMIT_L2B_CH4SENS_002_20250808T144449_2522010_003.tif` — source hint pixel is nodata in this granule (adjacent granule of the same overpass).
- `carbonmapper`: no Carbon Mapper table in assets/. At the team's request a **SYNTHETIC placeholder** `data/synthetic/carbonmapper_plumes_SYNTHETIC.csv` (4 rows; 2 detections, 2 non-detects) is used instead. Only the 2025-08-08 plume ID and ~21,500 kg/h come from the brief; all other rows are invented. Every output that uses it is labelled SYNTHETIC.
- `wind` ← `assets/wind.json` (has `hourly.wind_speed_10m`). wind_speed_10m already in m/s; no conversion; `temperature_2m` absent → default from case.yaml will be used; `surface_pressure` absent → default from case.yaml will be used; grid point (32.3023, -101.7818) is 5.0 km from the facility (Open-Meteo snaps to its grid).
- `firms`: `assets/firms_viirs.csv` looks like the FIRMS file by name but its content is not a CSV: "Invalid day range. Expects [1..5].". The FIRMS area API rejected the original request (day_count=15; the API accepts 1..5 per request). Ignored — superseded by the re-downloaded chunks below.
- `firms` ← 9 non-empty re-downloaded FIRMS area CSVs under `assets/firms/` (3 header-only chunks skipped), fetched in 5-day chunks by `scripts/fetch_firms.py` (NOAA-20 SP, NOAA-21 NRT, Suomi-NPP SP; NOAA-21 has no SP product for 2025-08). Concatenated to `data/normalized/firms_viirs.csv`: 73 rows, SP preferred over NRT duplicates; satellite code 'N' renamed to 'SNPP'; `type` column (SP only) kept where present.
- `s2_truecolor` ← `assets/s2_truecolor.jpg` (filename + colour check: mean RGB [171.0, 154.8, 137.1]). It is a Copernicus Browser **screenshot**, not a GeoTIFF: 830×664 px, burned-in header '2026-09-18, Sentinel-2 L2A', town labels and a 20 km scale bar. No `s2_bounds.json` → bounds fitted from town labels: W -102.1748, E -99.8949, S 31.311, N 32.8563 (rms 0.47 km, ≈258 m/px).
- `s2_swir` ← `assets/s2_swir.jpg` (filename + colour check: mean RGB [183.8, 189.6, 135.2]). It is a Copernicus Browser **screenshot**, not a GeoTIFF: 830×664 px, burned-in header '2026-09-18, Sentinel-2 L2A', town labels and a 20 km scale bar. No `s2_bounds.json` → bounds fitted from town labels: W -102.1748, E -99.8949, S 31.311, N 32.8563 (rms 0.47 km, ≈258 m/px).
- `tceq_sob` ← `assets/tceq_sob_lenorah.pdf` (page 1 text begins 'Statement of Basis of the Federal Operating Permit'; permit O4734; 18 pages).
- `tceq_steers` ← 2 legacy Excel (.xls/BIFF) exports of the TCEQ Air Emission Event Report Database, one per incident (441788, 452092); concatenated to `data/normalized/steers_emission_points.csv` (6 emission-point rows). Format differs from the expected PDF/HTML printout — parsed as tables instead of regex over text.
- `tceq_steers`: incident(s) 452090 mentioned in the brief (Red Lake plant) are **not** in the provided files. Only what is in assets/ is used.
- `tceq_steers`: extra incident(s) 441788 found (not in the brief) and kept.
- `site_imagery` ← `assets/site_imagery/tx-lenorah-redlake_region.jpg`, `assets/site_imagery/tx-lenorah-redlake_site.jpg`: Esri World Imagery basemap exports (plant close-up and the EMIT analysis window). Used for display only (report hero, plume overlay).
- `assets/datacollection.py`: Python helper script (FIRMS download), not data — ignored. ⚠️ It contains a hard-coded FIRMS MAP_KEY; excluded from git via .gitignore.

## Data gaps (reported by the agent, never blockers)

- **NO₂ / NOx observations, permit MAERT (NSR 177845), EPA GHGRP Subpart W**: not provided (out of scope).

## File inventory

| File | Size | SHA-256 (first 16) | Detected as |
|---|---:|---|---|
| `assets/Air Emission Event Report Database Incident 441788.xls` | 6,656 | `7c889b9ffabbb68c` | tceq_steers |
| `assets/Air Emission Event Report Database Incident 452092.xls` | 6,656 | `0e2169ab76b32c10` | tceq_steers |
| `assets/datacollection.py` | 811 | `74df39da2054b152` | script |
| `assets/emit_data/EMIT_L2B_CH4ENH_002_20250808T144449_2522010_003.tif` | 13,370,695 | `b1fffbb68183536c` | emit_ch4enh |
| `assets/emit_data/EMIT_L2B_CH4ENH_002_20250808T144501_2522010_004.tif` | 26,102,461 | `2aabb8a5f33770da` | emit_ch4enh |
| `assets/emit_data/EMIT_L2B_CH4SENS_002_20250808T144449_2522010_003.tif` | 11,804,071 | `9deed35200813f45` | emit_ch4sens |
| `assets/emit_data/EMIT_L2B_CH4SENS_002_20250808T144501_2522010_004.tif` | 23,314,777 | `cc6107ce43113379` | emit_ch4sens |
| `assets/emit_data/EMIT_L2B_CH4UNCERT_002_20250808T144449_2522010_003.tif` | 11,830,009 | `1e9791b1ac7b085e` | emit_ch4uncert |
| `assets/emit_data/EMIT_L2B_CH4UNCERT_002_20250808T144501_2522010_004.tif` | 23,268,828 | `b8f192959dcccfc8` | emit_ch4uncert |
| `assets/firms/firms_VIIRS_NOAA20_NRT_2025-08-01.csv` | 124 | `7f06a3928b143c6b` | firms |
| `assets/firms/firms_VIIRS_NOAA20_NRT_2025-08-06.csv` | 124 | `7f06a3928b143c6b` | firms |
| `assets/firms/firms_VIIRS_NOAA20_NRT_2025-08-11.csv` | 124 | `7f06a3928b143c6b` | firms |
| `assets/firms/firms_VIIRS_NOAA20_SP_2025-08-01.csv` | 625 | `3bcac2c4fdec870c` | firms |
| `assets/firms/firms_VIIRS_NOAA20_SP_2025-08-06.csv` | 1,028 | `ff72377abf80689b` | firms |
| `assets/firms/firms_VIIRS_NOAA20_SP_2025-08-11.csv` | 863 | `ca75f559b918bda2` | firms |
| `assets/firms/firms_VIIRS_NOAA21_NRT_2025-08-01.csv` | 291 | `a9abc6fcc5d94690` | firms |
| `assets/firms/firms_VIIRS_NOAA21_NRT_2025-08-06.csv` | 1,149 | `56aefbbfe89e2144` | firms |
| `assets/firms/firms_VIIRS_NOAA21_NRT_2025-08-11.csv` | 464 | `1d46dda6e9127f46` | firms |
| `assets/firms/firms_VIIRS_SNPP_SP_2025-08-01.csv` | 857 | `3c16bd496bf6d909` | firms |
| `assets/firms/firms_VIIRS_SNPP_SP_2025-08-06.csv` | 1,256 | `80bb9e244ce0e991` | firms |
| `assets/firms/firms_VIIRS_SNPP_SP_2025-08-11.csv` | 605 | `9f3e0d60935f1415` | firms |
| `assets/firms_viirs.csv` | 34 | `17cdb7699e3fa6a6` | unparseable_csv |
| `assets/s2_swir.jpg` | 412,915 | `d5b402099af091c2` | s2_swir |
| `assets/s2_truecolor.jpg` | 354,742 | `a56c6b0c3922626f` | s2_truecolor |
| `assets/site_imagery/tx-lenorah-redlake_region.jpg` | 409,692 | `760d2b5eb6f034a5` | site_imagery |
| `assets/site_imagery/tx-lenorah-redlake_region.json` | 242 | `ff2c46de45ff0b0c` | site_imagery_meta |
| `assets/site_imagery/tx-lenorah-redlake_site.jpg` | 456,718 | `3a0393569ef88ebf` | site_imagery |
| `assets/site_imagery/tx-lenorah-redlake_site.json` | 241 | `7b687b5648af5ce2` | site_imagery_meta |
| `assets/tceq_sob_lenorah.pdf` | 307,628 | `6c5fc20a7764c037` | tceq_sob |
| `assets/wind.json` | 1,683 | `aae801de6a1f42e5` | wind |

## Basic stats

- **emit_ch4enh**: valid_pixels=4237084, p1=-1078.74, median=-3.55, p99=1111.1, max=13371.1
- **emit_ch4uncert**: valid_pixels=4237084, p1=359.81, median=605.23, p99=1409.45, max=14287.91
- **emit_ch4sens**: valid_pixels=4237084, p1=0.36, median=0.96, p99=1.89, max=10.38
- **carbonmapper**: rows=4, detections=2
- **wind**: n_hours=24, u10_min=3.05, u10_max=5.62, grid_lat=32.3, grid_lon=-101.78, grid_distance_km=5.01
- **firms**: rows=73, files=9, satellites=['N20', 'N21', 'SNPP']
- **s2_truecolor**: width=830, height=664, approx_m_per_px=258
- **s2_swir**: width=830, height=664, approx_m_per_px=258
- **tceq_sob**: pages=18
- **tceq_steers**: rows=6, incidents=['441788', '452092'], facilities=['LENORAH GAS PLANT']

## Suggested fixes for the team

1. **Carbon Mapper**: replace the SYNTHETIC placeholder by exporting the real plume record(s) for the site (incl. `emi20250808t144501p10004-A`) and any non-detect overpasses to `assets/carbonmapper_plumes.csv`.
2. **FIRMS**: done — re-downloaded via `scripts/fetch_firms.py` into `assets/firms/`.
3. **Sentinel-2**: export a site-scale (~10 km) clear-sky image near 2025-08-08 (true colour + SWIR) with an `s2_bounds.json`. The current screenshots are from 2026-09-18 and regional-scale.
4. **STEERS**: add incident 452090 (Red Lake) if it exists; include any events around 2025-08-08.

Re-run `python -m backend.scripts.inventory` (or `make prep`) after adding files.
