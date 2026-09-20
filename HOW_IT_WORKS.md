# Save the North — how it works

A complete technical description of the system: the data, the tools, the skills, the mathematics,
the justification for each choice, how accurate the result actually is, and what happens end to end
when you press **Assess**.

---

## 1. What the system does

Given a **facility** and a **date**, the system decides whether a satellite-observed methane release
exceeds what the law allows, and whether the operator reported it. It produces a screening report in
which every number is traceable to a file with a SHA-256 hash.

The case it is built around: **Lenorah / Red Lake gas plants**, Martin County, Texas (ETC North
Permian Midstream, an Energy Transfer subsidiary), and NASA EMIT's overpass on
**2025-08-08 at 14:45 UTC**.

The headline result:

| Quantity | Value |
|---|---|
| Methane emission rate | **23.0 t/h** (22,954 kg/h), p5–p95 **14,955–29,126 kg/h** |
| Federal super-emitter threshold | 100 kg/h (40 CFR 60.5371a/b) |
| Ratio | **~230×** |
| CO₂-equivalent | **684 t CO₂e/h** observed vs **3.0 t CO₂e/h** at the threshold (GWP100 = 29.8) |
| Matching TCEQ emissions-event report within ±1 day | none in the records provided |
| Screening outcome | **FAILED** |

"FAILED" is a screening outcome, not a legal finding. The system is prohibited from saying anyone
violated anything — see §9.

---

## 2. Architecture in one picture

```
 assets/ (whatever files arrived)
        │
        ▼
 inventory pass ──────────► data/manifest.yaml + ASSET_REPORT.md
 (classify by content)       every file: sha256, coverage, quality, warnings, decisions
        │
        ▼
 data/normalized/  (GeoTIFF crops, CSVs, JSON, PDF)
        │
        ▼
 ┌─────────────────────────────────────────────────────────────┐
 │  AGENT LOOP                                                 │
 │                                                             │
 │  GPT-5.6-sol (OpenAI Responses API, function calling)       │
 │      │  chooses what to do next; never does arithmetic      │
 │      ▼                                                      │
 │  20 tools ── deterministic Python science ──► numbers       │
 │      │                                                      │
 │      ├──► Huawei OMNI (qwen3.5-omni-flash) ──► qualitative  │
 │      │     charts, satellite images, permit pages           │
 │      │                                                      │
 │      └──► Evidence Ledger (sha256, subsets, assumptions)    │
 │                                                             │
 │  rank_evidence (BM25 + dense + RRF + LLM rerank)            │
 │      ▼                                                      │
 │  submit_verdict ──► validator ──► report                    │
 └─────────────────────────────────────────────────────────────┘
        │
        ▼
 FastAPI + SSE ──► React front end (live trace, charts, evidence, export)
```

Two rules hold the whole design together:

1. **The language model never does arithmetic.** Every number in the report was computed by Python.
2. **OMNI never supplies a number that enters a calculation.** It describes what it sees; the maths
   comes from the arrays.

---

## 3. The data, and what each dataset represents

Eleven data slots are tracked. Each is recorded in `data/manifest.yaml` with its SHA-256, source,
citation, date coverage, quality flag and warnings.

| Slot | What it is | What it is used for |
|---|---|---|
| `emit_ch4enh` | NASA EMIT L2B methane **enhancement**, 60 m pixels, units **ppm·m** (excess methane in the vertical column above background) | The measurement itself: the plume |
| `emit_ch4uncert` | EMIT per-pixel **1σ uncertainty**, ppm·m | Per-pixel noise in the Monte Carlo |
| `emit_ch4sens` | EMIT **sensitivity** layer | Context on detection limit |
| `wind` | Open-Meteo / ERA5 reanalysis, hourly: 10 m wind speed and direction, temperature, pressure | Converts a mass to a rate; air density |
| `firms` | NASA FIRMS VIIRS 375 m active-fire detections: lat/lon, time, fire radiative power, day/night flag | Was a flare burning near the overpass? Cause analysis |
| `s2_truecolor`, `s2_swir` | Copernicus Sentinel-2 imagery (true colour and shortwave infrared) | Visual context: what kind of facility sits at these coordinates |
| `site_imagery` | Esri/Maxar basemap exports of the plant and the analysis window | Display only — report hero, plume overlay |
| `tceq_sob` | TCEQ Title V **Statement of Basis**, permit O4734, 18-page PDF | What the plant is authorised to do; design capacity |
| `tceq_steers` | TCEQ STEERS **Air Emission Event Reports** the operator filed (incidents 441788, 452092) | What the operator itself reported, and when |
| `carbonmapper` | **SYNTHETIC placeholder** — the real dataset never arrived | Independent cross-check, labelled synthetic everywhere |

