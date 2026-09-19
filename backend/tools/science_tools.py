"""Science tools: deterministic computation + charts + evidence subsets. GPT never does the arithmetic."""
from __future__ import annotations

import numpy as np
import pandas as pd

from backend.charts import builders
from backend.science import carbonmapper, emit, flare, ime, mask, physics, regulations, steers, wind
from backend.science.common import DataGap, finite, slot
from backend.settings import cfg
from backend.tools.envelope import data_used, gap, ok
from backend.tools.state import RunState


def _require_case(st: RunState, facility_id: str, date: str | None = None) -> dict:
    f = st.facility if facility_id == st.facility_id else None
    from backend.settings import facility as get_fac
    f = f or get_fac(facility_id)
    if not f:
        raise DataGap(f"unknown facility '{facility_id}'")
    if f.get("data_status") != "cached":
        raise DataGap(f"no cached observations for this facility ({f['name']})")
    if date and date != cfg("case", "event_date_utc"):
        raise DataGap(f"no cached satellite observations for {date} (cached event: {cfg('case', 'event_date_utc')})")
    return f


# ------------------------------------------------------------------ EMIT helpers (cached per run)
def _emit(st: RunState, f: dict):
    if "crop" not in st.cache:
        src = f.get("plume_source_hint") or {"lat": f["lat"], "lon": f["lon"]}
        crop = emit.load_crop(src["lat"], src["lon"])
        bg = mask.background(crop)
        masks = mask.all_masks(crop, bg)
        if not masks:
            raise DataGap(f"no plume attributable within {cfg('mask', 'attribution_radius_km')} km at any k")
        st.cache.update(crop=crop, bg=bg, masks=masks)
    return st.cache["crop"], st.cache["bg"], st.cache["masks"]


def _wind(st: RunState, when: str | None = None):
    key = f"wind:{when or 'overpass'}"
    if key not in st.cache:
        st.cache[key] = wind.at(when)
    return st.cache[key]


def _write_emit_evidence(st: RunState, crop, bg, m) -> tuple[str, list[str]]:
    import rasterio
    from PIL import Image
    ed = st.evidence_dir
    prof = dict(driver="GTiff", height=crop.enh.shape[0], width=crop.enh.shape[1], count=1, dtype="float32",
                crs=crop.crs, transform=crop.transform, nodata=-9999.0, compress="deflate")
    with rasterio.open(ed / "emit_crop.tif", "w", **prof) as w:
        w.write(np.nan_to_num(crop.enh, nan=-9999.0).astype("float32"), 1)
    z = np.nan_to_num(crop.enh, nan=0.0)
    v = np.clip(z / max(np.nanpercentile(crop.enh, 99.5), 1), 0, 1)
    rgb = np.stack([v * 230, v * 240, 60 + v * 195], -1).astype("uint8")
    rgb[m.mask] = [217, 89, 38]
    Image.fromarray(rgb).resize((rgb.shape[1] * 3, rgb.shape[0] * 3), Image.NEAREST).save(ed / "emit_quicklook.png")
    rr, cc = np.nonzero(m.mask)
    unc = crop.uncert[rr, cc] if crop.uncert is not None else np.full(rr.size, np.nan)
    df = pd.DataFrame({"lon": crop.lon[cc].round(6), "lat": crop.lat[rr].round(6), "enh_ppm_m": crop.enh[rr, cc].round(1),
                       "enh_minus_bg_ppm_m": (crop.enh[rr, cc] - bg.mu).round(1), "uncert_ppm_m": np.round(unc, 1),
                       "dist_km": crop.dist_km[rr, cc].round(3)})
    df.sort_values("enh_ppm_m", ascending=False).to_csv(ed / "emit_plume_pixels.csv", index=False)
    return st.evidence_ref("emit_plume_pixels.csv"), [st.evidence_ref("emit_quicklook.png"), st.evidence_ref("emit_crop.tif")]


