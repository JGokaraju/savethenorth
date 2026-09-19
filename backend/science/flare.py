"""§6.5 Flare activity from NASA FIRMS VIIRS detections."""
from __future__ import annotations

import pandas as pd

from backend.science.common import DataGap, haversine_km, parse_utc, slot
from backend.settings import cfg

CAVEAT = ("FIRMS fire radiative power (FRP) is not calibrated to flared gas volume; treat it qualitatively "
          "(flare burning / not detected). Absence of a detection can also be due to clouds, detection "
          "limits, or overpass timing.")


def load_firms() -> tuple[pd.DataFrame, dict]:
    rec = slot("firms")
    df = pd.read_csv(rec["path"])
    df.columns = [c.strip().lower() for c in df.columns]
    need = {"latitude", "longitude", "acq_date", "acq_time", "frp"}
    if not need <= set(df.columns):
        raise DataGap(f"FIRMS table missing columns {sorted(need - set(df.columns))}")
    t = df["acq_time"].astype(int).astype(str).str.zfill(4)
    df["time_utc"] = pd.to_datetime(df["acq_date"] + " " + t.str[:2] + ":" + t.str[2:], utc=True)
    return df, rec


def activity(lat: float, lon: float, start_date: str, end_date: str, overpass_utc: str | None = None) -> dict:
    df, rec = load_firms()
    radius = cfg("flare", "radius_km")
    df["dist_km"] = haversine_km(lat, lon, df["latitude"].to_numpy(), df["longitude"].to_numpy())
    t0 = pd.Timestamp(start_date, tz="UTC"); t1 = pd.Timestamp(end_date, tz="UTC") + pd.Timedelta(days=1)
    win = df[(df["time_utc"] >= t0) & (df["time_utc"] < t1)].copy()
    near = win[win["dist_km"] <= radius].sort_values("time_utc").reset_index(drop=True)
    ov = pd.Timestamp(parse_utc(overpass_utc or cfg("wind", "overpass_utc")))
    near["hours_from_overpass"] = (near["time_utc"] - ov).dt.total_seconds() / 3600
    before = near[near["hours_from_overpass"] < 0].tail(1)
    after = near[near["hours_from_overpass"] >= 0].head(1)
    h = cfg("flare", "near_overpass_h")
    by_day = (near.assign(day=near["time_utc"].dt.strftime("%Y-%m-%d"))
              .groupby(["day", "daynight"]).size().unstack(fill_value=0) if len(near) else pd.DataFrame())

    def row(r):
        if r.empty:
            return None
        r = r.iloc[0]
        return {"time_utc": r["time_utc"].isoformat().replace("+00:00", "Z"), "satellite": str(r.get("satellite")),
                "frp_mw": float(r["frp"]), "dist_km": round(float(r["dist_km"]), 3),
                "gap_hours": round(float(r["hours_from_overpass"]), 1), "daynight": r.get("daynight")}

    return {
        "radius_km": radius, "window": [start_date, end_date],
        "n_total_in_window": int(len(win)), "n_near_facility": int(len(near)),
        "by_day": {d: {k: int(v) for k, v in r.items()} for d, r in by_day.iterrows()} if len(near) else {},
        "n_day": int((near.get("daynight") == "D").sum()) if len(near) else 0,
        "n_night": int((near.get("daynight") == "N").sum()) if len(near) else 0,
        "frp_total_mw": float(near["frp"].sum()), "frp_max_mw": float(near["frp"].max()) if len(near) else 0.0,
        "nearest_before_overpass": row(before), "nearest_after_overpass": row(after),
        "flare_observed_near_overpass": bool((near["hours_from_overpass"].abs() <= h).any()),
        "near_overpass_window_h": h, "caveat": CAVEAT,
        "_near": near, "_all": win, "_file": rec,
    }
