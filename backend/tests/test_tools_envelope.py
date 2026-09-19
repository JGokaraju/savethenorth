"""Every tool returns the envelope; missing assets / stub facilities produce data_gap, never exceptions."""
import pytest

from backend.science import common
from backend.tools.registry import TOOLS, run_tool
from backend.tools.state import new_state

KEYS = {"status", "summary", "data", "charts", "evidence_ids", "assumptions", "warnings"}
MINIMAL_ARGS = {
    "list_skills": {}, "load_skill": {"name": "data-discovery"}, "find_facility": {"query": "Lenorah"},
    "list_available_data": {"facility_id": "{f}"}, "describe_dataset": {"slot_id": "wind"},
    "plume_map": {"facility_id": "{f}"}, "get_wind": {"facility_id": "{f}"}, "compute_emission_rate": {"facility_id": "{f}"},
    "compare_estimates": {"facility_id": "{f}"}, "flare_activity": {"facility_id": "{f}"}, "physics_bounds": {"facility_id": "{f}"},
    "annualize": {"facility_id": "{f}"}, "reporting_timeline": {"facility_id": "{f}"}, "check_regulations": {"facility_id": "{f}"},
    "analyze_chart": {"chart_id": "plume_map", "question": "?"}, "analyze_image": {"image_id": "s2_swir", "question": "?"},
    "read_document": {"doc_id": "tceq_sob", "question": "capacity?"}, "show_chart": {"chart_id": "plume_map"},
    "submit_verdict": {"verdict": {}},
}


def _args(name, fid):
    return {k: (v.replace("{f}", fid) if isinstance(v, str) else v) for k, v in MINIMAL_ARGS[name].items()}


def test_all_tools_have_args():
    assert set(MINIMAL_ARGS) == set(TOOLS)


@pytest.mark.parametrize("name", list(MINIMAL_ARGS))
def test_stub_facility_envelope(name):
    st = new_state("tx-pegasus", "2025-08-08")
    r = run_tool(st, name, _args(name, "tx-pegasus"))
    assert KEYS <= set(r)
    assert r["status"] in ("ok", "data_gap", "error")
    if name in ("plume_map", "compute_emission_rate", "flare_activity", "list_available_data"):
        assert r["status"] == "data_gap"
        assert "no cached observations" in r["summary"]


def test_missing_asset_is_data_gap(monkeypatch):
    real = common.load_manifest

    def no_firms():
        m = real()
        m["slots"]["firms"] = {"slot_id": "firms", "status": "missing", "reason": "test: removed"}
        return m
    monkeypatch.setattr(common, "load_manifest", no_firms)
    st = new_state("tx-lenorah-redlake", "2025-08-08")
    r = run_tool(st, "flare_activity", {"facility_id": "tx-lenorah-redlake"})
    assert r["status"] == "data_gap" and "firms" in r["summary"]


def test_unknown_tool_and_bad_args_do_not_raise():
    st = new_state("tx-lenorah-redlake", "2025-08-08")
    assert run_tool(st, "nope", {})["status"] == "error"
    assert run_tool(st, "analyze_image", {"image_id": "nope", "question": "x"})["status"] == "data_gap"
    assert run_tool(st, "compute_emission_rate", {})["status"] == "error"  # missing facility_id -> validation error