# ------------------------------------------------------------------ tools
def plume_map(st: RunState, facility_id: str, date: str | None = None) -> dict:
    f = _require_case(st, facility_id, date)
    crop, bg, masks = _emit(st, f)
    k0 = cfg("mask", "k_default")
    if k0 not in masks:
        k0 = sorted(masks)[len(masks) // 2]
    warnings = []
    try:
        w = _wind(st)
    except DataGap as e:
        raise DataGap(f"wind needed for per-k rates on the map: {e}")
    det = {k: ime.deterministic(crop, bg, m, w.u10, w.n_air_mol_m3) for k, m in masks.items()}
    art = builders.plume_map(crop, bg, masks, det, f, w, k0)
    st.charts[art.chart_id] = art.to_dict(include_figure=False)
    st.cache["plume_chart"] = art
    m = masks[k0]
    preview, extra = _write_emit_evidence(st, crop, bg, m)
    used = [data_used(crop.files["emit_ch4enh"], f"±{cfg('emit', 'crop_half_width_km')} km crop around plume source "
                      f"hint; {m.n_pixels} mask pixels of {crop.n_valid:,} valid in crop (k={k0})",
                      m.n_pixels, preview, extra)]
    if "emit_ch4uncert" in crop.files:
        used.append(data_used(crop.files["emit_ch4uncert"], "same crop; per-pixel 1σ used for Monte Carlo noise",
                              m.n_pixels, preview))
    ev = ["emit_ch4enh"] + (["emit_ch4uncert"] if "emit_ch4uncert" in crop.files else [])
    for key in ("crop_half_width_km",):
        ev.append(st.add_assumption("emit", key, "plume_map"))
    for key in ("bg_annulus_inner_km", "bg_annulus_outer_km", "k_default", "attribution_radius_km", "bg_exclude_plume"):
        ev.append(st.add_assumption("mask", key, "plume_map"))
    ext = art.summary_stats["plume_extent_north_km"]
    if ext >= cfg("emit", "crop_half_width_km") * 0.95:
        warnings.append(f"plume reaches the crop edge ({ext} km) — IME may be truncated")
    data = {"k_default": k0, "n_pixels": m.n_pixels, "area_m2": round(m.area_m2), "length_m": round(m.length_m),
            "max_enh_ppm_m": round(m.max_enh), "max_location": {"lat": m.max_lat, "lon": m.max_lon},
            "background_mu_ppm_m": round(bg.mu, 1), "background_sigma_ppm_m": round(bg.sigma, 1),
            "background_pixels": bg.n_pixels, "background_excluded_plume_pixels": bg.excluded_plume_pixels,
            "pixel_area_m2": round(crop.pixel_area_m2), "valid_pixels_in_crop": crop.n_valid,
            "plume_extent_downwind_km": ext, "wind_from_deg": round(w.direction_deg),
            "components_attributed": m.n_components,
            "mask_by_k": {str(k): {"n_pixels": mm.n_pixels, "q_kg_h": round(det[k].q_kg_h)} for k, mm in masks.items()}}
    s = (f"Plume of {m.n_pixels} pixels ({m.area_m2 / 1e6:.2f} km²) attributed within 1 km of the source; peak "
         f"{m.max_enh:,.0f} ppm·m, extends ~{ext} km downwind (wind from {w.direction_deg:.0f}°).")
    return ok(s, data, ["plume_map"], ev, crop.assumptions, warnings, used)


def get_wind(st: RunState, facility_id: str, datetime_utc: str | None = None) -> dict:
    _require_case(st, facility_id)
    w = _wind(st, datetime_utc)
    art = builders.wind_timeseries(w.hourly, w)
    st.charts[art.chart_id] = art.to_dict(include_figure=False)
    t = pd.Timestamp(w.time_utc)
    near = w.hourly[(w.hourly["time"] >= t - pd.Timedelta(hours=3)) & (w.hourly["time"] <= t + pd.Timedelta(hours=3))].copy()
    near["time"] = near["time"].dt.strftime("%Y-%m-%dT%H:%MZ")
    near = pd.concat([near, pd.DataFrame([{"time": w.time_utc + " (interpolated overpass)", "wind_speed_10m": round(w.u10, 3),
                                           "wind_direction_10m": round(w.direction_deg, 1)}])], ignore_index=True)
    near.to_csv(st.evidence_dir / "wind_hourly_near_overpass.csv", index=False)
    used = [data_used(w.file, f"hourly rows ±3 h around {w.time_utc} + interpolated overpass row", len(near),
                      st.evidence_ref("wind_hourly_near_overpass.csv"))]
    ev = ["wind"]
    for key in ("sigma_u_floor", "sigma_u_frac", "sigma_u_window_h"):
        ev.append(st.add_assumption("wind", key, "get_wind"))
    for a in w.assumptions:
        key = "default_pressure_pa" if "pressure" in a else "default_temperature_k"
        ev.append(st.add_assumption("physics_constants", key, "get_wind"))
    data = {"time_utc": w.time_utc, "u10_m_s": round(w.u10, 3), "direction_from_deg": round(w.direction_deg, 1),
            "sigma_u_m_s": round(w.sigma_u, 3), "pressure_pa": round(w.pressure_pa), "temperature_k": round(w.temperature_k, 2),
            "n_air_mol_m3": round(w.n_air_mol_m3, 3), "grid_point": [w.grid_lat, w.grid_lon]}
    s = (f"U10 at {w.time_utc} ≈ {w.u10:.2f} m/s from {w.direction_deg:.0f}° (σ_U {w.sigma_u:.2f} m/s); "
         f"air column density {w.n_air_mol_m3:.1f} mol/m³.")
    return ok(s, data, ["wind_timeseries"], ev, w.assumptions,
              ["reanalysis grid point is ~5 km from the site; local winds may differ"], used)


def compute_emission_rate(st: RunState, facility_id: str, date: str | None = None, k: float | None = None) -> dict:
    f = _require_case(st, facility_id, date)
    crop, bg, masks = _emit(st, f)
    w = _wind(st)
    k = float(k) if k is not None else cfg("mask", "k_default")
    if k not in masks:
        k = min(masks, key=lambda x: abs(x - k))
    det = ime.deterministic(crop, bg, masks[k], w.u10, w.n_air_mol_m3)
    mc = ime.monte_carlo(crop, bg, masks, w.u10, w.sigma_u, w.n_air_mol_m3)
    curve = ime.sensitivity_curve(det.ime_kg, det.length_m)
    st.cache["mc"] = mc
    cm_rows = []
    try:
        c = carbonmapper.compare(mc, st.date, cfg("case", "known_plume_id"))
        cm_rows = [{"their_kg_h": c["their_kg_h"], "synthetic": c["synthetic"]}]
    except DataGap:
        pass
    a1 = builders.emission_distribution(mc, cm_rows)
    a2 = builders.wind_sensitivity(curve, w.u10, det.q_kg_h, w.sigma_u)
    for a in (a1, a2):
        st.charts[a.chart_id] = a.to_dict(include_figure=False)
    pd.DataFrame({"q_kg_h": np.round(mc["samples_kg_h"], 1)}).to_csv(st.evidence_dir / "monte_carlo_samples.csv", index=False)
    model = cfg("wind", "ueff_model")
    ev = ["emit_ch4enh", "wind"] + (["emit_ch4uncert"] if crop.uncert is not None else [])
    for key in (("alpha", "beta") if model == "log" else ("linear_a", "linear_b")) + ("ueff_model", "ueff_min"):
        ev.append(st.add_assumption("wind", key, "compute_emission_rate"))
    for key in ("n", "seed", "coef_perturb_frac"):
        ev.append(st.add_assumption("monte_carlo", key, "compute_emission_rate"))
    ev.append(st.add_assumption("physics_constants", "M_CH4", "compute_emission_rate"))
    ev.append(st.add_derived_note("result:monte_carlo", {
        "type": "derived", "name": "Monte Carlo samples", "preview_ref": st.evidence_ref("monte_carlo_samples.csv"),
        "record_count": mc["n"], "source": "computed by compute_emission_rate"}, "compute_emission_rate"))
    result = {
        "median_kg_h": round(mc["median_kg_h"], 1), "p5_kg_h": round(mc["p5_kg_h"], 1), "p25_kg_h": round(mc["p25_kg_h"], 1),
        "p75_kg_h": round(mc["p75_kg_h"], 1), "p95_kg_h": round(mc["p95_kg_h"], 1),
        "median_t_h": round(mc["median_kg_h"] / 1000, 2), "p5_t_h": round(mc["p5_kg_h"] / 1000, 2),
        "p95_t_h": round(mc["p95_kg_h"] / 1000, 2),
        "times_super_emitter_threshold": round(mc["median_kg_h"] / cfg("regulations", "super_emitter_kg_h"), 1),
        "deterministic": {"k": k, "ime_kg": round(det.ime_kg, 1), "length_m": round(det.length_m), "u10_m_s": round(det.u10, 3),
                          "ueff_m_s": round(det.ueff, 3), "q_kg_h": round(det.q_kg_h, 1)},
        "n_air_mol_m3": round(w.n_air_mol_m3, 3), "pixel_area_m2": round(crop.pixel_area_m2),
        "method": "IME (EMIT L2B CH4ENH) + Monte Carlo", "ueff_model": model, "n_draws": mc["n"],
        "key_assumptions": [f"U_eff = {cfg('wind', 'alpha')}·ln(U10) + {cfg('wind', 'beta')} (Varon et al. 2018; verify)"
                            if model == "log" else f"U_eff = {cfg('wind', 'linear_a')}·U10 + {cfg('wind', 'linear_b')}",
                            f"P = {w.pressure_pa:.0f} Pa, T = {w.temperature_k:.0f} K",
                            f"background {bg.mu:.0f} ± {bg.sigma:.0f} ppm·m (annulus 2.5–4 km, plume excluded)",
                            f"U10 = {w.u10:.2f} ± {w.sigma_u:.2f} m/s (ERA5 via Open-Meteo)"]}
    st.results["emission"] = result
    s = (f"Estimated methane emission {mc['median_kg_h'] / 1000:.1f} t/h (p5–p95 {mc['p5_kg_h'] / 1000:.1f}–{mc['p95_kg_h'] / 1000:.1f} t/h), "
         f"~{result['times_super_emitter_threshold']:,.0f}× the 100 kg/h super-emitter threshold.")
    if not (st.evidence_dir / "emit_plume_pixels.csv").exists():
        _write_emit_evidence(st, crop, bg, masks[k])
    if not (st.evidence_dir / "wind_hourly_near_overpass.csv").exists():
        w.hourly.assign(time=w.hourly["time"].astype(str)).to_csv(st.evidence_dir / "wind_hourly_near_overpass.csv", index=False)
    used = [data_used(crop.files["emit_ch4enh"], f"plume-mask pixels for k ∈ {sorted(masks)} (IME)",
                      masks[k].n_pixels, st.evidence_ref("emit_plume_pixels.csv")),
            data_used(w.file, f"U10 interpolated to {w.time_utc}", None, st.evidence_ref("wind_hourly_near_overpass.csv"))]
    if crop.uncert is not None:
        used.append(data_used(crop.files["emit_ch4uncert"], "per-pixel 1σ inside mask (Monte Carlo noise)", masks[k].n_pixels))
    return ok(s, result, ["emission_distribution", "wind_sensitivity"], ev, w.assumptions + crop.assumptions,
              ["wind speed dominates the uncertainty"], used)


def compare_estimates(st: RunState, facility_id: str, date: str | None = None) -> dict:
    _require_case(st, facility_id, date)
    em = st.results.get("emission") or compute_emission_rate(st, facility_id, date)["data"]
    c = carbonmapper.compare(em, st.date, cfg("case", "known_plume_id"))
    c["_row"].assign(datetime_utc=c["_row"]["datetime_utc"].astype(str)).to_csv(st.evidence_dir / "carbonmapper_match.csv", index=False)
    c["_all"].assign(datetime_utc=c["_all"]["datetime_utc"].astype(str)).to_csv(st.evidence_dir / "carbonmapper_rows.csv", index=False)
    used = [data_used(c["_file"], f"plume {c['plume_id']} matched by {c['matched_by']}", len(c["_all"]),
                      st.evidence_ref("carbonmapper_rows.csv"), [st.evidence_ref("carbonmapper_match.csv")])]
    ev = ["carbonmapper", "result:monte_carlo", st.add_assumption("comparison", "conflict_ratio_hi", "compare_estimates"),
          st.add_assumption("comparison", "conflict_ratio_lo", "compare_estimates")]
    data = {k: v for k, v in c.items() if not k.startswith("_")}
    data = {**data, "ratio": round(data["ratio"], 3)}
    st.results["comparison"] = data
    warn = list(data["notes"])
    s = (f"Our median {em['median_kg_h']:,.0f} kg/h vs Carbon Mapper{' (SYNTHETIC)' if c['synthetic'] else ''} "
         f"{c['their_kg_h']:,.0f} kg/h: ratio {c['ratio']:.2f}, intervals {'overlap' if c['intervals_overlap'] else 'do not overlap'}"
         f"{' — CONFLICT' if c['conflict'] else ''}.")
    return ok(s, data, [], ev, [], warn, used)


def flare_activity(st: RunState, facility_id: str, start_date: str | None = None, end_date: str | None = None) -> dict:
    f = _require_case(st, facility_id)
    start = start_date or cfg("flare", "window_start")
    end = end_date or cfg("flare", "window_end")
    fa = flare.activity(f["lat"], f["lon"], start, end)
    art = builders.flare_timeline(fa, f, cfg("wind", "overpass_utc"))
    st.charts[art.chart_id] = art.to_dict(include_figure=False)
    cols = [c for c in ("acq_date", "acq_time", "satellite", "product", "latitude", "longitude", "frp", "confidence",
                        "daynight", "dist_km", "hours_from_overpass") if c in fa["_near"]]
    fa["_near"][cols].round(4).to_csv(st.evidence_dir / "firms_subset.csv", index=False)
    used = [data_used(fa["_file"], f"detections within {fa['radius_km']} km of facility, {start}..{end}",
                      fa["n_near_facility"], st.evidence_ref("firms_subset.csv"))]
    ev = ["firms", st.add_assumption("flare", "radius_km", "flare_activity"),
          st.add_assumption("flare", "near_overpass_h", "flare_activity")]
    data = {k: v for k, v in fa.items() if not k.startswith("_")}
    data["frp_total_mw"] = round(data["frp_total_mw"], 2)
    st.results["flare"] = data
    b, a = fa["nearest_before_overpass"], fa["nearest_after_overpass"]
    s = (f"{fa['n_near_facility']} VIIRS detections within {fa['radius_km']} km ({fa['n_night']} night, {fa['n_day']} day); "
         f"nearest to overpass: {b['gap_hours'] if b else 'none'} h before and {a['gap_hours'] if a else 'none'} h after. "
         f"Flare observed within ±{fa['near_overpass_window_h']} h: {fa['flare_observed_near_overpass']}.")
    return ok(s, data, ["flare_timeline"], ev, [], [fa["caveat"]], used)


def physics_bounds(st: RunState, facility_id: str, q_kg_h: float | None = None) -> dict:
    f = _require_case(st, facility_id)
    em = st.results.get("emission")
    if q_kg_h is None:
        if not em:
            em = compute_emission_rate(st, facility_id)["data"]
        q_kg_h = em["median_kg_h"]
    cap = f.get("design_capacity_mmscfd")
    if not cap:
        raise DataGap("facility design capacity unknown")
    ph = physics.bounds(float(q_kg_h), cap)
    ev = [st.add_facility_assumption("design_capacity_mmscfd", "physics_bounds"),
          st.add_assumption("plant", "ch4_fraction", "physics_bounds"),
          st.add_assumption("plant", "ch4_g_per_scf", "physics_bounds"),
          st.add_assumption("plant", "combustion_efficiency", "physics_bounds")]
    if em:
        ev.append("result:monte_carlo")
    data = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in ph.items()}
    data["required_flared_range_t_h"] = [round(x, 1) for x in ph["required_flared_range_t_h"]]
    data["ceiling_range_t_h"] = [round(x, 1) for x in ph["ceiling_range_t_h"]]
    st.results["physics"] = data
    s = (f"Plant CH₄ throughput ceiling ≈ {ph['ceiling_t_h']:.0f} t/h; estimate is {ph['q_fraction_of_ceiling'] * 100:.1f}% of it. "
         f"As flare slip at CE {ph['combustion_efficiency']:.2f} it would need {ph['required_flared_ch4_t_h']:,.0f} t/h flared → "
         f"{ph['classification']}.")
    return ok(s, data, [], ev, [], [], [])