Scale of the corpus actually analysed: **4,237,084 EMIT pixels**, **73 VIIRS detections**,
**24 hourly wind records**, **18 permit pages**, **6 emissions-event rows**.

### Known data quality problems (carried into the conclusion, not hidden)

- **Sentinel-2** images are regional screenshots from **2026-09-18**, not the event date, with no
  georeferencing. Bounds were fitted from 11 town labels by least squares (RMS 0.47 km ≈ 258 m/px).
  Flagged `quality: low` everywhere.
- **Carbon Mapper** is synthetic. Only the plume ID and the ~21,500 kg/h figure come from the brief;
  everything else is invented, and every output that touches it says SYNTHETIC.
- **FIRMS** originally arrived as an API error message saved as a `.csv`; re-downloaded in 5-day
  chunks across three satellites.
- **Not provided at all**: NO₂/NOx observations, the permit's MAERT table, EPA GHGRP Subpart W data.
  The rules that depend on them return `NOT_ASSESSED`.

---

## 4. The tools (20)

Every tool returns the same envelope:

```json
{"status": "ok|data_gap|error", "summary": "one line for the model",
 "data": {...}, "charts": [...], "evidence_ids": [...],
 "assumptions": [...], "warnings": [...], "data_used": [...]}
```

`data_used` names the exact subset that produced the answer (which pixels, which rows, which pages),
and is written to the run folder so it can be downloaded.

**Meta / discovery**
| Tool | Does |
|---|---|
| `list_skills` | Lists the skill playbooks available |
| `load_skill` | Loads a playbook (markdown) before a phase |
| `find_facility` | Fuzzy-searches the facility registry |
| `list_available_data` | Every data slot with status, dates, quality, warnings, and the known gaps |
| `describe_dataset` | Units, dimensions, coverage, bbox, statistics for one slot |

**Science**
| Tool | Does |
|---|---|
| `plume_map` | Crops EMIT, computes background, builds the plume mask, renders the plume map |
| `get_wind` | U10, direction, σ_U, pressure, temperature at the overpass; air column density |
| `compute_emission_rate` | IME → Q, Monte Carlo uncertainty, wind-sensitivity curve |
| `compare_estimates` | Our estimate vs Carbon Mapper for the same plume and date |
| `flare_activity` | VIIRS detections within 1.5 km, day/night split, nearest in time to the overpass |
| `physics_bounds` | Plant throughput ceiling; is the rate explicable as flare slip? |
| `annualize` | Annual scenarios from detection frequency (illustrative) |
| `reporting_timeline` | Parses STEERS events; detections vs reports on one timeline |
| `check_regulations` | Evaluates the screening rules and returns statuses |
| `rank_evidence` | Hybrid retrieval + LLM rerank over everything the run produced |

**Multimodal (Huawei OMNI)**
| Tool | Does |
|---|---|
| `analyze_chart` | Interprets a rendered chart qualitatively |
| `analyze_image` | Reads a satellite image — full scene with the facility circled plus an 8× zoom |
| `read_document` | Renders the most relevant PDF pages at 110 dpi and reads them |

**Reporting**
| Tool | Does |
|---|---|
| `show_chart` | Adds a chart to the final report |
| `submit_verdict` | Submits the conclusion — validated before acceptance (§9) |

**Not in the registry, on purpose:** `field_question` (field mode). An inspector at the site records
a spoken question; it goes to OMNI with the aerial view and the desk finding. The agent can't call it
because a desk run has no microphone. It is exposed at `POST /api/field-note`.

