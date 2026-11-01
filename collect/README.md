# collect/: keep the data current

`gews_collect.py` brings every lake's `data/lake_data/<lake>_windows.csv` up to the newest **finished** 10-day window,
using the same sources and rules as the Colab notebook (`golf.ipynb`):

| Signal | Source | Notes |
|---|---|---|
| Lake area | Sentinel-2 L2A (Planetary Computer) | NDWI and MNDWI water mask, keep only the water body touching the seed point. Lakes with `USE_SCL_WATER = TRUE` use ESA's scene-classification water instead |
| Radar level | Sentinel-1 RTC | mean VV dB, one orbit track only (the most common one over the record) |
| Thermal | MODIS 11A1 land surface temperature | positive-degree index |
| Glacier speed | ITS_LIVE cubes | 90th-percentile speed, one value per year; refreshed at most monthly |

Per-lake settings (seed point, box size, seed radius, Sentinel-2 tile, SCL flag) come from `data/lake_coordinates.csv`.
`shaushar_lake` has no coordinates yet, so it is skipped and reported.

## Run it

```bash
pip install -r requirements-collect.txt            # once; extra packages for the satellite downloads

python collect/gews_collect.py --verify --lake south_lhonak   # 1. does it reproduce your committed numbers?
python collect/gews_collect.py --dry-run --lake south_lhonak  # 2. preview an update, writes no CSV
python run_pipeline.py --update                               # 3. fetch + re-score + re-evaluate everything
```

Do step 1 for a few lakes before trusting step 3. It re-derives the last six windows that already have data and
compares them with your CSV (lake area, radar level, thermal). A lake that says `DIFFERS` has a different tile, seed or
threshold from the one used when its history was collected: fix that lake's row in `data/lake_coordinates.csv` first.

## How an update works
1. **Newest finished window.** A window is finished once its last day plus `--margin-days` (default 3) has passed. On
   31 Oct 2026 that is the window starting 18 Oct (it ended 27 Oct); the window starting 28 Oct finishes on 6 Nov.
2. **Per lake:** find the newest window that already has data, step back two windows (late scenes), fetch only that
   date range, and rebuild those windows. Scenes already in `data/raw_cache/` are never downloaded again.
3. **Merge, never rewrite history.** Rows older than the rewind point stay byte-for-byte identical. Rewound windows are
   replaced only when the new pull actually saw scenes. Radar change is recomputed so it is continuous across the seam.
4. **Failures are isolated.** If one lake fails (network, no scenes) it keeps its old data, shows as behind on the
   dashboard, and the others carry on. See `data/update_log.json`.
5. **Re-score and re-evaluate.** `run_pipeline.py --update` then rescores every lake (production detector only,
   in parallel; about 1 to 5 minutes depending on your cores), applies the v2 fusion, and refreshes the evaluation.
   A fingerprint of the data folder guarantees the scorer never reuses scores built from older data.

The newest window is usually thin because scenes arrive a few days late. That is expected: the next run re-fetches the
last two windows and fills it in.

## Things to know
- **Derived minimum lake area.** The notebook used a hand-set `MIN_AREA` per lake. The updater uses 10 % of the lake's own
  summer median from the committed history, so a shadow or ice patch is not mistaken for water.
- **Velocity.** ITS_LIVE gives one value per year, so only the current year's two velocity columns are refreshed
  (at most monthly); older years are never touched.
- **Tile.** For `A / B` entries the first tile is used. For `unresolved` or partial entries the tile with the most
  scenes over the box is chosen and remembered in `data/raw_cache/<lake>_meta.json`.
- **Planetary Computer key.** Optional. Set `GEWS_PC_KEY` in your environment for faster, unthrottled reads.
- **Tests.** `python -m pytest collect -q` runs 24 offline tests with a fake satellite source (grid, merge, idempotence,
  failure isolation).

## Schedule it (every 10 days)
- **Windows:** Task Scheduler, a daily trigger running
  `C:\path\to\project\.venv\Scripts\python.exe run_pipeline.py --update` with "Start in" set to the project folder.
  Running daily is safe: when nothing new has finished it does almost nothing.
- **macOS / Linux:** `0 6 * * * cd /path/to/project && .venv/bin/python run_pipeline.py --update >> data/update_cron.log 2>&1`
- Or use the **Refresh data** button in the dashboard header.
