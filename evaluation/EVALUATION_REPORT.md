# GEWS — Model Testing & Evaluation (Student C)

Judging Student B's model honestly, per the Student C handbook. Draft text for the
report's *Results and Discussion* chapter and the evaluation protocol.

## 1. Evaluation protocol (fixed before looking at results)
- **Truth list.** Inside the study window (2017–2026) and our 42 lakes there is exactly **one**
  confirmed moraine-dam outburst: **South Lhonak, 4 October 2023**. The other 41 lakes are **calm
  controls**. (The full HMA GLOF database — Zenodo 10.5281/zenodo.7271187 — is the week-3 manual
  cross-check; it adds historical events but none fall inside our lakes-and-years window.)
- **The leakage rule.** When testing whether the system would have warned about the flood, only data
  from **before** 4 Oct 2023 may be used. This is enforced by the model's walk-forward fitting and
  verified in test 4 below.
- **Metrics — not accuracy.** With one flood in years of data, "always safe" scores 99.9% accurate, so
  accuracy is banned. We use: **lead time** (how early a warning came), **false alarms per lake per
  year** on controls, and the **cannot-assess rate**. Precision/recall are reported but caveated (n=1).

## 2. Results

### Sikkim retrospective (the headline)
| Threshold | Lead time before burst | Detected? |
|---|---|---|
| watch (0.50) | **25.1 weeks** | yes |
| concern (0.70) | **25.1 weeks** | yes |
| high (0.85) | — | **no** |

South Lhonak sits in the **watch/concern** band for much of 2023 and is clearly elevated before the
burst, but **never reaches a sustained "high" alert**. So the system would have raised an early,
low-confidence flag months ahead — not a confident alarm.

### False alarms and cannot-assess
| Metric | Value |
|---|---|
| False alarms per control lake per year (watch / concern / high) | **2.57 / 2.23 / 2.46** |
| Detection recall at watch/concern | 1.0 (1 of 1 event) |
| Detection precision at watch/concern | **≈0.001** (857 control false alarms) |
| Cannot-assess rate overall | **18.5%** |
| Cannot-assess — monsoon vs dry | **17.6% vs 19.0%** |

### Leak / cheating check (test 4)
Scoring South Lhonak with the full series vs a series truncated at the event date gives **identical
pre-event scores (max difference 0.00 across 194 windows)** — the pipeline is **causal; no future data
leaks backward.** When we *deliberately* let the model use future data, pre-event scores shift by
**0.245 on average** — so the check actually catches leakage. This is the answer to the viva's "how do
you know it didn't see the future?"

### Unseen-lake generalisation (test 6)
Trained only on the **other** lakes (and only pre-event data for South Lhonak), the held-out South
Lhonak still peaks at **0.79 (concern)** before the burst — so the method learned something **general**,
not memorised. Held-out control lakes stay low (5–11% of windows in concern).

### Biggest false alarms (failure cases)
The largest control-lake alarms are driven mostly by **radar-change** spikes and the **annual
velocity** signals (`sccc_beas_34` — radar change; `tso_lhamo`, `ndma436_chandra` — glacier
speed/accel). These are the case studies to write up.

## 3. Discussion — what the numbers mean
**The idea works; the calibration does not, yet.** The system detects the one real event, proves it
isn't leaking the future, and generalises to a lake it never saw. But at the spec's thresholds it fires
**~2.5 times per lake per year** on calm lakes, giving a precision near zero, and it never reaches
"high" for the actual disaster. As a decision-support tool that ranks lakes for an officer, that is
usable; as an **alarm**, it is **too sensitive and not deployable as-is**.

**What drives the false alarms:** mainly the annual velocity signals (coarse, ~8 distinct values per
lake, so they max out easily) and raw radar-change spikes. Lowering their weight, or down-ranking
alarms driven *only* by velocity, is the most promising fix — a concrete recommendation back to
Student B.

**Monsoon coverage is a quiet win:** cannot-assess is *not* worse in the monsoon (17.6% vs 19.0% dry),
which is consistent with radar keeping lakes visible through cloud — the project's core claim.

## 4. What is NOT done here — hand these off
- **Full HMA GLOF cross-check** (week 3): download from Zenodo 10.5281/zenodo.7271187, filter to Indian
  events, confirm none fall in our lakes-and-window, and verify the South Lhonak date against a second
  source. Not reachable from this environment — a manual step.
- **Radar-benefit number** (week 12, with Student A): "optical-only vs optical+radar assessable
  windows in the monsoon." Our data only has the **combined** observability, so this needs A's
  **per-sensor** counts. Calculation: `radar_gain = (% monsoon windows assessable with S1+S2) − (% with
  S2 only)`, averaged per lake.

## 5. Files
- `gews_evaluation.py` — the harness (metrics, Sikkim test, false-alarm, threshold sweep, failure cases).
- `gews_leak_gen.py` — the leak/causality check and the unseen-lake test.
- `test_evaluation.py` — pytest suite (9 tests, incl. the leak guard). Run `pytest test_evaluation.py`.
- `eval_outputs/` — all result tables, the dashboard chart, and the JSON reports.
