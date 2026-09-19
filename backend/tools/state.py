"""Per-run state: tool outputs, evidence ledger, chart registry and the event emitter."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from backend.settings import RUNS_DIR, ROOT, case_config, facility

_RUNS: dict[str, "RunState"] = {}
_LOCK = threading.Lock()


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class RunState:
    run_id: str
    facility_id: str
    date: str
    results: dict[str, Any] = field(default_factory=dict)       # tool name -> envelope
    cache: dict[str, Any] = field(default_factory=dict)         # heavy python objects (crop, masks, ...)
    ledger: dict[str, dict] = field(default_factory=dict)       # evidence_id -> record
    charts: dict[str, dict] = field(default_factory=dict)       # chart_id -> {title, summary_stats, png_path}
    shown_charts: list[dict] = field(default_factory=list)
    skills_loaded: list[str] = field(default_factory=list)
    omni_calls: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    verdict: dict | None = None
    finished: bool = False
    emitter: Callable[[str, dict], None] | None = None
    events: list[dict] = field(default_factory=list)
    mode: str = "MOCK"
    current_call_id: str | None = None

    # ------------------------------------------------------------------ paths
    @property
    def dir(self) -> Path:
        p = RUNS_DIR / self.run_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def evidence_dir(self) -> Path:
        p = self.dir / "evidence"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def evidence_ref(self, name: str) -> str:
        return f"evidence/{name}"  # relative to the run: served at /api/runs/{run_id}/evidence/{name}

    @property
    def facility(self) -> dict | None:
        return facility(self.facility_id)

    # ------------------------------------------------------------------ events
    def emit(self, type_: str, payload: dict) -> None:
        ev = {"type": type_, "ts": now_iso(), "run_id": self.run_id, **payload}
        self.events.append(ev)
        with open(RUNS_DIR / f"{self.run_id}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, default=str) + "\n")
        if self.emitter:
            self.emitter(type_, ev)

    # ------------------------------------------------------------------ ledger
    def add_data_used(self, rec: dict, tool: str) -> str:
        eid = rec.get("id") or rec["slot_id"]
        cur = self.ledger.get(eid)
        if cur is None:
            cur = {"id": eid, "type": "data", **rec, "used_by_tools": [], "tool_call_ids": [], "subsets": []}
            self.ledger[eid] = cur
        else:
            for k in ("preview_ref", "record_count", "subset"):
                if rec.get(k) is not None and cur.get(k) is None:
                    cur[k] = rec[k]
        if tool not in cur["used_by_tools"]:
            cur["used_by_tools"].append(tool)
        if self.current_call_id and self.current_call_id not in cur["tool_call_ids"]:
            cur["tool_call_ids"].append(self.current_call_id)
        sub = {k: rec.get(k) for k in ("subset", "record_count", "preview_ref", "extra_refs") if rec.get(k) is not None}
        if sub and sub not in cur["subsets"]:
            cur["subsets"].append({**sub, "tool": tool})
        return eid

    def add_assumption(self, section: str, key: str, tool: str, value_override=None, note: str | None = None) -> str:
        entry = case_config()[section][key]
        eid = f"assumption:{section}.{key}"
        cur = self.ledger.setdefault(eid, {
            "id": eid, "type": "assumption", "source": "backend/config/case.yaml", "name": f"{section}.{key}",
            "value": entry.get("value") if value_override is None else value_override, "unit": entry.get("unit"),
            "rationale": note or entry.get("rationale"), "verify": bool(entry.get("verify")),
            "range": entry.get("range"), "used_by_tools": []})
        if tool not in cur["used_by_tools"]:
            cur["used_by_tools"].append(tool)
        return eid

    def add_facility_assumption(self, key: str, tool: str) -> str:
        eid = f"assumption:facility.{key}"
        f = self.facility or {}
        cur = self.ledger.setdefault(eid, {
            "id": eid, "type": "assumption", "source": "data/facilities.json", "name": f"facility.{key}",
            "value": f.get(key), "unit": {"design_capacity_mmscfd": "MMscfd"}.get(key, ""),
            "rationale": "hard-coded facility metadata (permit documents / public records)", "verify": False,
            "used_by_tools": []})
        if tool not in cur["used_by_tools"]:
            cur["used_by_tools"].append(tool)
        return eid

    def add_derived_note(self, eid: str, rec: dict, tool: str) -> str:
        """Records that are neither files nor constants (e.g. an OMNI call or a synthetic flag)."""
        cur = self.ledger.setdefault(eid, {"id": eid, **rec, "used_by_tools": []})
        if tool not in cur["used_by_tools"]:
            cur["used_by_tools"].append(tool)
        return eid

    def public_ledger(self) -> list[dict]:
        return [dict(v) for v in self.ledger.values()]


def new_state(facility_id: str, date: str, run_id: str | None = None, mode: str = "MOCK") -> RunState:
    prefix = "test-" if os.getenv("PYTEST_CURRENT_TEST") else ""  # keep test runs out of the recent-runs listing
    rid = run_id or (prefix + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6])
    st = RunState(rid, facility_id, date, mode=mode)
    with _LOCK:
        _RUNS[rid] = st
    return st


def get_state(run_id: str) -> RunState | None:
    return _RUNS.get(run_id)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()
