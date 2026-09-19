"""OMNI multimodal tools: charts, satellite images, document pages. OMNI supplies qualitative evidence only."""
from __future__ import annotations

import io
import json
import re

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw

from backend.charts.base import load as load_chart
from backend.llm import omni
from backend.science.common import DataGap, slot
from backend.settings import ROOT, cfg
from backend.tools.envelope import data_used, ok
from backend.tools.state import RunState, now_iso

IMAGE_IDS = {"s2_truecolor": "Sentinel-2 true colour", "s2_swir": "Sentinel-2 SWIR false colour (B12/B11/B8A)"}
DOC_IDS = {"tceq_sob": "TCEQ Statement of Basis (FOP O4734)", "tceq_steers": "TCEQ STEERS emissions-event records"}


def _record(st: RunState, tool: str, target: str, question: str, res: dict, sent_ref: str, extra: dict | None = None) -> str:
    n = len(st.omni_calls) + 1
    eid = f"omni:{n}"
    rec = {"id": eid, "type": "ai_analysis", "tool": tool, "target_id": target, "question": question,
           "answer": res["answer"], "model": res["model"], "mode": res["mode"].upper(), "timestamp": now_iso(),
           "input_ref": sent_ref, "cache_key": res.get("cache_key"), **(extra or {})}
    st.omni_calls.append(rec)
    st.add_derived_note(eid, rec, tool)
    st.emit("omni_analysis", {"tool": tool, "target_id": target, "question": question, "answer": res["answer"],
                              "mode": res["mode"].upper(), "model": res["model"], "thumbnail_url": f"/api/runs/{st.run_id}/{sent_ref}",
                              "evidence_id": eid, **(extra or {})})
    return eid


# ------------------------------------------------------------------ mock text (deterministic, from stats)
def _mock_chart(chart_id: str, s: dict) -> str:
    p = "[MOCK OMNI] "
    if chart_id == "plume_map":
        d = s.get("wind_from_deg", 0)
        to = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"][int(((d + 180) % 360 + 22.5) // 45) % 8]
        return (p + f"A single elongated enhancement feature starts at the plume-source marker, immediately beside the "
                f"facility marker, and extends roughly {s.get('plume_extent_north_km', '?')} km to the {to}, aligned with the "
                f"wind arrow (wind from {d}°). The highlighted mask outlines this feature only; the rest of the frame shows "
                f"speckle-like noise with no comparable coherent structure. The plume is narrowest and brightest near the source.")
    if chart_id == "emission_distribution":
        cm = s.get("carbon_mapper") or []
        cm_txt = (" The Carbon Mapper line sits inside the bulk of the distribution"
                  + (" (labelled SYNTHETIC)." if cm and cm[0].get("synthetic") else ".")) if cm else ""
        return (p + "The histogram is unimodal with a moderate spread; the median line and the whole p5–p95 band lie far to "
                "the right of the red 100 kg/h threshold line on the logarithmic axis — roughly two orders of magnitude "
                "above it. No draws fall near the threshold." + cm_txt)
    if chart_id == "wind_sensitivity":
        return (p + "Q increases steadily with wind speed; the shaded coefficient band widens at higher winds. Across the "
                "whole 1–12 m/s range the curve and its band stay well above the red threshold line, so the threshold "
                "conclusion does not depend on the exact wind speed.")
    if chart_id == "wind_timeseries":
        return (p + "Winds are light-to-moderate and steady through the day, with speeds changing little around the "
                "overpass line and direction consistently from the south to south-south-west.")
    if chart_id == "flare_timeline":
        b, a = s.get("nearest_before_overpass") or {}, s.get("nearest_after_overpass") or {}
        timing = (f"the closest detections are about {abs(b['gap_hours']):.0f} h before" if b else "no detection precedes") +                  (f" and {a['gap_hours']:.0f} h after the overpass line" if a else " the overpass, and none follows it")
        verdict = ("a flare appears to have been burning around the overpass" if s.get("flare_observed_near_overpass")
                   else "no flare activity is visible close to the overpass")
        return (p + f"Panel (a) shows {s.get('n_near_facility', 0)} low-FRP detections ({s.get('n_night', 0)} at night); "
                f"{timing}, so {verdict}. Panel (b) shows the attributed detections clustered inside the 1.5 km circle "
                f"around the facility marker, with other detections scattered elsewhere in the box.")
    if chart_id == "reporting_timeline":
        dets = [d for d, _ in s.get("detections", [])]
        incs = s.get("steers_incidents", [])
        near = [i for i, sd in incs for d in dets if abs((pd.Timestamp(sd[:10]) - pd.Timestamp(d)).days) <= 1]
        return (p + f"The red satellite detection markers ({', '.join(dets) or 'none'}) "
                + (f"coincide with blue STEERS event(s) {', '.join(near)}." if near else
                   f"have no blue STEERS reported-event bar at or near the same dates; the reported events "
                   f"({', '.join(i for i, _ in incs)}) fall at other times."))
    if chart_id == "regulatory_comparison":
        return (p + "On the log axis, the estimate bar (with its error bar) extends far beyond the red threshold bar, and "
                "remains well short of the grey plant-capacity ceiling bar.")
    if chart_id == "annual_scenarios":
        return (p + "Three bars rise from low to high scenario with a wide spread; the amber caveat notes the very small "
                "number of overpasses behind these numbers.")
    return p + "Chart shows the quantities described in its title and axes."


