"""Chart theme, artifact type and export (figure JSON for the frontend, PNG for OMNI)."""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field

import plotly.graph_objects as go
import plotly.io as pio

from backend.charts import static_png
from backend.settings import CHARTS_DIR, ROOT

# Validated dark-mode categorical steps (dataviz reference palette) + reserved status colours.
SURFACE = "#15171c"
PAGE = "#0b0d11"
INK = "#f3f4f6"
INK2 = "#c3c2b7"
MUTED = "#898781"
GRID = "#2c2c2a"
AXIS = "#383835"
S1, S2, S3 = "#3987e5", "#d95926", "#199e70"     # blue, orange, aqua
S_VIOLET = "#9085e9"
CRITICAL, WARNING, GOOD = "#d03b3b", "#fab219", "#0ca30c"
NEUTRAL = "#6b6a66"
# sequential (single hue: blue), dark surface -> low values recede into the surface
SEQ_BLUE = [[0.0, "#104281"], [0.25, "#1c5cab"], [0.5, "#3987e5"], [0.75, "#86b6ef"], [1.0, "#e6f0fd"]]

FONT = "system-ui, -apple-system, Segoe UI, sans-serif"

pio.templates["plumewatch"] = go.layout.Template(layout=dict(
    font=dict(family=FONT, color=INK2, size=13),
    title=dict(font=dict(color=INK, size=16), x=0.01, xanchor="left"),
    paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
    colorway=[S1, S2, S3, S_VIOLET],
    xaxis=dict(gridcolor=GRID, linecolor=AXIS, zerolinecolor=AXIS, tickfont=dict(color=MUTED), title=dict(font=dict(color=INK2))),
    yaxis=dict(gridcolor=GRID, linecolor=AXIS, zerolinecolor=AXIS, tickfont=dict(color=MUTED), title=dict(font=dict(color=INK2))),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=INK2), orientation="h", y=-0.18, x=0),
    hoverlabel=dict(bgcolor="#22252c", bordercolor=AXIS, font=dict(color=INK, family=FONT)),
    margin=dict(l=70, r=30, t=70, b=70),
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
