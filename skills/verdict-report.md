---
name: verdict-report
description: Choose the report charts and assemble a validated verdict with careful regulatory language.
---
# Verdict report

## Before submitting
1. `show_chart` for 4–6 of: `plume_map`, `emission_distribution`, `flare_timeline`, `reporting_timeline`,
   `regulatory_comparison`, `annual_scenarios`. Use one-line captions that say what the chart shows.
2. `submit_verdict(verdict)`. The backend validates it: medians/p5/p95 must equal `compute_emission_rate` output (±1%),
   regulatory statuses must equal `check_regulations`, and every evidence id must exist in the Evidence Ledger. If it is
   rejected, read the error, fix the listed fields and resubmit.

## Headline format
"Estimated X t/h [p5–p95 A–B t/h] of methane on 2025-08-08: ~N× the 100 kg/h EPA super-emitter threshold; no
matching TCEQ emissions-event report found." Copy X, A, B, N from tool outputs (`median_t_h`, `p5_t_h`, `p95_t_h`,
`times_super_emitter_threshold`). Adapt the second clause to the actual `TX_EMISSIONS_EVENT_REPORTING` status.

## Verdict schema
```json
{
  "facility_id": "", "facility_name": "", "event_date_utc": "2025-08-08",
  "headline": "one sentence",
  "methane_estimate": {"median_kg_h": 0, "p5_kg_h": 0, "p95_kg_h": 0, "method": "IME (EMIT L2B CH4ENH) + Monte Carlo",
                       "key_assumptions": [], "evidence_ids": ["emit_ch4enh", "wind", "result:monte_carlo"]},
  "cross_check": {"source": "Carbon Mapper", "their_kg_h": 0, "ratio": 0, "consistent": true, "note": "", "evidence_ids": ["carbonmapper"]},
  "attribution": {"conclusion": "", "confidence": "low|medium|high", "evidence": [], "evidence_ids": []},
  "likely_cause": {"conclusion": "", "confidence": "low|medium|high", "evidence": [], "evidence_ids": []},
  "annual_scenarios_t_ch4": {"low": 0, "central": 0, "high": 0, "caveat": "", "evidence_ids": []},
  "regulatory_findings": [{"rule_id": "", "rule": "", "threshold": "", "observed": "", "status": "", "note": "", "evidence_ids": []}],
  "data_gaps": [], "conflicts": [], "recommended_actions": [], "charts": [], "evidence_ids": [],
  "disclaimer": "Satellite-based screening estimate; not an enforcement determination."
}
```
Evidence ids are ledger ids returned in tool results' `evidence_ids`: slot ids (`emit_ch4enh`, `wind`, `firms`,
`carbonmapper`, `tceq_sob`, `tceq_steers`, `s2_truecolor`, `s2_swir`), `result:monte_carlo`, `assumption:<section>.<key>`,
and `omni:<n>` for OMNI analyses. Copy `regulatory_findings` from `check_regulations` (including each rule's `evidence_ids`).

## Content rules
- **Attribution**: plume origin vs facility (plume_map + OMNI), wind alignment. At least two evidence lines.
- **Likely cause**: from the flare-and-cause skill, with confidence (usually low–medium).
- **Data gaps**: missing slots, NO₂/NOx, MAERT, GHGRP, low-quality Sentinel-2, and SYNTHETIC Carbon Mapper if flagged.
- **Conflicts**: any source disagreement (ratio outside 0.5–2, OMNI vs metadata, etc.). Write "none identified" only if true.
- **Recommended actions** (plain language for a regulator):
  1. Request the potentially responsible operator's investigation and records for 2025-08-08 (flare pilot/ignition logs,
     compressor/blowdown logs, process upsets).
  2. Request or perform an OGI (optical gas imaging) survey of the flare, compression and dehydration areas.
  3. Check permit deviation reports and Title V semiannual deviation reports covering August 2025.
  4. Check whether the event should have been reported under 30 TAC 101.201 (emissions events).
  5. Task follow-up satellite overpasses to test persistence.
- **Stub facilities** (no cached data): headline "No cached observations — cannot assess"; leave numeric fields null;
  attribution/likely_cause conclusion "Not assessed", confidence "low"; data_gaps lists the missing observations.

## Language
Screening estimate; "potentially responsible operator"; "exceeds the codified threshold"; "no matching report found".
Never "violated the law".