def annualize(st: RunState, facility_id: str) -> dict:
    _require_case(st, facility_id)
    em = st.results.get("emission")
    an = carbonmapper.annualize(em["median_kg_h"] if em else None, st.date)
    art = builders.annual_scenarios(an)
    st.charts[art.chart_id] = art.to_dict(include_figure=False)
    an["_all"].assign(datetime_utc=an["_all"]["datetime_utc"].astype(str)).to_csv(st.evidence_dir / "carbonmapper_rows.csv", index=False)
    used = [data_used(an["_file"], "all overpass rows (detections + non-detects) for detection frequency",
                      an["n_overpasses"], st.evidence_ref("carbonmapper_rows.csv"))]
    ev = ["carbonmapper"] + (["result:monte_carlo"] if em else [])
    if an["detection_frequency"] is None:
        ev.append(st.add_assumption("annualization", "scenario_p", "annualize"))
    data = {k: v for k, v in an.items() if not k.startswith("_")}
    data["annual_t_ch4"] = {k: round(v) for k, v in data["annual_t_ch4"].items()}
    st.results["annual"] = data
    a = data["annual_t_ch4"]
    s = (f"Annualized scenarios: low {a['low']:,} / central {a['central']:,} / high {a['high']:,} t CH₄/yr from "
         f"{an['n_detections']} detections in {an['n_overpasses']} overpasses — illustrative only.")
    return ok(s, data, ["annual_scenarios"], ev, an["assumptions"], [an["caveat"]], used)


