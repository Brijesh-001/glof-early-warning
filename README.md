# GEWS — Glacial Lake Outburst Flood Early-Warning System

Satellite-based decision support that watches Himalayan glacial lakes and flags the ones
behaving abnormally — so a disaster-management officer can act weeks ahead, not minutes.
Major Project, 7th Semester · Dept. of AI & ML, DSCE.

> **Decision support only.** This system never issues a public alert. Where it cannot see a
> lake it reports **cannot assess** — which is not the same as *safe*.

---

## What this repository is

The four project stages, assembled into one connected pipeline. Each stage writes files with
a fixed schema; the next stage reads them. That is the whole "connection" — a wrong number can
always be traced to exactly one stage.

```
 data/        →   models/          →   evaluation/       →   dashboard/
 42 lakes,        per-lake anomaly     lead time, leak        ranked watch-list
 10-day windows   score + driver       check, generalisation  for the officer
 + DEM            → risk 0–1           → is it trustworthy?    → a human decides
```

| Stage | Folder | Reads | Writes |
|-------|--------|-------|--------|
| Data | `data/` | satellite archives | `lake_data/*.csv`, `dem_static.csv` |
| Modelling | `models/` | `data/lake_data/` | `outputs/anomaly_scores_all_lakes.csv`, `watchlist_latest.csv` |
| Evaluation | `evaluation/` | `models/outputs/` | `outputs/` (metrics, leak check, charts) |
| Dashboard | `dashboard/` | `models/outputs/` | the Watch Console UI |

---

## Quick start

```bash
pip install -r requirements.txt

# run the whole chain end-to-end (model scoring takes ~9 min the first time, then caches)
python run_pipeline.py

# or run a stage on its own:
cd models      && python gews_spec.py ../data/lake_data outputs        # score all lakes
cd evaluation  && python gews_evaluation.py                            # metrics + Sikkim test
cd evaluation  && python gews_leak_gen.py                              # leak check + unseen-lake
cd evaluation  && pytest test_evaluation.py                            # 9 harness unit tests

# open the Watch Console (data, modelling, evaluation and testing views)
python dashboard/run.py                                                 # http://127.0.0.1:8000
```

The committed `*/outputs/` files are the current results (model **2.1.0**, data **v3-final**),
so you can read every result without re-running anything.

---

## The method, in one paragraph

Only one GLOF is confirmed in our lakes and years (South Lhonak, 4 Oct 2023), so the system is
never trained to recognise disasters. Instead it learns what each lake looks like when **calm**
and measures how far the latest 10-day window has drifted from that lake's own normal. Five
signals (lake area, glacier speed, glacier acceleration, a thermal index, and radar-backscatter
change) are scored per lake, fused with a weighted p-norm into one **risk score (0–1)**, and the
top signals are reported as the **driver** ("why"). If too little of the lake was visible, the
window **abstains** instead of scoring. Fitting is **walk-forward** — a window is only ever scored
by a model trained on its own past — so the retrospective test cannot cheat.

---

## Headline results (see `evaluation/EVALUATION_REPORT.md`)

- **Detects the real event:** South Lhonak reaches the *watch/concern* level well before the burst.
- **No leakage:** pre-event scores are identical whether or not post-event data exists (max diff 0.00).
- **Generalises:** held out entirely, South Lhonak still peaks at 0.79 — the method didn't just memorise.
- **Honest limitation:** ~2.5 false alarms per lake-year at the current thresholds, and the real
  event never reaches sustained *high*. So the system is usable as a **ranked watch-list**, not yet
  as an automatic alarm. Threshold calibration is the main open task.

---

## Known limitations / open work

- **DEM is a 2-lake proof-of-concept.** `data/dem_static.csv` covers South Lhonak and Gurudongmar
  only (coordinates for the other 40 not yet collected). It feeds a future *hazard index*, not the
  anomaly model.
- **Radar-benefit number** needs per-sensor observability from the data stage (we only have the combined value).
- **Threshold calibration** (false-alarm rate) is the main fix needed in the modelling stage.
- The trained model artifact (`gews_model.pkl`, ~375 MB) is **not committed** — see
  `models/MODEL_ARTIFACT.md` to regenerate it.

---

## Project stages

- **Data Collection:** satellite extraction, cloud masking, the common 10-day grid, radar (`data/`).
- **Model Development:** the anomaly pipeline and risk score (`models/`).
- **Testing & Evaluation:** the honest test suite and the Sikkim experiment (`evaluation/`).
- **App Development:** the Watch Console dashboard (`dashboard/`), report and paper.

See `docs/` for the full project spec.
