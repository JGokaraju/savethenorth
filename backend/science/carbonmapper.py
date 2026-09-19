"""Carbon Mapper plume table loading, §6.8 comparison and §6.9 annualization."""
from __future__ import annotations

import pandas as pd

from backend.science.common import DataGap, slot
from backend.settings import cfg

ALIASES = {
    "plume_id": ["plume_id", "id", "plume"],
    "datetime_utc": ["datetime_utc", "datetime", "date_time", "scene_timestamp", "date"],
    "emission_rate_kg_h": ["emission_rate_kg_h", "emission_auto", "emission_rate", "rate_kg_h", "emission"],
    "emission_uncertainty_kg_h": ["emission_uncertainty_kg_h", "emission_uncertainty_auto", "emission_uncertainty", "uncertainty"],
    "lat": ["lat", "latitude", "plume_latitude"],
    "lon": ["lon", "longitude", "plume_longitude"],
    "instrument": ["instrument", "sensor"],
    "detected": ["detected", "detection"],
}


def load() -> tuple[pd.DataFrame, dict, list[str]]:
    rec = slot("carbonmapper")
    raw = pd.read_csv(rec["path"])
    cols = {c.lower().strip(): c for c in raw.columns}
    df, notes = pd.DataFrame(), []
    for canon, alts in ALIASES.items():
        src = next((cols[a] for a in alts if a in cols), None)
        if src is not None:
            df[canon] = raw[src]
    for c in ("synthetic", "note"):
        if c in cols:
            df[c] = raw[cols[c]]
    if "emission_rate_kg_h" not in df:
        raise DataGap("Carbon Mapper table has no emission-rate column")
    df["emission_rate_kg_h"] = pd.to_numeric(df["emission_rate_kg_h"], errors="coerce")
    if "emission_uncertainty_kg_h" in df:
        df["emission_uncertainty_kg_h"] = pd.to_numeric(df["emission_uncertainty_kg_h"], errors="coerce")
    unit_col = next((cols[c] for c in cols if "unit" in c), None)
    if unit_col is not None and raw[unit_col].astype(str).str.contains("t/h").any():
        m = raw[unit_col].astype(str).str.contains("t/h") & (df["emission_rate_kg_h"] < 100)
        df.loc[m, ["emission_rate_kg_h", "emission_uncertainty_kg_h"]] *= 1000
        notes.append(f"converted {int(m.sum())} rate(s) from t/h to kg/h")
    if "detected" not in df:
        df["detected"] = df["emission_rate_kg_h"].notna()
        notes.append("no `detected` column: rows with a rate treated as detections; non-detects unknown")
    else:
        df["detected"] = df["detected"].astype(str).str.lower().isin(["true", "1", "yes", "y"])
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True, errors="coerce")
    df["synthetic"] = df.get("synthetic", False)
    df["synthetic"] = df["synthetic"].astype(str).str.lower().isin(["true", "1", "yes"])
    return df, rec, notes


def compare(our: dict, date: str, plume_id: str | None = None) -> dict:
    df, rec, notes = load()
    det = df[df["detected"] & df["emission_rate_kg_h"].notna()]
    match = det[det["plume_id"].astype(str) == plume_id] if plume_id and "plume_id" in det else det.iloc[0:0]
    how = "plume_id"
    if match.empty:
        match = det[det["datetime_utc"].dt.strftime("%Y-%m-%d") == date]
        how = "date"
    if match.empty:
        raise DataGap(f"no Carbon Mapper detection for {date}")
    r = match.iloc[0]
    theirs = float(r["emission_rate_kg_h"])
    unc = float(r.get("emission_uncertainty_kg_h")) if pd.notna(r.get("emission_uncertainty_kg_h")) else None
    ratio = our["median_kg_h"] / theirs
    their_lo, their_hi = (theirs - 1.645 * unc, theirs + 1.645 * unc) if unc else (theirs, theirs)
    overlap = our["p5_kg_h"] <= their_hi and their_lo <= our["p95_kg_h"]
    conflict = ratio > cfg("comparison", "conflict_ratio_hi") or ratio < cfg("comparison", "conflict_ratio_lo")
    return {"matched_by": how, "plume_id": str(r.get("plume_id")), "instrument": str(r.get("instrument")),
            "their_kg_h": theirs, "their_uncertainty_kg_h": unc, "their_p5_p95_kg_h": [their_lo, their_hi],
            "our_median_kg_h": our["median_kg_h"], "our_p5_p95_kg_h": [our["p5_kg_h"], our["p95_kg_h"]],
            "ratio": ratio, "intervals_overlap": bool(overlap), "conflict": bool(conflict),
            "consistent": bool(overlap and not conflict), "synthetic": bool(r["synthetic"]),
            "notes": notes + (["Carbon Mapper value is a SYNTHETIC placeholder, not a real record"] if r["synthetic"] else []),
            "independence_note": "Same EMIT radiances, independent retrieval/quantification pipeline — not a fully "
                                 "independent measurement.", "_row": match, "_all": df, "_file": rec}


def annualize(our_rate_kg_h: float | None, event_date: str) -> dict:
    df, rec, notes = load()
    n_obs = len(df)
    n_det = int(df["detected"].sum())
    has_nondetects = (~df["detected"]).any()
    rates = []
    for _, r in df[df["detected"]].iterrows():
        d = r["datetime_utc"].strftime("%Y-%m-%d") if pd.notna(r["datetime_utc"]) else None
        if d == event_date and our_rate_kg_h is not None:
            rates.append({"date": d, "rate_kg_h": our_rate_kg_h, "source": "this analysis (EMIT IME)"})
        elif pd.notna(r["emission_rate_kg_h"]):
            rates.append({"date": d, "rate_kg_h": float(r["emission_rate_kg_h"]),
                          "source": "Carbon Mapper" + (" (SYNTHETIC)" if r["synthetic"] else "")})
    if not rates:
        raise DataGap("no detected emission rates to annualize")
    vals = sorted(x["rate_kg_h"] for x in rates)
    central_rate = float(pd.Series(vals).median())
    assumptions = []
    if has_nondetects:
        p = n_det / n_obs
        ps = {"low": p, "central": p, "high": p}
        rate = {"low": min(vals), "central": central_rate, "high": max(vals)}
        assumptions.append(f"detection frequency p = {n_det}/{n_obs} observed overpasses = {p:.2f}")
    else:
        sp = cfg("annualization", "scenario_p")
        ps = {"low": sp[0], "central": sp[1], "high": sp[2]}
        rate = {"low": central_rate, "central": central_rate, "high": central_rate}
        p = None
        assumptions.append(f"no non-detect overpasses recorded → detection frequency unknown; scenarios p ∈ {sp}")
    assumptions.append("rate per event: low = min, central = median, high = max of detected rates")
    scen = {k: ps[k] * rate[k] * 8760 / 1000 for k in ("low", "central", "high")}
    synthetic = bool(df["synthetic"].any())
    caveat = (f"Only {n_obs} overpasses ({n_det} detections) — far too few to pin down annual emissions. "
              "Scenarios are illustrative of persistence, not an inventory estimate.")
    if synthetic:
        caveat += " Overpass history includes SYNTHETIC placeholder records."
    return {"detection_frequency": p, "n_overpasses": n_obs, "n_detections": n_det, "rates": rates,
            "scenario_p": ps, "scenario_rate_kg_h": rate, "annual_t_ch4": scen, "assumptions": assumptions + notes,
            "caveat": caveat, "synthetic": synthetic, "_all": df, "_file": rec}