def _detections(st: RunState) -> tuple[list[dict], list[dict], dict | None]:
    em = st.results.get("emission")
    dets, nons, rec = [], [], None
    try:
        df, rec, _ = carbonmapper.load()
        for _, r in df.iterrows():
            t = r["datetime_utc"].isoformat() if pd.notna(r["datetime_utc"]) else None
            if not t:
                continue
            syn = " (SYNTHETIC)" if r["synthetic"] else ""
            if r["detected"]:
                is_event = t[:10] == st.date and em
                dets.append({"time": t, "rate_kg_h": em["median_kg_h"] if is_event else float(r["emission_rate_kg_h"]),
                             "label": f"{r.get('plume_id')} ({r.get('instrument')}){syn}",
                             "source": "this analysis (EMIT IME)" if is_event else f"Carbon Mapper{syn}"})
            else:
                nons.append({"time": t, "label": f"{r.get('instrument')} overpass, no plume{syn}"})
    except DataGap:
        if em:
            dets.append({"time": cfg("wind", "overpass_utc"), "rate_kg_h": em["median_kg_h"],
                         "label": "EMIT 2025-08-08", "source": "this analysis (EMIT IME)"})
    return dets, nons, rec


def reporting_timeline(st: RunState, facility_id: str) -> dict:
    _require_case(st, facility_id)
    rec = slot("tceq_steers")
    events = steers.parse()
    dets, nons, cm_rec = _detections(st)
    art = builders.reporting_timeline(dets, nons, events)
    st.charts[art.chart_id] = art.to_dict(include_figure=False)
    pd.DataFrame([{k: e.get(k) for k in ("incident_no", "start_date", "end_date", "duration_h", "facility", "event_type",
                                          "description", "methane_reported", "source")} for e in events]
                 ).to_csv(st.evidence_dir / "steers_events.csv", index=False)
    used = [data_used(rec, f"{len(events)} STEERS incidents parsed ({', '.join(e['incident_no'] for e in events)})",
                      len(events), st.evidence_ref("steers_events.csv"))]
    ev = ["tceq_steers"] + (["carbonmapper"] if cm_rec else []) + (["result:monte_carlo"] if st.results.get("emission") else [])
    st.results["steers"] = events
    st.results["detections"] = dets
    in_window = [e for e in events if "2025-07-01" <= (e["start_date"] or "") <= "2025-09-30"]
    data = {"events": events, "detections": dets, "non_detects": nons, "n_events": len(events),
            "events_near_event_date": in_window,
            "methane_listed_in_any_report": any(e.get("methane_reported") for e in events)}
    s = (f"{len(events)} STEERS emissions events on record ({', '.join(e['incident_no'] + ' ' + e['start_date'][:10] for e in events)}); "
         f"{len(dets)} satellite detection(s), {len(nons)} non-detect overpass(es). None of the reports lists methane explicitly."
         if not data["methane_listed_in_any_report"] else f"{len(events)} STEERS events on record.")
    return ok(s, data, ["reporting_timeline"], ev, [], ["STEERS records provided cover only the incidents exported by the team"], used)


