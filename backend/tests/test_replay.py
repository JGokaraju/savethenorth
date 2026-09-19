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
