"""§6.10 Regulatory screening rules. Returns evidence-backed statuses, never enforcement findings."""
from __future__ import annotations

import datetime as dt

from backend.settings import cfg

SUPER_EMITTER_NOTE = ("Codified threshold; program compliance date Jan 22, 2027 and under EPA reconsideration. "
                      "Screening result, not an enforcement finding.")
LB_PER_KG = 2.2046


def super_emitter(p5: float | None, p95: float | None, median: float | None) -> dict:
    thr = cfg("regulations", "super_emitter_kg_h")
    if p5 is None or p95 is None:
        status, observed = "NOT_ASSESSED", "no emission estimate available"
    else:
        status = "EXCEEDS" if p5 > thr else ("BELOW" if p95 < thr else "INCONCLUSIVE")
        observed = f"median {median:,.0f} kg/h (p5–p95 {p5:,.0f}–{p95:,.0f} kg/h)"
    return {"rule_id": "US_SUPER_EMITTER",
            "rule": "40 CFR 60.5371a/b — EPA Super-Emitter Program (remotely detected methane, incl. processing plants)",
            "threshold": f"{thr} kg/h CH₄", "observed": observed, "status": status,
            "multiple_of_threshold": (median / thr) if median else None, "note": SUPER_EMITTER_NOTE}


def emissions_event_reporting(q_median_kg_h: float | None, detection_dates: list[str], steers_events: list[dict] | None) -> dict:
    rq = cfg("regulations", "rq_lb")
    hours = cfg("regulations", "min_event_hours")
    window = cfg("regulations", "steers_match_window_days")
    base = {"rule_id": "TX_EMISSIONS_EVENT_REPORTING",
            "rule": "30 TAC 101.201 — initial notification within 24 h of discovery when a reportable quantity is exceeded",
            "threshold": f"RQ {rq:,} lb (natural-gas mixture, 30 TAC 101.1(89)(B)(iv) — verify)"}
    if q_median_kg_h is None:
        return {**base, "observed": "no emission estimate", "status": "NOT_ASSESSED", "note": "", "matches": []}
    lb = q_median_kg_h * LB_PER_KG * hours
    observed = f"≈{lb:,.0f} lb CH₄ in a {hours} h event at the median rate ({lb / rq:.1f}× RQ)"
    if steers_events is None:
        return {**base, "observed": observed, "status": "NOT_ASSESSED",
                "note": "STEERS event data unavailable (data gap).", "matches": []}
    matches = []
    for d in detection_dates:
        dd = dt.date.fromisoformat(d)
        for e in steers_events:
            s = e.get("start_date")
            en = e.get("end_date") or s
            if not s:
                continue
            s0 = dt.date.fromisoformat(s[:10]); e0 = dt.date.fromisoformat(en[:10])
            if s0 - dt.timedelta(days=window) <= dd <= e0 + dt.timedelta(days=window):
                matches.append({"detection_date": d, "incident_no": e["incident_no"], "start_date": s})
    if lb <= rq:
        status = "BELOW_RQ"
        note = "Estimated release in a 1 h event does not exceed the RQ."
    elif matches:
        status = "REPORTED"
        note = f"Matching STEERS incident(s): {', '.join(m['incident_no'] for m in matches)}."
    else:
        nearest = sorted(steers_events, key=lambda e: abs((dt.date.fromisoformat(e['start_date'][:10]) -
                                                           dt.date.fromisoformat(detection_dates[0])).days))
        near_txt = (f" Nearest reported event: incident {nearest[0]['incident_no']} starting {nearest[0]['start_date'][:10]}."
                    if nearest else "")
        status = "NO_MATCHING_REPORT_FOUND"
        note = (f"Mass in a plausible ≥{hours} h event exceeds the RQ and no STEERS event lies within ±{window} day "
                f"of the detection date(s) {', '.join(detection_dates)} in the records provided.{near_txt} "
                f"This is not a finding that a report was required or omitted.")
    return {**base, "observed": observed, "status": status, "note": note, "matches": matches,
            "lb_in_min_event": lb}


def physics_ceiling(phys: dict | None) -> dict:
    base = {"rule_id": "PLANT_PHYSICS_CEILING", "rule": "Sanity check: estimate vs plant methane throughput"}
    if not phys:
        return {**base, "threshold": "n/a", "observed": "not computed", "status": "NOT_ASSESSED", "note": ""}
    ok = phys["classification"] != "estimate_physically_implausible"
    return {**base, "threshold": f"{phys['ceiling_t_h']:.0f} t/h CH₄ (500 MMscfd × CH₄ fraction)",
            "observed": f"{phys['q_t_h']:.1f} t/h ({phys['q_fraction_of_ceiling'] * 100:.1f}% of ceiling)",
            "status": "CONSISTENT" if ok else "IMPLAUSIBLE", "note": phys["interpretation"]}


def not_assessed() -> list[dict]:
    return [
        {"rule_id": "NOX_PERMIT_LIMITS", "rule": "NSR 177845 MAERT (NOx / CO limits)", "threshold": "n/a",
         "observed": "n/a", "status": "NOT_ASSESSED", "note": "Data gap: MAERT and NO₂ observations not ingested."},
        {"rule_id": "GHGRP_REPORTED", "rule": "EPA GHGRP Subpart W reported emissions", "threshold": "n/a",
         "observed": "n/a", "status": "NOT_ASSESSED",
         "note": "Data gap: no GHGRP data provided; program reporting status in flux."},
    ]


def evaluate(mc: dict | None, detection_dates: list[str], steers_events: list[dict] | None, phys: dict | None) -> list[dict]:
    p5 = mc["p5_kg_h"] if mc else None
    p95 = mc["p95_kg_h"] if mc else None
    med = mc["median_kg_h"] if mc else None
    return [super_emitter(p5, p95, med), emissions_event_reporting(med, detection_dates, steers_events),
            physics_ceiling(phys), *not_assessed()]
