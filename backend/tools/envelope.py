"""Tool result envelope + data_used record helpers."""
from __future__ import annotations

from typing import Any


def ok(summary: str, data: dict | None = None, charts: list[str] | None = None, evidence_ids: list[str] | None = None,
       assumptions: list[str] | None = None, warnings: list[str] | None = None, data_used: list[dict] | None = None) -> dict:
    return {"status": "ok", "summary": summary, "data": data or {}, "charts": charts or [],
            "evidence_ids": evidence_ids or [], "assumptions": assumptions or [], "warnings": warnings or [],
            "data_used": data_used or []}


def gap(reason: str, **kw: Any) -> dict:
    return {"status": "data_gap", "summary": f"Data gap: {reason}", "data": {"reason": reason, **kw.pop("data", {})},
            "charts": [], "evidence_ids": kw.get("evidence_ids", []), "assumptions": [], "warnings": [],
            "data_used": []}


def error(msg: str) -> dict:
    return {"status": "error", "summary": f"Tool error: {msg}", "data": {"error": msg}, "charts": [],
            "evidence_ids": [], "assumptions": [], "warnings": [], "data_used": []}


def data_used(slot_rec: dict, subset: str, record_count: int | None = None, preview_ref: str | None = None,
              extra_refs: list[str] | None = None, file_override: str | None = None) -> dict:
    """Build a ledger record from a manifest slot record."""
    return {
        "slot_id": slot_rec["slot_id"],
        "file": file_override or slot_rec.get("file"),
        "normalized": slot_rec.get("normalized"),
        "sha256": slot_rec.get("sha256"),
        "source_name": slot_rec.get("source_name"),
        "source_url": slot_rec.get("source_url"),
        "citation": slot_rec.get("citation"),
        "provider": slot_rec.get("provider"),
        "date_coverage": slot_rec.get("date_coverage"),
        "retrieved_note": "provided by team, see data/manifest.yaml" if not slot_rec.get("synthetic")
        else "SYNTHETIC placeholder generated at the team's request (data/synthetic/README.md)",
        "synthetic": bool(slot_rec.get("synthetic")),
        "quality": slot_rec.get("quality", "ok"),
        "warnings": slot_rec.get("warnings", []),
        "subset": subset, "record_count": record_count, "preview_ref": preview_ref,
        "extra_refs": extra_refs,
    }
