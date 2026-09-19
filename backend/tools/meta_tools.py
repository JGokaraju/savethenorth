"""Discovery / skills / reporting tools."""
from __future__ import annotations

import difflib
import re

import numpy as np

from backend.agent import verdict as verdict_mod
from backend.science.common import DataGap, slot
from backend.settings import SKILLS_DIR, cfg, facilities, facility, load_manifest
from backend.tools.envelope import data_used, ok
from backend.tools.state import RunState

SLOT_DESCRIPTIONS = {
    "emit_ch4enh": "EMIT L2B methane enhancement raster (ppm·m), 60 m", "emit_ch4uncert": "EMIT per-pixel enhancement uncertainty (ppm·m)",
    "emit_ch4sens": "EMIT enhancement sensitivity (dimensionless)", "carbonmapper": "Carbon Mapper plume records (rates, overpasses)",
    "wind": "Open-Meteo/ERA5 hourly 10 m wind", "firms": "NASA FIRMS VIIRS active-fire detections",
    "s2_truecolor": "Sentinel-2 true-colour image", "s2_swir": "Sentinel-2 SWIR false-colour image",
    "tceq_sob": "TCEQ Title V Statement of Basis (permit O4734)", "tceq_steers": "TCEQ STEERS emissions-event reports",
}


def _skill_meta(p) -> dict:
    text = p.read_text(encoding="utf-8")
    m = re.search(r"^description:\s*(.+)$", text, re.M)
    return {"name": p.stem, "description": m.group(1).strip() if m else text.splitlines()[0].lstrip("# ")}


def list_skills(st: RunState) -> dict:
    skills = [_skill_meta(p) for p in sorted(SKILLS_DIR.glob("*.md"))]
    return ok(f"{len(skills)} skills available: {', '.join(s['name'] for s in skills)}", {"skills": skills})


def load_skill(st: RunState, name: str) -> dict:
    p = SKILLS_DIR / f"{name.removesuffix('.md')}.md"
    if not p.exists():
        raise DataGap(f"no skill named '{name}'")
    content = p.read_text(encoding="utf-8")
    if name not in st.skills_loaded:
        st.skills_loaded.append(name)
    st.emit("skill_loaded", {"name": p.stem, "description": _skill_meta(p)["description"]})
    return ok(f"Loaded skill '{p.stem}' ({len(content.splitlines())} lines).", {"name": p.stem, "content": content})


def find_facility(st: RunState, query: str) -> dict:
    q = query.lower().strip()
    scored = []
    for f in facilities():
        names = [f["name"], *f.get("aliases", []), f.get("county", "") + " county", f.get("nearest_city", ""), f["facility_id"]]
        best = max(difflib.SequenceMatcher(None, q, n.lower()).ratio() + (0.5 if q and q in n.lower() else 0) for n in names if n)
        scored.append((best, f))
    scored.sort(key=lambda x: -x[0])
    hits = [{"facility_id": f["facility_id"], "name": f["name"], "operator": f.get("operator"), "county": f.get("county"),
             "state": f.get("state"), "lat": f["lat"], "lon": f["lon"], "data_status": f.get("data_status"),
             "match_score": round(s, 2)} for s, f in scored if s > 0.35][:5]
    if not hits:
        raise DataGap(f"no facility matches '{query}'")
    top = facility(hits[0]["facility_id"])
    return ok(f"Best match: {top['name']} ({top.get('county')} County, {top.get('state')}), data status "
              f"'{top.get('data_status')}'.", {"matches": hits, "best": top})


