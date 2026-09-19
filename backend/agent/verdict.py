"""Verdict schema (spec §10) and validation against RunState values."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["low", "medium", "high"]
DISCLAIMER = "Satellite-based screening estimate; not an enforcement determination."


class MethaneEstimate(BaseModel):
    median_kg_h: float | None = None
    p5_kg_h: float | None = None
    p95_kg_h: float | None = None
    method: str = "IME (EMIT L2B CH4ENH) + Monte Carlo"
    key_assumptions: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class CrossCheck(BaseModel):
    source: str = "Carbon Mapper"
    their_kg_h: float | None = None
    ratio: float | None = None
    consistent: bool | None = None
    note: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    conclusion: str
    confidence: Confidence
    evidence: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class AnnualScenarios(BaseModel):
    low: float | None = None
    central: float | None = None
    high: float | None = None
    caveat: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class RegulatoryFinding(BaseModel):
    rule_id: str
    rule: str = ""
    threshold: str = ""
    observed: str = ""
    status: str
    note: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class Verdict(BaseModel):
    facility_id: str
    facility_name: str
    event_date_utc: str
    headline: str
    methane_estimate: MethaneEstimate = Field(default_factory=MethaneEstimate)
    cross_check: CrossCheck = Field(default_factory=CrossCheck)
    attribution: Finding
    likely_cause: Finding
    annual_scenarios_t_ch4: AnnualScenarios = Field(default_factory=AnnualScenarios)
    regulatory_findings: list[RegulatoryFinding] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    charts: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER


def _close(a, b, tol=0.01) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= tol * max(abs(float(b)), 1e-9)


def validate(raw: dict, st) -> tuple[Verdict | None, list[str]]:
    """Returns (verdict, errors). Numbers must match RunState within 1%."""
    errors: list[str] = []
    try:
        v = Verdict.model_validate(raw)
    except Exception as e:  # pydantic ValidationError
        return None, [f"schema: {e}"]
    if v.facility_id != st.facility_id:
        errors.append(f"facility_id must be '{st.facility_id}'")
    em = st.results.get("emission")
    if em:
        for k in ("median_kg_h", "p5_kg_h", "p95_kg_h"):
            if not _close(getattr(v.methane_estimate, k), em[k]):
                errors.append(f"methane_estimate.{k}={getattr(v.methane_estimate, k)} does not match computed {em[k]}")
    elif v.methane_estimate.median_kg_h is not None:
        errors.append("methane_estimate given but no emission rate was computed in this run")
    cmp_ = st.results.get("comparison")
    if cmp_ and v.cross_check.their_kg_h is not None:
        if not _close(v.cross_check.their_kg_h, cmp_["their_kg_h"]):
            errors.append(f"cross_check.their_kg_h must be {cmp_['their_kg_h']}")
        if v.cross_check.ratio is not None and not _close(v.cross_check.ratio, cmp_["ratio"], 0.02):
            errors.append(f"cross_check.ratio must be {cmp_['ratio']}")
    an = st.results.get("annual")
    if an:
        for k in ("low", "central", "high"):
            val = getattr(v.annual_scenarios_t_ch4, k)
            if val is not None and not _close(val, an["annual_t_ch4"][k]):
                errors.append(f"annual_scenarios_t_ch4.{k} must be {an['annual_t_ch4'][k]}")
    regs = {r["rule_id"]: r["status"] for r in st.results.get("regulations", [])}
    for f in v.regulatory_findings:
        if f.rule_id in regs and f.status != regs[f.rule_id]:
            errors.append(f"regulatory finding {f.rule_id} status must be {regs[f.rule_id]} (from check_regulations)")
    if st.results.get("emission") and not regs:
        errors.append("call check_regulations before submit_verdict")
    known = set(st.ledger)
    all_ids = set(v.evidence_ids) | set(v.methane_estimate.evidence_ids) | set(v.cross_check.evidence_ids) \
        | set(v.attribution.evidence_ids) | set(v.likely_cause.evidence_ids) | set(v.annual_scenarios_t_ch4.evidence_ids) \
        | {e for f in v.regulatory_findings for e in f.evidence_ids}
    unknown = sorted(all_ids - known)
    if unknown:
        errors.append(f"evidence_ids not in the Evidence Ledger: {unknown}. Valid ids: {sorted(known)[:40]}")
    bad_words = [w for w in ("violated", "violation of law", "illegal", "broke the law") if w in v.model_dump_json().lower()]
    if bad_words:
        errors.append(f"use careful regulatory language; avoid: {bad_words}")
    return (v if not errors else None), errors
