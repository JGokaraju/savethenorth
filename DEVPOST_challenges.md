# 🧗 Challenges we've overcome

*(Replacement for the "Challenges" section.)*

Our inputs were a folder of whatever a colleague could export: **legacy .xls** emissions-event reports, **GeoTIFF** rasters, **JPG browser screenshots**, nine **CSV** fragments, an 18-page **PDF** permit, **JSON** weather — nothing sharing a coordinate system, a date or a naming convention. Making that usable *was* the project.

**Cleaning and validation — classify by content, never by filename.** An inventory pass opens every file, decides what it actually is, and records the decision. That is how we caught `firms_viirs.csv`, which was not a CSV: its entire contents were `Invalid day range. Expects [1..5].` — a rejected API call saved as data. A filename-driven loader parses that as an empty table and reports "no flaring near the plant", silently changing the cause analysis. Instead it was quarantined with a reason and replaced by nine re-downloaded 5-day chunks across three satellites, deduplicated with the science-processed product preferred over near-real-time: 73 usable detections.

**Normalising each format into something the agent can reason over.**
- **Rasters → arrays.** EMIT products cropped with rasterio; one granule of the overpass was nodata at the plant, so the source pixel is checked and the dead granule rejected on the record.
- **.xls → events.** The STEERS exports arrived as BIFF spreadsheets (one row per emission point × contaminant), so we parse tables instead of text and group rows into events.
- **Screenshots → approximate geography.** The Sentinel-2 images had no georeferencing, so we fitted 11 visible town labels by least squares into a pixel→lat/lon mapping (**RMS 0.47 km**) and tagged everything built on them `quality: low`.
- **PDF → pages a model can read.** Pages are scored against the agent's question, the top three rendered at 110 dpi, and sent to OMNI with the question — the renders are kept as evidence.
- **Tables → pictures, deliberately.** The parsed emissions-event rows are rendered *back* into a table image for OMNI, so it reads the filing the way a regulator sees it, while every number used in the comparison comes from the dataframe, not from the model.

**Multi-source resolution and conflict.** The whole verdict is a conflict between sources: a satellite says ~23 t/h of methane, the operator's own filings for that window report VOCs and no matching event. The agent's job is to state the disagreement precisely rather than resolve it away.

**Error handling — missing data is a result, not an exception.** Any tool can raise a `DataGap`, which becomes a `status: "data_gap"` envelope, and `NOT_ASSESSED: data not available` is a legitimate row in the regulatory table. When the Carbon Mapper cross-check never arrived we used a placeholder labelled **SYNTHETIC** in the manifest, the chart, the ledger and the agent's own prompt — so the agent reports the cross-check *and* that it can't be trusted.

**Decision-making under uncertainty.** Every tool result carries its own `warnings`, `assumptions` (with a `verify` flag) and the exact subset used, so caveats travel with the number. Uncertainty is quantified — a 2,000-draw Monte Carlo giving 15.0–29.1 t/h — and stress-tested: alternative wind and density conventions span roughly 20–56 t/h. The detection, the attribution and "two orders of magnitude over the threshold" survive all of them; the precise value does not, and the report says so. One of the five questions our evidence reranker always asks is *which data are unreliable, synthetic, missing or in conflict* — so the mess is not something the pipeline survives, it is something the conclusion must account for.
