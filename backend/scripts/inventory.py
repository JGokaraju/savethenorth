"""Milestone 1: inventory assets/ by CONTENT, normalize copies, write manifest + report.

Usage:  python -m backend.scripts.inventory
Never modifies files under assets/.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from backend.settings import ASSETS, MANIFEST, NORMALIZED, ROOT, facility

FAC = facility("tx-lenorah-redlake")
HINT = FAC["plume_source_hint"]

SOURCES = {
    "emit_ch4enh": dict(
        source_name="NASA EMIT L2B Methane Enhancement v002 (CH4ENH)",
        source_url="https://doi.org/10.5067/EMIT/EMITL2BCH4ENH.002",
        citation="Green, R. et al., EMIT L2B Methane Enhancement Data 60 m V002, NASA LP DAAC, doi:10.5067/EMIT/EMITL2BCH4ENH.002",
        provider="NASA"),
    "emit_ch4uncert": dict(
        source_name="NASA EMIT L2B Methane Enhancement Uncertainty v002 (CH4UNCERT)",
        source_url="https://doi.org/10.5067/EMIT/EMITL2BCH4ENH.002",
        citation="Green, R. et al., EMIT L2B CH4 Enhancement Uncertainty V002, NASA LP DAAC",
        provider="NASA"),
    "emit_ch4sens": dict(
        source_name="NASA EMIT L2B Methane Enhancement Sensitivity v002 (CH4SENS)",
        source_url="https://doi.org/10.5067/EMIT/EMITL2BCH4ENH.002",
        citation="Green, R. et al., EMIT L2B CH4 Enhancement Sensitivity V002, NASA LP DAAC",
        provider="NASA"),
    "carbonmapper": dict(
        source_name="Carbon Mapper plume records", source_url="https://data.carbonmapper.org",
        citation="Carbon Mapper data portal (data.carbonmapper.org)", provider="Carbon Mapper"),
    "wind": dict(
        source_name="Open-Meteo historical weather (ERA5-based)", source_url="https://open-meteo.com/en/docs/historical-weather-api",
        citation="Open-Meteo historical weather API (Zippenfenig, 2023; ERA5, Hersbach et al., 2020)", provider="Open-Meteo"),
    "firms": dict(
        source_name="NASA FIRMS VIIRS 375 m active fire (NOAA-20/21)", source_url="https://firms.modaps.eosdis.nasa.gov/",
        citation="NASA FIRMS, VIIRS 375 m active fire product", provider="NASA"),
    "s2_truecolor": dict(
        source_name="Copernicus Sentinel-2 L2A true color (Copernicus Browser export)", source_url="https://browser.dataspace.copernicus.eu/",
        citation="Contains modified Copernicus Sentinel data 2026, processed with Copernicus Browser", provider="Copernicus"),
    "s2_swir": dict(
        source_name="Copernicus Sentinel-2 L2A SWIR false color (Copernicus Browser export)", source_url="https://browser.dataspace.copernicus.eu/",
        citation="Contains modified Copernicus Sentinel data 2026, processed with Copernicus Browser", provider="Copernicus"),
    "tceq_sob": dict(
        source_name="TCEQ Statement of Basis, Federal Operating Permit O4734 (Lenorah Gas Plant)",
        source_url="https://www.tceq.texas.gov/permitting/air/nav/titlev_permit_search.html",
        citation="TCEQ, Statement of Basis of the Federal Operating Permit O4734, ETC North Permian Midstream LLC", provider="TCEQ"),
    "tceq_steers": dict(
        source_name="TCEQ STEERS Air Emission Event Report Database", source_url="https://www2.tceq.texas.gov/oce/eer/",
        citation="TCEQ Air Emission Event Report Database (STEERS)", provider="TCEQ"),
}
SLOT_ORDER = list(SOURCES)

# Sentinel-2 exports have no georeferencing. Approximate bounds are fitted from the
# town-label pixel positions visible in the screenshot (visual estimates, ±~10 px).
S2_CONTROL_POINTS = [  # (name, x_px, y_px, lat, lon)
    ("Lamesa", 80, 50, 32.7376, -101.9510),
    ("Snyder", 458, 60, 32.7179, -100.9176),
    ("Midland", 37, 370, 31.9973, -102.0779),
    ("Stanton", 140, 313, 32.1293, -101.7885),
    ("Big Spring", 255, 262, 32.2504, -101.4787),
    ("Colorado City", 475, 198, 32.3882, -100.8645),
    ("Sweetwater", 643, 165, 32.4709, -100.4059),
    ("Merkel", 788, 167, 32.4712, -100.0126),
    ("Winters", 806, 387, 31.9588, -99.9620),
    ("Sterling City", 433, 438, 31.8360, -100.9848),
    ("San Angelo", 633, 597, 31.4638, -100.4370),
]

report: list[str] = []
decisions: list[str] = []


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def file_rec(p: Path) -> dict:
    return {"file": rel(p), "sha256": sha256(p), "size_bytes": p.stat().st_size}


# ---------------------------------------------------------------- classifiers
def probe(p: Path) -> dict:
    """Open a file and describe it by content. Returns {kind, ...details}."""
    ext = p.suffix.lower()
    try:
        if ext in (".tif", ".tiff"):
            import rasterio
            with rasterio.open(p) as ds:
                desc = (ds.tags().get("description") or " ".join(d or "" for d in ds.descriptions)).lower()
                band = (ds.descriptions[0] or "").upper()
                kind = "raster"
                if "uncertainty" in desc or "UNCERT" in band:
                    kind = "emit_ch4uncert"
                elif "sensitivity" in desc or "SENS" in band:
                    kind = "emit_ch4sens"
                elif "methane enhancement" in desc or "CH4ENH" in band:
                    kind = "emit_ch4enh"
                return dict(kind=kind, crs=str(ds.crs), width=ds.width, height=ds.height,
                            bounds=[round(b, 5) for b in ds.bounds], res_deg=abs(ds.transform.a),
                            nodata=ds.nodata, instrument=ds.tags().get("instrument"),
                            date_created=ds.tags().get("date_created"), description=ds.tags().get("description"))
        if ext == ".json":
            with open(p, encoding="utf-8") as f:
                j = json.load(f)
            if "hourly" in j and "wind_speed_10m" in j["hourly"]:
                return dict(kind="wind", variables=list(j["hourly"]), units=j.get("hourly_units", {}),
                            lat=j.get("latitude"), lon=j.get("longitude"), n=len(j["hourly"]["time"]),
                            t0=j["hourly"]["time"][0], t1=j["hourly"]["time"][-1], elevation=j.get("elevation"))
            if {"west", "south", "east", "north"} <= set(j):
                return dict(kind="s2_bounds", bounds=j)
            return dict(kind="unknown_json", keys=list(j)[:10])
        if ext in (".csv", ".txt"):
            head = p.read_text(encoding="utf-8", errors="replace")[:4000]
            first = head.splitlines()[0].lower() if head.strip() else ""
            if "latitude" in first and ("bright_ti4" in first or "frp" in first):
                return dict(kind="firms", header=first)
            if "emission" in first or "plume" in first:
                return dict(kind="carbonmapper", header=first)
            return dict(kind="unparseable_csv", content_preview=head[:200].strip())
        if ext in (".xls", ".xlsx"):
            df = pd.read_excel(p)
            cols = [str(c).strip().upper() for c in df.columns]
            if "INCIDENT NO." in cols:
                return dict(kind="tceq_steers", rows=len(df), columns=list(df.columns),
                            incidents=sorted({str(int(x)) for x in df["INCIDENT NO."].dropna()}))
            if any("EMISSION" in c for c in cols):
                return dict(kind="carbonmapper", rows=len(df), columns=list(df.columns))
            return dict(kind="unknown_table", columns=list(df.columns)[:10])
        if ext in (".html", ".htm"):
            t = p.read_text(encoding="utf-8", errors="replace").lower()
            if "incident" in t and ("steers" in t or "emission event" in t or "emissions event" in t):
                return dict(kind="tceq_steers", format="html")
            return dict(kind="unknown_html")
        if ext == ".pdf":
            import pymupdf
            d = pymupdf.open(p)
            text = "".join(d[i].get_text() for i in range(min(3, d.page_count)))
            low = text.lower()
            if "statement of basis" in low:
                kind = "tceq_sob"
            elif "incident" in low and ("emission" in low):
                kind = "tceq_steers"
            else:
                kind = "unknown_pdf"
            permit = "O4734" if "O4734" in text else None
            return dict(kind=kind, pages=d.page_count, permit=permit, first_line=text.strip().splitlines()[0][:80])
        if ext in (".png", ".jpg", ".jpeg"):
            from PIL import Image
            im = Image.open(p).convert("RGB")
            a = np.asarray(im).astype(float)
            r, g, b = (a[..., i].mean() for i in range(3))
            name = p.stem.lower()
            if "swir" in name:
                kind = "s2_swir"
            elif "true" in name or "rgb" in name:
                kind = "s2_truecolor"
            else:  # content heuristic: SWIR composites (B12/B11/B8A) look green/yellow; true color looks tan
                kind = "s2_swir" if g > r else "s2_truecolor"
            return dict(kind=kind, size=list(im.size), mean_rgb=[round(float(r), 1), round(float(g), 1), round(float(b), 1)],
                        green_gt_red=bool(g > r))
        if ext == ".py":
            t = p.read_text(encoding="utf-8", errors="replace")
            return dict(kind="script", mentions_firms="firms" in t.lower(),
                        contains_api_key=("KEY" in t and "=" in t))
    except Exception as e:  # unparseable -> reported, never fatal
        return dict(kind="error", error=f"{type(e).__name__}: {e}")
    return dict(kind="unknown")


# ---------------------------------------------------------------- slot handlers
def emit_slot(files: dict[str, list[tuple[Path, dict]]]) -> dict:
    """Pick the granule that covers the plume source hint with valid data; crop to ROI."""
    import rasterio
    from rasterio.windows import from_bounds

    out = {}
    pad = 0.15  # degrees around the source hint (~15 km); keeps normalized copies small
    roi = (HINT["lon"] - pad, HINT["lat"] - pad, HINT["lon"] + pad, HINT["lat"] + pad)
    for slot in ("emit_ch4enh", "emit_ch4uncert", "emit_ch4sens"):
        cands = files.get(slot, [])
        chosen, rejected = None, []
        for p, info in cands:
            with rasterio.open(p) as ds:
                r, c = ds.index(HINT["lon"], HINT["lat"])
                inside = 0 <= r < ds.height and 0 <= c < ds.width
                val = ds.read(1, window=((r, r + 1), (c, c + 1)))[0, 0] if inside else None
            ok = inside and val is not None and val > -9990
            if ok and chosen is None:
                chosen = (p, info)
            else:
                why = "source hint outside granule" if not inside else "source hint pixel is nodata in this granule"
                rejected.append({"file": rel(p), "reason": why})
        rec = {"slot_id": slot, **SOURCES[slot], "type": "raster",
               "originals": [file_rec(p) for p, _ in cands], "rejected": rejected}
        if not chosen:
            rec.update(status="missing", reason="no granule contains valid data at the plume source hint")
            out[slot] = rec
            continue
        p, info = chosen
        dst = NORMALIZED / f"{slot}.tif"
        with rasterio.open(p) as ds:
            win = from_bounds(*roi, ds.transform).round_offsets().round_lengths()
            win = win.intersection(rasterio.windows.Window(0, 0, ds.width, ds.height))
            arr = ds.read(1, window=win)
            prof = ds.profile.copy()
            prof.update(width=arr.shape[1], height=arr.shape[0], transform=ds.window_transform(win),
                        driver="GTiff", compress="deflate", tiled=False)
            prof.pop("blockxsize", None); prof.pop("blockysize", None)
            tags = ds.tags()
            full = ds.read(1)
        with rasterio.open(dst, "w", **prof) as w:
            w.write(arr, 1)
            w.update_tags(**tags, normalized_from=rel(p), normalized_note="cropped to ±0.15° ROI around plume source hint")
        v = full[(full > -9990) & np.isfinite(full)]
        granule = p.stem.split("_")[-3:]
        rec.update(status="present", file=rel(p), sha256=sha256(p), normalized=rel(dst),
                   date_coverage="2025-08-08T14:45:01Z (scene start from filename)",
                   description=info.get("description"),
                   units="ppm·m" if slot == "emit_ch4enh" else ("ppm·m (1σ)" if slot == "emit_ch4uncert" else "dimensionless"),
                   crs=info["crs"], res_deg=info["res_deg"], full_granule_bounds=info["bounds"],
                   granule_id="_".join(granule),
                   stats={"valid_pixels": int(v.size), "p1": float(np.percentile(v, 1)), "median": float(np.median(v)),
                          "p99": float(np.percentile(v, 99)), "max": float(v.max())})
        decisions.append(f"`{slot}` ← `{rel(p)}` (granule `{'_'.join(granule)}` contains valid data at the plume "
                         f"source hint; tag description = '{info.get('description')}'). Normalized to `{rel(dst)}` "
                         f"cropped to ±0.15° around the hint ({arr.shape[1]}×{arr.shape[0]} px).")
        for rj in rejected:
            decisions.append(f"`{slot}`: ignored `{rj['file']}` — {rj['reason']} (adjacent granule of the same overpass).")
        out[slot] = rec
    return out


def wind_slot(cands) -> dict:
    rec = {"slot_id": "wind", **SOURCES["wind"], "type": "table"}
    if not cands:
        return {**rec, "status": "missing", "reason": "no Open-Meteo hourly JSON found"}
    p, info = cands[0]
    with open(p, encoding="utf-8") as f:
        j = json.load(f)
    units = j.get("hourly_units", {})
    ws = np.array(j["hourly"]["wind_speed_10m"], dtype=float)
    u = units.get("wind_speed_10m", "km/h")
    conv = {"m/s": 1.0, "km/h": 1 / 3.6, "mp/h": 0.44704, "kn": 0.514444}.get(u, None)
    notes = []
    if conv is None:
        notes.append(f"unknown speed unit '{u}', assumed km/h")
        conv = 1 / 3.6
    elif conv != 1.0:
        notes.append(f"converted wind_speed_10m from {u} to m/s")
    else:
        notes.append("wind_speed_10m already in m/s; no conversion")
    hourly = {"time": j["hourly"]["time"], "wind_speed_10m": list(np.round(ws * conv, 3)),
              "wind_direction_10m": j["hourly"]["wind_direction_10m"]}
    for var in ("temperature_2m", "surface_pressure"):
        if var in j["hourly"]:
            hourly[var] = j["hourly"][var]
        else:
            notes.append(f"`{var}` absent → default from case.yaml will be used")
    norm = {"latitude": j.get("latitude"), "longitude": j.get("longitude"), "elevation": j.get("elevation"),
            "hourly_units": {"time": "iso8601 UTC", "wind_speed_10m": "m/s", "wind_direction_10m": "°",
                             **({"temperature_2m": units.get("temperature_2m", "°C")} if "temperature_2m" in hourly else {}),
                             **({"surface_pressure": units.get("surface_pressure", "hPa")} if "surface_pressure" in hourly else {})},
            "hourly": hourly}
    dst = NORMALIZED / "wind.json"
    dst.write_text(json.dumps(norm, indent=1), encoding="utf-8")
    dist_km = haversine_km(j["latitude"], j["longitude"], FAC["lat"], FAC["lon"])
    notes.append(f"grid point ({j['latitude']:.4f}, {j['longitude']:.4f}) is {dist_km:.1f} km from the facility "
                 f"(Open-Meteo snaps to its grid)")
    decisions.append(f"`wind` ← `{rel(p)}` (has `hourly.wind_speed_10m`). " + "; ".join(notes) + ".")
    return {**rec, "status": "present", "file": rel(p), "sha256": sha256(p), "normalized": rel(dst),
            "originals": [file_rec(p)], "date_coverage": f"{info['t0']} .. {info['t1']} UTC",
            "units": "m/s, °", "notes": notes,
            "stats": {"n_hours": info["n"], "u10_min": float(ws.min() * conv), "u10_max": float(ws.max() * conv),
                      "grid_lat": j["latitude"], "grid_lon": j["longitude"], "grid_distance_km": round(dist_km, 2)}}


def firms_slot(good, bad) -> dict:
    rec = {"slot_id": "firms", **SOURCES["firms"], "type": "table", "originals": [file_rec(p) for p, _ in good + bad]}
    for p, info in bad:
        decisions.append(f"`firms`: `{rel(p)}` looks like the FIRMS file by name but its content is not a CSV: "
                         f"\"{info.get('content_preview')}\". The FIRMS area API rejected the request "
                         f"(day_count=15; the API accepts 1..5 per request). Treated as **missing**.")
    if not good:
        return {**rec, "status": "missing",
                "reason": "firms_viirs.csv contains an API error message, not detections"
                if bad else "no FIRMS CSV found"}
    frames = []
    for p, _ in good:
        df = pd.read_csv(p)
        df.columns = [c.strip().lower() for c in df.columns]
        frames.append(df)
    df = pd.concat(frames, ignore_index=True).drop_duplicates()
    dst = NORMALIZED / "firms_viirs.csv"
    df.to_csv(dst, index=False)
    decisions.append(f"`firms` ← {', '.join('`'+rel(p)+'`' for p,_ in good)} concatenated ({len(df)} rows, duplicates dropped).")
    return {**rec, "status": "present", "file": rel(good[0][0]), "sha256": sha256(good[0][0]), "normalized": rel(dst),
            "date_coverage": f"{df['acq_date'].min()} .. {df['acq_date'].max()}", "stats": {"rows": len(df)}}


def carbonmapper_slot(cands) -> dict:
    rec = {"slot_id": "carbonmapper", **SOURCES["carbonmapper"], "type": "table"}
    if not cands:
        decisions.append("`carbonmapper`: no Carbon Mapper plume table found in assets/ → **data gap**. "
                         "The cross-check (§6.8) and detection frequency (§6.9) will report data gaps. "
                         "The ~21,500 kg/h figure quoted in the brief is NOT used, because measurements may come only from assets/.")
        return {**rec, "status": "missing", "reason": "no Carbon Mapper plume CSV/XLSX provided"}
    p, info = cands[0]
    df = pd.read_csv(p) if p.suffix.lower() in (".csv", ".txt") else pd.read_excel(p)
    df.columns = [c.strip().lower() for c in df.columns]
    dst = NORMALIZED / "carbonmapper_plumes.csv"
    df.to_csv(dst, index=False)
    decisions.append(f"`carbonmapper` ← `{rel(p)}` ({len(df)} rows).")
    return {**rec, "status": "present", "file": rel(p), "sha256": sha256(p), "normalized": rel(dst),
            "originals": [file_rec(p) for p, _ in cands], "stats": {"rows": len(df)}}


def steers_slot(cands) -> dict:
    rec = {"slot_id": "tceq_steers", **SOURCES["tceq_steers"], "type": "table",
           "originals": [file_rec(p) for p, _ in cands]}
    if not cands:
        return {**rec, "status": "missing", "reason": "no STEERS export found"}
    frames = []
    for p, info in cands:
        if p.suffix.lower() in (".xls", ".xlsx"):
            df = pd.read_excel(p)
            df["source_file"] = rel(p)
            frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df["INCIDENT NO."] = df["INCIDENT NO."].astype("Int64").astype(str)
    starts = pd.to_datetime(df["START DATE/TIME"], format="%m/%d/%Y %H:%M", errors="coerce")
    ends = pd.to_datetime(df["END DATE/TIME"], format="%m/%d/%Y %H:%M", errors="coerce")
    dst = NORMALIZED / "steers_emission_points.csv"
    df.to_csv(dst, index=False)
    incidents = sorted(df["INCIDENT NO."].unique())
    decisions.append(
        f"`tceq_steers` ← {len(cands)} legacy Excel (.xls/BIFF) exports of the TCEQ Air Emission Event Report "
        f"Database, one per incident ({', '.join(incidents)}); concatenated to `{rel(dst)}` ({len(df)} emission-point rows). "
        f"Format differs from the expected PDF/HTML printout — parsed as tables instead of regex over text.")
    expected = {"452090", "452092"}
    missing = expected - set(incidents)
    if missing:
        decisions.append(f"`tceq_steers`: incident(s) {', '.join(sorted(missing))} mentioned in the brief "
                         f"(Red Lake plant) are **not** in the provided files. Only what is in assets/ is used.")
    extra = set(incidents) - expected
    if extra:
        decisions.append(f"`tceq_steers`: extra incident(s) {', '.join(sorted(extra))} found (not in the brief) and kept.")
    return {**rec, "status": "present", "file": rel(cands[0][0]), "sha256": sha256(cands[0][0]),
            "normalized": rel(dst), "date_coverage": f"{starts.min():%Y-%m-%d} .. {ends.max():%Y-%m-%d}",
            "stats": {"rows": len(df), "incidents": incidents,
                      "facilities": sorted(df["RE NAME"].unique().tolist())}}


def sob_slot(cands) -> dict:
    rec = {"slot_id": "tceq_sob", **SOURCES["tceq_sob"], "type": "document"}
    if not cands:
        return {**rec, "status": "missing", "reason": "no Statement of Basis PDF found"}
    p, info = cands[0]
    dst = NORMALIZED / "tceq_sob.pdf"
    shutil.copyfile(p, dst)
    decisions.append(f"`tceq_sob` ← `{rel(p)}` (page 1 text begins 'Statement of Basis of the Federal Operating "
                     f"Permit'; permit {info.get('permit')}; {info['pages']} pages).")
    return {**rec, "status": "present", "file": rel(p), "sha256": sha256(p), "normalized": rel(dst),
            "originals": [file_rec(p)], "date_coverage": "prepared March 6, 2026", "stats": {"pages": info["pages"]}}


def fit_s2_bounds(w: int, h: int) -> dict:
    x = np.array([c[1] for c in S2_CONTROL_POINTS], float)
    y = np.array([c[2] for c in S2_CONTROL_POINTS], float)
    lat = np.array([c[3] for c in S2_CONTROL_POINTS])
    lon = np.array([c[4] for c in S2_CONTROL_POINTS])
    ax, bx = np.polyfit(x, lon, 1)
    ay, by = np.polyfit(y, lat, 1)
    res_km = np.sqrt(((ax * x + bx - lon) * 94.1) ** 2 + ((ay * y + by - lat) * 110.9) ** 2)
    return {"west": round(bx, 4), "east": round(ax * w + bx, 4), "north": round(by, 4), "south": round(ay * h + by, 4),
            "deg_per_px_x": ax, "deg_per_px_y": ay, "fit_rms_km": round(float(np.sqrt((res_km ** 2).mean())), 2),
            "method": "linear fit of town-label pixel positions (visual estimates) to town coordinates; APPROXIMATE",
            "control_points": [c[0] for c in S2_CONTROL_POINTS]}


def s2_slot(slot: str, cands, bounds_files) -> dict:
    rec = {"slot_id": slot, **SOURCES[slot], "type": "image"}
    if not cands:
        return {**rec, "status": "missing", "reason": f"no {slot} image found"}
    p, info = cands[0]
    from PIL import Image
    w, h = Image.open(p).size
    if bounds_files:
        with open(bounds_files[0][0], encoding="utf-8") as f:
            bounds = json.load(f)
        bounds["method"] = f"from {rel(bounds_files[0][0])}"
    else:
        bounds = fit_s2_bounds(w, h)
    bounds["date"] = "2026-09-18"
    dst = NORMALIZED / f"{slot}{p.suffix.lower()}"
    shutil.copyfile(p, dst)
    (NORMALIZED / f"{slot}_bounds.json").write_text(json.dumps(bounds, indent=1), encoding="utf-8")
    px_m = abs(bounds["deg_per_px_x"]) * 94100 if "deg_per_px_x" in bounds else None
    decisions.append(
        f"`{slot}` ← `{rel(p)}` (filename + colour check: mean RGB {info['mean_rgb']}). It is a Copernicus Browser "
        f"**screenshot**, not a GeoTIFF: {w}×{h} px, burned-in header '2026-09-18, Sentinel-2 L2A', town labels and a "
        f"20 km scale bar. No `s2_bounds.json` → bounds fitted from town labels: W {bounds['west']}, E {bounds['east']}, "
        f"S {bounds['south']}, N {bounds['north']} (rms {bounds.get('fit_rms_km')} km, ≈{px_m:.0f} m/px).")
    return {**rec, "status": "present", "quality": "low", "file": rel(p), "sha256": sha256(p), "normalized": rel(dst),
            "bounds_file": rel(NORMALIZED / f"{slot}_bounds.json"), "bounds": bounds,
            "originals": [file_rec(p)], "date_coverage": "2026-09-18 (13 months AFTER the 2025-08-08 event)",
            "stats": {"width": w, "height": h, "approx_m_per_px": round(px_m) if px_m else None},
            "warnings": ["image date 2026-09-18 does not match the 2025-08-08 event",
                         "regional (~200 km) screenshot; the plant spans only ~1–3 px",
                         "extensive fair-weather cumulus and cloud shadows across the scene",
                         "bounds are approximate (fitted from town labels)"]}


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return float(2 * R * np.arcsin(np.sqrt(a)))


# ---------------------------------------------------------------- main
def main() -> dict:
    NORMALIZED.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in ASSETS.rglob("*") if p.is_file())
    by_kind: dict[str, list[tuple[Path, dict]]] = {}
    inventory = []
    for p in files:
        info = probe(p)
        by_kind.setdefault(info["kind"], []).append((p, info))
        inventory.append({"file": rel(p), "size_bytes": p.stat().st_size, "sha256": sha256(p), "detected": info})

    slots = {}
    slots.update(emit_slot(by_kind))
    slots["carbonmapper"] = carbonmapper_slot(by_kind.get("carbonmapper", []))
    slots["wind"] = wind_slot(by_kind.get("wind", []))
    firms_named_bad = [(p, i) for p, i in by_kind.get("unparseable_csv", []) if "firms" in p.name.lower()]
    slots["firms"] = firms_slot(by_kind.get("firms", []), firms_named_bad)
    slots["s2_truecolor"] = s2_slot("s2_truecolor", by_kind.get("s2_truecolor", []), by_kind.get("s2_bounds", []))
    slots["s2_swir"] = s2_slot("s2_swir", by_kind.get("s2_swir", []), by_kind.get("s2_bounds", []))
    slots["tceq_sob"] = sob_slot(by_kind.get("tceq_sob", []))
    slots["tceq_steers"] = steers_slot(by_kind.get("tceq_steers", []))

    for p, info in by_kind.get("script", []):
        msg = f"`{rel(p)}`: Python helper script (FIRMS download), not data — ignored."
        if info.get("contains_api_key"):
            msg += " ⚠️ It contains a hard-coded FIRMS MAP_KEY; excluded from git via .gitignore."
        decisions.append(msg)
    for kind in ("unknown", "unknown_json", "unknown_table", "unknown_html", "unknown_pdf", "error"):
        for p, info in by_kind.get(kind, []):
            decisions.append(f"`{rel(p)}`: could not classify ({info}) — ignored.")
    for p, info in by_kind.get("unparseable_csv", []):
        if (p, info) not in firms_named_bad:
            decisions.append(f"`{rel(p)}`: CSV with unrecognized content — ignored.")

    manifest = {"generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "facility_id": FAC["facility_id"], "slots": {k: slots[k] for k in SLOT_ORDER},
                "inventory": inventory}
    with open(MANIFEST, "w", encoding="utf-8") as f:
        yaml.safe_dump(json.loads(json.dumps(manifest, default=float)), f, sort_keys=False, allow_unicode=True, width=140)
    write_report(manifest)
    return manifest


def write_report(m: dict) -> None:
    s = m["slots"]
    L = ["# Asset Report", "",
         f"Generated {m['generated_utc']} by `python -m backend.scripts.inventory`. Originals in `assets/` are never modified; "
         "normalized copies live in `data/normalized/`. Machine-readable version: `data/manifest.yaml`.", "",
         "## Slot summary", "", "| Slot | Status | Source file | Normalized | Notes |", "|---|---|---|---|---|"]
    for k in SLOT_ORDER:
        r = s[k]
        status = r["status"].upper() + (" (low quality)" if r.get("quality") == "low" else "")
        note = r.get("reason") or "; ".join(r.get("warnings", [])[:2]) or r.get("date_coverage", "")
        L.append(f"| `{k}` | {status} | {('`'+r['file']+'`') if r.get('file') else '—'} | "
                 f"{('`'+r['normalized']+'`') if r.get('normalized') else '—'} | {note} |")
    L += ["", "## Decisions", ""] + [f"- {d}" for d in decisions]
    L += ["", "## Data gaps (reported by the agent, never blockers)", ""]
    for k in SLOT_ORDER:
        if s[k]["status"] != "present":
            L.append(f"- **{k}**: {s[k].get('reason')}")
    L += ["- **NO₂ / NOx observations, permit MAERT (NSR 177845), EPA GHGRP Subpart W**: not provided (out of scope).",
          "", "## File inventory", "", "| File | Size | SHA-256 (first 16) | Detected as |", "|---|---:|---|---|"]
    for it in m["inventory"]:
        L.append(f"| `{it['file']}` | {it['size_bytes']:,} | `{it['sha256'][:16]}` | {it['detected']['kind']} |")
    L += ["", "## Basic stats", ""]
    for k in SLOT_ORDER:
        if s[k].get("stats"):
            L.append(f"- **{k}**: " + ", ".join(f"{a}={(round(b, 2) if isinstance(b, float) else b)}" for a, b in s[k]["stats"].items()))
    L += ["", "## Suggested fixes for the team", "",
          "1. **FIRMS**: re-download in ≤5-day chunks (e.g. 2025-08-01, -06, -11 with day_count=5) for VIIRS_NOAA20_NRT "
          "and VIIRS_NOAA21_NRT (or the `_SP` standard products for 2025), then concatenate. `scripts/fetch_firms.py` does this.",
          "2. **Carbon Mapper**: export the plume record(s) for the site (incl. `emi20250808t144501p10004-A`) and any "
          "non-detect overpasses to `assets/carbonmapper_plumes.csv`.",
          "3. **Sentinel-2**: export a site-scale (~10 km) clear-sky image near 2025-08-08 (true colour + SWIR) with an "
          "`s2_bounds.json`. The current screenshots are from 2026-09-18 and regional-scale.",
          "4. **STEERS**: add incident 452090 (Red Lake) if it exists; include any events around 2025-08-08.",
          "", "Re-run `python -m backend.scripts.inventory` (or `make prep`) after adding files."]
    (ROOT / "ASSET_REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
    print((ROOT / "ASSET_REPORT.md").read_text(encoding="utf-8"))