---

## 5. The skills (5)

Skills are markdown playbooks in `skills/`, loaded by the agent before each phase. They encode
*method* rather than code, so a domain expert can review the procedure without reading Python.

| Skill | Tells the agent |
|---|---|
| `data-discovery` | Inventory first; treat gaps as findings; never assume a slot exists |
| `methane-quantification` | The IME procedure, which mask threshold to prefer, how to report uncertainty |
| `flare-and-cause-analysis` | How close in time and space a flare must be to be relevant; how to weigh causes |
| `texas-regulatory-check` | The federal and Texas rules, the reportable quantity, the matching window |
| `verdict-report` | How to write the conclusion: required sections, careful language, evidence citation |

---

## 6. The mathematics, and why each step is justified

### 6.1 Crop

EMIT L2B rasters are read with rasterio and cropped to **±6 km** around the source coordinates.

*Justification:* the brief said ±4 km; the 2025-08-08 plume extends ~4.8 km downwind, and a ±4 km
window truncates it, biasing the integrated mass **low**. The deviation is recorded as an assumption
with `verify: true`. Fill values (≤ −9990) are masked out.

### 6.2 Background

Background is estimated from an **annulus 2.5–4 km** from the source, using the **median** and
**MAD × 1.4826** rather than mean and standard deviation.

*Justification:* the median/MAD pair is a robust estimator — a few bright plume pixels leaking into
the annulus barely move it, where a mean would be dragged upward and the emission rate downward.
Because this plume is long enough to cross the annulus, a **two-pass** procedure runs: a first-pass
mask is dilated by 2 pixels and those pixels are removed from the annulus before the background is
recomputed. For this scene: background **58 ± 471 ppm·m**, with the excluded-pixel count recorded.

### 6.3 Plume mask

A pixel is a candidate if `enhancement > μ_bg + k·σ_bg`. Then:
1. **3×3 binary opening** removes isolated hot pixels (speckle) while keeping connected structure.
2. **Connected-component labelling**, keeping only components with a pixel within **1 km** of the
   source — this is the attribution step: a plume from a neighbouring pad is not counted as ours.
3. The mask is built at **five thresholds** (k = 1.5, 2.0, 2.5, 3.0, 4.0), default **k = 2.5**.

Result for this scene: **672 pixels, 2.05 km², peak 13,371 ppm·m**, extending ~4.83 km downwind.

*Justification:* k·σ thresholding is the standard plume-delineation approach for enhancement
retrievals; carrying five thresholds rather than one means the threshold choice becomes a source of
*quantified* uncertainty instead of a hidden decision (§6.6).

### 6.4 Column mass → integrated mass

Per-pixel excess column mass:

```
ΔΩ [kg/m²] = Δ[ppm·m] × 1e-6 × n_air [mol/m³] × M_CH4 [kg/mol]
```

with `M_CH4 = 0.01604 kg/mol` and air column density `n_air = P / (R·T)` from the observed pressure
and temperature (defaults 92,000 Pa and 305 K at ~820 m elevation when the weather file lacks them;
for this run n_air = 36.3 mol/m³).

Integrated mass enhancement:

```
IME [kg] = Σ (ΔΩ · A_pixel)   over mask pixels, background-subtracted
```

*Justification:* this is the definition of IME in **Varon et al. (2018)**, "Quantifying methane point
sources from fine-scale satellite observations of atmospheric methane plumes" (AMT). The ppm·m → kg/m²
conversion is dimensional bookkeeping with no free parameters.

### 6.5 Emission rate

```
U_eff = α · ln(U10) + β        (α = 1.1, β = 0.6)
L     = √A_mask                (plume length scale)
Q     = U_eff · IME / L        [kg/s]  → ×3600 → kg/h
```

*Justification:* Varon et al. show that the instantaneous source rate of a point-source plume is
well approximated by `Q = U_eff · IME / L`, where `U_eff` is an **effective** wind — slower than the
10 m wind, because the plume samples a vertical profile and turbulence, not the single 10 m value —
and `L` is a characteristic plume length, taken as the square root of the plume area. The logarithmic
form of `U_eff(U10)` and the coefficients come from their large-eddy-simulation calibration.