def _mock_image(image_id: str, question: str) -> str:
    base = ("[MOCK OMNI] The image is a regional-scale Sentinel-2 composite (header date 2026-09-18) covering roughly "
            "Lamesa to San Angelo, with widespread fair-weather cumulus and cloud shadows. At the marked location near "
            "Stanton the plant footprint spans only a few pixels and individual infrastructure cannot be resolved in "
            "the zoomed inset. ")
    if image_id == "s2_swir":
        return base + ("No distinct bright SWIR hot spot can be confirmed at the marked location at this scale; the image "
                       "also post-dates the event by 13 months, so it cannot show flare status on 2025-08-08.")
    return base + "Cleared pads and roads consistent with oil-and-gas infrastructure are visible regionally, but the image cannot confirm the plant layout."


def _mock_doc(doc_id: str, texts: dict[int, str], question: str) -> str:
    joined = "\n".join(texts.values())
    if doc_id == "tceq_sob":
        cap = re.search(r"combined processing capacity of ([\d,]+ ?MMSCFD)", joined, re.I)
        flares = sorted(set(re.findall(r"FL-\d{4}", joined)))
        rules = sorted(set(m.strip() for m in re.findall(r"(?:40 CFR Part 60,? )?Subpart\s+[A-Z]{1,6}b?", joined)))
        return "[MOCK OMNI] " + json.dumps({"processing_capacity": cap.group(1) if cap else None, "flare_ids": flares,
                                            "federal_rules": rules[:8],
                                            "note": "mock extraction by pattern-matching the rendered pages' text"})
    return "[MOCK OMNI] " + json.dumps({"note": "mock: see parsed STEERS table"})


# ------------------------------------------------------------------ tools
def analyze_chart(st: RunState, chart_id: str, question: str) -> dict:
    art = load_chart(chart_id)
    if art is None or chart_id not in st.charts:
        raise DataGap(f"chart '{chart_id}' has not been produced in this run yet")
    if not art.png_path:
        raise DataGap(f"chart '{chart_id}' has no PNG export (PNG snapshot failed)")
    png = ROOT / art.png_path
    sent = st.evidence_dir / f"omni_{chart_id}.png"
    sent.write_bytes(png.read_bytes())
    prompt = (f"This is a chart titled '{art.title}' from a methane emissions screening analysis. {question} "
              "Answer in 2-4 sentences, qualitatively.")
    res = omni.ask(prompt, image_path=png, mock_text=_mock_chart(chart_id, art.summary_stats))
    eid = _record(st, "analyze_chart", chart_id, question, res, st.evidence_ref(sent.name))
    return ok(f"OMNI ({res['mode']}) on {chart_id}: {res['answer'][:220]}",
              {"chart_id": chart_id, "question": question, "answer": res["answer"], "mode": res["mode"], "model": res["model"]},
              [], [eid])


