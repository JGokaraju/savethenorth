# 🧗 Challenges we've overcome

*(Replacement for the "Challenges" section of the Devpost write-up.)*

## Seven file formats, one investigation

The honest description of our inputs is: a folder of things a colleague sent over. Emissions-event reports arrived as **legacy .xls** exports. The satellite science came as **GeoTIFF** rasters, the imagery as **JPG browser screenshots**, the flare detections as **nine CSV fragments**, the permit as an **18-page PDF**, the weather as **JSON**, and the cross-check dataset never arrived at all. Nothing shared a coordinate system, a date, a naming convention or a notion of what "missing" means.

The agent can't reason over that directly, and we didn't want a pipeline that silently normalised the mess away either — the mess *is* information about how much you can trust the conclusion. So we built two layers: an **inventory pass** that decides what each file actually is and records every decision it made, and a **tool layer** that hands the agent typed, self-describing results with the caveats still attached.

**The inventory classifies by content, not by filename**, and writes both a machine-readable `manifest.yaml` and a human-readable `ASSET_REPORT.md` listing every choice. That is how we caught the best bug of the weekend: `firms_viirs.csv` was not a CSV. Its entire contents were the string `Invalid day range. Expects [1..5].` — the API had rejected our 15-day request and we had saved the error page as data. A filename-driven loader would have parsed that into an empty table and reported "no flaring near the plant", which would have changed the cause analysis. Instead the file was flagged as not-a-CSV, quarantined with a reason, and superseded by nine re-downloaded 5-day chunks across three satellites, concatenated with the science-processed product preferred over near-real-time duplicates where they overlap: 73 usable detections.

## A different technique for each kind of mess

**Rasters → arrays.** The three EMIT products (enhancement, uncertainty, sensitivity) are read with rasterio and cropped to ±6 km around the source hint. One granule of the overpass turned out to be nodata at the plant, so the inventory checks the source pixel in each and picks the granule that actually contains data — recording the one it rejected and why.

**Legacy .xls → events.** The STEERS exports were supposed to be the PDF printouts our parser was written for. They arrived as BIFF spreadsheets, one file per incident, shaped as one row per emission point × contaminant. We rebuilt the parser around table parsing: group rows into events, sum the reported quantities per contaminant, and — crucially — record whether methane appears in the contaminant list at all. It doesn't: the operator's own filings for this site report VOCs, which is exactly the kind of mismatch the comparison chart is there to show.

**Unreferenced screenshots → approximately georeferenced imagery.** The Sentinel-2 "data" was a pair of Copernicus Browser screenshots, regional in scale, from a *different date*, with burned-in town labels and no georeferencing whatsoever. Throwing them away loses real context; pretending they are aligned is worse. So we georeferenced them from the picture itself: **11 town labels visible in the screenshot** became control points, least-squares fitted to a linear pixel→lat/lon mapping (**RMS 0.47 km, ≈258 m/px**). Every product built on them carries `quality: low`, the fitted-bounds method, and the date mismatch — in the manifest, in the chart legend, in the evidence ledger, and in what the agent is told before it looks.

**PDF → pages a model can read.** The 18-page Title V Statement of Basis is text, but which page matters depends on the question. The `read_document` tool extracts the text layer, scores pages against the question with a weighted keyword model (rare decisive terms like the capacity statement outweigh common ones), renders the **top three pages at 110 dpi** with PyMuPDF, and sends those images to OMNI with the question. The rendered pages and the extracted snippets are both written into the run's evidence folder, so you can see exactly what the model was shown.

**Spreadsheet → picture, on purpose.** For the emissions-event records we do something that sounds backwards: we take the parsed table and render it *back* into an image with matplotlib, then ask OMNI to read it. That gets us a model that reasons over the report the way a regulator sees it — incident numbers, dates, event type, contaminants and quantities laid out together — while the numbers used in the actual comparison come from the parsed dataframe, never from the model's reading of the picture.

**Imagery → a question OMNI can actually answer.** `analyze_image` doesn't just forward a satellite tile. It composes a two-panel image — full scene with the facility circled, next to an 8× zoom on that circle — and asks OMNI both the analytical question *and* whether the resolution and date allow a confident answer. On these low-quality screenshots it says no, which is the right answer and becomes a recorded caveat rather than a quiet assumption.

**Charts → static renders.** OMNI reads pictures, and our charts are interactive Plotly figures. Kaleido hung indefinitely exporting them on Windows and the newer export path wanted a headless Chrome we didn't want in the demo, so we wrote a small matplotlib renderer that turns the same figure JSON into a PNG. Humans get the interactive chart, the model gets a static render, and both come from one source of truth.

## Missing data as a first-class result

Any tool can raise a `DataGap`, which becomes a `status: "data_gap"` envelope with an explanation instead of an exception or a zero. The agent is instructed to *report* gaps rather than reason around them, and the regulatory table has `NOT_ASSESSED: data not available` as a legitimate outcome — which is what the EPA greenhouse-gas reporting rule returns for this facility, because we have no GHGRP data for it. A regulator is far better served by an explicit gap than by a confident guess.

Carbon Mapper is the sharpest version of this. The cross-check dataset never arrived, so rather than drop the comparison we generated a placeholder that is labelled **SYNTHETIC** in the manifest, in the chart legend, in the evidence ledger, in the tool's summary line and in the agent's own prompt. The agent duly reports the cross-check *and* says it is synthetic, and the reliability question in the evidence ranker surfaces it as a limitation. A number you cannot trust, clearly marked, is useful; the same number unmarked is a lie.

## Making the mess visible to the model, not hiding it from it

Every tool returns the same envelope: `status`, `summary`, `data`, `charts`, `evidence_ids`, `assumptions`, `warnings`, `data_used`. Warnings travel *with* the result, so when the agent reads the Sentinel-2 analysis it also reads "image date 2026-09-18 does not match the 2025-08-08 event; bounds fitted from town labels". Assumptions are separate records with a `verify` flag, so a hard-coded constant can never masquerade as a measurement. And `data_used` names the exact subset — which pages, which rows, which pixels — that produced the answer.

The payoff shows up in the conclusion. One of the five questions the evidence reranker always asks is *"which data are unreliable, synthetic, missing or in conflict, and how do they limit the conclusion?"* — so the messiness is not something the pipeline survives, it is something the final report is required to account for.

## Representing the mathematics faithfully

Getting from a raster of ppm·m to kilograms per hour means committing to a background estimator, a mask threshold, an effective-wind parameterisation, an air-column density and a plume length scale — and each of those choices moves the answer. We did the research to understand which conventions exist, implemented the one we could defend (Varon et al. 2018), exposed α and β as assumption records flagged **needs verification**, and added a wind-sensitivity chart so a reader can see how the estimate responds across the plausible range.

We also went looking for the ways our own number could be wrong: alternative effective-wind and density conventions span roughly **20–56 t/h**. The detection, the attribution and the "exceeds the threshold by two orders of magnitude" conclusion survive all of them. The precise value does not — and we say so, in the report, where a regulator will see it.
