# dashboard/ — Student D (App Development)

The **GEWS Watch Console** — the browser dashboard a disaster-management officer opens. A FastAPI
backend reads the committed pipeline outputs and serves them as JSON; a plain HTML + canvas + Plotly
frontend draws them (no Streamlit, no build step). Nothing is recomputed in the browser, so every number traces back to the
stage that wrote it.

## Run
```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python dashboard/run.py              # -> http://127.0.0.1:8000   (--port 9000 to change)
```
Run `python run_pipeline.py` first if you want fresh model/evaluation outputs. The console works
offline: Plotly is served from the `plotly` pip package, not a CDN.

## Layout
```
dashboard/
├── run.py               # starts uvicorn (backend + frontend on one port)
├── backend/main.py      # FastAPI: JSON API over data/, models/outputs/, evaluation/outputs/
└── frontend/            # index.html, styles.css, board.js (triage board + watch surface), app.js (pipeline tabs, Plotly)
```

## Tabs
| Tab | Shows | Source |
|-----|-------|--------|
| Triage board | six tier cards, attention queue, selected-lake card, every-lake heatmap (triage / risk / vs peers), lake workbench with raw signals, "can I trust this" and alert-volume panels | `/api/board`, `/api/lakes/{lake}/scores`, `/api/data/{lake}`, `/api/evaluation` |
| Watch surface | rotatable 3D columns (height = risk) placed by real lon/lat and a ranked watch-list with 90-day traces, driven by the same window scrubber | `/api/board` |
| Data | signal coverage heatmap, transformed signals per lake, per-signal anomaly scores, stats, DEM | `data/lake_data/`, `data/dem_static.csv`, `models/outputs/per_signal_cache/` |
| Modelling | v1 vs v2 comparison, detector comparison, ablation, risk distribution, band mix by year, drivers, fusion weights, abstention reasons | `models/outputs/` |
| Evaluation | lead time, threshold sweep, precision/recall per band, false alarms, leak check, unseen-lake test, failure cases. **Re-run evaluation** re-executes stage C | `evaluation/outputs/` |
| Testing | runs `evaluation/test_evaluation.py` live with pytest and charts the results | pytest |

## API
`GET /api/board` · `/api/summary` · `/api/watchlist` · `/api/lakes` · `/api/lakes/{lake}/scores` · `/api/data/overview` ·
`/api/data/{lake}` · `/api/model` · `/api/evaluation` · `/api/images/{name}` ·
`POST /api/tests/run` · `POST /api/pipeline/evaluate` · `POST /api/pipeline/update` (fetch, re-score, re-evaluate in the
background) · `GET /api/pipeline/update/status`. Interactive docs at `/docs`.

`/api/board` returns every lake x every window in one payload (risk, observability, driver, abstain reason, tier code, per-window
share of lakes at Concern+, fleet median) so the browser only draws and filters.

## Triage tiers
Thresholds come from `models/outputs/experiment_log.json` (High 0.85, Concern 0.70, Watch 0.50).
`cannot_assess` is never shown as clear. A High or Concern lake is shown as **Regional** (discounted) when 40 % or more of
assessed lakes are at Concern or above in the same window, since a signal shared by most lakes is more likely seasonal or
regional than lake-specific. "Latest" is the newest window with data for at least half of the lakes.

## Design rules
- **Decision support only**: it never issues a public alert.
- Abstaining lakes are drawn hatched grey and are **never** coloured as low risk.
- Bands: High ≥0.85, Concern ≥0.70, Watch ≥0.50, Low below.
- Coordinates come from `data/lake_coordinates.csv` (seed points, 41 of 42 lakes). A lake without coordinates gets disabled
  imagery buttons and is placed beside its region on the 3D surface. Add its `lon`/`lat` to that file to enable them.
