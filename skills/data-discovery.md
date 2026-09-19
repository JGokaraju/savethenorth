---
name: data-discovery
description: Inventory the facility's data first, check that dates align, and list every gap before analysing.
---
# Data discovery

Use this playbook at the start of every assessment, before any quantitative tool.

## Steps
1. `find_facility(query)`: confirm the facility, operator and `data_status`.
   - `data_status = no_cached_observations` → call `list_available_data` once. It returns a data gap. Then go straight
     to `load_skill("verdict-report")` and submit a verdict stating *"no cached observations — cannot assess"*.
     Do not call the science tools repeatedly on a facility without data.
2. `list_available_data(facility_id)`: read every slot's `status`, `date`, `quality`, `synthetic` flag and `warnings`.
3. Optionally, `describe_dataset(slot_id)` for any slot whose coverage or units you need to confirm (e.g. `emit_ch4enh`).

## Alignment checks (state them explicitly in your notes)
| Check | Expectation for this case |
|---|---|
| EMIT overpass | 2025-08-08 ~14:45 UTC (granule `_004`, plume ID `emi20250808t144501p10004-A`) |
| Wind | hourly Open-Meteo/ERA5 for the same day, covering 14:45 UTC |
| FIRMS window | 2025-08-01 … 2025-08-15, brackets the overpass |
| Carbon Mapper | contains a record for the same plume/date |
| STEERS | reported events around the detection date (±1 day window) |

## Known quality issues to carry forward
- **Carbon Mapper**: slot may be flagged `synthetic: true`, meaning a SYNTHETIC placeholder, not real data. Every statement that
  uses it must say "(SYNTHETIC placeholder)". It can illustrate the workflow but cannot corroborate the estimate.
- **Sentinel-2**: screenshots dated 2026-09-18 (13 months after the event), regional scale (~260 m/px), cloudy,
  approximate bounds. They are contextual only and cannot show conditions on 2025-08-08.
- **Wind**: the reanalysis grid point is ~5 km from the plant, and there is no temperature/pressure, so defaults are used.
- **STEERS**: only the incidents exported by the team (441788, 452092) are available.

## Gaps to list up front (always)
- NO₂ / NOx observations (not ingested)
- Permit MAERT for NSR 177845 (not ingested)
- EPA GHGRP Subpart W reports (not provided)
- Any slot whose status is not `present`

## Rules
- Never assume a missing dataset exists; a missing slot is a data gap, not an error.
- Never invent numbers. Every number comes from a tool.
- Move on to `load_skill("methane-quantification")` once the inventory is clear.
