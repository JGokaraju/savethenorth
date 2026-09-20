# Save the North — Devpost

## 💡 Inspiration

How do we make sure factories don't pollute more than they are allowed to? How do we know that an oil and gas operator is actually following the environmental regulations it is bound by?

Today, that question is answered mostly by hand. A regulator who wants to check a single release has to pull a satellite granule, find the matching weather reanalysis, hunt down the facility's permit, search a state database for self-reported emissions events, and then ask an atmospheric scientist to run a plume-inversion model — for one plume, on one day, at one plant. The United States has hundreds of thousands of oil and gas sites. The arithmetic of that simply does not work.

So the gaps are enormous, and they are not exotic ones. On **8 August 2025 at 14:45 UTC**, NASA's EMIT imaging spectrometer flew over Martin County, Texas and recorded a methane plume stretching nearly five kilometres downwind of the Lenorah / Red Lake gas plants. In the Texas emissions-event records we were able to export for that facility, there is no matching report anywhere near that date. A plume that large should be one of the most visible events in the Permian Basin, and in the paperwork it is simply absent.

That is the gap we wanted to close: not "detect methane" — satellites already do that — but **do the reasoning that turns a detection into something a regulator can act on**, and do it in minutes instead of weeks.

## 🎯 Goal

Our goal was to build an agent that can reason its way from raw, messy, multi-source observations to a defensible regulatory screening conclusion:

- NASA EMIT L2B methane enhancement, uncertainty and sensitivity rasters
- NASA FIRMS VIIRS thermal detections (flaring activity near the plant)
- ERA5 / Open-Meteo wind, temperature and pressure at the overpass hour
- Copernicus Sentinel-2 true-colour and shortwave-infrared imagery
- The operator's own TCEQ Title V permit (Statement of Basis, 18 pages of PDF)
- TCEQ STEERS emissions-event reports the operator filed itself
- Carbon Mapper plume records as an independent cross-check

…and to answer one question about a named facility on a named date: **does the observed release exceed what the law allows, and did the operator report it?**

The hard part was never calling an API. It was making an agent that can hold together a physics calculation, a legal threshold, a document, and a data gap at the same time — and be honest about which of those it actually has.

## 🔭 What is Save the North?

Save the North is a satellite emissions verification agent. You give it a facility and a date. It plans its own investigation, calls twenty deterministic tools, reads charts and documents with a multimodal model, screens the result against federal and Texas rules, ranks its own evidence, and produces a screening report where **every number is traceable to a file with a SHA-256 hash**.

For the Lenorah / Red Lake case it concludes:

| | |
|---|---|
| **Observed methane** | 23.0 t/h (22,954 kg/h, p5–p95 14,955–29,126 kg/h) |
| **Federal super-emitter threshold** | 0.1 t/h (100 kg/h, 40 CFR 60.5371a/b) |
| **In CO₂-equivalent terms** | 684 t CO₂e/h observed against 3.0 t CO₂e/h allowed (GWP100 = 29.8, IPCC AR6) |
| **Ratio** | ~230× the codified threshold |
| **Reported to TCEQ within ±1 day** | none found in the exported records |
| **Screening outcome** | **FAILED** |

The plume itself: 672 attributed pixels covering 2.05 km², peak enhancement 13,371 ppm·m, extending ~4.8 km downwind, in a 4.20 ± 1.26 m/s wind from 194°.

The verdict wording is deliberately careful. The agent is forbidden from saying anyone "violated the law" — it says the observation *exceeds the codified threshold*, and names a *potentially responsible operator*. A screening estimate is not an enforcement determination, and the product should not pretend otherwise.

### End-to-end agent pipeline

The agent runs five phases, and you watch it happen live — the trace streams over SSE, showing each tool call along with the actual chart, satellite image or permit page it is reading at that moment.

1. **Discover** — load the skill playbooks, find the facility, inventory what data exists, and, crucially, what doesn't. Every dataset carries status, date coverage and quality flags.
2. **Quantify** — crop the EMIT scene, build a plume mask, pull the wind at the overpass hour, and compute the emission rate with a Monte Carlo uncertainty envelope.
3. **Explain** — look for flares in VIIRS around the overpass, inspect Sentinel-2 imagery, read the permit, and test the estimate against the plant's physical throughput ceiling.
4. **Screen** — evaluate the federal super-emitter rule, the Texas emissions-event reporting rule (30 TAC 101.201), NOx permit limits and greenhouse-gas reporting, each with an explicit status.
5. **Rank and conclude** — hybrid-search and rerank every piece of evidence the run produced, then submit a verdict that is validated against the computed numbers before it is allowed through.

