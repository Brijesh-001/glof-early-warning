# GEWS — Glacial Early Warning System

## Overview

The **Glacial Early Warning System (GEWS)** is a satellite-based decision-support system designed to study and monitor glacial lakes in the Indian Himalaya for potential Glacial Lake Outburst Floods (GLOFs).

Glacial Lake Outburst Floods occur when water stored in a glacial lake is suddenly released, potentially causing severe downstream flooding and damage to communities, infrastructure, and ecosystems.

GEWS combines satellite-derived environmental indicators into a fused risk score and presents the results through an interactive watch console. The system supports historical risk analysis, lake prioritisation, and assessment of satellite data availability.

The project focuses on two important questions:

- Can satellite-derived indicators identify periods of elevated glacial lake risk?
- How can multiple satellite sensors improve lake monitoring when some observations are unavailable?

## Key Features

- **Triage Board:** Sorts every lake into High, Concern, Watch, Regional (discounted), Cannot assess or Clear for the selected 10-day window, with an attention queue that says which lakes need a human look and why.
- **Every Lake, Every Window Heatmap:** All 42 lakes across all windows in one view, switchable between triage tier, risk, and difference from the fleet median.
- **Interactive 3D Watch Surface:** Visualises glacial lakes as columns whose heights represent their fused risk scores for a selected time window.
- **Time-Series Analysis:** Explores historical risk scores across multiple observation windows from 2017 to 2024.
- **Ranked Watch List:** Orders lakes by their current assessed risk and displays severity indicators, status labels, and recent risk trends.
- **Lake-Level Analysis:** Displays historical risk scores, risk thresholds, and periods when the system could not assess a lake.
- **Multi-Sensor Monitoring:** Incorporates optical, Synthetic Aperture Radar (SAR), surface velocity, thermal, and terrain-related indicators.
- **Data Observability:** Shows the availability and contribution of different sensor types to lake assessment.
- **Event Analysis:** Supports examination of the South Lhonak Lake outburst on 4 October 2023.
- **Abstention-Aware Visualisation:** Explicitly distinguishes lakes that cannot be assessed from lakes with low assessed risk.
- **Pipeline Tabs:** Data, Modelling, Evaluation and Testing tabs show the stages behind every number, and can re-run the evaluation and the test suite from the browser.
- **Works Offline:** Plotly is served from the installed `plotly` package, so the console needs no internet connection once installed.

## System Architecture

The console is a small FastAPI backend that reads the committed pipeline outputs and serves them as JSON, plus a plain HTML, CSS and JavaScript frontend. There is no frontend build step and no separate frontend server.

| Component | Purpose |
|---|---|
| `data/` | One tidy CSV of satellite measurements per lake (42 lakes, 10-day windows) |
| `models/` | Isolation Forest scoring; writes `models/outputs/` |
| `evaluation/` | Lead-time, false-alarm, leak and unseen-lake tests; writes `evaluation/outputs/` |
| `dashboard/backend/main.py` | FastAPI JSON API (`/api/board`, `/api/evaluation`, ...) over the outputs above |
| `dashboard/frontend/` | `index.html`, `styles.css`, `board.js` (triage board and watch surface), `app.js` (pipeline tabs) |
| `collect/` | Data updater: fetches new finished windows from the satellite archives and merges them into `data/lake_data/` |
| `run_pipeline.py` | Runs data, model and evaluation stages end to end (`--update` adds the fetch step) |

The backend never recomputes model scores. Every number on screen traces back to the stage that wrote it.

## Dataset and Study Period

The current data cube contains **42 glacial lakes across 360 ten-day observation windows**, starting 1 January 2017. Satellite readings run to 28 September 2026; later windows are empty and are reported as *cannot assess*. The model learns each lake's normal behaviour from 2017-2024 and scores every window against it.

The data includes:

- Fused risk scores and assessment status.
- Optical and SAR-derived lake-area indicators.
- Surface velocity trends and acceleration.
- Thermal indicators.
- SAR backscatter changes.
- Terrain and slope-related indicators.
- Sensor observability and reasons for unavailable assessments.
- Lake coordinates, provenance information, and potential glacial lake identification flags.

### Data Sources

The study uses satellite and geospatial datasets accessed through the following sources:

- **Sentinel-2 Level-2A:** Optical satellite observations.
- **Sentinel-1 RTC:** Radar observations for monitoring under conditions where optical imagery may be limited.
- **MODIS MOD11A1:** Land surface temperature observations.
- **Copernicus GLO-30:** Digital elevation data.
- **NASA/JPL ITS_LIVE:** Surface velocity observations.
- **NRSC/ISRO Glacial Lake Atlases:** Glacial lake inventory information.

