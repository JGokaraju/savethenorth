"""DEMO_REPLAY=1 replays the most recent successful recorded run through the real API, fully offline."""
import json

from fastapi.testclient import TestClient

from backend import app as app_mod
from backend.agent import orchestrator
from backend.tools.state import new_state


def _sse_types(client, run_id):
    types = []
    with client.stream("GET", f"/api/runs/{run_id}/events") as r:
        for line in r.iter_lines():
            if line.startswith("event:"):
                t = line.split(":", 1)[1].strip()
                types.append(t)
                if t == "run_finished":
                    break
    return types


def test_replay_of_recorded_run(monkeypatch):
    monkeypatch.setenv("MOCK_STEP_DELAY", "0")
    src = new_state("tx-lenorah-redlake", "2025-08-08", mode="MOCK")  # record a run
    orchestrator.run(src)
    assert src.verdict
    monkeypatch.setenv("DEMO_REPLAY", "1")
    monkeypatch.setattr(app_mod.time, "sleep", lambda s: None)  # no realistic delays in tests
    c = TestClient(app_mod.app)
    r = c.post("/api/runs", json={"facility_id": "tx-lenorah-redlake", "date": "2025-08-08"}).json()
    assert r["mode"] == "REPLAY"
    types = _sse_types(c, r["run_id"])
    assert types[0] == "run_started" and "verdict" in types and types.count("chart") >= 6
    ev = c.get(f"/api/runs/{r['run_id']}/evidence").json()
    assert len(ev["ledger"]) > 10 and ev["omni_calls"]
    assert c.get(f"/api/runs/{r['run_id']}/evidence/firms_subset.csv").status_code == 200
    first = json.loads((app_mod.RUNS_DIR / f"{r['run_id']}.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert first["mode"] == "REPLAY"


def test_recent_runs_listing_hides_test_runs(monkeypatch):
    monkeypatch.setenv("MOCK_STEP_DELAY", "0")
    listed = new_state("tx-lenorah-redlake", "2025-08-08", run_id="20990101T000000-listed", mode="MOCK")
    orchestrator.run(listed)
    hidden = new_state("tx-lenorah-redlake", "2025-08-08", mode="MOCK")  # auto id is test-prefixed under pytest
    orchestrator.run(hidden)
    rows = TestClient(app_mod.app).get("/api/runs?limit=10").json()
    ids = [r["run_id"] for r in rows]
    assert listed.run_id in ids and hidden.run_id.startswith("test-") and hidden.run_id not in ids
    row = next(r for r in rows if r["run_id"] == listed.run_id)
    assert row["finished"] and row["outcome"] == "FAILED" and row["facility_name"] == "Lenorah / Red Lake Gas Plants"
