# models/ — Student B (Model Development)

Turns the data cube into one **risk score (0–1) per lake per 10-day window**, with the reason
attached. Built to the project spec (`../docs/GEWS_Project_Concise.pdf`).

## Code
- `gews_spec.py` — the pipeline. Per-lake Isolation Forest (300 trees, contamination 0.02),
  per-signal scoring, **weighted p-norm (p=3)** fusion, **walk-forward** fitting, causal
  deseasonalisation, the leave-one-out **driver**, and the abstain / watch-concern-high rules.
- `gews_modelling.ipynb` — the same pipeline as a Colab notebook (upload `lake_data.zip`, run all).
- `METHODOLOGY_NOTE.md` — method write-up and viva prep.

Run:
```bash
python gews_spec.py ../data/lake_data outputs
```
First run fits the models (~9 min) and caches per-signal scores in `outputs/per_signal_cache/`;
later runs are instant.

## Outputs (committed — model 2.1.0)
- `anomaly_scores_all_lakes.csv` — risk, band, driver, status for every lake/window → **Students C & D**
- `watchlist_latest.csv` — the current ranked watch-list → **Student D**
- `detector_comparison.csv`, `ablation_results.csv` — evidence for model choices
- `south_lhonak_2023.png` — the Sikkim trajectory chart
- `experiment_log.json` — settings for reproducibility
- `per_signal_cache/` — saved per-signal scores (speeds up re-runs; safe to delete)

## Key numbers
Isolation Forest run-up **0.765** (spec target 0.769), the lowest false-alarm rate of the four
detectors; **lake area** and **glacier speed** are the load-bearing signals.