def _mark_image(image_path, bounds: dict, lat: float, lon: float) -> tuple[bytes, dict]:
    im = Image.open(image_path).convert("RGB")
    w, h = im.size
    x = (lon - bounds["west"]) / (bounds["east"] - bounds["west"]) * w
    y = (bounds["north"] - lat) / (bounds["north"] - bounds["south"]) * h
    full = im.copy()
    d = ImageDraw.Draw(full)
    for r, col in ((14, (255, 255, 255)), (12, (217, 89, 38))):
        d.ellipse([x - r, y - r, x + r, y + r], outline=col, width=3)
    half = 40
    box = (int(max(0, x - half)), int(max(0, y - half)), int(min(w, x + half)), int(min(h, y + half)))
    zoom = im.crop(box).resize(((box[2] - box[0]) * 8, (box[3] - box[1]) * 8), Image.LANCZOS)
    dz = ImageDraw.Draw(zoom)
    zx, zy = (x - box[0]) * 8, (y - box[1]) * 8
    dz.ellipse([zx - 40, zy - 40, zx + 40, zy + 40], outline=(217, 89, 38), width=4)
    canvas = Image.new("RGB", (w + zoom.width + 20, max(h, zoom.height)), (15, 17, 22))
    canvas.paste(full, (0, 0)); canvas.paste(zoom, (w + 20, 0))
    ImageDraw.Draw(canvas).text((w + 28, zoom.height - 20 if zoom.height < canvas.height else 8),
                                "8x zoom around marked facility", fill=(240, 240, 240))
    buf = io.BytesIO(); canvas.save(buf, "PNG")
    return buf.getvalue(), {"pixel_xy": [round(x), round(y)], "zoom_box_px": list(box)}


def analyze_image(st: RunState, image_id: str, question: str) -> dict:
    if image_id not in IMAGE_IDS:
        raise DataGap(f"unknown image '{image_id}' (available: {', '.join(IMAGE_IDS)})")
    rec = slot(image_id)
    f = st.facility
    if not f or f.get("data_status") != "cached":
        raise DataGap("no cached imagery for this facility")
    bounds = rec.get("bounds") or json.loads((ROOT / rec["bounds_file"]).read_text())
    img, geo = _mark_image(rec["path"], bounds, f["lat"], f["lon"])
    sent = st.evidence_dir / f"omni_{image_id}.png"
    sent.write_bytes(img)
    prompt = (f"This is a {IMAGE_IDS[image_id]} satellite image. Left: full scene with the facility circled in orange. "
              f"Right: 8x zoom around the circled location. {question} Also state whether the image resolution and "
              "date allow a confident answer.")
    res = omni.ask(prompt, image_bytes=img, mock_text=_mock_image(image_id, question))
    eid = _record(st, "analyze_image", image_id, question, res, st.evidence_ref(sent.name), {"image_geo": geo})
    used = [data_used(rec, f"full scene with facility marker + 8x zoom (image px {geo['pixel_xy']})", 1,
                      st.evidence_ref(sent.name))]
    warnings = rec.get("warnings", [])
    return ok(f"OMNI ({res['mode']}) on {image_id}: {res['answer'][:220]}",
              {"image_id": image_id, "question": question, "answer": res["answer"], "mode": res["mode"],
               "image_date": bounds.get("date"), "bounds": {k: bounds[k] for k in ("west", "south", "east", "north")},
               "bounds_method": bounds.get("method")}, [], [image_id, eid], [], warnings, used)


# keyword -> weight; rare decisive terms (the capacity statement) outweigh frequent ones
_DEFAULT_KEYWORDS = {"tceq_sob": {"MMSCF": 10, "capacity": 1, "flare": 1, "FL-35": 2, "Subpart": 1, "OOOO": 1, "KKKK": 1}}


def _pick_pages(texts: list[str], question: str, doc_id: str, n: int = 3) -> list[int]:
    words = [w for w in re.findall(r"[A-Za-z0-9\-]{4,}", question) if w.lower() not in
             {"extract", "list", "with", "json", "from", "that", "this", "applicable", "dates", "rules", "federal"}]
    kws = {**{w: 1 for w in words}, **_DEFAULT_KEYWORDS.get(doc_id, {})}
    scores = [sum(wt * len(re.findall(re.escape(k), t, re.I)) for k, wt in kws.items()) for t in texts]
    order = sorted(range(len(texts)), key=lambda i: (-scores[i], i))
    return sorted(i + 1 for i in order[:n] if scores[i] > 0) or [1]


