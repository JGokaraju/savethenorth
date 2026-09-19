"""Orchestrator: live GPT (OpenAI Responses API, Chat Completions fallback) or the scripted mock trajectory.

The mock is also the fallback if the live model fails mid-run: it continues on the same RunState.
"""
from __future__ import annotations

import json
import os
import time
import traceback
from pathlib import Path

from backend.settings import max_agent_steps, mock_llm
from backend.tools.registry import for_model, openai_tools, run_tool
from backend.tools.state import RunState

PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "system.md"
SHOW = ["plume_map", "emission_distribution", "flare_timeline", "reporting_timeline", "regulatory_comparison", "annual_scenarios"]


# ====================================================================== verdict templating (mock + auto-complete)
def _find_call(st: RunState, name: str) -> dict | None:
    for c in reversed(st.tool_calls):
        if c["name"] == name and c["status"] == "ok":
            return st.results["_calls"][c["call_id"]]
    return None


def build_verdict(st: RunState) -> dict:
    f = st.facility or {"facility_id": st.facility_id, "name": st.facility_id}
    em = st.results.get("emission")
    if not em:
        gaps = ["No cached satellite observations for this facility and date — cannot assess.",
                "NO₂/NOx, permit MAERT and GHGRP data not provided."]
        return {"facility_id": st.facility_id, "facility_name": f["name"], "event_date_utc": st.date,
                "headline": f"No cached observations for {f['name']} on {st.date} — cannot assess.",
                "attribution": {"conclusion": "Not assessed (no observations).", "confidence": "low", "evidence": []},
                "likely_cause": {"conclusion": "Not assessed (no observations).", "confidence": "low", "evidence": []},
                "regulatory_findings": [], "data_gaps": gaps, "conflicts": [],
                "recommended_actions": ["Acquire satellite observations (EMIT / Carbon Mapper / Tanager) for this facility.",
                                        "Re-run the assessment once data is cached."],
                "charts": [], "evidence_ids": []}
    cmp_ = st.results.get("comparison")
    fl = st.results.get("flare") or {}
    ph = st.results.get("physics") or {}
    an = st.results.get("annual")
    regs = st.results.get("regulations", [])
    pm = (_find_call(st, "plume_map") or {}).get("data", {})
    status = {r["rule_id"]: r["status"] for r in regs}
    tx = status.get("TX_EMISSIONS_EVENT_REPORTING")
    tx_clause = {"NO_MATCHING_REPORT_FOUND": "no matching TCEQ emissions-event report found",
                 "REPORTED": "a matching TCEQ emissions-event report was found",
                 "BELOW_RQ": "below the Texas reportable quantity"}.get(tx, "Texas reporting not assessed")
    t = {k: em[f"{k}_kg_h"] / 1000 for k in ("median", "p5", "p95")}  # format from kg/h: avoid double rounding
    headline = (f"Estimated {t['median']:.1f} t/h [p5–p95 {t['p5']:.1f}–{t['p95']:.1f} t/h] of methane on "
                f"{st.date} — ~{em['times_super_emitter_threshold']:,.0f}× the 100 kg/h EPA super-emitter threshold; {tx_clause}.")
    omni = {c["target_id"]: c for c in st.omni_calls}
    attr_ev = [f"EMIT plume of {pm.get('n_pixels', '?')} pixels originates within 1 km of the source hint beside the "
               f"facility and extends ~{pm.get('plume_extent_downwind_km', '?')} km downwind",
               f"Plume axis aligned with the reanalysis wind (from {pm.get('wind_from_deg', '?')}°)"]
    if "plume_map" in omni:
        attr_ev.append(f"Huawei OMNI chart read ({omni['plume_map']['mode']}): {omni['plume_map']['answer'][:160]}")
    if "s2_truecolor" in omni:
        attr_ev.append("Sentinel-2 true colour is regional-scale and from 2026-09-18; it cannot resolve the plant (limitation)")
    cause_ev = []
    if fl:
        a = fl.get("nearest_after_overpass") or {}
        b = fl.get("nearest_before_overpass") or {}
        cause_ev.append(f"FIRMS: {fl['n_near_facility']} VIIRS detections ≤1.5 km in Aug 1–15; nearest "
                        f"{b.get('gap_hours', 'n/a')} h before and {a.get('gap_hours', 'n/a')} h after the overpass — a flare was burning around the overpass")
    if ph:
        cause_ev.append(f"Physics: slip from a lit flare at CE {ph['combustion_efficiency']} would need "
                        f"{ph['required_flared_ch4_t_h']:,.0f} t/h flared vs a ~{ph['ceiling_t_h']:.0f} t/h plant ceiling ({ph['classification']})")
    if "tceq_sob" in omni:
        cause_ev.append("Statement of Basis: amine and TEG flash gas is routed to the process flares (FL-3501/3502/3504)")
    cause = ("Likely a large uncombusted release associated with the flare/relief system — e.g. an unlit or malfunctioning "
             "flare, or a blowdown/relief venting event — rather than normal combustion slip; compressor or dehydrator "
             "venting cannot be ruled out." if ph.get("classification") == "flare_slip_implausible"
             else "Cause undetermined; combustion slip cannot be ruled out.")
    gaps = ["NO₂/NOx observations not ingested (NOx permit limits not assessed)",
            "Permit MAERT (NSR 177845) not ingested", "EPA GHGRP Subpart W data not provided",
            "Sentinel-2 images are 2026-09-18 regional screenshots — cannot show site conditions on the event date",
            "Wind from reanalysis grid point ~5 km away; no local temperature/pressure (defaults used)"]
    conflicts = []
    if cmp_:
        if cmp_.get("synthetic"):
            gaps.insert(0, "Carbon Mapper record is a SYNTHETIC placeholder — the cross-check provides no corroboration")
        if cmp_.get("conflict"):
            conflicts.append(f"Our estimate and Carbon Mapper differ by a factor of {cmp_['ratio']:.2f}")
    if (_find_call(st, "plume_map") or {}).get("warnings"):
        gaps.append("Plume reaches the crop edge — IME may be underestimated")
    if not conflicts:
        conflicts.append("None identified between the quantitative sources used")
    ev_all = sorted(k for k in st.ledger)
    v = {
        "facility_id": st.facility_id, "facility_name": f["name"], "event_date_utc": st.date, "headline": headline,
        "methane_estimate": {"median_kg_h": em["median_kg_h"], "p5_kg_h": em["p5_kg_h"], "p95_kg_h": em["p95_kg_h"],
                             "method": em["method"], "key_assumptions": em["key_assumptions"],
                             "evidence_ids": [e for e in ("emit_ch4enh", "emit_ch4uncert", "wind", "result:monte_carlo",
                                                          "assumption:wind.alpha", "assumption:wind.beta") if e in st.ledger]},
        "cross_check": ({"source": "Carbon Mapper" + (" (SYNTHETIC placeholder)" if cmp_.get("synthetic") else ""),
                         "their_kg_h": cmp_["their_kg_h"], "ratio": cmp_["ratio"], "consistent": cmp_["consistent"],
                         "note": cmp_["independence_note"] + (" SYNTHETIC placeholder value — illustrative only." if cmp_.get("synthetic") else ""),
                         "evidence_ids": [e for e in ("carbonmapper",) if e in st.ledger]}
                        if cmp_ else {"source": "Carbon Mapper", "note": "not available (data gap)"}),
        "attribution": {"conclusion": f"The plume is attributed to the {f['name']} (potentially responsible operator: "
                                      f"{f.get('operator', 'unknown').split(' — ')[0]}).",
                        "confidence": "high" if "plume_map" in omni else "medium", "evidence": attr_ev,
                        "evidence_ids": [e for e in ("emit_ch4enh", "wind") if e in st.ledger] +
                                        [c["id"] for c in st.omni_calls if c["target_id"] in ("plume_map", "s2_truecolor")]},
        "likely_cause": {"conclusion": cause, "confidence": "medium" if len(cause_ev) >= 2 else "low", "evidence": cause_ev,
                         "evidence_ids": [e for e in ("firms", "assumption:plant.combustion_efficiency", "assumption:plant.ch4_fraction",
                                                      "tceq_sob") if e in st.ledger] +
                                         [c["id"] for c in st.omni_calls if c["target_id"] in ("flare_timeline", "s2_swir", "tceq_sob")]},
        "annual_scenarios_t_ch4": ({**an["annual_t_ch4"], "caveat": an["caveat"],
                                    "evidence_ids": [e for e in ("carbonmapper", "result:monte_carlo") if e in st.ledger]}
                                   if an else {"caveat": "not computed"}),
        "regulatory_findings": [{k: r.get(k, "") for k in ("rule_id", "rule", "threshold", "observed", "status", "note")}
                                | {"evidence_ids": [e for e in r.get("evidence_ids", []) if e in st.ledger]} for r in regs],
        "data_gaps": gaps, "conflicts": conflicts,
        "recommended_actions": [
            "Request the potentially responsible operator's investigation and records for 2025-08-08 (flare pilot/ignition logs, compressor and blowdown logs, process upsets).",
            "Request or perform an optical gas imaging (OGI) survey of the flare, compression and dehydration areas.",
            "Review permit deviation reports and Title V semiannual deviation reports covering August 2025.",
            "Determine whether the event met emissions-event reporting criteria under 30 TAC 101.201.",
            "Task follow-up satellite overpasses to test whether the emission persists."],
        "charts": [c["chart_id"] for c in st.shown_charts],
        "evidence_ids": ev_all,
    }
    return v


