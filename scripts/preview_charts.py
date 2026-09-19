"""Build all charts from the cached case and write a static HTML gallery for visual QA.

Usage: python scripts/preview_charts.py  ->  data/processed/charts/gallery.html
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.settings import CHARTS_DIR  # noqa: E402


def main() -> None:
    from backend.tools.registry import new_state, run_tool
    t = time.time()
    st = new_state("tx-lenorah-redlake", "2025-08-08")
    for name, args in [("plume_map", {}), ("get_wind", {}), ("compute_emission_rate", {}),
                       ("compare_estimates", {}), ("flare_activity", {}), ("physics_bounds", {}),
                       ("annualize", {}), ("reporting_timeline", {}), ("check_regulations", {})]:
        r = run_tool(st, name, {"facility_id": st.facility_id, **args})
        print(f"{name:24s} {r['status']:9s} {r['summary'][:110]}")
    figs = sorted(CHARTS_DIR.glob("*.json"))
    figs = [f for f in figs if not f.name.endswith(".meta.json")]
    divs = []
    for i, f in enumerate(figs):
        divs.append(f'<h2>{f.stem}</h2><div id="c{i}" style="height:640px"></div>'
                    f'<script>var f={f.read_text(encoding="utf-8")};Plotly.newPlot("c{i}",f.data,f.layout,{{responsive:true}});</script>')
    html = ("<!doctype html><meta charset='utf-8'><title>Chart gallery</title>"
            "<script src='https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js'></script>"
            "<body style='background:#0b0d11;color:#eee;font-family:system-ui;max-width:1200px;margin:auto'>"
            + "".join(divs) + "</body>")
    out = CHARTS_DIR / "gallery.html"
    out.write_text(html, encoding="utf-8")
    print(f"{len(figs)} charts -> {out}  ({time.time() - t:.1f}s)")


if __name__ == "__main__":
    main()
