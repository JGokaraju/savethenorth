"""Screening outcome (BUSTED / ACCEPTED) and the satellite-vs-technical-report comparison."""
from __future__ import annotations

import datetime as dt

LB_PER_KG = 2.2046


def outcome(rules: list[dict], has_estimate: bool) -> dict:
    """Deterministic headline from the regulatory statuses. Screening language, not an enforcement finding."""
    st = {r["rule_id"]: r["status"] for r in rules}
    fed, tx, phys = st.get("US_SUPER_EMITTER"), st.get("TX_EMISSIONS_EVENT_REPORTING"), st.get("PLANT_PHYSICS_CEILING")
    if not has_estimate:
        return {"outcome": "NOT_ASSESSED", "reason": "No satellite observation available for this facility and date."}
    if phys == "IMPLAUSIBLE":
        return {"outcome": "INCONCLUSIVE", "reason": "The estimate exceeds the plant's physical throughput — data-quality issue."}
    if tx == "NO_MATCHING_REPORT_FOUND":
        why = ("Satellite-observed methane exceeds the federal super-emitter threshold and the Texas reportable quantity, "
               "and no matching emissions-event report was found.") if fed == "EXCEEDS" else (
               "Estimated release exceeds the Texas reportable quantity and no matching emissions-event report was found.")
        return {"outcome": "BUSTED", "reason": why}
    if fed == "BELOW" or tx in ("REPORTED", "BELOW_RQ"):
        why = "The release was reported to TCEQ." if tx == "REPORTED" else "Emissions are consistent with reporting obligations."
        return {"outcome": "ACCEPTED", "reason": why}
    return {"outcome": "INCONCLUSIVE", "reason": "Uncertainty spans the threshold; more observations are needed."}


def _lb(p: dict) -> float:
    q = float(p.get("quantity") or 0)
    u = (p.get("units") or "").lower()
    return q if "pound" in u or u in ("lb", "lbs") else q * LB_PER_KG if "kg" in u else q


def core_figures(em: dict | None, threshold_kg_h: float, gwp: float, reported_same_day: int) -> dict | None:
    """Headline numbers in CO2-equivalent. 'Allowed' = the federal super-emitter threshold (no CO2/CH4 permit limit
    is in the data provided — the NSR MAERT was not ingested)."""
    if not em:
        return None
    to_co2e_t_h = lambda kg_h: kg_h * gwp / 1000  # noqa: E731
    return {"gwp100_ch4": gwp,
            "allowed": {"ch4_kg_h": threshold_kg_h, "co2e_t_h": to_co2e_t_h(threshold_kg_h),
                        "basis": "EPA super-emitter threshold (40 CFR 60.5371a/b)"},
            "actual": {"ch4_kg_h": em["median_kg_h"], "co2e_t_h": to_co2e_t_h(em["median_kg_h"]),
                       "co2e_t_h_p5": to_co2e_t_h(em["p5_kg_h"]), "co2e_t_h_p95": to_co2e_t_h(em["p95_kg_h"])},
            "ratio": em["median_kg_h"] / threshold_kg_h, "reported_same_day": reported_same_day}


def comparison(em: dict | None, annual: dict | None, events: list[dict] | None, event_date: str, window_days: int = 1) -> dict:
    """What the satellite implies vs what the operator's technical reports (TCEQ STEERS) contain."""
    events = events or []
    reported = []
    for e in events:
        by = {}
        for p in e.get("pollutants", []):
            by[p["contaminant"]] = by.get(p["contaminant"], 0.0) + _lb(p)
        reported.append({"incident_no": e["incident_no"], "start": e.get("start_date"), "end": e.get("end_date"),
                         "duration_h": e.get("duration_h"), "event_type": e.get("event_type"),
                         "emission_points": e.get("emission_points", []), "lb_by_contaminant": by,
                         "methane_reported": bool(e.get("methane_reported"))})
    d0 = dt.date.fromisoformat(event_date)
    on_date = [r for r in reported if r["start"] and abs((dt.date.fromisoformat(r["start"][:10]) - d0).days) <= window_days]
    voc_total = sum(v for r in reported for k, v in r["lb_by_contaminant"].items() if "voc" in k.lower() or "natural gas" in k.lower())
    out = {"event_date": event_date, "reported_events": reported, "reported_on_event_date": on_date,
           "reported_voc_total_lb": round(voc_total, 1), "reported_voc_total_t": round(voc_total / LB_PER_KG / 1000, 3),
           "methane_reported_anywhere": any(r["methane_reported"] for r in reported),
           "note": ("TCEQ reports list CO, NOx and natural-gas VOCs from flaring; methane is not itemised. "
                    "Reported quantities are shown for scale, not as a like-for-like comparison.")}
    if em:
        kg_h = em["median_kg_h"]
        out["satellite"] = {"median_kg_h": kg_h, "p5_kg_h": em["p5_kg_h"], "p95_kg_h": em["p95_kg_h"],
                            "lb_per_hour": round(kg_h * LB_PER_KG), "lb_if_24h": round(kg_h * LB_PER_KG * 24)}
    if annual:
        a = annual["annual_t_ch4"]
        out["projection_t_ch4_yr"] = {"low": a["low"], "central": a["central"], "high": a["high"],
                                     "detection_frequency": annual.get("detection_frequency"), "caveat": annual.get("caveat")}
        if voc_total > 0:
            out["projection_vs_reported_ratio"] = round(a["central"] / (voc_total / LB_PER_KG / 1000))
    return out