def list_available_data(st: RunState, facility_id: str) -> dict:
    f = facility(facility_id)
    if not f:
        raise DataGap(f"unknown facility '{facility_id}'")
    if f.get("data_status") != "cached":
        raise DataGap(f"no cached observations for this facility ({f['name']})")
    m = load_manifest()["slots"]
    rows = []
    for sid, r in m.items():
        rows.append({"slot_id": sid, "type": r.get("type"), "status": r.get("status"), "date": r.get("date_coverage"),
                     "description": SLOT_DESCRIPTIONS.get(sid, ""), "quality": r.get("quality", "ok"),
                     "synthetic": bool(r.get("synthetic")), "warnings": r.get("warnings", []), "reason": r.get("reason")})
    missing = [r["slot_id"] for r in rows if r["status"] != "present"]
    flagged = [r["slot_id"] for r in rows if r["quality"] in ("low", "synthetic")]
    gaps = ["NO₂/NOx observations", "permit MAERT (NSR 177845)", "EPA GHGRP Subpart W"]
    return ok(f"{len(rows) - len(missing)}/{len(rows)} data slots present"
              + (f"; missing: {', '.join(missing)}" if missing else "")
              + (f"; low-quality/synthetic: {', '.join(flagged)}" if flagged else "") + f"; not provided: {', '.join(gaps)}.",
              {"slots": rows, "missing": missing, "flagged": flagged, "out_of_scope_gaps": gaps,
               "event": {"date": cfg("case", "event_date_utc"), "overpass_utc": cfg("case", "overpass_utc"),
                         "known_plume_id": cfg("case", "known_plume_id")}},
              warnings=[w for r in rows for w in r["warnings"]])


def describe_dataset(st: RunState, slot_id: str) -> dict:
    rec = slot(slot_id)
    info = {k: rec.get(k) for k in ("slot_id", "type", "source_name", "citation", "date_coverage", "units", "crs",
                                    "res_deg", "full_granule_bounds", "bounds", "stats", "warnings", "synthetic", "quality")}
    info = {k: v for k, v in info.items() if v is not None}
    if slot_id.startswith("emit_"):
        import rasterio
        with rasterio.open(rec["path"]) as ds:
            a = ds.read(1).astype(float)
            info["normalized_crop_bounds"] = [round(b, 4) for b in ds.bounds]
            info["dims"] = [ds.height, ds.width]
        v = a[a > -9990]
        info["crop_stats"] = {"valid_pixels": int(v.size), **{f"p{p}": round(float(np.percentile(v, p)), 1) for p in (1, 5, 50, 95, 99)},
                              "max": round(float(v.max()), 1)}
    used = [data_used(rec, "metadata and summary statistics only", None)]
    return ok(f"{rec.get('source_name')}: coverage {rec.get('date_coverage')}.", info, evidence_ids=[slot_id],
              warnings=rec.get("warnings", []), data_used=used)


def show_chart(st: RunState, chart_id: str, caption: str = "") -> dict:
    if chart_id not in st.charts:
        raise DataGap(f"chart '{chart_id}' was not produced in this run")
    if chart_id not in [c["chart_id"] for c in st.shown_charts]:
        st.shown_charts.append({"chart_id": chart_id, "caption": caption, "title": st.charts[chart_id]["title"]})
    return ok(f"Chart '{chart_id}' added to the report.", {"shown": [c["chart_id"] for c in st.shown_charts]})


def submit_verdict(st: RunState, verdict: dict) -> dict:
    v, errors = verdict_mod.validate(verdict, st)
    if errors:
        return {"status": "error", "summary": "Verdict rejected: " + "; ".join(errors)[:900], "data": {"errors": errors},
                "charts": [], "evidence_ids": [], "assumptions": [], "warnings": [], "data_used": []}
    d = v.model_dump()
    from backend.science import reports
    d["outcome"] = st.results.get("outcome") or reports.outcome(st.results.get("regulations", []), bool(st.results.get("emission")))
    d["report_comparison"] = st.results.get("report_comparison")
    d["key_evidence"] = (st.results.get("evidence_ranking") or {}).get("key_evidence")
    if not d["charts"]:
        d["charts"] = [c["chart_id"] for c in st.shown_charts]
    st.verdict = d
    st.finished = True
    return ok("Verdict accepted.", {"verdict": d})
