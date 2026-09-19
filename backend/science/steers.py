"""§6.6 TCEQ STEERS emissions-event parsing -> data/processed/steers_events.json.

The provided exports are tabular (one row per emission point x contaminant), so events are built by
grouping rows per incident. A text/regex path handles PDF/HTML printouts if those are supplied.
"""
from __future__ import annotations

import json
import re

import pandas as pd

from backend.science.common import DataGap, slot
from backend.settings import PROCESSED

OUT = PROCESSED / "steers_events.json"
_DT = "%m/%d/%Y %H:%M"


def _from_table(df: pd.DataFrame, source: str) -> list[dict]:
    df.columns = [str(c).strip().upper() for c in df.columns]
    events = []
    for inc, g in df.groupby("INCIDENT NO."):
        r = g.iloc[0]
        start = pd.to_datetime(r["START DATE/TIME"], format=_DT, errors="coerce")
        end = pd.to_datetime(r["END DATE/TIME"], format=_DT, errors="coerce")
        dur = (end - start).total_seconds() / 3600 if pd.notna(start) and pd.notna(end) else None
        pollutants = [{"contaminant": str(x["CONTAMINANT"]), "quantity": float(x["EST QUANTITY/OPACITY"]),
                       "units": str(x["UNITS"]).strip().lower(),
                       "emission_point": f"{x['EMISSION POINT NAME']} ({x['EPN']})"} for _, x in g.iterrows()]
        methane_listed = any("methane" in p["contaminant"].lower() for p in pollutants)
        events.append({
            "incident_no": str(inc).replace(".0", ""), "start_date": start.strftime("%Y-%m-%dT%H:%M") if pd.notna(start) else None,
            "end_date": end.strftime("%Y-%m-%dT%H:%M") if pd.notna(end) else None,
            "duration_h": round(dur, 1) if dur is not None else None,
            "facility": str(r["RE NAME"]).title(), "regulated_entity": str(r["RN"]),
            "event_type": str(r["EVENT TYPE"]).title(),
            "emission_points": sorted({p["emission_point"] for p in pollutants}),
            "pollutants": pollutants, "methane_reported": methane_listed,
            "authorization": str(r.get("AUTHORIZATION COMMENT", "")),
            "description": f"{str(r['EVENT TYPE']).title()} at {', '.join(sorted({p['emission_point'] for p in pollutants}))}; "
                           f"contaminants reported: {', '.join(p['contaminant'] for p in pollutants)}",
            "source": source,
        })
    return sorted(events, key=lambda e: e["start_date"] or "")


def _from_text(text: str, source: str) -> list[dict]:
    events = []
    for m in re.finditer(r"\b(\d{5,7})\b", text):
        ctx = text[max(0, m.start() - 200): m.end() + 400]
        dates = re.findall(r"\d{1,2}/\d{1,2}/\d{4}(?: \d{1,2}:\d{2})?", ctx)
        if not dates:
            continue
        et = re.search(r"(emissions event|maintenance|startup|shutdown|excess opacity)", ctx, re.I)
        events.append({"incident_no": m.group(1), "start_date": dates[0], "end_date": dates[1] if len(dates) > 1 else None,
                       "facility": None, "event_type": et.group(1).title() if et else None,
                       "description": re.sub(r"\s+", " ", ctx)[:200], "source": source})
    uniq = {e["incident_no"]: e for e in events}
    return list(uniq.values())


def parse() -> list[dict]:
    rec = slot("tceq_steers")
    path = rec["path"]
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
        events = _from_table(df, "tceq_steers_export")
    elif path.suffix.lower() == ".pdf":
        import pymupdf
        text = "".join(p.get_text() for p in pymupdf.open(path))
        events = _from_text(text, "tceq_steers_pdf")
    else:
        events = _from_text(path.read_text(encoding="utf-8", errors="replace"), "tceq_steers_html")
    if not events:
        raise DataGap("STEERS file parsed but no incidents found")
    OUT.write_text(json.dumps(events, indent=1), encoding="utf-8")
    return events


def load() -> list[dict]:
    if OUT.exists():
        return json.loads(OUT.read_text(encoding="utf-8"))
    return parse()
