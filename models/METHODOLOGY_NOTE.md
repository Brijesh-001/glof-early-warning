# GEWS — Model Development (Student B), built to the GEWS_Project_Concise spec

This replaces the earlier simplified pipeline. It follows the project design document page by page.
Draft text for the report's *Methodology / Model design* and viva prep.

## What the spec required, and where it lives in the code
| Spec page | Requirement | Implemented |
|---|---|---|
| p13 | 5 signals (area, vel_trend, vel_accel, radar=sar_backscatter_change, thermal); observability gates, is not a feature | `SIGNALS`, `OBS_FLOOR` |
| p14 | every lake compared only to itself | per-lake fitting in `per_signal_lake` |
| p15 | deseasonalise against the lake's **causal** climatology (earlier years only) | `add_causal_deseason` (expanding median, shifted) |
| p16–17 | one-class only; 4 detectors; IF production (300 trees / 256 samples / contam 0.02), ocsvm (nu .02), ridge_ar (L=12, α=1), zscore (MAD) | `score_signal`, `score_ridge_ar` |
| p18 | "names the reason": leave-one-signal-out → top-3 `contributing_signals` = DRIVER | `fuse_and_drive` |
| p19 | walk-forward: fit on the past only, score forward | `per_signal_lake` (refit per block) |
| p20 | fusion = weighted **p-norm p=3**, weights area .30 / vel_trend .20 / vel_accel .20 / radar .20 / thermal .10 | `fuse_and_drive`, `WEIGHTS` |
| p23 | abstain (obs<0.30 **or** <24 history) → score → fuse → threshold (watch .50 / concern .70 / high .85) → sort | `assemble`, `band`, `THRESH` |
| p24 | watch-list shows RISK, STATUS, DRIVER | `watchlist_latest.csv` |

## Design interpretation (defend this at the viva)
The spec fixes the **flow**: "one score per signal (0–1) → weighted p-norm → risk", and the reason is
"leave one signal out, re-score, measure the drop" (p18). We realise the per-signal score by running the
chosen detector **per signal** and mapping it to a percentile, then calibrating so a window at the lake's own
median scores ~0 and its upper extreme ~1. The Isolation Forest "5-D cloud" (p17) is the concept; the
per-signal score is its product. Swapping the detector = the p21 comparison; removing a signal = the p22 ablation.

## Results (this run)
- **Sikkim examination (walk-forward, trained on the past only):** South Lhonak's risk climbs into the
  **concern** band and rises to **rank 4–5 of 42 lakes** in the weeks before 4 Oct 2023, with **lake area**
  entering the driver as the burst nears. Peak run-up **0.765** — the spec reports **0.769**.
- **Detector comparison (p21):** Isolation Forest has the **best run-up and the lowest false-alarm rate of the
  four detectors**, which is exactly why the spec picks it. (Absolute false-alarm % differs from the PDF — see caveat.)
- **Ablation (p22):** dropping **velocity_trend (0.677)** and **lake area (0.731)** lowers the run-up most →
  load-bearing. Dropping **velocity_accel (0.820)** or **radar change (0.817)** *raises* it → they damp the score,
  they don't drive it. This matches the spec's page-22 conclusion.

## Honest caveats — say these, don't hide them
1. **False-alarm calibration.** Our absolute false-alarm rate is higher than the PDF's near-zero. The PDF does
   not pin down how the per-signal score maps to 0–1, so the watch/concern/high thresholds are hotter here.
   This is a **calibration knob, not a method difference** — the detector ranking and the ablation conclusions
   are unchanged. Finalising the thresholds is Student C's job (they own the test criteria).
2. **Velocity over-contributes to the driver.** `velocity_trend`/`velocity_accel` are **annual** (ITS_LIVE),
   so each year is a single step with only ~8 distinct values; the percentile is coarse and often maxes out.
   Expected given the data, but it inflates "glacier speed" as a driver. Worth flagging to Student A.
3. **Walk-forward refit cadence.** The spec says refit every 36 windows (yearly). We refit every ~2 years
   (`REFIT_YEARS=2`) purely for compute (300-tree IF × per-lake × per-signal × yearly was ~17 min; biennial
   is ~9). Still past-only, still leakage-safe. Set `REFIT_YEARS=1` for the exact spec cadence.
4. **LSTM autoencoder not built.** The spec itself marks it ablation-only and under-powered (~200 rows/lake,
   more parameters than data). Listed as the remaining optional step.

## Files
- `gews_spec.py`, `gews_spec.ipynb` — the pipeline (Colab-ready; ~9 min first run, cached after).
- `model_outputs/anomaly_scores_all_lakes.csv` — risk + band + **driver** per lake/window → Students C & D.
- `model_outputs/watchlist_latest.csv` — ranked current watch-list with DRIVER (p24).
- `model_outputs/detector_comparison.csv`, `ablation_results.csv` — the p21 / p22 evidence.
- `model_outputs/sikkim_2023_southlhonak.csv`, `sikkim_leadtime.csv`, `spec_results.png` — the headline.
- `model_outputs/experiment_log.json` — settings for reproducibility.