A typical run is **32 tool calls and 7 multimodal readings in about three minutes**.

## 🛠️ How we built it

**A hard separation between reasoning and arithmetic.** This is the design decision everything else hangs off:

- **GPT-5.6-sol (OpenAI Responses API, function calling)** is the orchestrator. It decides what to look at next, what is worth explaining, and what the evidence adds up to. It never performs a calculation. Every number in the final report was produced by Python.
- **Python does the science, deterministically.** Integrated Mass Enhancement after Varon et al. (2018): a robust background from a 2.5–4 km annulus with the dilated plume excluded (median and MAD × 1.4826), k·σ thresholding, a 3×3 morphological opening, connected components kept only within 1 km of the source, then ΔΩ → IME → Q = U_eff · IME / √A with U_eff = α·ln(U10) + β. Uncertainty is a 2,000-draw Monte Carlo over background, wind, calibration and mask choice with a fixed seed, so the same inputs always give the same answer.
- **Huawei OMNI (qwen3.5-omni-flash)** reads the things that are pictures and documents rather than arrays: the plume map, the Monte Carlo distribution, the flare timeline, Sentinel-2 crops, and rendered pages of the TCEQ permit. Its answers are *qualitative only* — OMNI is explicitly never allowed to supply a number that enters a calculation. It describes shape, direction, plausibility and document content; Python owns the math.
- **Field mode** adds OMNI's third modality. On the report there is a record button: an inspector standing at the site holds it, asks a question out loud, and the recording is sent to OMNI together with the aerial view of that facility and the desk assessment's one-line finding. Audio, image and language go up in a single request; a spoken answer comes back as text, under the same rule as every other OMNI call — it may describe what it sees, and it may point you at the part of the report that holds a number, but it may not invent one.

**Twenty tools**, each returning the same envelope (`status`, `summary`, `data`, `charts`, `evidence_ids`, `assumptions`, `warnings`, `data_used`): `plume_map`, `get_wind`, `compute_emission_rate`, `compare_estimates`, `flare_activity`, `physics_bounds`, `annualize`, `reporting_timeline`, `check_regulations`, `rank_evidence`, three OMNI tools, and the meta-tools for skills, data inventory and verdict submission.

**Five markdown skill playbooks** the agent loads before each phase — `data-discovery`, `methane-quantification`, `flare-and-cause-analysis`, `texas-regulatory-check`, `verdict-report`. They encode the method (how to pick a mask threshold, when a flare is close enough in time to matter, what the Texas reportable quantity actually is) as instructions rather than code, so the analysis procedure is readable and reviewable by a domain expert who doesn't write Python.

**Hybrid evidence ranking.** Before the agent is allowed to submit a verdict, it must call `rank_evidence`, which builds a corpus out of everything the run produced — tool results, assumptions, warnings, document readings, regulatory statuses — and ranks it against five fixed questions (threshold, reporting, attribution, cause, reliability). The pipeline is BM25 (Okapi, with stopwording and hyphen splitting) **plus** dense vectors (OpenAI `text-embedding-3-small`, or a local hashed n-gram vectoriser offline), fused with **reciprocal rank fusion (k = 60)**, then **reranked by an LLM** on importance per question, with the five reranks running in parallel. Ranked IDs are validated back against the ledger; importance scores outside [0, 1] are rejected. The reranker speaks the OpenAI chat protocol, so it can be pointed at a Baseten endpoint by changing three environment variables.

**An evidence ledger, not a chat log.** Every dataset the agent touches is recorded with its SHA-256, citation, date coverage and quality flags; every hard-coded constant is an assumption record with a `verify` flag; every OMNI call is logged with its input image and its answer. The run writes out the exact subsets used, downloadable as a zip. If you don't believe the number, you can check the file it came from.

**Verdict validation.** `submit_verdict` is not a free-text field. The submitted medians must be within 1% of the computed ones, the regulatory statuses must exactly equal what `check_regulations` returned, every evidence ID must resolve in the ledger, `rank_evidence` must have run, and a banned-phrase check rejects enforcement language. A verdict that fails validation goes back to the model with the reason.