# ====================================================================== mock trajectory
def _inventory_note(st: RunState) -> str:
    inv = (_find_call(st, "list_available_data") or {}).get("data", {})
    missing, flagged = inv.get("missing", []), inv.get("flagged", [])
    parts = ["The EMIT, wind and FIRMS slots cover the event window."]
    if flagged:
        parts.append(f"Flagged low-quality or SYNTHETIC: {', '.join(flagged)} — I will treat them as such.")
    if missing:
        parts.append(f"Missing: {', '.join(missing)}.")
    return " ".join(parts) + " Quantifying the plume next."


def _canonical(st: RunState) -> list[tuple]:
    fid, d = st.facility_id, st.date
    steps: list[tuple] = [
        ("list_skills", {}, "Starting with the skill catalogue and the facility registry."),
        ("find_facility", {"query": (st.facility or {}).get("name", fid)}, None),
        ("list_available_data", {"facility_id": fid}, None),
        ("load_skill", {"name": "data-discovery"}, "Checking which datasets exist and whether their dates line up with the event."),
    ]
    if not st.facility or st.facility.get("data_status") != "cached":
        return steps + [("load_skill", {"name": "verdict-report"}, "No cached observations for this facility; I will report that and stop."),
                        ("submit_verdict", {}, None)]
    return steps + [
        ("load_skill", {"name": "methane-quantification"}, _inventory_note),
        ("plume_map", {"facility_id": fid, "date": d}, None),
        ("analyze_chart", {"chart_id": "plume_map", "question": "Where does the plume originate relative to the facility marker, and which direction does it extend?"}, "Asking Huawei OMNI to read the plume map independently."),
        ("analyze_image", {"image_id": "s2_truecolor", "question": "Identify the gas processing plant footprint and infrastructure near the marked location."}, None),
        ("get_wind", {"facility_id": fid}, "Plume attribution looks clear; now the wind at the overpass, which drives the rate."),
        ("compute_emission_rate", {"facility_id": fid, "date": d}, None),
        ("analyze_chart", {"chart_id": "emission_distribution", "question": "Describe the distribution relative to the 100 kg/h threshold line and the Carbon Mapper line."}, None),
        ("compare_estimates", {"facility_id": fid, "date": d}, "Cross-checking against Carbon Mapper (same EMIT radiances, independent pipeline — not a fully independent measurement)."),
        ("load_skill", {"name": "flare-and-cause-analysis"}, "Turning to the likely cause: flare activity, imagery, permit and physics."),
        ("flare_activity", {"facility_id": fid, "start_date": "2025-08-01", "end_date": "2025-08-15"}, None),
        ("analyze_chart", {"chart_id": "flare_timeline", "question": "Were flares detected near the facility around the EMIT overpass, and how does activity vary over the period?"}, None),
        ("analyze_image", {"image_id": "s2_swir", "question": "Are there bright SWIR hot spots consistent with active flares?"}, None),
        ("read_document", {"doc_id": "tceq_sob", "question": "Extract processing capacity, flare IDs, and applicable federal rules as JSON"}, None),
        ("physics_bounds", {"facility_id": fid}, "Testing whether normal flare slip could explain a plume this large."),
        ("annualize", {"facility_id": fid}, None),
        ("load_skill", {"name": "texas-regulatory-check"}, "Now the regulatory screening against federal and Texas rules."),
        ("read_document", {"doc_id": "tceq_steers", "question": "List all incidents with dates as JSON"}, None),
        ("reporting_timeline", {"facility_id": fid}, None),
        ("check_regulations", {"facility_id": fid}, None),
        ("load_skill", {"name": "verdict-report"}, "Assembling the report and verdict."),
        *[("show_chart", {"chart_id": c, "caption": ""}, None) for c in SHOW],
        ("submit_verdict", {}, None),
    ]


