"""Render a Plotly figure JSON to a static PNG with matplotlib (no browser, no kaleido).

The PNG is what OMNI sees; the interactive figure JSON is what the frontend renders. Only the trace and
layout features used by our eight builders are supported: heatmap, contour, scatter (lines / markers /
text / fill), bar (h/v, error bars), subplot domains, log/date/tick-text axes, vline/hline/vrect shapes,
annotations (incl. arrows) and a visible-trace subset chosen by the active slider step.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap, to_rgba  # noqa: E402

W, H, DPI = 12, 8, 100  # 1200x800 px


def _color(c, default="#3987e5"):
    if c is None:
        return default
    if isinstance(c, str) and c.startswith("rgba("):
        r, g, b, a = [float(x) for x in c[5:-1].split(",")]
        return (r / 255, g / 255, b / 255, a)
    if isinstance(c, str) and c.startswith("rgb("):
        r, g, b = [float(x) for x in c[4:-1].split(",")]
        return (r / 255, g / 255, b / 255)
    try:
        to_rgba(c)
        return c
    except (ValueError, TypeError):
        return default


def _is_date(v) -> bool:
    return isinstance(v, str) and len(v) >= 10 and v[4] == "-" and v[7] == "-"


def _conv(vals):
    if vals is None:
        return None
    if isinstance(vals, dict):  # plotly typed-array encoding {"dtype","bdata"}
        import base64
        arr = np.frombuffer(base64.b64decode(vals["bdata"]), dtype=np.dtype(vals["dtype"]))
        if "shape" in vals:
            arr = arr.reshape([int(s) for s in str(vals["shape"]).split(",")])
        return arr
    vals = list(vals)
    if vals and any(_is_date(v) for v in vals if v is not None):
        return [dt.datetime.fromisoformat(str(v).replace("Z", "+00:00")).replace(tzinfo=None) if v else None for v in vals]
    return vals


def _val(v):
    if _is_date(v):
        return dt.datetime.fromisoformat(v.replace("Z", "+00:00")).replace(tzinfo=None)
    return v


def _axes_for(fig, layout: dict) -> dict:
    """Create one matplotlib Axes per (xaxis, yaxis) pair from layout domains."""
    axes = {}
    ml = max(0.08, (layout.get("margin", {}).get("l") or 0) / (W * DPI) * 0.9)
    names = sorted({k for k in layout if k.startswith("xaxis")} or {"xaxis"})
    for xn in names:
        xa = layout.get(xn, {})
        suffix = xn[5:]
        ya = layout.get("yaxis" + suffix, {})
        xd = xa.get("domain", [0, 1]); yd = ya.get("domain", [0, 1])
        span = 0.92 - ml
        left, bottom = ml + xd[0] * span, 0.13 + yd[0] * 0.75
        ax = fig.add_axes([left, bottom, (xd[1] - xd[0]) * span - 0.02, (yd[1] - yd[0]) * 0.75 - 0.03])
        axes[("x" + suffix, "y" + suffix)] = (ax, xa, ya)
    return axes


def _style_axis(ax, xa, ya, ink, muted, grid):
    ax.set_facecolor(ax.figure.get_facecolor())
    ax.set_axisbelow(True)
    for s in ax.spines.values():
        s.set_color(grid)
    ax.tick_params(colors=muted, labelsize=9)
    for which, a in (("x", xa), ("y", ya)):
        if a.get("type") == "log":
            (ax.set_xscale if which == "x" else ax.set_yscale)("log")
        rng = a.get("range")
        if rng and len(rng) == 2 and rng[0] is not None:
            lo, hi = rng
            if a.get("type") == "log":
                lo, hi = 10 ** lo, 10 ** hi
            lo, hi = _val(lo), _val(hi)
            if which == "x":
                ax.set_xlim(lo, hi)
            else:
                ax.set_ylim(lo, hi)
        if a.get("autorange") == "reversed":
            (ax.invert_xaxis if which == "x" else ax.invert_yaxis)()
        t = a.get("title", {})
        t = t.get("text") if isinstance(t, dict) else t
        if t:
            (ax.set_xlabel if which == "x" else ax.set_ylabel)(t, color=ink, fontsize=10)
        if a.get("tickvals") is not None and a.get("ticktext") is not None:
            (ax.set_xticks if which == "x" else ax.set_yticks)(a["tickvals"])
            (ax.set_xticklabels if which == "x" else ax.set_yticklabels)(a["ticktext"])
        if a.get("showgrid", True):
            ax.grid(True, axis=which, color=grid, linewidth=0.6)
    if ya.get("scaleanchor"):
        ax.set_aspect(ya.get("scaleratio", 1), adjustable="box")


def _cmap(scale):
    if not scale or isinstance(scale, str):
        return "Blues_r"
    return LinearSegmentedColormap.from_list("c", [(float(p), _color(c)) for p, c in scale])


def render(fig_json: dict, out: Path) -> None:
    layout = fig_json.get("layout", {})
    tmpl = layout.get("template", {}).get("layout", {})
    bg = layout.get("paper_bgcolor") or tmpl.get("paper_bgcolor") or "#15171c"
    ink, muted, grid = "#f3f4f6", "#b9b8b0", "#34342f"
    fig = plt.figure(figsize=(W, H), dpi=DPI, facecolor=_color(bg))
    axes = _axes_for(fig, layout)
    default = next(iter(axes.values()))
    # respect the active slider step's visibility (plume_map k frames)
    vis_override = None
    sl = layout.get("sliders")
    if sl:
        step = sl[0]["steps"][sl[0].get("active", 0)]
        vis_override = step["args"][0].get("visible")
    legend_items = []
    for i, tr in enumerate(fig_json.get("data", [])):
        visible = tr.get("visible", True) if vis_override is None else vis_override[i]
        if visible is False or visible == "legendonly":
            continue
        ax = axes.get((tr.get("xaxis", "x"), tr.get("yaxis", "y")), default)[0]
        t = tr.get("type", "scatter")
        x, y = _conv(tr.get("x")), _conv(tr.get("y"))
        name = tr.get("name")
        show_leg = tr.get("showlegend", True) and name
        if t == "heatmap":
            z = np.array(_conv(tr["z"]) if isinstance(tr["z"], dict) else tr["z"], dtype=float)
            m = ax.pcolormesh(np.asarray(x, float), np.asarray(y, float), z, cmap=_cmap(tr.get("colorscale")),
                              vmin=tr.get("zmin"), vmax=tr.get("zmax"), shading="nearest")
            cb = fig.colorbar(m, ax=ax, fraction=0.035, pad=0.02)
            cb.ax.tick_params(colors=muted, labelsize=8)
            ct = tr.get("colorbar", {}).get("title", {})
            cb.set_label((ct.get("text") if isinstance(ct, dict) else ct or "").replace("<br>", " "), color=ink)
        elif t == "contour":
            z = np.array(_conv(tr["z"]) if isinstance(tr["z"], dict) else tr["z"], dtype=float)
            c = tr.get("contours", {})
            ax.contour(np.asarray(x, float), np.asarray(y, float), z, levels=[c.get("start", 0.5)],
                       colors=[_color(tr.get("line", {}).get("color"))], linewidths=2)
            legend_items.append((plt.Line2D([], [], color=_color(tr.get("line", {}).get("color")), lw=2), name or "contour"))
        elif t == "bar":
            mk = tr.get("marker", {})
            col = mk.get("color")
            horiz = tr.get("orientation") == "h"
            xs = x if not horiz else y
            vals = y if not horiz else x
            cols = [_color(c) for c in col] if isinstance(col, list) else _color(col)
            err = tr.get("error_x" if horiz else "error_y") or {}
            e = None
            if err.get("array"):
                e = [err.get("arrayminus", err["array"]), err["array"]]
            width = tr.get("width")
            if horiz:
                ax.barh(xs, vals, color=cols, xerr=e, height=0.5, ecolor=ink, capsize=6)
            else:
                kw = {"width": width} if width is not None else {}
                ax.bar(xs, vals, color=cols, yerr=e, ecolor=ink, align="center", **kw)
            if tr.get("text") and tr.get("textposition") == "outside":
                for xi, vi, ti in zip(xs, vals, tr["text"]):
                    if horiz:
                        ax.text(vi, xi, f"  {ti}", va="center", color=ink, fontsize=10)
                    else:
                        ax.text(xi, vi, ti, ha="center", va="bottom", color=ink, fontsize=10)
        elif t == "scatter":
            mode = tr.get("mode", "lines")
            line, mk = tr.get("line", {}), tr.get("marker", {})
            if x is None or y is None or all(v is None for v in (y or [])):
                if show_leg:
                    legend_items.append((plt.Line2D([], [], color=_color(line.get("color")), lw=line.get("width", 2)), name))
                continue
            if tr.get("fill") == "toself":
                ax.fill(x, y, color=_color(tr.get("fillcolor")), lw=0)
                if show_leg:
                    legend_items.append((plt.Rectangle((0, 0), 1, 1, color=_color(tr.get("fillcolor"))), name))
                continue
            h = None
            if "lines" in mode:
                ls = {"dash": "--", "dot": ":", "dashdot": "-."}.get(line.get("dash"), "-")
                h, = ax.plot(x, y, color=_color(line.get("color")), lw=line.get("width", 2), ls=ls)
            if "markers" in mode:
                size = mk.get("size", 8)
                s = (np.array(size, float) if isinstance(size, list) else size) ** 2 * 0.8
                sym = {"square": "s", "x": "x", "diamond": "D"}.get(mk.get("symbol"), "o")
                col = mk.get("color")
                h = ax.scatter(x, y, s=s, c=[_color(c) for c in col] if isinstance(col, list) else _color(col),
                               marker=sym, zorder=5, linewidths=1 if sym != "x" else 2,
                               **({} if sym == "x" else {"edgecolors": _color(mk.get("line", {}).get("color"), "none")}))
            if "text" in mode and tr.get("text"):
                for xi, yi, ti in zip(x, y, tr["text"]):
                    ax.annotate(ti, (xi, yi), textcoords="offset points", xytext=(0, -16), ha="center", color=ink, fontsize=10)
            if show_leg and h is not None:
                legend_items.append((h, name))
    # shapes: vline/hline/vrect
    for sh in layout.get("shapes", []):
        xr, yr = sh.get("xref", "x"), sh.get("yref", "y")
        key = ("x" + xr[1:].replace(" domain", ""), "y" + yr[1:].replace(" domain", "")) if xr != "paper" else None
        ax = axes.get(key, (default[0],))[0] if key else default[0]
        ln = sh.get("line", {})
        ls = {"dash": "--", "dot": ":"}.get(ln.get("dash"), "-")
        col = _color(ln.get("color") or sh.get("fillcolor"))
        x0, x1, y0, y1 = (_val(sh.get(k)) for k in ("x0", "x1", "y0", "y1"))
        if sh.get("type") == "rect":
            if "domain" in yr or yr == "paper":
                ax.axvspan(x0, x1, color=_color(sh.get("fillcolor")), alpha=sh.get("opacity", 0.1), lw=0)
            else:
                ax.axhspan(y0, y1, color=_color(sh.get("fillcolor")), alpha=sh.get("opacity", 0.1), lw=0)
        elif x0 == x1 and ("domain" in yr or yr == "paper"):
            ax.axvline(x0, color=col, ls=ls, lw=ln.get("width", 2))
        elif y0 == y1 and ("domain" in xr or xr == "paper"):
            ax.axhline(y0, color=col, ls=ls, lw=ln.get("width", 2))
    # annotations
    for an in layout.get("annotations", []):
        text = str(an.get("text", "")).replace("<br>", "\n")
        xr, yr = an.get("xref", "x"), an.get("yref", "y")
        if xr == "paper" and yr == "paper":
            fig.text(0.08 + an.get("x", 0) * 0.84, 0.13 + an.get("y", 0) * 0.75, text, color=ink, fontsize=9,
                     ha=an.get("xanchor", "center") if an.get("xanchor") in ("left", "right", "center") else "center")
            continue
        key = ("x" + xr[1:].replace(" domain", ""), "y" + yr[1:].replace(" domain", ""))
        ax = axes.get(key, default)[0]
        x = _val(an.get("x"))
        xa = axes.get(key, default)[1]
        if xa.get("type") == "log" and isinstance(x, (int, float)):
            x = 10 ** x
        trans_y = yr == "paper" or "domain" in yr
        if an.get("showarrow") and an.get("axref") == "x":
            ax.annotate("", xy=(an["x"], an["y"]), xytext=(an["ax"], an["ay"]),
                        arrowprops=dict(arrowstyle="-|>", color=_color(an.get("arrowcolor"), ink), lw=2.5, mutation_scale=20))
            continue
        if trans_y:
            ax.text(x, an.get("y", 1), text, transform=ax.get_xaxis_transform(), color=ink, fontsize=9, ha="center",
                    va="bottom")
        else:
            ax.annotate(text, (x, _val(an.get("y"))), color=ink, fontsize=9, ha="center",
                        textcoords="offset points", xytext=(0, an.get("yshift", 0)))
    for ax, xa, ya in axes.values():
        _style_axis(ax, xa, ya, ink, muted, grid)
    title = layout.get("title", {})
    title = title.get("text") if isinstance(title, dict) else title
    if title:
        fig.suptitle(title, color=ink, fontsize=14, x=0.08, ha="left", y=0.97)
    if legend_items:
        leg = fig.legend([h for h, _ in legend_items], [n for _, n in legend_items], loc="lower left",
                         bbox_to_anchor=(0.08, 0.01), ncol=min(4, len(legend_items)), frameon=False, fontsize=9)
        for tx in leg.get_texts():
            tx.set_color(ink)
    fig.savefig(out, dpi=DPI, facecolor=fig.get_facecolor())
    plt.close(fig)