def _steers_table_png(st: RunState) -> tuple[bytes, pd.DataFrame]:
    """Render the STEERS rows as a table image (matplotlib; no browser needed)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rec = slot("tceq_steers")
    df = pd.read_csv(rec["path"])
    cols = ["INCIDENT NO.", "RE NAME", "START DATE/TIME", "END DATE/TIME", "EVENT TYPE", "EPN", "CONTAMINANT",
            "EST QUANTITY/OPACITY", "UNITS"]
    df = df[[c for c in cols if c in df]]
    fig, ax = plt.subplots(figsize=(14, 1.2 + 0.4 * len(df)), dpi=100)
    ax.axis("off")
    tbl = ax.table(cellText=df.astype(str).values, colLabels=list(df.columns), loc="center", cellLoc="left")
    tbl.auto_set_font_size(False); tbl.set_fontsize(10); tbl.scale(1, 1.6)
    for (r, _), cell in tbl.get_celld().items():
        if r == 0:
            cell.set_facecolor("#dddddd"); cell.set_text_props(weight="bold")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue(), df


def read_document(st: RunState, doc_id: str, question: str, pages: list[int] | None = None) -> dict:
    if doc_id not in DOC_IDS:
        raise DataGap(f"unknown document '{doc_id}' (available: {', '.join(DOC_IDS)})")
    rec = slot(doc_id)
    answers, sent_refs, snippets = [], [], {}
    if rec["path"].suffix.lower() == ".pdf":
        import pymupdf
        doc = pymupdf.open(rec["path"])
        texts = [p.get_text() for p in doc]
        pages = [p for p in (pages or _pick_pages(texts, question, doc_id)) if 1 <= p <= len(texts)][:3]
        for pno in pages:
            pix = doc[pno - 1].get_pixmap(dpi=110)
            img = pix.tobytes("png")
            name = f"omni_{doc_id}_p{pno}.png"
            (st.evidence_dir / name).write_bytes(img)
            sent_refs.append(st.evidence_ref(name))
            snippets[pno] = texts[pno - 1]
            prompt = (f"This is page {pno} of the {DOC_IDS[doc_id]}. {question} If this page has nothing relevant, "
                      "return an empty JSON object {}.")
            res = omni.ask(prompt, image_bytes=img, mock_text=_mock_doc(doc_id, {pno: texts[pno - 1]}, question))
            answers.append({"page": pno, **res})
        kw = list(_DEFAULT_KEYWORDS.get(doc_id, {}))
        snip = {p: [ln.strip() for ln in t.splitlines() if any(k.lower() in ln.lower() for k in kw) and ln.strip()][:8]
                for p, t in snippets.items()}
        pd.DataFrame([{"page": p, "snippet": s} for p, ss in snip.items() for s in ss]).to_csv(
            st.evidence_dir / f"{doc_id}_snippets.csv", index=False)
        subset = f"pages {pages} rendered at 110 dpi and sent to OMNI; keyword snippets extracted"
        n_units = len(pages)
    else:
        img, df = _steers_table_png(st)
        name = f"omni_{doc_id}_table.png"
        (st.evidence_dir / name).write_bytes(img)
        sent_refs.append(st.evidence_ref(name))
        mock = "[MOCK OMNI] " + json.dumps([{"incident_no": str(i), "start": g["START DATE/TIME"].iloc[0],
                                              "end": g["END DATE/TIME"].iloc[0], "event_type": g["EVENT TYPE"].iloc[0],
                                              "contaminants": sorted(g["CONTAMINANT"].unique().tolist())}
                                             for i, g in df.groupby("INCIDENT NO.")])
        res = omni.ask(f"This image is a table exported from the {DOC_IDS[doc_id]}. {question}", image_bytes=img, mock_text=mock)
        answers.append({"page": 1, **res})
        snip = {}
        subset = f"{len(df)} emission-point rows rendered as a table image and sent to OMNI"
        n_units = len(df)
    merged_text = "\n".join(f"[page {a['page']}] {a['answer']}" for a in answers)
    parsed = [omni.parse_json(a["answer"].replace("[MOCK OMNI]", "")) for a in answers]
    mode = answers[0]["mode"] if answers else "mock"
    eid = _record(st, "read_document", doc_id, question, {"answer": merged_text, "mode": mode, "model": answers[0]["model"],
                                                         "cache_key": answers[0].get("cache_key")},
                  sent_refs[0], {"pages": [a["page"] for a in answers], "all_inputs": sent_refs})
    used = [data_used(rec, subset, n_units, sent_refs[0], sent_refs[1:] + ([st.evidence_ref(f"{doc_id}_snippets.csv")] if snip else []))]
    st.results.setdefault("documents", {})[doc_id] = {"question": question, "parsed": parsed, "pages": [a["page"] for a in answers]}
    return ok(f"OMNI ({mode}) read {doc_id} pages {[a['page'] for a in answers]}: {merged_text[:240]}",
              {"doc_id": doc_id, "pages": [a["page"] for a in answers], "answers": [a["answer"] for a in answers],
               "parsed_json": parsed, "snippets": snip, "mode": mode}, [], [doc_id, eid], [], [], used)