**The rest of the stack:** FastAPI + Python 3.11 on the backend with SSE streaming; React 18 + TypeScript + Vite on the front end, with Plotly figures, a react-globe.gl wireframe globe, and a live agent trace; 53 tests covering the physics on synthetic plumes, the mask, the regulatory rules, the tool envelopes, replay, and the ranking pipeline. The whole thing runs without API keys in a deterministic demo mode, which is what makes it safe to present.

## 🧗 Challenges we've overcome

**The data was genuinely messy, and that turned out to be the project.**

- The FIRMS CSV in our asset folder wasn't a CSV at all. Its contents were the string `Invalid day range. Expects [1..5].` — the API had rejected our 15-day request and we had saved the error message as data. We wrote a fetcher that pulls in 5-day chunks across three satellites, concatenates them, prefers the science-processed product over near-real-time duplicates where they overlap, and ends up with 73 usable detections.
- The TCEQ emissions-event reports arrived as **legacy .xls exports**, not the PDF printout we had designed the parser for, so the reporting timeline had to be rebuilt around table parsing. One incident mentioned in our own notes turned out not to be in the files at all — so it isn't in the analysis either.
- The Sentinel-2 "images" were **Copernicus Browser screenshots from a different date**, regional in scale, with burned-in labels and no georeferencing whatsoever. Rather than throw them away or pretend they were aligned, we fitted the bounds from the town labels visible in the screenshot (RMS 0.47 km, ≈258 m/px) and labelled them low quality everywhere they appear — including in what the agent is told about them.
- Carbon Mapper data never arrived. Instead of quietly dropping the cross-check, we generated a clearly-labelled **SYNTHETIC** placeholder that is marked as synthetic in the manifest, in the chart legend, in the evidence ledger, and in the agent's own prompt.

**Missing data had to be a first-class result, not an exception.** Any tool can raise a `DataGap`, which becomes a `status: "data_gap"` envelope with an explanation. The agent is instructed to report gaps rather than reason around them — "NOT_ASSESSED: data not available" is a legitimate and common outcome in our regulatory table, and it is far more useful to a regulator than a confident guess.

**Representing the mathematics faithfully.** Getting from a raster of ppm·m to kilograms per hour means committing to a background estimator, a mask threshold, an effective-wind parameterisation, an air-column density, and a plume length scale — and each of those choices moves the answer. We ended up doing the research to understand which conventions exist, implementing the one we could defend (Varon et al. 2018), exposing α and β as assumption records flagged **needs verification**, and running a wind-sensitivity chart so a reader can see how the estimate responds across the plausible range. We also went looking for the ways our own number could be wrong: alternative effective-wind and density conventions give **19.7–45.1 t/h** for the same scene — a factor of 2.3, and 6.9 t/h if you also swap the plume length scale from √A to the downwind extent. The detection, the attribution and the "exceeds threshold by two orders of magnitude" conclusion survive all of them; the precise value does not, and we say so.

**Infrastructure friction, as always.** Kaleido hung indefinitely when exporting Plotly figures on Windows, and the newer Plotly export path wanted a headless Chrome we didn't want in the demo. Since OMNI needs actual images to read, we wrote a small matplotlib renderer that turns the same figure JSON into a PNG — interactive charts for humans, static renders for the model, one source of truth.

## 🏆 What we're proud of

**The agent independently reproduced the finding that motivated the project.** Given nothing but a facility ID and a date, it found the plume, attributed it to the site, quantified it at ~230× the federal super-emitter threshold, checked the operator's own filings, found no matching report, and said so — in language careful enough to put in front of a regulator. That is the entire manual workflow, compressed into three minutes and rendered auditable.

**Reasoning over messy data, not curated data.** Screenshots with no georeferencing. An error message masquerading as a CSV. A legacy spreadsheet format. A dataset that never showed up. An 18-page permit PDF. A plume that needs a wind field from a different data source to become a number. The agent handles all of it, tracks the quality of each source, and carries those caveats into the conclusion instead of dropping them on the floor. Our favourite property of the system is that the *reliability* question is one of the five questions the evidence reranker always asks.