def run_mock(st: RunState, delay: float = 0.0, skip_done: bool = False) -> None:
    done = {(c["name"], json.dumps(c["args"], sort_keys=True)) for c in st.tool_calls if c["status"] == "ok"} if skip_done else set()
    for name, args, note in _canonical(st):
        if st.finished:
            return
        if (name, json.dumps(args, sort_keys=True)) in done:
            continue
        if callable(note):
            note = note(st)
        if note:
            st.emit("assistant_message", {"text": note, "source": "scripted"})
        if name == "submit_verdict":
            args = {"verdict": build_verdict(st)}
        run_tool(st, name, args)
        if delay:
            time.sleep(delay)


# ====================================================================== live GPT
def _system_prompt(st: RunState) -> str:
    f = st.facility
    line = f"{f['name']} ({f.get('county')} County, {f.get('state')}), facility_id={f['facility_id']}" if f else st.facility_id
    return PROMPT.read_text(encoding="utf-8").replace("{facility_line}", line).replace("{date}", st.date)


def _user_msg(st: RunState) -> str:
    return (f"Assess facility_id '{st.facility_id}' for the event date {st.date}. Estimate the methane emission rate with "
            "uncertainty, attribute it, judge the likely cause, screen it against the regulations, and submit a verdict.")


def _run_responses(st: RunState, client, model: str) -> None:
    tools = openai_tools("responses")
    resp = client.responses.create(model=model, instructions=_system_prompt(st), input=_user_msg(st), tools=tools)
    for _ in range(max_agent_steps()):
        outputs = []
        for item in resp.output:
            if item.type == "message":
                text = "".join(getattr(c, "text", "") for c in item.content if getattr(c, "type", "") in ("output_text", "text"))
                if text.strip():
                    st.emit("assistant_message", {"text": text.strip(), "source": "gpt"})
            elif item.type == "function_call":
                args = json.loads(item.arguments or "{}")
                res = run_tool(st, item.name, args)
                outputs.append({"type": "function_call_output", "call_id": item.call_id, "output": for_model(res, item.name)})
        if st.finished:
            return
        if not outputs:  # model stopped talking without submitting
            outputs = [{"role": "user", "content": "Continue. Use tools; finish with show_chart and submit_verdict."}]
        resp = client.responses.create(model=model, previous_response_id=resp.id, input=outputs, tools=tools)


