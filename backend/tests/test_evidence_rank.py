"""rank_evidence: hybrid retrieval + validated LLM rerank."""
import json

import httpx
import numpy as np
from openai import OpenAI

from backend.agent import orchestrator
from backend.science import evidence_rank as er
from backend.tools.registry import run_tool
from backend.tools.state import new_state


def _run_until_regulations():
    st = new_state("tx-lenorah-redlake", "2025-08-08", mode="MOCK")
    for name, args, _ in orchestrator._canonical(st):
        if name == "rank_evidence":
            break
        if name != "submit_verdict":
            run_tool(st, name, args)
    return st


def test_bm25_prefers_matching_doc():
    s = er.bm25_scores("super-emitter threshold exceed", ["plume wind north", "rule super-emitter threshold EXCEEDS", "flare"])
    assert int(np.argmax(s)) == 1


def test_rrf_fuses_rankings():
    f = er.rrf([0, 1, 2], [2, 0, 1])
    assert max(f, key=f.get) == 0


def test_demo_ranking_valid_and_required_by_verdict(monkeypatch):
    monkeypatch.setenv("MOCK_STEP_DELAY", "0")
    st = _run_until_regulations()
    res = run_tool(st, "rank_evidence", {"facility_id": st.facility_id})
    assert res["status"] == "ok"
    r = st.results["evidence_ranking"]
    assert set(r["questions"]) == set(er.QUESTIONS)
    assert r["backends"]["dense"].startswith("local") and r["backends"]["rerank_modes"] == ["demo"]
    for q in r["questions"].values():
        assert all(x["id"] in st.ledger for x in q["ranking"])  # every ranked id is citable
        imps = [x["importance"] for x in q["ranking"]]
        assert imps == sorted(imps, reverse=True)
    top_threshold = [x["id"] for x in r["questions"]["threshold"]["ranking"][:3]]
    assert "rule:US_SUPER_EMITTER" in top_threshold


def test_verdict_requires_ranking(monkeypatch):
    monkeypatch.setenv("MOCK_STEP_DELAY", "0")
    st = _run_until_regulations()
    v = orchestrator.build_verdict(st)
    res = run_tool(st, "submit_verdict", {"verdict": v})
    assert res["status"] == "error" and "rank_evidence" in res["summary"]


def test_validate_ranking_drops_invented_ids():
    items = [er.Item("a", "x", "data", "s", 0.9), er.Item("b", "y", "data", "s", 0.9)]
    cands = [{"idx": 0, "fused": 0.03}, {"idx": 1, "fused": 0.02}]
    raw = json.dumps({"ranking": [{"id": "ghost", "importance": 1}, {"id": "b", "importance": 7, "reason": "r"}]})
    out = er.validate_ranking(raw, cands, items)
    assert [o["id"] for o in out] == ["b", "a"] and out[0]["importance"] == 1.0 and out[1]["importance"] == 0.0


def test_live_path_with_fake_endpoints(monkeypatch, tmp_path):
    monkeypatch.setenv("MOCK_STEP_DELAY", "0")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("OPENAI_MODEL", "fake-gpt")
    monkeypatch.setattr(er, "CACHE_DIR", tmp_path)
    st = _run_until_regulations()

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        if req.url.path.endswith("/embeddings"):
            data = [{"object": "embedding", "index": i, "embedding": list(np.random.default_rng(i).normal(size=8))}
                    for i, _ in enumerate(body["input"])]
            return httpx.Response(200, json={"object": "list", "data": data, "model": "e", "usage": {"prompt_tokens": 1, "total_tokens": 1}})
        ids = [c["id"] for c in json.loads(body["input"].split("Candidates: ", 1)[1])]
        ranking = [{"id": i, "importance": round(1 - n / 20, 2), "reason": "fake"} for n, i in enumerate(reversed(ids))]
        text = json.dumps({"ranking": ranking})
        return httpx.Response(200, json={"id": "r", "object": "response", "created_at": 0, "model": "fake-gpt", "status": "completed",
                                         "output": [{"type": "message", "id": "m", "role": "assistant", "status": "completed",
                                                     "content": [{"type": "output_text", "text": text, "annotations": []}]}],
                                         "parallel_tool_calls": True, "tool_choice": "auto", "tools": []})

    fake = lambda: OpenAI(api_key="t", base_url="http://fake.local/v1", http_client=httpx.Client(transport=httpx.MockTransport(handler)), max_retries=0)  # noqa: E731
    r = er.rank(st, live=True, embed_client=fake, rerank_client=fake)
    assert r["backends"]["dense"].startswith("openai") and "live" in r["backends"]["rerank_modes"]
    q = r["questions"]["threshold"]["ranking"]
    assert q[0]["reason"] == "fake" and q[0]["importance"] == 1.0
