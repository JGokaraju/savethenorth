"""Huawei OMNI (Qwen3.5-Omni) client over the OpenAI-compatible Chat Completions endpoint.

- one image per request (multi-page documents are called per page and merged by the caller)
- non-streaming first; on a stream-related error retry with stream=True and accumulate deltas
- disk cache keyed by sha256(model + prompt + image hash)
- mock mode: deterministic, clearly labelled text built from the chart's summary_stats
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
import time
from pathlib import Path

from backend.settings import CACHE_DIR, mock_omni

SYSTEM = ("You are a remote-sensing and regulatory-document analyst. Describe only what is visible. "
          "Do not estimate numeric emission rates. If asked for structured output, return valid JSON only.")

_counter = {"live_calls": 0, "cached": 0, "mock": 0}
_stream_mode: dict[str, bool | None] = {"value": None}
_lock = threading.Lock()


def counters() -> dict:
    return dict(_counter)


def model_name() -> str:
    return os.getenv("OMNI_MODEL", "qwen3.5-omni-flash")


def _client():
    from openai import OpenAI
    return OpenAI(base_url=os.getenv("OMNI_BASE_URL"), api_key=os.getenv("OMNI_API_KEY"), timeout=60, max_retries=0)


def _cache_key(prompt: str, image_bytes: bytes | None) -> str:
    h = hashlib.sha256()
    h.update(model_name().encode()); h.update(b"\0"); h.update(SYSTEM.encode()); h.update(b"\0"); h.update(prompt.encode())
    if image_bytes:
        h.update(hashlib.sha256(image_bytes).digest())
    return h.hexdigest()


def _call_live(prompt: str, image_bytes: bytes | None, mime: str) -> str:
    content = []
    if image_bytes:
        b64 = base64.b64encode(image_bytes).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    content.append({"type": "text", "text": prompt})
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}]
    client = _client()
    force = os.getenv("OMNI_FORCE_STREAM", "auto").lower()
    use_stream = True if force == "true" else False if force == "false" else (_stream_mode["value"] or False)
    extra = {"modalities": ["text"]}

    def once(stream: bool, with_modalities: bool) -> str:
        kw = dict(model=model_name(), messages=messages, stream=stream)
        if with_modalities:
            kw["extra_body"] = extra
        if not stream:
            r = client.chat.completions.create(**kw)
            return r.choices[0].message.content or ""
        parts = []
        for chunk in client.chat.completions.create(**kw):
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                parts.append(chunk.choices[0].delta.content)
        return "".join(parts)

    with_mod, retries, last = True, 0, None
    while retries <= 2:
        try:
            out = once(use_stream, with_mod)
            if force == "auto":
                _stream_mode["value"] = use_stream  # remember which mode worked
            return out
        except Exception as e:  # noqa: BLE001
            last, msg = e, str(e).lower()
            if with_mod and "modalit" in msg:
                with_mod = False            # endpoint rejects `modalities`: drop it, retry immediately
            elif "stream" in msg and force == "auto" and not use_stream:
                use_stream = True           # endpoint requires stream=True
            else:
                retries += 1
                time.sleep(1.5 * retries)
    raise RuntimeError(f"OMNI call failed: {last}")


def ask(prompt: str, image_path: Path | None = None, image_bytes: bytes | None = None,
        mock_text: str | None = None) -> dict:
    """Returns {answer, mode: live|cached|mock, model, cache_key}."""
    if image_path is not None and image_bytes is None:
        image_bytes = Path(image_path).read_bytes()
    mime = "image/jpeg" if image_path and str(image_path).lower().endswith((".jpg", ".jpeg")) else "image/png"
    key = _cache_key(prompt, image_bytes)
    cache_file = CACHE_DIR / "omni" / f"{key}.json"
    if cache_file.exists():
        with _lock:
            _counter["cached"] += 1
        d = json.loads(cache_file.read_text(encoding="utf-8"))
        return {**d, "mode": "cached" if d.get("mode") == "live" else d.get("mode", "cached")}
    if mock_omni():
        with _lock:
            _counter["mock"] += 1
        return {"answer": mock_text or "[MOCK OMNI] No live model configured.", "mode": "mock",
                "model": f"{model_name()} (mock)", "cache_key": key}
    try:
        answer = _call_live(prompt, image_bytes, mime)
    except Exception as e:  # noqa: BLE001 — never fail the run; fall back to the mock text
        with _lock:
            _counter["mock"] += 1
        return {"answer": (mock_text or "") + f"\n[OMNI unavailable: {str(e)[:160]}]", "mode": "mock",
                "model": f"{model_name()} (fallback)", "cache_key": key, "error": str(e)[:300]}
    with _lock:
        _counter["live_calls"] += 1
    rec = {"answer": answer, "mode": "live", "model": model_name(), "cache_key": key,
           "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    cache_file.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return rec


def parse_json(text: str):
    """Best-effort JSON extraction from a model answer."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = t[t.find("\n") + 1:] if "\n" in t else t
    for opener, closer in (("{", "}"), ("[", "]")):
        i, j = t.find(opener), t.rfind(closer)
        if i != -1 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except json.JSONDecodeError:
                continue
    return None
