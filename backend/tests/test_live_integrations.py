"""Live code paths against fake OpenAI-compatible endpoints (no network, no keys).

- OMNI: endpoint that rejects non-streaming -> client retries with stream=True, accumulates deltas, caches to disk.
- Orchestrator: Responses API tool loop; mid-run API failure -> scripted agent completes the run on the same state;
  Responses unavailable at the first call -> Chat Completions fallback.
"""
import json

import httpx
import pytest
from openai import OpenAI

from backend.agent import orchestrator
from backend.llm import omni
from backend.tools.state import new_state


def _client(handler, **kw) -> OpenAI:
    return OpenAI(api_key="test", base_url="http://fake.local/v1", http_client=httpx.Client(transport=httpx.MockTransport(handler)),
                  max_retries=0, **kw)


# ------------------------------------------------------------------ OMNI
def _sse(chunks: list[str]) -> bytes:
    lines = []
    for i, c in enumerate(chunks):
        lines.append("data: " + json.dumps({"id": "c1", "object": "chat.completion.chunk", "created": 0, "model": "fake-omni",
                                            "choices": [{"index": 0, "delta": {"content": c}, "finish_reason": None}]}))
    lines.append("data: [DONE]")
    return ("\n\n".join(lines) + "\n\n").encode()


def test_omni_stream_fallback_and_cache(monkeypatch, tmp_path):
    calls = {"nonstream": 0, "stream": 0}

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        if not body.get("stream"):
            calls["nonstream"] += 1
            return httpx.Response(400, json={"error": {"message": "This model only supports stream=True"}})
        calls["stream"] += 1
        assert body["messages"][1]["content"][0]["type"] == "image_url"  # one image, then text
        return httpx.Response(200, content=_sse(["The plume ", "extends north."]), headers={"content-type": "text/event-stream"})

    monkeypatch.setenv("MOCK_OMNI", "0")
    monkeypatch.setenv("OMNI_API_KEY", "k")
    monkeypatch.setenv("OMNI_BASE_URL", "http://fake.local/v1")
    monkeypatch.setenv("OMNI_MODEL", "fake-omni")
    monkeypatch.setenv("OMNI_FORCE_STREAM", "auto")
    monkeypatch.setattr(omni, "CACHE_DIR", tmp_path)
    (tmp_path / "omni").mkdir()
    monkeypatch.setattr(omni, "_client", lambda: _client(handler))
    omni._stream_mode["value"] = None

    r1 = omni.ask("Where does the plume go?", image_bytes=b"\x89PNG fake")
    assert r1["mode"] == "live" and r1["answer"] == "The plume extends north."
    assert calls == {"nonstream": 1, "stream": 1}
    r2 = omni.ask("Where does the plume go?", image_bytes=b"\x89PNG fake")
    assert r2["mode"] == "cached" and r2["answer"] == r1["answer"]
    assert calls["stream"] == 1  # served from disk cache
    assert omni._stream_mode["value"] is True  # remembered


def test_omni_failure_falls_back_to_mock_text(monkeypatch, tmp_path):
    monkeypatch.setenv("MOCK_OMNI", "0")
    monkeypatch.setenv("OMNI_API_KEY", "k")
    monkeypatch.setenv("OMNI_BASE_URL", "http://fake.local/v1")
    monkeypatch.setattr(omni, "CACHE_DIR", tmp_path)
    (tmp_path / "omni").mkdir()
    monkeypatch.setattr(omni, "_client", lambda: _client(lambda r: httpx.Response(500, json={"error": {"message": "boom"}})))
    monkeypatch.setattr(omni.time, "sleep", lambda s: None)
    r = omni.ask("q", image_bytes=b"x", mock_text="[MOCK OMNI] fallback")
    assert r["mode"] == "mock" and "fallback" in r["answer"] and "error" in r


# ------------------------------------------------------------------ orchestrator
def _resp(rid: str, output: list[dict]) -> dict:
    return {"id": rid, "object": "response", "created_at": 0, "model": "fake-gpt", "status": "completed",
            "output": output, "parallel_tool_calls": True, "tool_choice": "auto", "tools": []}


def _fc(i: int, name: str, args: dict) -> dict:
    return {"type": "function_call", "id": f"fc_{i}", "call_id": f"call_{i}", "name": name,
            "arguments": json.dumps(args), "status": "completed"}


@pytest.fixture
def live_env(monkeypatch):
    monkeypatch.setenv("MOCK_OMNI", "1")
    monkeypatch.setenv("OPENAI_MODEL", "fake-gpt")
    monkeypatch.setenv("MOCK_STEP_DELAY", "0")


def test_responses_loop_then_midrun_failure_falls_back_to_scripted(monkeypatch, live_env):
    script = [
        [{"type": "message", "id": "m1", "role": "assistant", "status": "completed",
          "content": [{"type": "output_text", "text": "I'll start by listing skills.", "annotations": []}]},
         _fc(1, "list_skills", {})],
        [_fc(2, "find_facility", {"query": "Lenorah"})],
        [_fc(3, "plume_map", {"facility_id": "tx-lenorah-redlake", "date": "2025-08-08"})],
    ]
    seen_outputs = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        assert req.url.path.endswith("/responses")
        if body.get("previous_response_id"):
            seen_outputs.append(body["input"])
        n = len(seen_outputs)
        if n >= len(script):
            return httpx.Response(500, json={"error": {"message": "upstream exploded"}})
        return httpx.Response(200, json=_resp(f"resp_{n}", script[n]))

    monkeypatch.setattr(orchestrator, "openai_client", lambda: _client(handler))
    st = new_state("tx-lenorah-redlake", "2025-08-08", mode="LIVE")
    orchestrator.run(st)
    names = [c["name"] for c in st.tool_calls]
    assert names[:3] == ["list_skills", "find_facility", "plume_map"]
    assert seen_outputs[0][0]["type"] == "function_call_output" and seen_outputs[0][0]["call_id"] == "call_1"
    assert any(e["type"] == "assistant_message" and e.get("source") == "gpt" for e in st.events)
    assert any(e["type"] == "error" and e.get("recoverable") for e in st.events)
    assert st.verdict is not None  # scripted agent finished the run
    assert names.count("plume_map") == 1  # already-done steps were not repeated


def test_responses_unavailable_uses_chat_completions(monkeypatch, live_env):
    state = {"chat": 0}

    def handler(req: httpx.Request):
        if req.url.path.endswith("/responses"):
            return httpx.Response(404, json={"error": {"message": "Responses API not supported for this model"}})
        state["chat"] += 1
        if state["chat"] == 1:
            msg = {"role": "assistant", "content": "Listing skills first.",
                   "tool_calls": [{"id": "t1", "type": "function", "function": {"name": "list_skills", "arguments": "{}"}}]}
        else:
            return httpx.Response(500, json={"error": {"message": "stop here"}})
        return httpx.Response(200, json={"id": "cc", "object": "chat.completion", "created": 0, "model": "fake-gpt",
                                         "choices": [{"index": 0, "message": msg, "finish_reason": "tool_calls"}]})

    monkeypatch.setattr(orchestrator, "openai_client", lambda: _client(handler))
    st = new_state("tx-lenorah-redlake", "2025-08-08", mode="LIVE")
    orchestrator.run(st)
    assert any("Chat Completions" in e.get("text", "") for e in st.events if e["type"] == "assistant_message")
    assert st.tool_calls[0]["name"] == "list_skills"
    assert st.verdict is not None
