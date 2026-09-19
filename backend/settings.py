"""Paths, env flags and config loading shared by the whole backend."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

ASSETS = ROOT / "assets"
DATA = ROOT / "data"
NORMALIZED = DATA / "normalized"
PROCESSED = DATA / "processed"
CHARTS_DIR = PROCESSED / "charts"
RUNS_DIR = DATA / "runs"
CACHE_DIR = DATA / "cache"
MANIFEST = DATA / "manifest.yaml"
FACILITIES = DATA / "facilities.json"
CASE_YAML = Path(__file__).resolve().parent / "config" / "case.yaml"
SKILLS_DIR = ROOT / "skills"

for _d in (NORMALIZED, PROCESSED, CHARTS_DIR, RUNS_DIR, CACHE_DIR / "omni", CACHE_DIR / "llm"):
    _d.mkdir(parents=True, exist_ok=True)


def _flag(name: str, key_var: str) -> bool:
    """auto -> on when the corresponding API key is empty."""
    v = os.getenv(name, "auto").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return not os.getenv(key_var, "").strip()


def mock_llm() -> bool:
    return _flag("MOCK_LLM", "OPENAI_API_KEY") or not os.getenv("OPENAI_MODEL", "").strip()


def mock_omni() -> bool:
    return _flag("MOCK_OMNI", "OMNI_API_KEY") or not os.getenv("OMNI_BASE_URL", "").strip()


def demo_replay() -> bool:
    return os.getenv("DEMO_REPLAY", "0").strip().lower() in ("1", "true", "yes")


def max_agent_steps() -> int:
    return int(os.getenv("MAX_AGENT_STEPS", "30"))


@lru_cache
def case_config() -> dict:
    with open(CASE_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


def cfg(section: str, key: str):
    """Value of a case.yaml constant (entries are {value, unit, rationale, verify})."""
    entry = case_config()[section][key]
    return entry["value"] if isinstance(entry, dict) and "value" in entry else entry


def cfg_entry(section: str, key: str) -> dict:
    return case_config()[section][key]


@lru_cache
def facilities() -> list[dict]:
    with open(FACILITIES, encoding="utf-8") as f:
        return json.load(f)


def facility(facility_id: str) -> dict | None:
    return next((f for f in facilities() if f["facility_id"] == facility_id), None)


def load_manifest() -> dict:
    if not MANIFEST.exists():
        return {"slots": {}}
    with open(MANIFEST, encoding="utf-8") as f:
        return yaml.safe_load(f) or {"slots": {}}
