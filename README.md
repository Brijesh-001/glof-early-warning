# GEWS: Glacial Lake Outburst Flood Early-Warning System

Decision support for 41 Himalayan glacial lakes, built from free satellite data.
**This system never issues a public alert.** Where it cannot see, it says so.

## Run the dashboard

```bash
conda env create -f environment.yml   # or: pip install -r requirements.txt
conda activate gews
streamlit run app/app.py
```

Open http://localhost:8501. With no pipeline output present, the dashboard runs on
synthetic demo data and shows a demo banner on every page.

## Pages

| Page | What it answers |
|---|---|
| Watch-list | Which lakes are most unlike their own past this window? Which could not be assessed, and why? |
| Lake detail | Risk history with blind spells, per-signal scores, observability, and an A4 evidence PDF with a signature block |
| What we can see | Assessability with and without radar, per-lake radar gain, a lake-by-window grid, longest blind spells |
| How it was tested | Retrospective test on South Lhonak, detector comparison, signal ablation, the instrument-limit argument |
| Scope and limits | What the system is and is not, how the ranking is produced, known limits, terms |

The 10-day window selector in the sidebar applies to every page.

## Connecting the pipeline

The dashboard reads (never writes) these files from `data/processed/`, or from the folder in `GEWS_DATA_DIR`:

| File | Layer | Columns |
|---|---|---|
| `lakes.csv` | register | `lake_id, name, region, lat, lon`; optional `elevation_m, area_ref_km2`, and per-lake threshold overrides `watch, concern, high` |
| `features.parquet` | L3 | `lake_id, window_start, lake_area_km2, velocity_trend, velocity_accel, thermal_index, sar_backscatter_change, observability, obs_optical, obs_radar, obs_velocity, obs_thermal` |
| `scores.parquet` | L4 | `lake_id, window_start, risk, abstain_reason, score_<signal>` for each of the 5 signals, `contributing_signals` (`;`-separated, most important first) |
| `evaluation.json` | evaluation | optional; same keys as `REPORTED` in `app/gews_ui/results.py` |
| `events.csv` | — | optional: `lake_id, date, description` |
| `manifest.json` | — | optional: `{"data_version": "v3-final"}` |

Rules the loader enforces:

- An abstaining window has `risk = NaN` and a non-empty `abstain_reason`. A numeric risk on an abstaining row is rejected.
- `window_start` is the 1st, 11th or 21st of a month (36 windows a year).
- Missing windows are shown as gaps. Nothing is interpolated.

## Tests

```bash
pytest tests/
```

`tests/test_dashboard.py` checks the display rules: blind lakes are never ranked, NaN never becomes 0 or "normal",
gaps are kept, the fusion matches the formula, and the evidence PDF builds for both scored and blind lakes.

## Code layout

```
app/
  app.py              entry point, navigation, window selector
  views/              one file per page
  gews_ui/
    config.py         frozen thresholds, fusion weights, fusion and level functions
    data.py           data contract, loader, validation, watch-list and series views
    demo.py           synthetic demo data (same schema)
    results.py        evaluation results (evaluation.json or deck values)
    charts.py         Plotly figures; gaps are never bridged
    components.py     watch-list table and banners
    report.py         A4 evidence PDF
    theme.py          colours, type, CSS, Plotly template
.streamlit/config.toml
tests/test_dashboard.py
```

Data: ESA Copernicus, NASA, NRSC/ISRO. Code MIT-licensed.
