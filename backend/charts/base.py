"""Chart theme, artifact type and export (figure JSON for the frontend, PNG for OMNI)."""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field

import plotly.graph_objects as go
import plotly.io as pio

from backend.charts import static_png
from backend.settings import CHARTS_DIR, ROOT

# Validated dark-mode categorical steps (dataviz reference palette, checked against surface #102124)
# + reserved status colours.
SURFACE = "#102124"
PAGE = "#0b1719"
INK = "#f3f1ea"
INK2 = "#cfd8d6"
MUTED = "#9bacab"
GRID = "rgba(243,241,234,0.10)"
AXIS = "rgba(243,241,234,0.28)"
S1, S2, S3 = "#3987e5", "#d95926", "#199e70"     # blue, orange, aqua
S_VIOLET = "#8a79e0"
CRITICAL, WARNING, GOOD = "#e05c4b", "#e0a83c", "#2fa96b"
NEUTRAL = "#6f8382"
# sequential (single hue: blue), dark surface -> low values recede into the surface
SEQ_BLUE = [[0.0, "#12262c"], [0.25, "#1b4a73"], [0.5, "#2a74bd"], [0.75, "#5aa3e8"], [1.0, "#b7d9f7"]]

FONT = "Public Sans, system-ui, -apple-system, Segoe UI, sans-serif"

pio.templates["plumewatch"] = go.layout.Template(layout=dict(
    font=dict(family=FONT, color=INK2, size=13),
    title=dict(font=dict(color=INK, size=16), x=0.01, xanchor="left"),
    paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
    colorway=[S1, S2, S3, S_VIOLET],
    xaxis=dict(gridcolor=GRID, linecolor=AXIS, zerolinecolor=AXIS, tickfont=dict(color=MUTED), title=dict(font=dict(color=INK2))),
    yaxis=dict(gridcolor=GRID, linecolor=AXIS, zerolinecolor=AXIS, tickfont=dict(color=MUTED), title=dict(font=dict(color=INK2))),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=INK2), orientation="h", y=1.0, yanchor="bottom", x=1.0, xanchor="right"),
    hoverlabel=dict(bgcolor="#16292c", bordercolor=AXIS, font=dict(color=INK, family=FONT)),
    margin=dict(l=70, r=30, t=90, b=60),
))
pio.templates.default = "plumewatch"

_png_lock = threading.Lock()  # matplotlib pyplot state is global


@dataclass
class ChartArtifact:
    chart_id: str
    title: str
    figure_json: dict
    png_path: str | None
    summary_stats: dict = field(default_factory=dict)

    def to_dict(self, include_figure: bool = True) -> dict:
        d = asdict(self)
        if not include_figure:
            d.pop("figure_json")
        return d


def save(chart_id: str, title: str, fig: go.Figure, summary_stats: dict, png: bool = True) -> ChartArtifact:
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    fig_json = json.loads(pio.to_json(fig, validate=False))
    (CHARTS_DIR / f"{chart_id}.json").write_text(json.dumps(fig_json), encoding="utf-8")
    png_path = None
    if png:
        try:  # static snapshot for OMNI, rendered with matplotlib from the same figure JSON
            with _png_lock:
                static_png.render(fig_json, CHARTS_DIR / f"{chart_id}.png")
            png_path = (CHARTS_DIR / f"{chart_id}.png").relative_to(ROOT).as_posix()
        except Exception as e:  # PNG is for OMNI only; never fail the run for it
            summary_stats = {**summary_stats, "png_error": f"{type(e).__name__}: {e}"[:300]}
    (CHARTS_DIR / f"{chart_id}.meta.json").write_text(json.dumps({"chart_id": chart_id, "title": title,
                                                                  "summary_stats": summary_stats}, default=str),
                                                      encoding="utf-8")
    return ChartArtifact(chart_id, title, fig_json, png_path, summary_stats)


def load(chart_id: str) -> ChartArtifact | None:
    p = CHARTS_DIR / f"{chart_id}.json"
    if not p.exists():
        return None
    meta_p = CHARTS_DIR / f"{chart_id}.meta.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {"title": chart_id, "summary_stats": {}}
    png = CHARTS_DIR / f"{chart_id}.png"
    return ChartArtifact(chart_id, meta["title"], json.loads(p.read_text(encoding="utf-8")),
                         png.relative_to(ROOT).as_posix() if png.exists() else None, meta.get("summary_stats", {}))