**A genuinely creative use of Huawei OMNI.** We didn't use a multimodal model as a chat interface — we used it as an instrument for the parts of the problem that are irreducibly visual, and then as a way to put the same analysis in the hands of someone standing in a field. It looks at the plume map and says whether the shape is consistent with the wind direction. It looks at the Sentinel-2 crop and describes what kind of facility sits at the coordinates. It reads the permit pages and extracts what the plant is actually authorised to emit. And because it is prevented from contributing numbers, a wrong answer degrades the explanation rather than corrupting the measurement. During one live run OMNI reported a rate with the wrong units, and the orchestrator caught the discrepancy against the computed value and discarded it — exactly the failure mode the architecture was designed to contain.

**Two different jobs for one model.** At the desk, OMNI is an analyst: it reads charts and permit pages so the agent can explain what the numbers mean. In field mode it is a radio operator: audio in, situational answer out, grounded in the same imagery and the same verdict. The orchestrator deliberately does not have field mode in its tool set — a desk run has no microphone and no one standing at the fence, so there is nothing for it to call the tool with. It is operator-triggered, and it is the same client, the same model and the same "no numbers from the model" rule underneath.

**Elastic-style hybrid retrieval as a decision-making step, not a chatbot.** The ranking stage isn't there to answer user questions; it's there so the agent decides *what matters* before it concludes. BM25 for the exact regulatory and unit vocabulary, dense vectors for the paraphrases, RRF to fuse them, an LLM rerank for importance under each of five investigation questions, and hard validation on the output. The report's "Key evidence" section is that ranking, made visible, with importance bars.

## 📚 What we learned

**A strong orchestrator changes what you can attempt.** We expected to write a rigid state machine and ended up not needing one. Given good tool descriptions, envelope-shaped results and skill playbooks, GPT-5.6-sol sequenced a 32-step investigation sensibly, recovered from data gaps, noticed a unit inconsistency in another model's output, and produced a verdict that passed our validator on the first attempt in a live run. The lesson we'll keep: **spend the effort on the tool contract and the validation, not on scripting the agent.** The tools' envelope shape and the verdict validator did more for reliability than any prompt we wrote.

**Constraints make the model more useful, not less.** "You may not do arithmetic" and "you may not call this a violation" sound like they'd weaken the output. They're the reason the output is trustworthy enough to show a regulator.

**Determinism is a feature you have to build.** Fixed Monte Carlo seeds, cached embeddings and rerank responses, a replayable run log, and a demo mode that works with no API keys at all — that's what makes this demonstrable under conference wifi, and it's also what makes the science reproducible.

**How Codex helped us build it.**

_______________________________________________________________________

_______________________________________________________________________

_______________________________________________________________________

## 🔜 The future

- **Wire the retrieval layer to Elasticsearch properly.** The hybrid pattern is already in place — BM25 + dense + RRF + rerank — but running it in-process means we don't get aggregations, ES|QL, or geo and time-series queries over a corpus of many facilities. With Elasticsearch as the context layer, the same agent could screen a whole basin and rank *facilities*, not just evidence within one run.
- **Close the loop on action.** Today the agent produces a report. The natural next step is for it to draft the regulator's information request, attach the evidence zip, and file it — with a human approving before anything leaves the building.
- **Grow field mode into a live inspection companion.** The spoken channel works today with a recorded question and the stored aerial view. The version we want next streams the phone's own camera instead, so the answer is grounded in what the inspector is looking at *now* rather than in last year's basemap: point at a flare stack and ask whether it looks lit, point at a tank battery and ask what the permit authorises for it. From there it becomes a two-way loop — the inspector's observations go back into the evidence ledger as a dated, attributed record, so what a person saw on the ground sits beside what the satellite measured, and the next assessment of that site can weigh both. Wearables and vehicle-mounted cameras are the obvious hardware for it; the model and the plumbing are already the same.
- **Scale past one plume.** Automatic EMIT and Sentinel-5P granule ingestion, so every overpass of every monitored site is screened, and only the exceedances surface. Our annualisation is currently illustrative because we only have a handful of overpasses; with a real detection history it becomes a defensible annual estimate.
- **Verify the physics constants.** α and β in the effective-wind parameterisation are flagged as needing verification against an EMIT-specific calibration, and a controlled-release comparison would tighten the uncertainty band substantially.
- **More rules, more jurisdictions.** The regulatory layer is a small declarative rule set. Adding another state — or the EU methane regulation — is mostly a matter of writing the rules down.
