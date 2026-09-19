"""Wind at the overpass: U10 (m/s), direction, σ_U, P and T from the Open-Meteo hourly file."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from backend.science.common import parse_utc, slot
from backend.settings import cfg


@dataclass
class WindAtOverpass:
    time_utc: str
    u10: float
    direction_deg: float           # meteorological: direction wind blows FROM
    sigma_u: float
    pressure_pa: float
    temperature_k: float
    n_air_mol_m3: float
    hourly: pd.DataFrame
    assumptions: list[str] = field(default_factory=list)
    grid_lat: float | None = None
    grid_lon: float | None = None
    file: dict | None = None


def load_hourly() -> tuple[pd.DataFrame, dict, dict]:
    rec = slot("wind")
    with open(rec["path"], encoding="utf-8") as f:
        j = json.load(f)
    h = j["hourly"]
    df = pd.DataFrame(h)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df, j, rec


def _interp_linear(t: pd.Timestamp, times: pd.Series, vals) -> float:
    x = (times - times.iloc[0]).dt.total_seconds().to_numpy()
    return float(np.interp((t - times.iloc[0]).total_seconds(), x, np.asarray(vals, float)))


def at(datetime_utc: str | None = None) -> WindAtOverpass:
    t = pd.Timestamp(parse_utc(datetime_utc or cfg("wind", "overpass_utc")))
    df, j, rec = load_hourly()
    if not (df["time"].min() <= t <= df["time"].max()):
        from backend.science.common import DataGap
        raise DataGap(f"wind file covers {df['time'].min()}..{df['time'].max()}, not {t}")
    u10 = _interp_linear(t, df["time"], df["wind_speed_10m"])
    # interpolate direction via vector components (handles the 360° wrap)
    rad = np.radians(df["wind_direction_10m"].astype(float))
    s = _interp_linear(t, df["time"], np.sin(rad)); c = _interp_linear(t, df["time"], np.cos(rad))
    wdir = float(np.degrees(np.arctan2(s, c)) % 360)
    win = cfg("wind", "sigma_u_window_h")
    near = df[(df["time"] >= t - pd.Timedelta(hours=win)) & (df["time"] <= t + pd.Timedelta(hours=win))]
    sd_local = float(near["wind_speed_10m"].std(ddof=1)) if len(near) > 1 else 0.0
    sigma_u = max(cfg("wind", "sigma_u_floor"), sd_local, cfg("wind", "sigma_u_frac") * u10)
    assumptions = []
    if "surface_pressure" in df:
        P = _interp_linear(t, df["time"], df["surface_pressure"]) * 100.0
    else:
        P = float(cfg("physics_constants", "default_pressure_pa"))
        assumptions.append(f"surface pressure not in wind file → default {P:.0f} Pa (case.yaml)")
    if "temperature_2m" in df:
        T = _interp_linear(t, df["time"], df["temperature_2m"]) + 273.15
    else:
        T = float(cfg("physics_constants", "default_temperature_k"))
        assumptions.append(f"2 m temperature not in wind file → default {T:.0f} K (case.yaml)")
    n_air = P / (cfg("physics_constants", "R") * T)
    return WindAtOverpass(t.isoformat().replace("+00:00", "Z"), u10, wdir, sigma_u, P, T, n_air, df, assumptions,
                          j.get("latitude"), j.get("longitude"), rec)
