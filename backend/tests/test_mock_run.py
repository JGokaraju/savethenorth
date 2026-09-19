"""A full mock orchestrator run produces a valid verdict, >= 6 charts, and finishes in < 60 s."""
import time

import pytest

from backend.agent import orchestrator, verdict
from backend.tools.state import new_state


@pytest.fixture(autouse=True)
def mock_mode(monkeypatch):
    monkeypatch.setenv("MOCK_LLM", "1")
    monkeypatch.setenv("MOCK_OMNI", "1")
    monkeypatch.setenv("MOCK_STEP_DELAY", "0")


def test_full_mock_run():
    t = time.time()
    st = new_state("tx-lenorah-redlake", "2025-08-08", mode="MOCK")
    orchestrator.run(st)
    assert time.time() - t < 60
    assert st.verdict is not None, [e for e in st.events if e["type"] == "error"]
    types = [e["type"] for e in st.events]
    assert types[0] == "run_started" and types[-1] == "run_finished"
    assert len({e["chart_id"] for e in st.events if e["type"] == "chart"}) >= 6
    assert "skill_loaded" in types and "omni_analysis" in types and "verdict" in types
    v = st.verdict
    em = st.results["emission"]
    assert v["methane_estimate"]["median_kg_h"] == pytest.approx(em["median_kg_h"], rel=0.01)
    status = {r["rule_id"]: r["status"] for r in v["regulatory_findings"]}
    assert status["US_SUPER_EMITTER"] in ("EXCEEDS", "INCONCLUSIVE", "BELOW")
    assert status["NOX_PERMIT_LIMITS"] == "NOT_ASSESSED"
    assert set(v["evidence_ids"]) <= set(st.ledger)
    assert 4 <= len(v["charts"]) <= 6


def test_verdict_rejects_wrong_numbers():
    st = new_state("tx-lenorah-redlake", "2025-08-08", mode="MOCK")
    orchestrator.run(st)
    bad = dict(st.verdict)
    bad["methane_estimate"] = {**bad["methane_estimate"], "median_kg_h": bad["methane_estimate"]["median_kg_h"] * 1.5}
    v, errs = verdict.validate(bad, st)
    assert v is None and any("median_kg_h" in e for e in errs)


def test_stub_facility_concludes_cannot_assess():
    st = new_state("tx-redbluff", "2025-08-08", mode="MOCK")
    orchestrator.run(st)
    assert st.verdict and "cannot assess" in st.verdict["headline"].lower()
