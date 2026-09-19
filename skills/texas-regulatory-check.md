---
name: texas-regulatory-check
description: Screen the estimate against the federal super-emitter threshold and Texas emissions-event reporting rules.
---
# Texas / federal regulatory screening

## Tool order
1. `read_document("tceq_steers", "List all incidents with dates as JSON")`
2. `reporting_timeline(facility_id)`
3. `analyze_chart("reporting_timeline", "Is there a reported event near the satellite detection date?")` (optional)
4. `check_regulations(facility_id)`: statuses come ONLY from this tool. Never compute or override them yourself.

## Rules
| rule_id | Citation | Threshold | Status logic |
|---|---|---|---|
| `US_SUPER_EMITTER` | 40 CFR 60.5371a/b (EPA Super-Emitter Program; remotely detected methane at oil & gas facilities incl. processing plants) | 100 kg/h CH₄ | p5 > 100 → EXCEEDS; p95 < 100 → BELOW; else INCONCLUSIVE |
| `TX_EMISSIONS_EVENT_REPORTING` | 30 TAC 101.201 (initial notification within 24 h of discovery); RQ per 30 TAC 101.1(89) | RQ 5,000 lb natural-gas mixture (**verify**) | mass in a ≥1 h event > RQ and no STEERS event within ±1 day → NO_MATCHING_REPORT_FOUND; match → REPORTED; ≤ RQ → BELOW_RQ |
| `PLANT_PHYSICS_CEILING` | sanity check | ~300 t/h | CONSISTENT / IMPLAUSIBLE |
| `NOX_PERMIT_LIMITS` | NSR 177845 MAERT | n/a | always NOT_ASSESSED (data gap) |
| `GHGRP_REPORTED` | EPA GHGRP Subpart W | n/a | always NOT_ASSESSED (data gap) |

## Mandatory notes
- Super-emitter: *"Codified threshold; program compliance date Jan 22, 2027 and under EPA reconsideration. Screening
  result, not an enforcement finding."*
- STEERS matching window is **±1 day** of the detection date. A report months earlier or later does not match.
- Reported STEERS events at this plant list CO, NOx and "Natural Gas VOCs" from flare FL-3501. They do **not** list
  methane explicitly. Mention this.
- The event records available are only those exported by the team. Absence in this set ≠ absence in STEERS.

## Wording rules
- The operator is always the **"potentially responsible operator"**.
- Say "exceeds the codified threshold", "no matching report found in the records provided".
- NEVER say "violated", "illegal", "non-compliant" or "failed to report".
