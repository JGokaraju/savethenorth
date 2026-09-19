"""FastAPI app. Milestone 1: health + datasets only; the rest arrives in milestone 4."""
from __future__ import annotations

import os

from fastapi import FastAPI

from backend import settings

app = FastAPI(title="Plumewatch API")


@app.get("/api/health")
def health() -> dict:
    m = settings.load_manifest()
    return {
        "mode": {"mock_llm": settings.mock_llm(), "mock_omni": settings.mock_omni(), "demo_replay": settings.demo_replay()},
        "keys_present": {"openai": bool(os.getenv("OPENAI_API_KEY")), "omni": bool(os.getenv("OMNI_API_KEY"))},
        "assets": {k: v.get("status") for k, v in m.get("slots", {}).items()},
    }


@app.get("/api/datasets")
def datasets() -> list[dict]:
    m = settings.load_manifest()
    keys = ("slot_id", "status", "file", "normalized", "source_name", "source_url", "citation", "provider",
            "sha256", "date_coverage", "reason", "warnings")
    return [{k: v.get(k) for k in keys} for v in m.get("slots", {}).values()]
