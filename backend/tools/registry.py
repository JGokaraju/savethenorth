"""Tool registry: Pydantic input models -> OpenAI function schemas; run_tool() executes with events + ledger."""
from __future__ import annotations

import json
import traceback
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, Field

from backend.charts.base import load as load_chart
from backend.science.common import DataGap
from backend.tools import envelope, meta_tools, omni_tools, science_tools
from backend.tools.state import RunState, get_state, new_state  # noqa: F401  (re-exported)


class NoArgs(BaseModel):
    pass


class SkillName(BaseModel):
    name: str = Field(description="Skill name, e.g. 'data-discovery'")


class Query(BaseModel):
    query: str = Field(description="Facility name, alias, city or county")


class FacilityId(BaseModel):
    facility_id: str


class SlotId(BaseModel):
    slot_id: str = Field(description="Manifest slot id, e.g. 'emit_ch4enh', 'wind', 'firms'")


class FacilityDate(BaseModel):
    facility_id: str
    date: str | None = Field(None, description="Event date YYYY-MM-DD")


class WindArgs(BaseModel):
    facility_id: str
    datetime_utc: str | None = Field(None, description="ISO UTC time; default = EMIT overpass")


class EmissionArgs(BaseModel):
    facility_id: str
    date: str | None = None
    k: float | None = Field(None, description="Mask threshold multiplier (1.5, 2, 2.5, 3, 4); default 2.5")


class FlareArgs(BaseModel):
    facility_id: str
    start_date: str | None = Field(None, description="YYYY-MM-DD, default 2025-08-01")
    end_date: str | None = Field(None, description="YYYY-MM-DD, default 2025-08-15")


class PhysicsArgs(BaseModel):
    facility_id: str
    q_kg_h: float | None = Field(None, description="Emission rate to test; default = this run's median estimate")


class ChartQuestion(BaseModel):
    chart_id: str
    question: str


class ImageQuestion(BaseModel):
    image_id: str = Field(description="'s2_truecolor' or 's2_swir'")
    question: str


class DocQuestion(BaseModel):
    doc_id: str = Field(description="'tceq_sob' or 'tceq_steers'")
    question: str
    pages: list[int] | None = Field(None, description="Optional 1-based page numbers (max 3); default = keyword search")


class ShowChart(BaseModel):
    chart_id: str
    caption: str = ""


class VerdictArgs(BaseModel):
    verdict: dict[str, Any] = Field(description="Verdict object following the schema in the verdict-report skill")


@dataclass
class Tool:
    name: str
    fn: Callable
    model: type[BaseModel]
    description: str


TOOLS: dict[str, Tool] = {t.name: t for t in [
    Tool("list_skills", meta_tools.list_skills, NoArgs, "List available skill playbooks (name + one-line description)."),
    Tool("load_skill", meta_tools.load_skill, SkillName, "Load a skill playbook (markdown) before an analysis phase."),
    Tool("find_facility", meta_tools.find_facility, Query, "Fuzzy-search the facility registry."),
    Tool("list_available_data", meta_tools.list_available_data, FacilityId, "List data slots for a facility with status, dates, quality flags."),
    Tool("describe_dataset", meta_tools.describe_dataset, SlotId, "Units, dims, coverage, bbox and basic stats of a dataset."),
    Tool("plume_map", science_tools.plume_map, FacilityDate, "Crop EMIT enhancement, build plume mask and plume map chart."),
    Tool("get_wind", science_tools.get_wind, WindArgs, "10 m wind at the overpass (U10, direction, σ_U, P, T) + wind chart."),
    Tool("compute_emission_rate", science_tools.compute_emission_rate, EmissionArgs,
         "IME emission rate with Monte Carlo uncertainty + distribution and wind-sensitivity charts."),
    Tool("compare_estimates", science_tools.compare_estimates, FacilityDate, "Compare our estimate with Carbon Mapper's for the same plume/date."),
    Tool("flare_activity", science_tools.flare_activity, FlareArgs, "FIRMS VIIRS flare detections near the facility + timeline chart."),
    Tool("physics_bounds", science_tools.physics_bounds, PhysicsArgs, "Plant throughput ceiling and flare-slip plausibility."),
    Tool("annualize", science_tools.annualize, FacilityId, "Annualized emission scenarios from detection frequency + chart."),
    Tool("reporting_timeline", science_tools.reporting_timeline, FacilityId, "Parse STEERS events; timeline of detections vs reports."),
    Tool("check_regulations", science_tools.check_regulations, FacilityId, "Evaluate regulatory screening rules from this run's results + chart."),
    Tool("analyze_chart", omni_tools.analyze_chart, ChartQuestion, "Huawei OMNI: interpret a chart image qualitatively."),
    Tool("analyze_image", omni_tools.analyze_image, ImageQuestion, "Huawei OMNI: interpret a Sentinel-2 image around the facility."),
    Tool("read_document", omni_tools.read_document, DocQuestion, "Huawei OMNI: read rendered document pages (TCEQ permit / STEERS)."),
    Tool("show_chart", meta_tools.show_chart, ShowChart, "Add a chart to the final report panel."),
    Tool("submit_verdict", meta_tools.submit_verdict, VerdictArgs, "Submit the final verdict; validated against computed results."),
]}