**This is the weakest link and it is flagged as such.** α and β are instrument-specific (calibrated
for GHGSat-like sampling, not EMIT's 60 m pixels) and both carry `verify: true` in `case.yaml`. The
alternative linear form (`0.33·U10 + 0.45`) is implemented and switchable.

Wind for this scene: **U10 = 4.20 ± 1.26 m/s from 194°** (ERA5 via Open-Meteo, the grid point 5.0 km
from the plant), giving `U_eff ≈ 2.2 m/s`.

### 6.6 Uncertainty: Monte Carlo, 2,000 draws

Each draw perturbs, independently:

| Source | Distribution |
|---|---|
| Wind speed | `U10 ~ N(4.20, 1.26)`, resampled below 0.5 m/s. σ_U is the greater of 30% of U10 and 1.0 m/s, informed by the ±2 h spread |
| Mask threshold | `k ~ Uniform{1.5, 2.0, 2.5, 3.0, 4.0}` — the threshold choice is *sampled*, not fixed |
| Retrieval noise | per-pixel `N(0, σ_pixel)` from the EMIT uncertainty layer, summed in quadrature inside the mask |
| Wind coefficients | `α, β ~ Uniform(±20%)` |

Seed **20250808**, fixed — identical inputs always give identical output.

Result: **median 22,954 kg/h, p5 14,955, p95 29,126** (≈ −35% / +27% around the median).

*Justification:* the dominant uncertainties in IME quantification are wind and mask definition, so
both are sampled rather than assumed. Sampling `k` is the important choice: it converts "we picked
2.5σ" from a hidden assumption into a contribution to the published interval.

### 6.7 Physical plausibility

- **Throughput ceiling:** plant capacity (MMscfd, from the permit) × CH₄ fraction (0.75 for Permian
  wet gas) × 19.2 g/scf → ceiling ≈ **300 t CH₄/h**. Our 23.0 t/h is **7.7%** of it — large but
  physically possible.
- **Flare slip:** at 98% combustion efficiency, explaining the plume as unburned slip from a lit
  flare would require flaring ≈ **1,148 t/h**, far above the ceiling → *flare slip implausible*. This
  matters for cause: the plume is more consistent with venting or an unlit/partially-lit flare than
  with normal combustion inefficiency.

*Justification:* a quantification that exceeds what the plant can physically process is wrong, no
matter how clean the mathematics. This is a falsification test on our own answer.

### 6.8 Regulatory screening

| Rule | Test | This case |
|---|---|---|
| `US_SUPER_EMITTER` (40 CFR 60.5371a/b) | `EXCEEDS` if **p5 > 100 kg/h**, `BELOW` if p95 < 100, else `INCONCLUSIVE` | **EXCEEDS** |
| `TX_EMISSIONS_EVENT_REPORTING` (30 TAC 101.201) | Mass in a ≥1 h event vs **RQ 5,000 lb**; then look for a STEERS event within **±1 day** | **NO_MATCHING_REPORT_FOUND** (≈50,604 lb, 10.1× RQ) |
| `PLANT_PHYSICS_CEILING` | Is the rate below the plant ceiling? | **CONSISTENT** (7.7%) |
| `NOX_PERMIT_LIMITS` | — | **NOT_ASSESSED** (MAERT and NO₂ not provided) |
| `GHGRP_REPORTED` | — | **NOT_ASSESSED** (no GHGRP data) |

Note the deliberately conservative construction of the federal test: it requires the **5th percentile**
to clear the threshold, not the median. And the Texas rule's note says in full that this "is not a
finding that a report was required or omitted".

### 6.9 CO₂-equivalent

`684 t CO₂e/h = 22.954 t CH₄/h × 29.8`, using **IPCC AR6 GWP100 = 29.8** for fossil methane.

*Justification and caveat:* GWP100 is a convention, not a measurement. EPA's GHGRP has used 25 and 28
in different vintages; the value carries `verify: true`, and the figure is displayed with its basis.

---

## 7. How the agent runs (the five phases)

1. **Discover** — `list_skills` → `load_skill(data-discovery)` → `find_facility` →
   `list_available_data`. The agent learns what exists *and what is missing* before analysing.
2. **Quantify** — `plume_map` → `get_wind` → `compute_emission_rate`, with `analyze_chart` on the
   plume map and the Monte Carlo distribution for a qualitative read.
3. **Explain** — `flare_activity`, `analyze_image` (Sentinel-2), `read_document` (permit),
   `physics_bounds`, `annualize`.
4. **Screen** — `reporting_timeline` → `check_regulations`.
5. **Rank and conclude** — `rank_evidence` → `submit_verdict`.

A typical run is **32 tool calls and 7 OMNI readings in ~3 minutes**. The trace streams to the
browser over SSE, showing each call with the actual chart, image or permit page being read.

**Demo vs live.** The science is identical in both — the tools always compute from the normalized
files, nothing is replayed. What differs: in **live** mode GPT-5.6-sol chooses the sequence and
writes the verdict, and OMNI is called for real (answers are cached on disk by prompt+image hash, so
a repeated question is served from cache and labelled CACHED). In **demo** mode a scripted trajectory
calls the same tools in a fixed order and OMNI answers come from cache or deterministic mock text. If
the live orchestrator fails mid-run, the scripted agent finishes the remaining steps and says so.

---

## 8. Evidence ranking (`rank_evidence`)

Before a verdict is allowed, the agent must rank its own evidence. The corpus is everything the run
produced: tool results, assumptions, warnings, document readings, regulatory statuses.

1. **BM25** (Okapi, k1 = 1.5, b = 0.75, stopworded, hyphen-split) — exact regulatory and unit vocabulary.
2. **Dense vectors** — OpenAI `text-embedding-3-small` live, or a local hashed n-gram vectoriser
   offline, so the system still works with no keys.
3. **Reciprocal rank fusion** (k = 60) over both rankings.
4. **LLM rerank** by importance, for each of five fixed questions, run in parallel:
   threshold · reporting · attribution · cause · **reliability**.
5. **Validation** — returned IDs must exist in the ledger; importance must lie in [0, 1]; otherwise
   the fused order stands.

Results are cached on disk. The reranker speaks the OpenAI chat protocol, so it can be pointed at a
Baseten endpoint with `RERANK_BASE_URL` / `RERANK_API_KEY` / `RERANK_MODEL`.

The fifth question is the one that matters most for honesty: *which data are unreliable, synthetic,
missing or in conflict, and how do they limit the conclusion?*

---

## 9. The verdict validator

`submit_verdict` is not a free-text field. A submitted verdict is rejected, with reasons returned to
the model, unless:

- the schema validates (pydantic);
- `facility_id` matches the run;
- `median_kg_h`, `p5_kg_h`, `p95_kg_h` are **within 1%** of what Python computed;
- cross-check and annualisation figures match the computed values;
- every `regulatory_findings[].status` **equals** what `check_regulations` returned;
- `check_regulations` and `rank_evidence` were both called;
- every `evidence_id` resolves in the Evidence Ledger;
- the text contains none of *violated*, *violation of law*, *illegal*, *broke the law*.

This is what makes the output safe to show a regulator: the model can choose emphasis and wording,
but it cannot restate a number, invent a citation, or upgrade a screening result into an accusation.

---

## 10. The Evidence Ledger

Every run writes a ledger containing:

- **Dataset records** — SHA-256, source name, citation, URL, date coverage, quality flags, warnings,
  and the exact subset used (written to the run folder and downloadable as a zip).
- **Assumption records** — every constant from `case.yaml` with its value, unit, rationale and
  `verify` flag. A constant can never be mistaken for a measurement.
- **AI analysis records** — every OMNI call: the question, the image that was sent, the answer, the
  model, and whether it was LIVE, CACHED or MOCK.
- **Derived results** — the computed intermediate values other tools depend on.

In the UI, clicking a headline number highlights the ledger entries behind it.

---

## 11. How accurate is this, really?

**What is robust:**

- **Detection.** A 672-pixel coherent structure peaking at 13,371 ppm·m against a 471 ppm·m
  background is not noise.
- **Attribution.** The plume starts at the facility and extends downwind in the direction ERA5 gives
  for that hour, and the component is within 1 km of the source.
- **"Exceeds the threshold."** Across the whole plausible wind range (1–12 m/s) and all five mask
  thresholds, the rate stays two orders of magnitude above 100 kg/h. For the conclusion to flip, the
  estimate would have to be wrong by a factor of ~230. The most conservative variant in the table
  below still sits **69×** above the threshold.

**What is uncertain:**

- **The value itself.** The stated p5–p95 of 15.0–29.1 t/h reflects wind, mask and retrieval noise —
  but *not* the choice of parameterisation. Recomputing the same scene under other published
  conventions gives:

  | Variant | Q (t/h) |
  |---|---|
  | Baseline (log U_eff, L = √A, n_air at 92 kPa / 305 K), k = 2.5 | 23.4 |
  | α, β −20% / +20% | 18.7 / 28.1 |
  | U10 ∓1σ (2.94 / 5.46 m/s) | 19.2 / 26.5 |
  | Mask k = 1.5 / k = 4.0 | 24.2 / 22.0 |
  | Linear U_eff (0.33·U10 + 0.45) | 19.7 |
  | U_eff = 0.7·U10 | 31.6 |
  | U_eff = U10 (no attenuation) | 45.1 |
  | n_air at 101.3 kPa / 288 K | 27.3 |
  | L = downwind extent (4.83 km) instead of √A | 6.9 |

  So: **±30% statistical**, **19.7–45.1 t/h (factor 2.3)** once the effective-wind and density
  conventions are allowed to vary, and **6.9–45.1 t/h (factor 6.5)** if the plume length scale is
  also changed — though using the downwind extent in place of √A is arguably a different method
  rather than a different parameter. The published p5–p95 is therefore an interval *conditional on*
  the Varon log-form with α = 1.1, β = 0.6, not a statement about the true rate.
- **α and β** are not calibrated for EMIT. This is the single largest systematic.
- **"No matching report."** True of the records we hold — two STEERS incidents. An incident
  mentioned in our own notes (452090, Red Lake) was not in the provided export. The correct reading
  is "absent from the provided records", not "never filed".
- **The annual projection** (14,016 / 57,276 / 100,537 t CH₄/yr) is illustrative only: it extrapolates
  from a handful of overpasses, two of which come from the synthetic placeholder.
- **Sentinel-2 context** is from the wrong date with fitted bounds; OMNI is asked to say whether the
  resolution and date support a confident answer, and for these images it says they do not.

**The honest summary:** the *decision* — this facility released methane far beyond the codified
threshold on this date, and no matching report exists in the available records — is robust to every
sensitivity we tested; the weakest variant is still 69× the threshold. The *number* is good to about
a factor of two, and the report says so.

---

## 12. Testing and reproducibility

- **59 tests**: synthetic-plume IME recovery (a plume of known mass is injected and re-measured),
  mask behaviour, unit conversions, regulatory rule logic, tool envelopes, replay, the ranking
  pipeline, live-integration behaviour against fake endpoints, and field mode.
- **Determinism**: fixed Monte Carlo seed, cached embeddings and OMNI answers, replayable JSONL run
  logs.
- **Runs with no API keys**: mock LLM trajectory, mock OMNI text, local vectoriser — the whole demo
  works offline.
- **Provenance**: `ASSET_REPORT.md` and `data/manifest.yaml` record every decision the inventory
  made, including the files it rejected and why.

---

## 13. Stack

**Backend** — Python 3.11, FastAPI, SSE streaming, rasterio, NumPy/SciPy, pandas, PyMuPDF, Plotly
(figure JSON) + matplotlib (static PNGs for OMNI), OpenAI SDK for both GPT and OMNI
(OpenAI-compatible gateway).

**Front end** — React 18, TypeScript, Vite, Tailwind, react-plotly.js, react-globe.gl, EventSource
for the live trace.

**Models** — `gpt-5.6-sol` (orchestration and rerank), `text-embedding-3-small` (dense retrieval),
`qwen3.5-omni-flash` (multimodal: charts, imagery, documents, and field-mode audio).
