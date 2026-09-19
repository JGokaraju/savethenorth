# Synthetic placeholder data

`carbonmapper_plumes_SYNTHETIC.csv` is **not real data**. No Carbon Mapper export was provided, so the
team asked for a best-guess stand-in so that the cross-check (§6.8) and annualization (§6.9) code
paths run end to end. Only the 2025-08-08 plume ID and the ~21,500 kg/h figure come from the brief;
every other row (the Tanager detection and both non-detect overpasses) is invented.

The inventory only uses this file when `assets/` has no Carbon Mapper table. It marks the slot
`synthetic: true`, and every tool, chart and verdict that uses it labels it SYNTHETIC.
Replace it by dropping a real export into `assets/` and re-running `python tasks.py prep`.
