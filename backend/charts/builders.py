"""The eight interactive chart builders (spec §7). Each returns a ChartArtifact."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from backend.charts.base import (AXIS, CRITICAL, GOOD, GRID, INK, INK2, MUTED, NEUTRAL, S1, S2, S3, SEQ_BLUE,
                                 SURFACE, WARNING, ChartArtifact, save)

THRESHOLD = 100.0  # kg/h, EPA super-emitter (label only; logic lives in science.regulations)


def _vline(fig, x, text, color, row=None, col=None, dash="dash", yref="paper", log_x=False):
    """Vertical line + label. On a log x-axis Plotly positions annotations in log10 units (shapes use data units)."""
    kw = dict(row=row, col=col) if row else {}
    fig.add_vline(x=x, line=dict(color=color, width=2, dash=dash), **kw)
    fig.add_annotation(x=np.log10(x) if log_x else x, y=1.0, yref=yref, text=text, showarrow=False, yanchor="bottom",
                       font=dict(color=INK2, size=11), bgcolor=SURFACE, **({"row": row, "col": col} if row else {}))


def _fmt_kgh(v: float) -> str:
    return f"{v / 1000:,.1f} t/h" if v >= 1000 else f"{v:,.0f} kg/h"


# 1 -------------------------------------------------------------------- plume map
def plume_map(crop, bg, masks: dict, det_by_k: dict, facility: dict, wind, k_default: float) -> ChartArtifact:
    lon, lat = crop.lon, crop.lat
    z = crop.enh
    zmax = float(np.nanpercentile(z, 99.7))
    coslat = np.cos(np.radians(crop.src_lat))
    fig = go.Figure()
    fig.add_trace(go.Heatmap(
        x=lon, y=lat, z=np.round(z, 1), zmin=0, zmax=zmax, colorscale=SEQ_BLUE,
        colorbar=dict(title=dict(text="CH₄ enh.<br>(ppm·m)", font=dict(color=INK2)), tickfont=dict(color=MUTED), len=0.8),
        hovertemplate="lon %{x:.4f}<br>lat %{y:.4f}<br>%{z:.0f} ppm·m<extra></extra>", name="enhancement"))
    ks = sorted(masks)
    for k in ks:
        fig.add_trace(go.Contour(
            x=lon, y=lat, z=masks[k].mask.astype(float), showscale=False, contours=dict(start=0.5, end=0.5, coloring="lines"),
            line=dict(color=S2, width=2), colorscale=[[0, S2], [1, S2]], hoverinfo="skip", name=f"plume mask k={k}",
            visible=(k == k_default), showlegend=False))
    src = facility.get("plume_source_hint", {"lat": facility["lat"], "lon": facility["lon"]})
    fig.add_trace(go.Scatter(x=[facility["lon"]], y=[facility["lat"]], mode="markers+text", text=["Facility"],
                             textposition="bottom center", textfont=dict(color=INK),
                             marker=dict(symbol="square", size=12, color=INK, line=dict(color=SURFACE, width=2)),
                             name="Facility", hovertemplate=f"{facility['name']}<br>%{{y:.4f}}, %{{x:.4f}}<extra></extra>"))
    fig.add_trace(go.Scatter(x=[src["lon"]], y=[src["lat"]], mode="markers", name="Plume source hint",
                             marker=dict(symbol="x", size=12, color=S2, line=dict(color=SURFACE, width=1)),
                             hovertemplate="Plume source hint<br>%{y:.4f}, %{x:.4f}<extra></extra>"))
    # wind arrow: meteorological direction is where wind comes FROM; arrow points downwind
    to = np.radians((wind.direction_deg + 180) % 360)
    L = 0.012
    x0, y0 = lon[0] + 0.25 * (lon[-1] - lon[0]), lat[-1] + 0.2 * (lat[0] - lat[-1])
    fig.add_annotation(x=x0 + L * np.sin(to) / coslat, y=y0 + L * np.cos(to), ax=x0, ay=y0, xref="x", yref="y",
                       axref="x", ayref="y", showarrow=True, arrowhead=3, arrowsize=1.4, arrowwidth=2.5, arrowcolor=INK,
                       text="")
    fig.add_annotation(x=x0, y=y0, text=f"wind {wind.u10:.1f} m/s from {wind.direction_deg:.0f}°", showarrow=False,
                       yshift=-18, font=dict(color=INK, size=12), bgcolor="rgba(255,255,255,0.85)")
    steps = []
    for i, k in enumerate(ks):
        vis = [True] + [kk == k for kk in ks] + [True, True]
        steps.append(dict(method="update", label=f"{k}σ",
                          args=[{"visible": vis},
                                {"title.text": f"EMIT CH₄ enhancement, 2025-08-08 14:45 UTC — mask k={k}: "
                                               f"{masks[k].n_pixels} px, Q≈{_fmt_kgh(det_by_k[k].q_kg_h)}"}]))
    active = ks.index(k_default)
    fig.update_layout(
        title=dict(text=steps[active]["args"][1]["title.text"]),
        sliders=[dict(active=active, steps=steps, currentvalue=dict(prefix="Threshold k = ", font=dict(color=INK2)),
                      pad=dict(t=40), font=dict(color=MUTED), bgcolor=GRID, bordercolor=AXIS)],
        xaxis=dict(title="Longitude (°E)", range=[lon[0], lon[-1]], showgrid=False),
        yaxis=dict(title="Latitude (°N)", range=[lat[-1], lat[0]], showgrid=False, scaleanchor="x", scaleratio=1 / coslat),
        margin=dict(t=90, b=60, l=70, r=20))
    m = masks[k_default]
    stats = {"k_default": k_default, "n_pixels": m.n_pixels, "area_m2": round(m.area_m2), "length_m": round(m.length_m),
             "max_enh_ppm_m": round(m.max_enh), "max_at": [round(m.max_lat, 5), round(m.max_lon, 5)],
             "bg_mu_ppm_m": round(bg.mu, 1), "bg_sigma_ppm_m": round(bg.sigma, 1),
             "wind_from_deg": round(wind.direction_deg), "u10_m_s": round(wind.u10, 2),
             "plume_extent_north_km": round(float(((crop.lat[:, None] - crop.src_lat) * 110.54)[m.mask.any(axis=1)].max()), 2),
             "q_by_k_kg_h": {str(k): round(det_by_k[k].q_kg_h) for k in ks}}
    return save("plume_map", "EMIT methane plume map", fig, stats)


# 2 -------------------------------------------------------------------- emission distribution
def emission_distribution(mc: dict, cm_rows: list[dict]) -> ChartArtifact:
    edges = np.array(mc["hist"]["log10_edges"])
    counts = np.array(mc["hist"]["counts"])
    x = 10 ** ((edges[:-1] + edges[1:]) / 2)
    w = 10 ** edges[1:] - 10 ** edges[:-1]
    fig = go.Figure(go.Bar(x=x, y=counts, width=w * 0.92, marker=dict(color=S1, line=dict(width=0)),
                           name="Monte Carlo draws",
                           hovertemplate="Q ≈ %{x:,.0f} kg/h<br>%{y} draws<extra></extra>"))
    _vline(fig, mc["median_kg_h"], f"median {_fmt_kgh(mc['median_kg_h'])}", INK, dash="solid", log_x=True)
    fig.add_vrect(x0=mc["p5_kg_h"], x1=mc["p95_kg_h"], fillcolor=S1, opacity=0.10, line_width=0)
    fig.add_annotation(x=np.log10(mc["p95_kg_h"]), y=0.88, yref="paper", xref="x", text="p5–p95", showarrow=False,
                       xanchor="left", font=dict(color=MUTED, size=11))
    for r in cm_rows:
        lab = "Carbon Mapper" + (" (SYNTHETIC)" if r.get("synthetic") else "")
        fig.add_vline(x=r["their_kg_h"], line=dict(color=S2, width=2, dash="dot"))
        fig.add_annotation(x=np.log10(r["their_kg_h"]), y=0.78, yref="paper", text=f"{lab} {_fmt_kgh(r['their_kg_h'])}",
                           showarrow=False, xanchor="right", font=dict(color=INK2, size=11), bgcolor=SURFACE)
    _vline(fig, THRESHOLD, "EPA super-emitter threshold (100 kg/h)", CRITICAL, log_x=True)
    fig.update_layout(title="Emission rate uncertainty (Monte Carlo, N = %d)" % mc["n"], bargap=0,
                      xaxis=dict(type="log", title="Emission rate Q (kg/h, log scale)",
                                 range=[1.8, np.log10(max(mc["p95_kg_h"] * 3, 1000))]),
                      yaxis=dict(title="Draws (count)"), showlegend=False)
    stats = {k: round(mc[k]) for k in ("median_kg_h", "p5_kg_h", "p25_kg_h", "p75_kg_h", "p95_kg_h")}
    stats.update(n=mc["n"], times_threshold=round(mc["median_kg_h"] / THRESHOLD, 1),
                 carbon_mapper=[{k: r[k] for k in ("their_kg_h", "synthetic")} for r in cm_rows])
    return save("emission_distribution", "Emission rate distribution", fig, stats)


# 3 -------------------------------------------------------------------- wind sensitivity
def wind_sensitivity(curve: dict, u10_obs: float, q_obs_kg_h: float, sigma_u: float) -> ChartArtifact:
    u = curve["u10"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=u + u[::-1], y=curve["q_hi_kg_h"] + curve["q_lo_kg_h"][::-1], fill="toself",
                             fillcolor="rgba(57,135,229,0.18)", line=dict(width=0), hoverinfo="skip",
                             name="α, β ± 20%"))
    fig.add_trace(go.Scatter(x=u, y=curve["q_kg_h"], mode="lines", line=dict(color=S1, width=2), name="Q(U10), default mask",
                             hovertemplate="U10 %{x:.1f} m/s<br>Q %{y:,.0f} kg/h<extra></extra>"))
    fig.add_vrect(x0=max(u10_obs - sigma_u, u[0]), x1=u10_obs + sigma_u, fillcolor=S2, opacity=0.08, line_width=0)
    fig.add_trace(go.Scatter(x=[u10_obs], y=[q_obs_kg_h], mode="markers+text", text=[f"observed U10 {u10_obs:.1f} m/s"],
                             textposition="top left", textfont=dict(color=INK),
                             marker=dict(size=11, color=S2, line=dict(color=SURFACE, width=2)), name="Observed wind",
                             hovertemplate="U10 %{x:.2f} m/s<br>Q %{y:,.0f} kg/h<extra></extra>"))
    fig.add_hline(y=THRESHOLD, line=dict(color=CRITICAL, dash="dash", width=2))
    fig.add_annotation(x=u[-1], y=np.log10(THRESHOLD), xanchor="right", yanchor="bottom", showarrow=False,  # log axis: log10 units
                       text="EPA super-emitter threshold (100 kg/h)", font=dict(color=INK2, size=11), bgcolor=SURFACE)
    fig.update_layout(title="Sensitivity of the emission rate to wind speed",
                      xaxis=dict(title="10 m wind speed U10 (m/s)"),
                      yaxis=dict(type="log", title="Emission rate Q (kg/h, log scale)",
                                 range=[1.8, np.log10(max(curve["q_hi_kg_h"]) * 1.5)]))
    i_lo = int(np.argmin(np.abs(np.array(u) - 1.0)))
    stats = {"u10_obs": round(u10_obs, 2), "sigma_u": round(sigma_u, 2), "q_at_obs_kg_h": round(q_obs_kg_h),
             "q_at_1ms_kg_h": round(curve["q_kg_h"][i_lo]), "q_at_12ms_kg_h": round(curve["q_kg_h"][-1]),
             "min_q_in_range_exceeds_threshold": bool(min(curve["q_lo_kg_h"]) > THRESHOLD)}
    return save("wind_sensitivity", "Wind-speed sensitivity", fig, stats)


# 4 -------------------------------------------------------------------- wind time series
def wind_timeseries(hourly: pd.DataFrame, wind) -> ChartArtifact:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.6, 0.4])
    t = hourly["time"]
    fig.add_trace(go.Scatter(x=t, y=hourly["wind_speed_10m"], mode="lines+markers", line=dict(color=S1, width=2),
                             marker=dict(size=8, line=dict(color=SURFACE, width=2)), name="U10 (m/s)",
                             hovertemplate="%{x|%H:%M} UTC<br>U10 %{y:.2f} m/s<extra></extra>"), row=1, col=1)
    fig.add_trace(go.Scatter(x=t, y=hourly["wind_direction_10m"], mode="markers", name="Direction (° from)",
                             marker=dict(size=8, color=S3, line=dict(color=SURFACE, width=2)),
                             hovertemplate="%{x|%H:%M} UTC<br>from %{y:.0f}°<extra></extra>"), row=2, col=1)
    ov = pd.Timestamp(wind.time_utc)
    for r in (1, 2):
        fig.add_vline(x=ov, line=dict(color=S2, width=2, dash="dash"), row=r, col=1)
    fig.add_annotation(x=ov, y=1.0, yref="paper", text="EMIT overpass 14:45 UTC", showarrow=False, yanchor="bottom",
                       font=dict(color=INK2, size=11))
    fig.add_trace(go.Scatter(x=[ov], y=[wind.u10], mode="markers", name="Interpolated at overpass",
                             marker=dict(size=12, symbol="diamond", color=S2, line=dict(color=SURFACE, width=2)),
                             hovertemplate="overpass<br>U10 %{y:.2f} m/s<extra></extra>"), row=1, col=1)
    fig.update_yaxes(title_text="U10 (m/s)", rangemode="tozero", row=1, col=1)
    fig.update_yaxes(title_text="Direction (° from)", range=[0, 360], tickvals=[0, 90, 180, 270, 360],
                     ticktext=["N", "E", "S", "W", "N"], row=2, col=1)
    fig.update_xaxes(title_text="Time (UTC), 2025-08-08", row=2, col=1)
    fig.update_layout(title="Hourly 10 m wind at the site (Open-Meteo / ERA5)")
    stats = {"u10_at_overpass": round(wind.u10, 2), "direction_from_deg": round(wind.direction_deg),
             "sigma_u": round(wind.sigma_u, 2), "u10_min": float(hourly["wind_speed_10m"].min()),
             "u10_max": float(hourly["wind_speed_10m"].max())}
    return save("wind_timeseries", "Wind at overpass", fig, stats)


# 5 -------------------------------------------------------------------- flare timeline
def flare_timeline(fa: dict, facility: dict, overpass_utc: str) -> ChartArtifact:
    near, allw = fa["_near"], fa["_all"]
    fig = make_subplots(rows=1, cols=2, column_widths=[0.6, 0.4], horizontal_spacing=0.1,
                        subplot_titles=("(a) FRP of detections ≤ %.1f km, Aug 1–15" % fa["radius_km"],
                                        "(b) All detections in the search box"))
    for dn, name, color in (("N", "Night", S1), ("D", "Day", S2)):
        d = near[near["daynight"] == dn]
        fig.add_trace(go.Scatter(x=d["time_utc"], y=d["frp"], mode="markers", name=f"{name} detection",
                                 marker=dict(size=11, color=color, line=dict(color=SURFACE, width=2)),
                                 customdata=np.stack([d["satellite"].astype(str), d["dist_km"]], axis=1) if len(d) else None,
                                 hovertemplate="%{x|%Y-%m-%d %H:%M} UTC<br>FRP %{y:.2f} MW<br>%{customdata[0]}, "
                                               "%{customdata[1]:.2f} km from facility<extra></extra>"), row=1, col=1)
    ov = pd.Timestamp(overpass_utc)
    fig.add_vline(x=ov, line=dict(color=CRITICAL, dash="dash", width=2), row=1, col=1)
    fig.add_annotation(x=ov, y=1.0, yref="y domain", xref="x", text="EMIT overpass", showarrow=False, yanchor="bottom",
                       font=dict(color=INK2, size=11), row=1, col=1)
    far = allw[allw["dist_km"] > fa["radius_km"]]
    fig.add_trace(go.Scatter(x=far["longitude"], y=far["latitude"], mode="markers", name="Other detections",
                             marker=dict(size=8, color=NEUTRAL, line=dict(color=SURFACE, width=1)),
                             hovertemplate="%{y:.4f}, %{x:.4f}<extra></extra>"), row=1, col=2)
    fig.add_trace(go.Scatter(x=near["longitude"], y=near["latitude"], mode="markers", name="≤ 1.5 km (attributed)",
                             marker=dict(size=10, color=S2, line=dict(color=SURFACE, width=2)),
                             hovertemplate="%{y:.4f}, %{x:.4f}<extra></extra>"), row=1, col=2)
    coslat = np.cos(np.radians(facility["lat"]))
    th = np.linspace(0, 2 * np.pi, 120)
    r = fa["radius_km"]
    fig.add_trace(go.Scatter(x=facility["lon"] + r / (111.32 * coslat) * np.cos(th), y=facility["lat"] + r / 110.54 * np.sin(th),
                             mode="lines", line=dict(color=INK2, width=1.5, dash="dot"), name="1.5 km radius",
                             hoverinfo="skip"), row=1, col=2)
    fig.add_trace(go.Scatter(x=[facility["lon"]], y=[facility["lat"]], mode="markers", name="Facility",
                             marker=dict(symbol="square", size=12, color=INK, line=dict(color=SURFACE, width=2)),
                             hovertemplate="Facility<extra></extra>"), row=1, col=2)
    fig.update_xaxes(title_text="Time (UTC)", row=1, col=1)
    fig.update_yaxes(title_text="Fire radiative power (MW)", rangemode="tozero", row=1, col=1)
    fig.update_xaxes(title_text="Longitude (°E)", row=1, col=2)
    fig.update_yaxes(title_text="Latitude (°N)", scaleanchor="x2", scaleratio=1 / coslat, row=1, col=2)
    fig.update_layout(title="VIIRS active-fire detections near the plant (NASA FIRMS)")
    for a in fig.layout.annotations[:2]:
        a.font = dict(color=INK2, size=12)
    stats = {k: fa[k] for k in ("n_near_facility", "n_day", "n_night", "frp_max_mw", "flare_observed_near_overpass",
                                "nearest_before_overpass", "nearest_after_overpass")}
    stats["frp_total_mw"] = round(fa["frp_total_mw"], 2)
    return save("flare_timeline", "Flare activity timeline", fig, stats)


# 6 -------------------------------------------------------------------- reporting timeline
def reporting_timeline(detections: list[dict], nondetects: list[dict], events: list[dict]) -> ChartArtifact:
    fig = go.Figure()
    lanes = {"Satellite detections": 2, "Non-detect overpasses": 1, "TCEQ STEERS reported events": 0}
    if detections:
        rates = np.array([d["rate_kg_h"] for d in detections])
        fig.add_trace(go.Scatter(
            x=[d["time"] for d in detections], y=[2] * len(detections), mode="markers", name="Satellite detection",
            marker=dict(size=np.clip(10 + 6 * np.log10(rates / 100), 10, 34), color=CRITICAL, line=dict(color=SURFACE, width=2)),
            customdata=[[d["label"], d["rate_kg_h"], d["source"]] for d in detections],
            hovertemplate="%{x|%Y-%m-%d}<br>%{customdata[0]}<br>%{customdata[1]:,.0f} kg/h<br>%{customdata[2]}<extra></extra>"))
    if nondetects:
        fig.add_trace(go.Scatter(x=[d["time"] for d in nondetects], y=[1] * len(nondetects), mode="markers",
                                 name="Non-detect overpass", marker=dict(size=11, color=NEUTRAL, line=dict(color=SURFACE, width=2)),
                                 customdata=[[d["label"]] for d in nondetects],
                                 hovertemplate="%{x|%Y-%m-%d}<br>%{customdata[0]}<extra></extra>"))
    for e in events:
        fig.add_trace(go.Scatter(x=[e["start_date"], e["end_date"] or e["start_date"]], y=[0, 0], mode="lines+markers",
                                 line=dict(color=S1, width=6), marker=dict(size=10, color=S1),
                                 name=f"STEERS {e['incident_no']}", showlegend=False,
                                 hovertemplate=f"Incident {e['incident_no']}<br>{e['event_type']}<br>"
                                               f"{e['start_date']} → {e.get('end_date')}<br>{(e.get('description') or '')[:90]}<extra></extra>"))
        fig.add_annotation(x=e["start_date"], y=0, text=f"#{e['incident_no']}", showarrow=False, yshift=-18,
                           font=dict(color=INK2, size=11))
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="lines", line=dict(color=S1, width=6), name="STEERS reported event"))
    fig.update_layout(title="Satellite detections vs. TCEQ-reported emissions events",
                      yaxis=dict(tickvals=list(lanes.values()), ticktext=list(lanes.keys()), range=[-0.7, 2.7],
                                 showgrid=False, title=""),
                      xaxis=dict(title="Date (UTC)"), margin=dict(l=190))
    stats = {"n_detections": len(detections), "n_nondetects": len(nondetects),
             "steers_incidents": [(e["incident_no"], e["start_date"]) for e in events],
             "detections": [(d["time"][:10], round(d["rate_kg_h"])) for d in detections]}
    return save("reporting_timeline", "Reporting timeline", fig, stats)


# 7 -------------------------------------------------------------------- regulatory comparison
def regulatory_comparison(mc: dict, cm: dict | None, phys: dict | None) -> ChartArtifact:
    rows = [("EPA super-emitter threshold", THRESHOLD, None, None, CRITICAL)]
    rows.append(("This analysis (EMIT IME, median)", mc["median_kg_h"], mc["median_kg_h"] - mc["p5_kg_h"],
                 mc["p95_kg_h"] - mc["median_kg_h"], S1))
    if cm:
        lab = "Carbon Mapper" + (" (SYNTHETIC)" if cm.get("synthetic") else "")
        rows.append((lab, cm["their_kg_h"], None, None, S2))
    if phys:
        rows.append(("Plant CH₄ throughput ceiling", phys["ceiling_t_h"] * 1000, None, None, NEUTRAL))
    fig = go.Figure()
    for name, v, lo, hi, color in rows:
        fig.add_trace(go.Bar(
            y=[name], x=[v], orientation="h", marker=dict(color=color, line=dict(width=0)), name=name, showlegend=False,
            error_x=dict(type="data", symmetric=False, array=[hi], arrayminus=[lo], color=INK, thickness=2, width=8) if lo else None,
            text=[_fmt_kgh(v)], textposition="outside", textfont=dict(color=INK),
            hovertemplate=f"{name}<br>%{{x:,.0f}} kg/h" + (f"<br>p5–p95 {_fmt_kgh(mc['p5_kg_h'])}–{_fmt_kgh(mc['p95_kg_h'])}" if lo else "")
                          + "<extra></extra>"))
    fig.update_layout(title="Estimate vs. regulatory threshold and plant capacity", bargap=0.45,
                      xaxis=dict(type="log", title="Methane rate (kg/h, log scale)", range=[1.5, np.log10(max(r[1] for r in rows) * 6)]),
                      yaxis=dict(autorange="reversed", title=""), margin=dict(l=240))
    stats = {r[0]: round(r[1]) for r in rows}
    stats["times_threshold"] = round(mc["median_kg_h"] / THRESHOLD, 1)
    return save("regulatory_comparison", "Regulatory comparison", fig, stats)


# 8 -------------------------------------------------------------------- annual scenarios
def annual_scenarios(an: dict) -> ChartArtifact:
    names = ["low", "central", "high"]
    vals = [an["annual_t_ch4"][k] for k in names]
    hover = [f"p = {an['scenario_p'][k]:.2f}<br>rate {an['scenario_rate_kg_h'][k]:,.0f} kg/h<br>"
             f"→ {an['annual_t_ch4'][k]:,.0f} t CH₄/yr" for k in names]
    fig = go.Figure(go.Bar(x=[n.title() for n in names], y=vals, marker=dict(color=[S1, S1, S1], line=dict(width=0)),
                           text=[f"{v:,.0f} t" for v in vals], textposition="outside", textfont=dict(color=INK),
                           customdata=hover, hovertemplate="%{customdata}<extra></extra>", width=0.5))
    fig.add_annotation(text=an["caveat"], xref="paper", yref="paper", x=0, y=-0.2, showarrow=False, align="left",
                       font=dict(color=WARNING, size=11), xanchor="left")
    fig.update_layout(title="Annualized emission scenarios (illustrative)",
                      yaxis=dict(title="Methane (t CH₄ / year)", rangemode="tozero", range=[0, max(vals) * 1.2]),
                      xaxis=dict(title="Scenario"), margin=dict(b=110))
    stats = {"annual_t_ch4": {k: round(v) for k, v in an["annual_t_ch4"].items()}, "scenario_p": an["scenario_p"],
             "n_overpasses": an["n_overpasses"], "n_detections": an["n_detections"], "synthetic": an["synthetic"]}
    return save("annual_scenarios", "Annual scenarios", fig, stats)


# 9 -------------------------------------------------------------------- satellite vs technical report
def report_comparison(cmp_: dict) -> ChartArtifact:
    """Methane implied by the satellite vs quantities in the operator's TCEQ emissions-event reports (lb, log)."""
    rows = []
    sat = cmp_.get("satellite")
    if sat:
        rows.append(("Satellite · CH₄, 1 hour", sat["lb_per_hour"], S1))
        rows.append(("Satellite · CH₄, if sustained 24 h", sat["lb_if_24h"], S1))
    for r in cmp_.get("reported_events", []):
        voc = sum(v for k, v in r["lb_by_contaminant"].items() if "voc" in k.lower() or "natural gas" in k.lower())
        if voc > 0:
            rows.append((f"Reported #{r['incident_no']} · VOCs, whole event", voc, S2))
    fig = go.Figure()
    for name, v, c in rows:
        fig.add_trace(go.Bar(y=[name], x=[v], orientation="h", marker=dict(color=c, line=dict(width=0)), showlegend=False,
                             text=[f"{v:,.0f} lb"], textposition="outside", textfont=dict(color=INK),
                             hovertemplate=f"{name}<br>%{{x:,.0f}} lb<extra></extra>"))
    none_txt = ("No emissions-event report filed within ±1 day of " + cmp_["event_date"]) if not cmp_.get("reported_on_event_date") else ""
    if none_txt:
        fig.add_annotation(text=none_txt, xref="paper", yref="paper", x=0, y=-0.22, showarrow=False, xanchor="left",
                           font=dict(color=CRITICAL, size=12))
    vmax = max([r[1] for r in rows] or [10])
    fig.update_layout(title="Satellite observation vs the operator's reported emissions", bargap=0.45,
                      xaxis=dict(type="log", title="Pounds (log scale)", range=[1, np.log10(vmax * 8)]),
                      yaxis=dict(autorange="reversed", title=""), margin=dict(l=230, b=90))
    stats = {"rows": {r[0]: round(r[1]) for r in rows}, "reported_on_event_date": len(cmp_.get("reported_on_event_date", [])),
             "methane_reported_anywhere": cmp_.get("methane_reported_anywhere")}
    return save("report_comparison", "Satellite vs technical report", fig, stats)