The data-processing pipeline uses the Microsoft Planetary Computer STAC API and other relevant public data repositories to access the required datasets.

## Risk Assessment Methodology

GEWS combines multiple environmental indicators into a fused risk score. The interface uses the following predefined thresholds to classify assessed lakes.

| Risk Level | Fused Risk Score |
|---|---:|
| High | ≥ 0.85 |
| Concern | ≥ 0.70 |
| Watch | ≥ 0.50 |
| Low | < 0.50 |
| Cannot Assess | No valid assessment |

The risk thresholds and fusion weights are defined in the project configuration. They remain fixed for the reported analysis to preserve reproducibility.

### Handling Missing Observations

A central design principle is that **an unassessed lake must never be interpreted as a low-risk lake**.

When the available data is insufficient for assessment, the console explicitly marks the lake as *Cannot Assess*. This state is represented through:

- Desaturated grey styling.
- Hatched markers and chart columns.
- Explicit status text instead of a misleading risk number.
- An explanation that unavailable observations do not imply safety.

This approach helps distinguish low assessed risk from uncertainty caused by missing or insufficient observations.

## Dashboard Components

### 1. Triage Board

A time scrubber (with Play, Latest and an Event jump to the 4 October 2023 outburst) drives six summary cards, an attention queue, and a selected-lake card explaining why a lake is flagged. Tiers use the fixed thresholds in `models/outputs/experiment_log.json`: High at 0.85, Concern at 0.70, Watch at 0.50. When 40% or more of assessed lakes are at Concern or above in the same window, those flags are shown as **Regional** (discounted) because a signal shared by most lakes is more likely seasonal or regional than lake-specific.

### 2. Every Lake, Every Window

A heatmap of all lakes and all windows with a strip of the share of lakes at Concern or above. Click any cell to jump to that lake and window.

### 3. See the Lake: Open Imagery

The selected-lake card has three buttons:

- **Open imagery**: opens the Planet Insights Platform browser already centred on the lake (zoom set from the lake's size) and filtered to about two months either side of the selected window. A Planet login is needed.
- **Copy coords**: copies `latitude, longitude` (for example `27.9100, 88.1800`) so you can paste it into the search bar of Planet, Google Maps or any other map.
- **Copernicus**: opens the free Copernicus Browser (Sentinel-2) at the same spot.

Coordinates are the seed points in `data/lake_coordinates.csv`, so the map may centre a few hundred metres from the lake itself. `shaushar_lake` has no coordinates yet, so its buttons are disabled.

### 4. Lake Workbench

The selected lake's risk history against the fleet median, threshold lines, abstained windows, the outburst marker, and optional raw signals (lake area, radar, thermal, glacier speed and acceleration), each scaled to its own range.

### 5. Evidence Panels

"Can I trust this?" and the alert-volume table come straight from `evaluation/outputs/`, including the outburst lead time, false alarms per lake-year, and how often a typical lake sits at or above each tier.

### 6. Watch Surface

A rotatable 3D view where column height is the risk score, next to a ranked watch-list with 90-day traces. Lakes are placed by their real longitude and latitude (north at the back).

### 7. Data, Modelling, Evaluation and Testing Tabs

Signal coverage and transformed signals, detector comparison and ablation, threshold sweep and leak check, and a live pytest run.

## Model v2 (fusion and calibration)

The per-signal detectors are unchanged (one Isolation Forest per lake and signal, walk-forward, past-only). Version 2 improves how those scores become a risk: scores are made **relative to peers** (a lake must stand out from the fleet, not only from its own history), a flag needs **corroboration** (a lone signal or a lone annual velocity value cannot reach Concern or High), and the 0.50 / 0.70 / 0.85 tiers are **calibrated to explicit false-alarm budgets** on calm lakes (walk-forward, never using South Lhonak).

| | v1 | v2 |
|---|---|---|
| South Lhonak rank among 42 lakes, 40 days before the burst | 7th | 2nd |
| Calm-lake windows at Watch / Concern / High | 63.7 / 46.0 / 18.1 % | 10.3 / 3.2 / 1.1 % |
| Share of lakes at Concern in 2019-2020 (common-mode artefact) | 98 % | 0.6 % |
| Lead time at Concern | 25.1 weeks | 5.1 weeks |

One confirmed outburst means these are suggestive, not proof of predictive skill. The full method, trade-offs and limits are in [`models/MODEL_V2_NOTE.md`](models/MODEL_V2_NOTE.md). The v1 scores are kept in `models/outputs/anomaly_scores_v1.csv` and the comparison in `models/outputs/v1_vs_v2.csv`.

## Key Findings

### 1. Limitations in Anticipating the South Lhonak Outburst

The historical analysis indicates that the fused risk score for South Lhonak Lake did not cross the concern threshold of 0.70 or the high-risk threshold of 0.85 during the 27-window run-up to the 4 October 2023 outburst.

The maximum score during this period was **0.769**.

The watch threshold of 0.50 was crossed 245 days before the event. However, this threshold was associated with a reported false-alarm rate of 6.7% and 24.1 alarm-days per lake-year.

These results indicate that the system did not anticipate the event at the evaluated operationally relevant thresholds. This limitation is an important finding of the study.

### 2. Improved Assessment Coverage Through SAR

Adding SAR observations substantially improved the proportion of monsoon observation windows that could be assessed.

| Monitoring Approach | Assessable Monsoon Windows |
|---|---:|
| Optical observations only | 42.1% |
| All sensors, including SAR | 97.7% |

The inclusion of additional sensors recovered **2,197 of 3,936 monsoon windows** that were otherwise unavailable for assessment.

This demonstrates the value of multi-sensor monitoring for improving data coverage. Improved coverage, however, should not be interpreted as proof of improved event anticipation.

## Technology Stack

- **Backend:** Python, FastAPI, Uvicorn.
- **Frontend:** HTML, CSS, JavaScript (no framework, no build step).
- **Visualisation:** Canvas-based heatmap, workbench and 3D-style watch surface; Plotly for the pipeline tabs.
- **Data Format:** CSV pipeline outputs served as JSON.
- **Geospatial and Satellite Data:** Sentinel-1, Sentinel-2, MODIS, Copernicus GLO-30, ITS_LIVE, and glacial lake inventories.
- **Data Processing and Modelling:** Python (pandas, scikit-learn Isolation Forest).
- **Risk Analysis:** Fused environmental indicators and fixed, configuration-defined thresholds.
- **Version Control:** Git and GitHub.

The console needs no Node.js, no npm install, and no frontend build process. Streamlit is not used.

## Installation and Local Usage

### Prerequisites

- Python 3.10 to 3.13 is best (tested on 3.12). Very new releases such as 3.14 may lack prebuilt wheels for some packages; if `pip install` starts compiling NumPy, use 3.12 or 3.13.
- An up-to-date `pip`: run `python -m pip install --upgrade pip` first.
- A modern web browser.
- Git, only if you are cloning the repository.

### Steps to Run the Project

1. **Get the code.** Either clone it or unzip the project folder:

   ```bash
   git clone https://github.com/Brijesh-001/glof-early-warning.git
   cd glof-early-warning
   ```

2. **Create and activate a virtual environment** (recommended):

   ```bash
   python -m venv .venv
   ```

   Activate it:

   - Windows (PowerShell): `.venv\Scripts\Activate.ps1`
   - Windows (Command Prompt): `.venv\Scripts\activate.bat`
   - macOS / Linux: `source .venv/bin/activate`

   On macOS or Linux use `python3` instead of `python` if `python` is not found.

3. **Install the dependencies:**

   ```bash
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

   The Jupyter notebooks need extra packages: `pip install -r requirements-notebooks.txt` (optional).

4. **Start the console:**

   ```bash
   python dashboard/run.py
   ```

5. **Open it in your browser:** <http://127.0.0.1:8000>

   Stop the server with `Ctrl+C` in the terminal.

The model and evaluation outputs are already committed, so the console works straight away. You do not need to run the pipeline first.

### Options

```bash
python dashboard/run.py --port 9000        # use a different port
python dashboard/run.py --host 0.0.0.0     # allow other devices on your network
```

Interactive API documentation is available at <http://127.0.0.1:8000/docs>.

### Using the Console

- **Triage board:** drag the slider or press **Play** to move through the 10-day windows. **Latest** jumps to the newest window with data for at least half of the lakes. **Event** jumps to the 4 October 2023 South Lhonak outburst.
- Click a card in the attention queue, a cell in the heatmap, or a chip to open a lake in the workbench.
- In the selected-lake card, **Open imagery** opens Planet at the lake; **Copy coords** copies `lat, lon` to paste into a search bar.
- **Watch surface:** drag the 3D view to rotate it; click a column or a row in the ranked list to select a lake.
- **Evaluation** tab: **Re-run evaluation** re-executes the evaluation stage. **Testing** tab: **Run test suite** runs the pytest suite live.

### Regenerating the Model and Evaluation Outputs (optional)

Run these from the repository root, then refresh the browser:

```bash
python run_pipeline.py           # data -> model (v1 + v2) -> evaluation -> tests (per-signal scoring takes about 9 minutes the first time, then it is cached)
python run_pipeline.py --eval    # skip modelling; re-evaluate the committed scores and run the tests
python run_pipeline.py --tests   # run only the evaluation unit tests
```

### Troubleshooting

| Problem | Fix |
|---|---|
| `pip install` tries to build NumPy from source, or fails with `No such file or directory ... Long Path` | pip found no prebuilt wheel for your Python. Run `python -m pip install --upgrade pip`, then `pip install --only-binary=:all: -r requirements.txt`. If it still fails, install Python 3.12 from python.org, recreate the virtual environment, and try again. You can also enable Windows long paths (see pip's `enable-long-paths` hint). |
| `ModuleNotFoundError: No module named 'uvicorn'` (or `fastapi`, `pandas`) | The install did not finish. Fix the install error first, then run `python dashboard/run.py`. |
| `ModuleNotFoundError` (for example `fastapi` or `pandas`) | Activate the virtual environment, then run `pip install -r requirements.txt` again. |
| `Address already in use` | Another program is using port 8000. Start with `python dashboard/run.py --port 9000`. |
| `python` is not recognised | On macOS or Linux use `python3`. On Windows reinstall Python and tick **Add Python to PATH**. |
| A page shows `missing pipeline output` | Run `python run_pipeline.py` to regenerate the files in `models/outputs/` and `evaluation/outputs/`. |
| Charts in the Data, Modelling or Evaluation tabs are blank | Make sure the `plotly` package installed correctly (`pip install plotly`) and hard-refresh the page. |

## Keeping the System Current (new windows)

The dashboard shows whatever is in `data/lake_data/`, so staying current means fetching each newly **finished** 10-day window, re-scoring, and re-evaluating. The updater in [`collect/`](collect/README.md) does all three, using the same satellite sources and rules as the Colab notebook (Sentinel-2, Sentinel-1, MODIS, ITS_LIVE via Microsoft Planetary Computer; no Earth Engine account needed).

```bash
pip install -r requirements-collect.txt                       # once: extra packages for the downloads
python collect/gews_collect.py --verify --lake south_lhonak   # 1. check it reproduces your committed numbers
python collect/gews_collect.py --dry-run                      # 2. preview what would change, write nothing
python run_pipeline.py --update                               # 3. fetch, re-score (v2), re-evaluate
```

- **One command, or one click.** `python run_pipeline.py --update` does everything; the **Refresh data** button in the dashboard header runs the same thing in the background and reloads the board when it finishes. `--skip-fetch` re-scores the data files as they are.
- **"Newest window" means newest finished window.** A window counts as finished 3 days after its last day. On 31 Oct 2026 that is the window starting 18 Oct; the window starting 28 Oct finishes on 6 Nov. Scenes arrive a few days late, so the newest window is thin at first and the next run fills it in.
- **History is never rewritten.** Only the last two windows with data and anything newer are touched; older rows stay byte-for-byte identical.
- **One bad lake never stops the rest.** A lake that fails keeps its old data and shows as behind; the header reports it (`data/update_log.json` has the reason).
- **Stale scores are impossible.** A fingerprint of `data/lake_data/` makes the scorer recompute whenever the data changed.
- **Schedule it** (every day is safe; it does almost nothing when no window is new): see "Schedule it" in [`collect/README.md`](collect/README.md) for Windows Task Scheduler and cron.
- **Needs the live services.** The fetch step downloads from Planetary Computer and ITS_LIVE, so it needs internet access, and it was written from the notebook without being run against the live services. Do step 1 on a few lakes first; a lake that says `DIFFERS` has a tile, seed or threshold that does not match how its history was collected.

Scoring a full refresh takes about 5 minutes on one core and about a minute on several (lakes are scored in parallel; set `GEWS_JOBS=1` to force serial). The slow detector comparison is only regenerated by a full `python run_pipeline.py`.

To edit data by hand instead: change the per-lake CSVs in `data/lake_data/` (see `data/README.md`) and run `python run_pipeline.py --update --skip-fetch`.

The risk thresholds and fusion weights are fixed in the project configuration and should stay unchanged when reproducing the reported results.

## Project Scope and Limitations

GEWS is an academic research and decision-support project. It is intended to support historical analysis and exploration of satellite-derived glacial lake indicators.

The current implementation has important limitations:

- The available study period ends on 21 December 2024.
- The system did not anticipate the South Lhonak outburst at the evaluated concern and high-risk thresholds.
- Satellite data availability, quality, and observability affect the ability to assess individual lakes.
- Historical risk scores should not be interpreted as guaranteed predictions of future events.
- The dashboard is not validated for operational disaster-warning use and does not issue public alerts.

The system should therefore be understood as a research prototype rather than a replacement for official monitoring, forecasting, or disaster-management procedures.

## Authors

Aman Kumar, Keerti T Naik, Hitesh Jain, Brijesh Niranjan K, and Chaitra R.

**Department of Artificial Intelligence and Machine Learning**  
Dayananda Sagar College of Engineering, Bengaluru, India