def _run_chat(st: RunState, client, model: str) -> None:
    tools = openai_tools("chat")
    msgs = [{"role": "system", "content": _system_prompt(st)}, {"role": "user", "content": _user_msg(st)}]
    for _ in range(max_agent_steps()):
        r = client.chat.completions.create(model=model, messages=msgs, tools=tools)
        m = r.choices[0].message
        msgs.append(m.model_dump(exclude_none=True))
        if m.content and m.content.strip():
            st.emit("assistant_message", {"text": m.content.strip(), "source": "gpt"})
        if not m.tool_calls:
            msgs.append({"role": "user", "content": "Continue. Use tools; finish with show_chart and submit_verdict."})
            continue
        for tc in m.tool_calls:
            res = run_tool(st, tc.function.name, json.loads(tc.function.arguments or "{}"))
            msgs.append({"role": "tool", "tool_call_id": tc.id, "content": for_model(res, tc.function.name)})
        if st.finished:
            return


def run_live(st: RunState) -> None:
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), timeout=120, max_retries=2)
    model = os.getenv("OPENAI_MODEL")
    try:
        _run_responses(st, client, model)
    except Exception as e:  # noqa: BLE001
        if st.tool_calls:  # failed mid-run: fall back to the scripted agent on the same state
            raise
        st.emit("assistant_message", {"text": f"Responses API unavailable ({str(e)[:120]}); using Chat Completions.", "source": "system"})
        _run_chat(st, client, model)


# ====================================================================== entry point
def run(st: RunState) -> None:
    st.emit("run_started", {"facility_id": st.facility_id, "date": st.date, "mode": st.mode})
    try:
        if st.mode == "LIVE":
            try:
                run_live(st)
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                st.emit("error", {"message": f"Live orchestrator failed: {str(e)[:300]}. Continuing with the scripted agent.",
                                  "recoverable": True})
            if not st.finished:
                if st.tool_calls:
                    st.emit("assistant_message", {"text": "Completing the remaining steps with the scripted agent.", "source": "system"})
                run_mock(st, skip_done=True)
        else:
            run_mock(st, delay=float(os.getenv("MOCK_STEP_DELAY", "0.15")))
        if not st.finished:  # last resort: templated verdict so the UI always gets one
            run_tool(st, "submit_verdict", {"verdict": build_verdict(st)})
        if st.verdict:
            st.emit("verdict", {"verdict": st.verdict, "shown_charts": st.shown_charts})
            (st.dir / "verdict.json").write_text(json.dumps(st.verdict, indent=1, default=str), encoding="utf-8")
        (st.dir / "ledger.json").write_text(json.dumps(st.public_ledger(), indent=1, default=str), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        st.emit("error", {"message": f"{type(e).__name__}: {e}", "recoverable": False})
    finally:
        st.finished = True
        st.emit("run_finished", {"ok": st.verdict is not None, "n_tool_calls": len(st.tool_calls)})


def mode() -> str:
    return "MOCK" if mock_llm() else "LIVE"

