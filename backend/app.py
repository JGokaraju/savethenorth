"""Save the North FastAPI backend (spec §12)."""
from __future__ import annotations

import asyncio
import difflib
import html
import io
import json
import os
import threading
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend import settings
from backend.agent import orchestrator
from backend.charts.base import load as load_chart
from backend.llm import omni
from backend.science.common import DataGap, haversine_km, slot
from backend.settings import CHARTS_DIR, DATA, ROOT, RUNS_DIR, facilities
from backend.tools import field_tools
from backend.tools.state import RunState, get_state, new_state

app = FastAPI(title="Save the North API", version="1.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GAZETTEER = json.loads((DATA / "gazetteer.json").read_text(encoding="utf-8")) if (DATA / "gazetteer.json").exists() else []


# ====================================================================== health / facilities / geocode
@app.get("/api/health")
def health() -> dict:
    m = settings.load_manifest()
    return {
        "mode": {"mock_llm": settings.mock_llm(), "mock_omni": settings.mock_omni(), "demo_replay": settings.demo_replay(),
                 "label": "REPLAY" if settings.demo_replay() else ("MOCK" if settings.mock_llm() else "LIVE")},
        "keys_present": {"openai": bool(os.getenv("OPENAI_API_KEY")), "omni": bool(os.getenv("OMNI_API_KEY"))},
        "live_available": orchestrator.live_available(),
        "omni_live_available": not settings.mock_omni(),
        "models": {"openai": os.getenv("OPENAI_MODEL") or None, "omni": omni.model_name()},
        "omni_calls": omni.counters(),
        "assets": {k: {"status": v.get("status"), "quality": v.get("quality", "ok"), "synthetic": bool(v.get("synthetic"))}
                   for k, v in m.get("slots", {}).items()},
    }


def _fac_public(f: dict) -> dict:
    m = settings.load_manifest().get("slots", {}) if f.get("data_status") == "cached" else {}
    avail = {}
    for label, sids in (("EMIT", ["emit_ch4enh"]), ("Wind", ["wind"]), ("FIRMS", ["firms"]), ("Sentinel-2", ["s2_truecolor", "s2_swir"]),
                        ("TCEQ docs", ["tceq_sob", "tceq_steers"]), ("Carbon Mapper", ["carbonmapper"])):
        recs = [m.get(s, {}) for s in sids]
        ok = bool(recs) and all(r.get("status") == "present" for r in recs)
        q = "synthetic" if any(r.get("synthetic") for r in recs) else ("low" if any(r.get("quality") == "low" for r in recs) else "ok")
        avail[label] = {"available": ok, "quality": q if ok else None}
    return {**f, "availability": avail}


@app.get("/api/facilities")
def list_facilities(q: str = "") -> list[dict]:
    fs = facilities()
    if q.strip():
        ql = q.lower()

        def score(f):
            names = [f["name"], *f.get("aliases", []), f.get("county", ""), f.get("nearest_city", ""), f.get("operator", "")]
            return max(difflib.SequenceMatcher(None, ql, n.lower()).ratio() + (0.6 if ql in n.lower() else 0) for n in names if n)
        fs = [f for f in sorted(fs, key=score, reverse=True) if score(f) > 0.3]
    return [_fac_public(f) for f in fs]


@app.get("/api/facilities/{facility_id}")
def get_facility(facility_id: str) -> dict:
    f = settings.facility(facility_id)
    if not f:
        raise HTTPException(404, "unknown facility")
    return _fac_public(f)


@app.get("/api/facilities/{facility_id}/imagery/{role}")
def facility_imagery(facility_id: str, role: str):
    """Site basemap (role 'site' = plant close-up, 'region' = EMIT window). Display only."""
    if facility_id != "tx-lenorah-redlake":
        raise HTTPException(404, "no imagery for this facility")
    try:
        img = slot("site_imagery").get("images", {}).get(role)
    except DataGap as e:
        raise HTTPException(404, str(e))
    if not img:
        raise HTTPException(404, "no such image")
    return FileResponse(ROOT / img["normalized"], headers={"Cache-Control": "max-age=3600"})


@app.get("/api/geocode")
def geocode(q: str = Query(..., min_length=1), limit: int = 8) -> list[dict]:
    ql = q.lower().strip()
    head = ql.split(",")[0].strip()  # "Lenorah Gas Plant, Stanton, Texas" -> "lenorah gas plant"
    out = []
    for f in facilities():
        names = [f["name"], *f.get("aliases", []), f"{f.get('county', '')} county", f.get("nearest_city", "")]
        s = max(difflib.SequenceMatcher(None, head, n.lower()).ratio() + (0.8 if head and head in n.lower() else 0)
                for n in names if n)
        out.append({"label": f"{f['name']} — {f.get('county', '')} County, {f.get('state', '')}", "lat": f["lat"], "lon": f["lon"],
                    "kind": "facility", "facility_id": f["facility_id"], "score": s + 0.2})
    for g in GAZETTEER:
        label = f"{g['name']}, {g['state']}"
        s = difflib.SequenceMatcher(None, ql, label.lower()).ratio() + (0.6 if head and label.lower().startswith(head) else 0)
        out.append({"label": label, "lat": g["lat"], "lon": g["lon"], "kind": g.get("kind", "place"), "score": s})
    out.sort(key=lambda r: -r["score"])
    res = []
    for r in out[:limit]:
        if r["score"] < 0.45:
            continue
        near = min(facilities(), key=lambda f: haversine_km(r["lat"], r["lon"], f["lat"], f["lon"]))
        d = float(haversine_km(r["lat"], r["lon"], near["lat"], near["lon"]))
        r["nearest_facility"] = {"facility_id": near["facility_id"], "name": near["name"], "distance_km": round(d, 1)} if d <= 25 else None
        r["score"] = round(r["score"], 2)
        res.append(r)
    return res


# ====================================================================== runs + SSE
class RunRequest(BaseModel):
    facility_id: str
    date: str = "2025-08-08"
    mode: str | None = None  # "demo" | "live"; default: live when keys are configured


def _latest_successful_run(facility_id: str) -> Path | None:
    cands = []
    for p in RUNS_DIR.glob("*.jsonl"):
        if p.stem == "prep":
            continue
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
            first, last = json.loads(lines[0]), json.loads(lines[-1])
        except Exception:  # noqa: BLE001
            continue
        if first.get("type") == "run_started" and first.get("facility_id") == facility_id and first.get("mode") != "REPLAY" \
                and last.get("type") == "run_finished" and last.get("ok"):
            cands.append((first.get("mode") == "LIVE", p.stat().st_mtime, p))
    return max(cands)[2] if cands else None  # prefer LIVE recordings, then most recent


def _replay(st: RunState, src: Path) -> None:
    """Replay a recorded run's events with realistic delays (offline-capable)."""
    import shutil
    events = [json.loads(line) for line in src.read_text(encoding="utf-8").splitlines() if line.strip()]
    src_dir = RUNS_DIR / src.stem
    if src_dir.exists():
        shutil.copytree(src_dir, st.dir, dirs_exist_ok=True)
    ledger = src_dir / "ledger.json"
    if ledger.exists():
        for rec in json.loads(ledger.read_text(encoding="utf-8")):
            st.ledger[rec["id"]] = rec
    delays = {"tool_call": 0.35, "tool_result": 0.5, "chart": 0.3, "omni_analysis": 0.9, "assistant_message": 0.6,
              "skill_loaded": 0.4, "verdict": 0.5}
    for ev in events:
        typ = ev.pop("type")
        ev.pop("run_id", None); ev.pop("ts", None)
        if typ == "run_started":
            ev["mode"] = "REPLAY"; ev["replay_of"] = src.stem
        if typ == "verdict":
            st.verdict = ev.get("verdict")
        if typ == "tool_result":
            st.tool_calls.append({k: ev.get(k) for k in ("call_id", "name", "status", "summary", "charts", "evidence_ids")})
        time.sleep(delays.get(typ, 0.1))
        st.emit(typ, ev)
    st.finished = True


@app.post("/api/runs")
def create_run(req: RunRequest) -> dict:
    if not settings.facility(req.facility_id):
        raise HTTPException(404, "unknown facility")
    if settings.demo_replay():
        src = _latest_successful_run(req.facility_id)
        if src:
            st = new_state(req.facility_id, req.date, mode="REPLAY")
            threading.Thread(target=_replay, args=(st, src), daemon=True).start()
            return {"run_id": st.run_id, "mode": "REPLAY", "replay_of": src.stem}
    if (req.mode or "").lower() == "live" and not orchestrator.live_available():
        raise HTTPException(400, "Live mode needs OPENAI_API_KEY and OPENAI_MODEL in .env (restart the backend after editing)")
    st = new_state(req.facility_id, req.date, mode=orchestrator.mode(req.mode))
    threading.Thread(target=orchestrator.run, args=(st,), daemon=True).start()
    return {"run_id": st.run_id, "mode": st.mode}


@app.post("/api/field-note")
async def field_note(facility_id: str = Form(...), audio: UploadFile = File(...),
                     context: str | None = Form(None)) -> dict:
    """Field mode: a spoken question from someone at the site, answered by OMNI from the audio + site view.

    Not part of the agent's tool set — the desk assessment has no microphone to call it with.
    """
    blob = await audio.read()
    if len(blob) > 8_000_000:
        raise HTTPException(413, "recording too long")
    fmt = (audio.filename or "clip.webm").rsplit(".", 1)[-1].lower()
    if fmt not in {"webm", "wav", "mp3", "m4a", "ogg"}:
        fmt = "webm"
    try:
        return field_tools.field_question(facility_id, blob, fmt, context)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


def _run_or_404(run_id: str) -> RunState | None:
    st = get_state(run_id)
    if st is None and not (RUNS_DIR / f"{run_id}.jsonl").exists():
        raise HTTPException(404, "unknown run")
    return st


@app.get("/api/runs")
def recent_runs(limit: int = 8) -> list[dict]:
    """Recent assessments, newest first (for the landing page and for re-opening a finished report)."""
    out = []
    for p in sorted(RUNS_DIR.glob("*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.stem == "prep" or p.stem.startswith("test-"):
            continue
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
            first, last = json.loads(lines[0]), json.loads(lines[-1])
        except Exception:  # noqa: BLE001 — a partially written run is simply skipped
            continue
        if first.get("type") != "run_started":
            continue
        vf = RUNS_DIR / p.stem / "verdict.json"
        v = json.loads(vf.read_text(encoding="utf-8")) if vf.exists() else None
        f = settings.facility(first.get("facility_id", "")) or {}
        out.append({"run_id": p.stem, "facility_id": first.get("facility_id"), "facility_name": f.get("name"),
                    "date": first.get("date"), "mode": first.get("mode"), "started": first.get("ts"),
                    "finished": last.get("type") == "run_finished",
                    "outcome": (v or {}).get("outcome", {}).get("outcome"),
                    "median_kg_h": ((v or {}).get("methane_estimate") or {}).get("median_kg_h")})
        if len(out) >= max(1, min(limit, 50)):
            break
    return out


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str):
    st = _run_or_404(run_id)

    async def gen():
        if st is None:  # finished run from a previous server process: stream the recording
            for line in (RUNS_DIR / f"{run_id}.jsonl").read_text(encoding="utf-8").splitlines():
                ev = json.loads(line)
                yield {"event": ev["type"], "data": json.dumps(ev, default=str)}
            return
        i = 0
        while True:
            while i < len(st.events):
                ev = st.events[i]
                i += 1
                yield {"event": ev["type"], "data": json.dumps(ev, default=str)}
                if ev["type"] == "run_finished":
                    return
            await asyncio.sleep(0.1)

    return EventSourceResponse(gen(), ping=15)


@app.get("/api/runs/{run_id}")
def run_summary(run_id: str) -> dict:
    st = _run_or_404(run_id)
    if st is None:
        d = RUNS_DIR / run_id
        v = d / "verdict.json"
        return {"run_id": run_id, "finished": True, "verdict": json.loads(v.read_text(encoding="utf-8")) if v.exists() else None}
    return {"run_id": run_id, "facility_id": st.facility_id, "date": st.date, "mode": st.mode, "finished": st.finished,
            "verdict": st.verdict, "shown_charts": st.shown_charts, "tool_calls": st.tool_calls, "skills_loaded": st.skills_loaded}


# ====================================================================== charts / images
@app.get("/api/charts/{chart_id}.png")
def chart_png(chart_id: str):
    p = CHARTS_DIR / f"{chart_id}.png"
    if not p.exists():
        raise HTTPException(404, "no PNG for chart")
    return FileResponse(p, media_type="image/png")


@app.get("/api/charts/{chart_id}")
def chart_json(chart_id: str):
    art = load_chart(chart_id)
    if not art:
        raise HTTPException(404, "unknown chart")
    return {"chart_id": chart_id, "title": art.title, "figure_json": art.figure_json, "summary_stats": art.summary_stats}


@app.get("/api/images/{image_id}")
def image_meta(image_id: str):
    try:
        rec = slot(image_id)
    except DataGap as e:
        raise HTTPException(404, str(e))
    b = rec.get("bounds") or {}
    return {"image_id": image_id, "url": f"/api/images/{image_id}/file", "bounds": {k: b.get(k) for k in ("west", "south", "east", "north")},
            "date": b.get("date"), "bounds_method": b.get("method"), "warnings": rec.get("warnings", []),
            "source_name": rec.get("source_name"), "citation": rec.get("citation")}


@app.get("/api/images/{image_id}/file")
def image_file(image_id: str):
    try:
        rec = slot(image_id)
    except DataGap as e:
        raise HTTPException(404, str(e))
    return FileResponse(rec["path"])


# ====================================================================== datasets
DATASET_KEYS = ("slot_id", "status", "type", "file", "normalized", "source_name", "source_url", "citation", "provider",
                "sha256", "date_coverage", "reason", "warnings", "quality", "synthetic", "stats")


@app.get("/api/datasets")
def datasets() -> list[dict]:
    m = settings.load_manifest()
    out = []
    for v in m.get("slots", {}).values():
        d = {k: v.get(k) for k in DATASET_KEYS}
        f = ROOT / v["file"] if v.get("file") and (ROOT / v["file"]).is_file() else (ROOT / v["normalized"] if v.get("normalized") else None)
        d["size_bytes"] = f.stat().st_size if f and f.exists() else None
        out.append(d)
    return out


def _raster_quicklook(path: Path) -> bytes:
    import rasterio
    from PIL import Image
    with rasterio.open(path) as ds:
        a = ds.read(1, out_shape=(min(ds.height, 600), min(ds.width, 600))).astype(float)
    a[a <= -9990] = np.nan
    lo, hi = np.nanpercentile(a, 2), np.nanpercentile(a, 99.5)
    v = np.clip((a - lo) / max(hi - lo, 1e-9), 0, 1)
    rgb = np.stack([v * 230, v * 240, 60 + v * 195], -1)
    rgb[np.isnan(a)] = 20
    buf = io.BytesIO(); Image.fromarray(rgb.astype("uint8")).save(buf, "PNG")
    return buf.getvalue()


@app.get("/api/datasets/{slot_id}/preview")
def dataset_preview(slot_id: str):
    try:
        rec = slot(slot_id)
    except DataGap as e:
        return {"slot_id": slot_id, "status": "data_gap", "reason": str(e)}
    p = rec["path"]
    base = {"slot_id": slot_id, "source_name": rec.get("source_name"), "sha256": rec.get("sha256"), "warnings": rec.get("warnings", []),
            "synthetic": bool(rec.get("synthetic"))}
    suf = p.suffix.lower()
    if suf == ".csv":
        df = pd.read_csv(p).head(200)
        return {**base, "kind": "table", "columns": list(df.columns), "rows": json.loads(df.to_json(orient="records"))}
    if suf == ".json":
        j = json.loads(p.read_text(encoding="utf-8"))
        df = pd.DataFrame(j.get("hourly", {}))
        return {**base, "kind": "table", "columns": list(df.columns), "rows": json.loads(df.to_json(orient="records")),
                "units": j.get("hourly_units")}
    if suf in (".tif", ".tiff"):
        return {**base, "kind": "raster", "quicklook_url": f"/api/datasets/{slot_id}/quicklook.png", "stats": rec.get("stats"),
                "bounds": rec.get("full_granule_bounds"), "units": rec.get("units")}
    if suf == ".pdf":
        import pymupdf
        n = pymupdf.open(p).page_count
        return {**base, "kind": "document", "pages": n, "thumbnails": [f"/api/datasets/{slot_id}/page/{i}.png" for i in range(1, n + 1)]}
    if suf in (".jpg", ".jpeg", ".png"):
        return {**base, "kind": "image", "url": f"/api/images/{slot_id}/file", "bounds": rec.get("bounds")}
    return {**base, "kind": "file"}


@app.get("/api/datasets/{slot_id}/quicklook.png")
def dataset_quicklook(slot_id: str):
    try:
        rec = slot(slot_id)
    except DataGap as e:
        raise HTTPException(404, str(e))
    return Response(_raster_quicklook(rec["path"]), media_type="image/png")


@app.get("/api/datasets/{slot_id}/page/{n}.png")
def dataset_page(slot_id: str, n: int, dpi: int = 50):
    import pymupdf
    try:
        rec = slot(slot_id)
    except DataGap as e:
        raise HTTPException(404, str(e))
    doc = pymupdf.open(rec["path"])
    if not 1 <= n <= doc.page_count:
        raise HTTPException(404, "no such page")
    return Response(doc[n - 1].get_pixmap(dpi=min(dpi, 150)).tobytes("png"), media_type="image/png")


# ====================================================================== evidence
def _ledger(run_id: str) -> list[dict]:
    st = get_state(run_id)
    if st is not None:
        return st.public_ledger()
    p = RUNS_DIR / run_id / "ledger.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    raise HTTPException(404, "unknown run")


@app.get("/api/runs/{run_id}/evidence")
def evidence(run_id: str) -> dict:
    led = _ledger(run_id)
    st = get_state(run_id)
    return {"run_id": run_id, "ledger": led,
            "omni_calls": (st.omni_calls if st and st.omni_calls else [r for r in led if r.get("type") == "ai_analysis"]),
            "tool_calls": st.tool_calls if st else []}


@app.get("/api/runs/{run_id}/evidence.zip")
def evidence_zip(run_id: str):
    led = _ledger(run_id)
    d = RUNS_DIR / run_id
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("ledger.json", json.dumps(led, indent=1, default=str))
        st = get_state(run_id)
        verdict = st.verdict if st else (json.loads((d / "verdict.json").read_text(encoding="utf-8")) if (d / "verdict.json").exists() else None)
        if verdict:
            z.writestr("verdict.json", json.dumps(verdict, indent=1, default=str))
        ev = d / "evidence"
        if ev.exists():
            for f in ev.iterdir():
                z.write(f, f"evidence/{f.name}")
        z.writestr("manifest.yaml", (DATA / "manifest.yaml").read_text(encoding="utf-8"))
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="savethenorth_evidence_{run_id}.zip"'})


@app.get("/api/runs/{run_id}/evidence/{file}")
def evidence_file(run_id: str, file: str):
    p = (RUNS_DIR / run_id / "evidence" / file).resolve()
    if not str(p).startswith(str((RUNS_DIR / run_id / "evidence").resolve())) or not p.exists():
        raise HTTPException(404, "no such evidence file")
    return FileResponse(p, filename=file if p.suffix in (".csv", ".tif") else None)


@app.get("/api/runs/{run_id}/report.html", response_class=HTMLResponse)
def report_html(run_id: str):
    st = get_state(run_id)
    d = RUNS_DIR / run_id
    v = st.verdict if st else (json.loads((d / "verdict.json").read_text(encoding="utf-8")) if (d / "verdict.json").exists() else None)
    if not v:
        raise HTTPException(404, "no verdict yet")
    e = html.escape
    me = v.get("methane_estimate") or {}
    rows = "".join(f"<tr><td>{e(r['rule_id'])}</td><td>{e(r.get('rule', ''))}</td><td>{e(r.get('threshold', ''))}</td>"
                   f"<td>{e(r.get('observed', ''))}</td><td><b>{e(r['status'])}</b></td><td>{e(r.get('note', ''))}</td></tr>"
                   for r in v.get("regulatory_findings", []))
    li = lambda xs: "".join(f"<li>{e(str(x))}</li>" for x in xs)  # noqa: E731
    charts = "".join(f'<figure><img src="/api/charts/{e(c)}.png" style="max-width:100%"><figcaption>{e(c)}</figcaption></figure>'
                     for c in v.get("charts", []))
    ann = v.get("annual_scenarios_t_ch4") or {}
    body = f"""<!doctype html><html><head><meta charset="utf-8"><title>Save the North report — {e(v['facility_name'])}</title>
<style>body{{font-family:system-ui,Segoe UI,sans-serif;max-width:900px;margin:2em auto;color:#111;line-height:1.45}}
table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{border:1px solid #ccc;padding:6px;vertical-align:top}}
h1{{font-size:22px}}h2{{font-size:16px;margin-top:1.6em;border-bottom:1px solid #ddd}}.disc{{background:#fff7e0;padding:10px;border-left:4px solid #e0a000}}
@media print{{figure{{page-break-inside:avoid}}}}</style></head><body>
<p style="color:#666">Save the North — Satellite Emissions Verification · run {e(run_id)}</p>
<h1>{e(v['facility_name'])} — {e(v['event_date_utc'])}</h1><p><b>{e(v['headline'])}</b></p>
<p class="disc">{e(v.get('disclaimer', ''))}</p>
<h2>Methane estimate</h2><p>Median {me.get('median_kg_h') or 0:,.0f} kg/h (p5–p95 {me.get('p5_kg_h') or 0:,.0f}–{me.get('p95_kg_h') or 0:,.0f} kg/h). Method: {e(me.get('method', ''))}.</p>
<ul>{li(me.get('key_assumptions', []))}</ul>
<h2>Cross-check</h2><p>{e(json.dumps(v.get('cross_check'), ensure_ascii=False))}</p>
<h2>Attribution ({e(v['attribution']['confidence'])} confidence)</h2><p>{e(v['attribution']['conclusion'])}</p><ul>{li(v['attribution'].get('evidence', []))}</ul>
<h2>Likely cause ({e(v['likely_cause']['confidence'])} confidence)</h2><p>{e(v['likely_cause']['conclusion'])}</p><ul>{li(v['likely_cause'].get('evidence', []))}</ul>
<h2>Annualized scenarios (t CH₄/yr)</h2><p>Low {ann.get('low')} · Central {ann.get('central')} · High {ann.get('high')}</p><p><i>{e(ann.get('caveat', ''))}</i></p>
<h2>Regulatory screening</h2><table><tr><th>Rule</th><th>Citation</th><th>Threshold</th><th>Observed</th><th>Status</th><th>Note</th></tr>{rows}</table>
<h2>Data gaps</h2><ul>{li(v.get('data_gaps', []))}</ul><h2>Conflicts</h2><ul>{li(v.get('conflicts', []))}</ul>
<h2>Recommended actions</h2><ol>{li(v.get('recommended_actions', []))}</ol>
<h2>Charts</h2>{charts}
<h2>Data sources</h2><ul>{li([f"{d['source_name']} — {d['citation']} (sha256 {str(d.get('sha256'))[:16]}…)" for d in datasets() if d.get('status') == 'present'])}</ul>
</body></html>"""
    return HTMLResponse(body)


# ====================================================================== static frontend (production build)
_DIST = ROOT / "frontend" / "dist"
if _DIST.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")
    if (_DIST / "textures").exists():
        app.mount("/textures", StaticFiles(directory=_DIST / "textures"), name="textures")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = _DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(_DIST / "index.html")

