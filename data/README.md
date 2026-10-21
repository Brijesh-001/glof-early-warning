# data/ — Student A (Data Collection)

The output of the data stage: satellite measurements reduced to one tidy table per lake.

## Files
- `lake_data/*.csv` — **42 lakes**, one file each. One row per **10-day window** (2017–2026),
  columns:
  - `window` — window start date
  - `lake_area_km2`, `lake_area_min_km2` — lake area (Sentinel-2 optical)
  - `vv_db`, `sar_backscatter_change` — radar backscatter and its change (Sentinel-1)
  - `thermal_index` — melt-season temperature index (MODIS LST)
  - `velocity_trend`, `velocity_accel` — glacier speed and acceleration (ITS_LIVE, **annual**)
  - `observability` — 0–1, how much of the lake was visible this window (gates the model)
- `dem_static.csv` — static terrain per lake (Copernicus DEM): elevation min/max, relief,
  mean and 90th-percentile slope. **Currently 2 lakes only** (South Lhonak, Gurudongmar) — a
  proof-of-concept; coordinates for the other 40 are not yet collected.

## Notes
- Gaps are **never filled in**: a window with no usable observation stays empty and its
  `observability` stays low. The model abstains on those rather than guessing.
- Date formats are mixed across files (ISO and M/D/YYYY); the model parses both. For a clean
  export, standardise to `YYYY-MM-DD`.
- `velocity_*` updates once a year (ITS_LIVE native resolution), so it separates years/lakes,
  not individual windows.

How the raw satellites were turned into these files is documented in
`../docs/GEWS_Colab_Code_Illustrated.pdf`.
