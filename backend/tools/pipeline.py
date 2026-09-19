"""Precompute (make prep): run every science tool once so charts/PNGs and steers_events.json exist."""
from __future__ import annotations

from backend.tools.registry import run_tool
from backend.tools.state import new_state

STEPS = ["plume_map", "get_wind", "compute_emission_rate", "compare_estimates", "flare_activity",
         "physics_bounds", "annualize", "reporting_timeline", "check_regulations"]


def precompute(facility_id: str = "tx-lenorah-redlake", date: str = "2025-08-08") -> dict:
    st = new_state(facility_id, date, run_id="prep")
    out = {}
    for name in STEPS:
        r = run_tool(st, name, {"facility_id": facility_id})
        out[name] = f"{r['status']}: {r['summary'][:120]}"
    return out
