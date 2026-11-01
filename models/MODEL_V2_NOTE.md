# GEWS model v2: what changed, and what it does and does not prove

v2 keeps v1's per-signal Isolation Forests (walk-forward, per lake, causal) and changes only what happens
after the per-signal scores exist. Code: `models/gews_v2.py`. Run: `python run_pipeline.py` (or
`cd models && python gews_v2.py ../data/lake_data outputs`; uses the cached per-signal scores, takes seconds).
v1 scores are kept in `models/outputs/anomaly_scores_v1.csv`; the side-by-side is `models/outputs/v1_vs_v2.csv`.

## Why change it
v1's own methodology note admits the thresholds run hot and that annual velocity inflates the driver. Looking
at the output showed more:

| Problem in v1 | Evidence |
|---|---|
| Common-mode noise | In 2019-2020 about 98 % of all 42 lakes sat at Concern or above at the same time. A flag shared by nearly every lake says nothing about one lake. |
| Lone-signal flags | Fusion divided by the weights of the signals that happened to be present, so one thermal reading at 0.7 became a Concern. |
| Hot, uncalibrated thresholds | 63.7 % of calm-lake windows were at Watch, 46 % at Concern, 18 % at High. |
| Annual-signal plateaus | Glacier speed and acceleration are yearly values; in 2022 eight calm lakes were flagged High in all 36 windows on velocity alone. |

## What v2 does
1. **Peer-relative scores.** Each signal's score has the fleet median of that signal in the same window subtracted. A lake has to stand out from its peers as well as from its own history. Uses one window's cross-section only, so it is causal. Needs 8 or more lakes in the window; otherwise the last fleet median is carried forward for at most 6 windows.
2. **Corroboration.** The weighted p-norm (p = 3, weights unchanged) is divided by the full weight sum, so a missing signal means "no evidence", not "evidence of anomaly".
3. **Annual-signal cap.** Glacier speed and acceleration can lift a lake to Watch, but not to Concern or High, unless a fast signal (lake area, radar change, thermal) is also elevated.
4. **Budget calibration.** The fused score is mapped onto the same 0.50 / 0.70 / 0.85 tiers, now anchored to false-alarm budgets chosen up front: Watch = top 10 %, Concern = top 3 %, High = top 1 % of calm-lake windows. Calibration is walk-forward: each year uses only control lakes (never South Lhonak) and only windows before 1 January of that year. The 2023 outburst is scored with a calibration that has seen nothing from 2023 on.

Tried and rejected: a 3-window rolling median (lowered the event signal, no matching gain).

## Results (same evaluation code, same data)
| | v1 | v2 |
|---|---|---|
| South Lhonak rank among 42 lakes, 40 / 90 / 180 days before the burst | 7 / 9 / 6 | **2 / 2 / 3** |
| Peak score in the 40 days before the burst | 0.765 | 0.885 |
| Lead time at Watch / Concern / High (sustained) | 25.1 / 25.1 wk / never | 25.1 / 5.1 wk / never |
| Calm-lake windows at Watch / Concern / High | 63.7 / 46.0 / 18.1 % | **10.3 / 3.2 / 1.1 %** |
| False alarms per lake-year at Watch / Concern / High | 2.57 / 2.23 / 2.46 | **0.98 / 0.75 / 0.31** |
| Share of lakes at Concern in 2019-2020 | 98 % | **0.6 %** |

Checks: 17 pytest tests pass (8 new ones for v2, including that peer adjustment and calibration are causal and
that the calibration never touches the event lake or the future). Truncating the data at the burst date gives
identical pre-burst risk for all 10,248 windows of all lakes (fleet-level leak check).

## Read this before quoting the numbers
- **One confirmed outburst.** Every event number is n = 1. v2 ranks South Lhonak higher before the burst and cuts false alarms by 2.6x to 8x depending on tier, but one event cannot prove predictive skill.
- **The rank is suggestive, not conclusive.** South Lhonak is in the top 2 of 42 in about 11 % of sampled 40-day windows across the record, so a top-2 rank before the burst is better than v1's 7th but is not proof.
- **The lead time got shorter on purpose.** v1's 25-week lead at Concern came from flagging nearly half of all calm windows. At a 3 % false-alarm budget the event reaches Concern 5.1 weeks ahead and reaches High in a single window (0.885) without sustaining it for two. That is a real cost of an honest calibration.
- **Budgets are met overall, not every year.** Calm-lake windows still run above budget in 2021-2024 (for example Watch about 19-25 %); the records are drifting, and this layer cannot remove drift.
- **Percentile choices are a priori, not tuned.** 10 / 3 / 1 % were fixed before looking at the event result. Changing them moves the trade-off, and tuning them on the event would overfit one data point.
- **Still not a flood probability.** A score says how unusual a window is against that lake's history and its peers.
