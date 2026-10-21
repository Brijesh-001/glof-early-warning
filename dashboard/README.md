# dashboard/ — Student D (App Development)

The **GEWS Watch Console** — the browser dashboard a disaster-management officer opens. A FastAPI
backend reads the committed pipeline outputs and serves them as JSON; a plain HTML + Plotly
frontend draws them. Nothing is recomputed in the browser, so every number traces back to the
stage that wrote it.

## Run
```bash
pip install -r requirements.txt
python dashboard/run.py              # -> http://127.0.0.1:8000
```
Run `python run_pipeline.py` first if you want fresh model/evaluation outputs. The console works
offline: Plotly is served from the `plotly` pip package, not a CDN.

## Layout
```
dashboard/
├── run.py               # starts uvicorn (backend + frontend on one port)
├── backend/main.py      # FastAPI: JSON API over data/, models/outputs/, evaluation/outputs/
└── frontend/            # index.html, app.js, styles.css (Plotly charts)
```

## Tabs
| Tab | Shows | Source |
|-----|-------|--------|
| Watch-list | ranked latest status per lake, driver, per-lake risk history | `models/outputs/watchlist_latest.csv`, `anomaly_scores_all_lakes.csv` |
| Data | signal coverage heatmap, transformed signals per lake, per-signal anomaly scores, stats, DEM | `data/lake_data/`, `data/dem_static.csv`, `models/outputs/per_signal_cache/` |
| Modelling | detector comparison, ablation, risk distribution, band mix by year, drivers, fusion weights, abstention reasons | `models/outputs/` |
| Evaluation | lead time, threshold sweep, precision/recall per band, false alarms, leak check, unseen-lake test, failure cases. **Re-run evaluation** re-executes stage C | `evaluation/outputs/` |
| Testing | runs `evaluation/test_evaluation.py` live with pytest and charts the results | pytest |

## API
`GET /api/summary` · `/api/watchlist` · `/api/lakes` · `/api/lakes/{lake}/scores` · `/api/data/overview` ·
`/api/data/{lake}` · `/api/model` · `/api/evaluation` · `/api/images/{name}` ·
`POST /api/tests/run` · `POST /api/pipeline/evaluate`. Interactive docs at `/docs`.

## Design rules
- **Decision support only**: it never issues a public alert.
- Abstaining lakes are drawn hatched grey and are **never** coloured as low risk.
- Bands: High ≥0.85, Concern ≥0.70, Watch ≥0.50, Low below.
- No map: the data has no lake coordinates. Add `lat`/`lon` to `data/dem_static.csv` (or a new
  lake table) to enable one.