def openai_tools(style: str = "responses") -> list[dict]:
    out = []
    for t in TOOLS.values():
        params = t.model.model_json_schema()
        params.pop("title", None)
        for p in params.get("properties", {}).values():
            p.pop("title", None)
        params.setdefault("properties", {})
        if style == "responses":
            out.append({"type": "function", "name": t.name, "description": t.description, "parameters": params})
        else:
            out.append({"type": "function", "function": {"name": t.name, "description": t.description, "parameters": params}})
    return out


def run_tool(st: RunState, name: str, args: dict | None) -> dict:
    """Execute a tool; never raises. Emits tool_call / tool_result / chart events; feeds the ledger."""
    args = dict(args or {})
    call_id = f"call-{len(st.tool_calls) + 1:02d}-{uuid.uuid4().hex[:4]}"
    st.current_call_id = call_id
    st.emit("tool_call", {"call_id": call_id, "name": name, "args": args})
    tool = TOOLS.get(name)
    if tool is None:
        res = envelope.error(f"unknown tool '{name}'")
    else:
        try:
            parsed = tool.model.model_validate(args)
            res = tool.fn(st, **parsed.model_dump())
        except DataGap as e:
            res = envelope.gap(str(e))
        except Exception as e:  # noqa: BLE001 — a tool error is reported, never crashes the run
            traceback.print_exc()
            res = envelope.error(f"{type(e).__name__}: {e}")
    for rec in res.get("data_used", []):
        st.add_data_used(rec, name)
    res["evidence_ids"] = list(dict.fromkeys(res.get("evidence_ids", []) + [r["slot_id"] for r in res.get("data_used", [])]))
    res["call_id"] = call_id
    st.results.setdefault("_calls", {})[call_id] = res
    st.tool_calls.append({"call_id": call_id, "name": name, "args": args, "status": res["status"], "summary": res["summary"],
                          "charts": res.get("charts", []), "evidence_ids": res["evidence_ids"]})
    for eid in res["evidence_ids"]:
        if eid in st.ledger:
            st.ledger[eid].setdefault("tool_call_ids", [])
            if call_id not in st.ledger[eid]["tool_call_ids"]:
                st.ledger[eid]["tool_call_ids"].append(call_id)
    st.emit("tool_result", {"call_id": call_id, "name": name, "status": res["status"], "summary": res["summary"],
                            "charts": res.get("charts", []), "evidence_ids": res["evidence_ids"],
                            "warnings": res.get("warnings", []), "data": _compact(res.get("data", {}), name)})
    for cid in res.get("charts", []):
        art = load_chart(cid)
        if art:
            st.emit("chart", {"chart_id": cid, "title": art.title, "figure_json": art.figure_json, "call_id": call_id})
    st.current_call_id = None
    return res


def _compact(data: dict, name: str) -> dict:
    """Trim big payloads for the event stream (skill content, verdict are kept)."""
    if name == "load_skill":
        return {"name": data.get("name")}
    s = json.dumps(data, default=str)
    if len(s) < 6000:
        return json.loads(s)
    return {k: v for k, v in data.items() if len(json.dumps(v, default=str)) < 1500}


def for_model(res: dict, name: str) -> str:
    """Compact JSON sent back to GPT: summary, key data fields and chart ids — never raw arrays."""
    data = res.get("data", {})
    if name == "load_skill":
        payload_data = {"content": data.get("content", "")}
    else:
        payload_data = {}
        for k, v in data.items():
            s = json.dumps(v, default=str)
            payload_data[k] = v if len(s) <= 1800 else (s[:1800] + "…(truncated)")
    return json.dumps({"status": res["status"], "summary": res["summary"], "data": payload_data,
                       "charts": res.get("charts", []), "evidence_ids": res.get("evidence_ids", []),
                       "assumptions": res.get("assumptions", []), "warnings": res.get("warnings", [])}, default=str)
