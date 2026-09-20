"""Field mode: a spoken question from someone standing at the site, answered by OMNI.

This is the third OMNI modality (audio in, alongside the site image, answered in language). It is
deliberately NOT in the orchestrator's tool registry: the desk assessment has no microphone and no
inspector, so there is nothing for the agent to call it with. It is exposed to the operator through
`POST /api/field-note` instead, and obeys the same rule as every other OMNI tool — qualitative
observations only, never a number that feeds a calculation.
"""
from __future__ import annotations

from pathlib import Path

from backend.llm import omni
from backend.science.common import DataGap, slot
from backend.settings import ROOT, facilities

# Kept short: a spoken question carries its own context, and OMNI answers better with a tight brief.
PROMPT = (
    "You are answering an environmental inspector who is standing at {name} ({county} County, {state}) "
    "and has just asked you a question out loud. The recording of their question is attached, together "
    "with an aerial view of the site.\n"
    "Answer in two or three sentences, in plain spoken English, as if replying over a radio.\n"
    "Rules: describe only what is visible in the image or what you are told here. Do not estimate or "
    "quote any emission rate, concentration or mass — the measurement comes from the satellite analysis, "
    "not from you. If the question needs a number, say which part of the assessment report holds it. "
    "If you cannot make out the question, say so and ask them to repeat it."
)

CONTEXT = (
    "\n\nWhat the desk assessment already established for this site: {summary}"
)

MOCK = (
    "[demo] I can see the processing train, the flare stack at the north end of the pad and the tank "
    "battery beside it. I can't measure anything from here — the emission rate and the threshold "
    "comparison are in the screening report's summary. Nothing in this view contradicts it."
)


def _site_image(facility_id: str) -> Path | None:
    if facility_id != "tx-lenorah-redlake":
        return None
    try:
        img = slot("site_imagery").get("images", {}).get("site")
    except DataGap:
        return None
    return ROOT / img["normalized"] if img else None


def field_question(facility_id: str, audio_bytes: bytes, audio_format: str = "webm",
                   context_summary: str | None = None) -> dict:
    """Answer a spoken question about a site. Returns {answer, mode, model, facility, image_used}."""
    if not audio_bytes:
        raise ValueError("no audio in the request")
    fac = next((f for f in facilities() if f["facility_id"] == facility_id), None)
    if fac is None:
        raise KeyError(f"unknown facility: {facility_id}")

    prompt = PROMPT.format(name=fac["name"], county=fac.get("county", "—"), state=fac.get("state", "—"))
    if context_summary:
        prompt += CONTEXT.format(summary=context_summary[:600])

    img = _site_image(facility_id)
    res = omni.ask(prompt, image_path=img, audio_bytes=audio_bytes, audio_format=audio_format, mock_text=MOCK)
    return {"answer": res["answer"], "mode": res["mode"].upper(), "model": res["model"],
            "facility": fac["name"], "image_used": bool(img),
            "modalities": ["audio", "image", "text"] if img else ["audio", "text"]}