def check_regulations(st: RunState, facility_id: str) -> dict:
    _require_case(st, facility_id)
    mc = st.results.get("emission")
    if mc is None:
        try:
            compute_emission_rate(st, facility_id)
            mc = st.results.get("emission")
        except DataGap:
            mc = None
    events = st.results.get("steers")
    if events is None:
        try:
            events = steers.parse()
        except DataGap:
            events = None
    phys = st.results.get("physics")
    if phys is None and mc:
        try:
            physics_bounds(st, facility_id)
            phys = st.results.get("physics")
        except DataGap:
            pass
    dates = [st.date] if mc else []
    rules = regulations.evaluate(mc, dates, events, phys)
    ev_base = ["result:monte_carlo"] if mc else []
    ev_map = {"US_SUPER_EMITTER": ev_base + [st.add_assumption("regulations", "super_emitter_kg_h", "check_regulations")],
              "TX_EMISSIONS_EVENT_REPORTING": ev_base + ["tceq_steers",
                                                         st.add_assumption("regulations", "rq_lb", "check_regulations"),
                                                         st.add_assumption("regulations", "steers_match_window_days", "check_regulations"),
                                                         st.add_assumption("regulations", "min_event_hours", "check_regulations")],
              "PLANT_PHYSICS_CEILING": ev_base + ["assumption:plant.ch4_fraction", "assumption:facility.design_capacity_mmscfd"],
              "NOX_PERMIT_LIMITS": [], "GHGRP_REPORTED": []}
    for r in rules:
        r["evidence_ids"] = [e for e in ev_map.get(r["rule_id"], []) if e in st.ledger or e == "result:monte_carlo"]
        for k in ("multiple_of_threshold", "lb_in_min_event"):
            if k in r and r[k] is not None:
                r[k] = round(r[k], 1)
    cm = st.results.get("comparison")
    art = builders.regulatory_comparison(st.cache["mc"], cm, phys) if mc and "mc" in st.cache else None
    charts = []
    if art:
        st.charts[art.chart_id] = art.to_dict(include_figure=False)
        charts.append(art.chart_id)
    st.results["regulations"] = rules
    s = "; ".join(f"{r['rule_id']}: {r['status']}" for r in rules)
    ev = sorted({e for r in rules for e in r["evidence_ids"]})
    return ok(s, {"findings": rules}, charts, ev, [], ["Screening results, not enforcement determinations"], [])
