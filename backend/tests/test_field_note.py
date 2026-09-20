"""Field mode: the spoken-question tool and its endpoint (OMNI audio + image + text)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend.llm import omni
from backend.tools import field_tools

CLIP = b"RIFF\x24\x00\x00\x00WAVEfake-audio-bytes"


def test_field_question_sends_audio_and_image(monkeypatch):
    seen = {}

    def fake_ask(prompt, image_path=None, image_bytes=None, mock_text=None, audio_bytes=None, audio_format="webm"):
        seen.update(prompt=prompt, image_path=image_path, audio=audio_bytes, fmt=audio_format)
        return {"answer": "Flare stack visible at the north end of the pad.", "mode": "live",
                "model": "qwen3.5-omni-flash", "cache_key": "x"}

    monkeypatch.setattr(omni, "ask", fake_ask)
    out = field_tools.field_question("tx-lenorah-redlake", CLIP, "webm", "Exceeds the federal threshold.")

    assert seen["audio"] == CLIP and seen["fmt"] == "webm"
    assert seen["image_path"] is not None, "the site view should travel with the question"
    assert "inspector" in seen["prompt"].lower()
    assert "Exceeds the federal threshold." in seen["prompt"], "desk findings are given as context"
    assert out["modalities"] == ["audio", "image", "text"]
    assert out["answer"].startswith("Flare stack")


def test_field_question_rejects_empty_audio():
    with pytest.raises(ValueError):
        field_tools.field_question("tx-lenorah-redlake", b"")


def test_field_question_unknown_facility():
    with pytest.raises(KeyError):
        field_tools.field_question("nope", CLIP)


def test_endpoint_returns_the_answer(monkeypatch):
    monkeypatch.setattr(field_tools, "field_question",
                        lambda fid, blob, fmt, ctx: {"answer": "ok", "mode": "MOCK", "model": "m",
                                                    "facility": fid, "image_used": True,
                                                    "modalities": ["audio", "image", "text"]})
    c = TestClient(app)
    r = c.post("/api/field-note", data={"facility_id": "tx-lenorah-redlake"},
               files={"audio": ("question.webm", CLIP, "audio/webm")})
    assert r.status_code == 200, r.text
    assert r.json()["answer"] == "ok"


def test_endpoint_unknown_facility_is_404(monkeypatch):
    c = TestClient(app)
    r = c.post("/api/field-note", data={"facility_id": "nope"},
               files={"audio": ("question.webm", CLIP, "audio/webm")})
    assert r.status_code == 404


def test_the_agent_cannot_call_it():
    """Field mode is operator-facing: the orchestrator has no microphone, so the tool is not registered."""
    from backend.tools.registry import TOOLS
    assert not any("field" in name for name in TOOLS)
