# evaluation/ — Student C (Model Testing & Evaluation)

Judges Student B's model honestly. Metrics are **lead time, false alarms per lake-year, and
cannot-assess rate** — never accuracy (with one flood in years of data, "always safe" is 99.9%
accurate and useless).

## Code
- `gews_evaluation.py` — the harness: truth list, metrics, Sikkim retrospective, threshold sweep,
  failure cases. Self-tests on fake data before touching real scores.
- `gews_leak_gen.py` — the **leak / cheating check** (proves the pipeline is causal) and the
  **unseen-lake** generalisation test. Imports the model (`gews_spec.py`, copied here so it runs
  standalone — it is identical to `../models/gews_spec.py`).
- `test_evaluation.py` — **pytest** suite, 9 tests including the leak guard.

Run (from this folder):
```bash
python gews_evaluation.py        # reads ../models/outputs/anomaly_scores_all_lakes.csv
python gews_leak_gen.py          # reads ../data/lake_data
pytest test_evaluation.py        # 9 pass
```

## Reports
- `EVALUATION_REPORT.md` — the protocol + Results & Discussion (draft for the report chapter).
- `best_model_summary_report.md` — the model-comparison summary (which detector, and why).
- `model_testing_summary.pdf` — the compiled testing summary.

## Outputs (committed)
- `outputs/threshold_sweep.csv` — lead time vs false alarms trade-off
- `outputs/failure_cases.csv` — the biggest control-lake false alarms, with their drivers
- `outputs/sikkim_trajectory_2023.csv` — South Lhonak through 2023
- `outputs/evaluation_report.json`, `leak_and_generalisation.json` — all numbers
- `outputs/evaluation_dashboard.png` — the four-panel results figure

## Headline
Detects the real event (watch/concern, not sustained high), **leak check clean (max diff 0.00)**,
generalises to an unseen lake (0.79), but **~2.5 false alarms per lake-year** at current thresholds
— usable as a ranked watch-list, not yet as an alarm.
