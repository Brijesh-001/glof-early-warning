# GEWS — Glacial Early Warning System

## Overview

The **Glacial Early Warning System (GEWS)** is a satellite-based decision-support system designed to study and monitor glacial lakes in the Indian Himalaya for potential Glacial Lake Outburst Floods (GLOFs).

Glacial Lake Outburst Floods occur when water stored in a glacial lake is suddenly released, potentially causing severe downstream flooding and damage to communities, infrastructure, and ecosystems.

GEWS combines satellite-derived environmental indicators into a fused risk score and presents the results through an interactive watch console. The system supports historical risk analysis, lake prioritisation, and assessment of satellite data availability.

The project focuses on two important questions:

- Can satellite-derived indicators identify periods of elevated glacial lake risk?
- How can multiple satellite sensors improve lake monitoring when some observations are unavailable?

## Key Features

- **Interactive 3D Watch Surface:** Visualises glacial lakes as columns whose heights represent their fused risk scores for a selected time window.
- **Time-Series Analysis:** Explores historical risk scores across multiple observation windows from 2017 to 2024.
- **Ranked Watch List:** Orders lakes by their current assessed risk and displays severity indicators, status labels, and recent risk trends.
- **Lake-Level Analysis:** Displays historical risk scores, risk thresholds, and periods when the system could not assess a lake.
- **Multi-Sensor Monitoring:** Incorporates optical, Synthetic Aperture Radar (SAR), surface velocity, thermal, and terrain-related indicators.
- **Data Observability:** Shows the availability and contribution of different sensor types to lake assessment.
- **Event Analysis:** Supports examination of the South Lhonak Lake outburst on 4 October 2023.
- **Abstention-Aware Visualisation:** Explicitly distinguishes lakes that cannot be assessed from lakes with low assessed risk.
- **Offline Console:** Provides a standalone HTML version for demonstrations and presentations without requiring a server.

## System Architecture

The console uses a lightweight static architecture consisting of an HTML interface and a JSON data feed.

| Component | Purpose |
|---|---|
| `index.html` | Interactive dashboard, visualisations, and user interface |
| `data.json` | Processed lake records, risk scores, sensor indicators, and historical observations |
| `GEWS_Watch_Console.html` | Standalone offline version with data embedded in the HTML file |
| `config/thresholds.yaml` | Defines risk thresholds and fusion weights used by the analysis pipeline |
| `config/pipeline.yaml` | Contains pipeline configuration, including the study period |

The dashboard fetches `data.json` when it loads. Updating the data feed does not require rebuilding the HTML interface.

The analytical pipeline processes satellite-derived features, observability information, lake metadata, and risk scores to generate the data consumed by the console.

## Dataset and Study Period

The current console contains records for **41 glacial lakes across 288 ten-day observation windows**, covering 1 January 2017 to 21 December 2024.

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

### 1. Interactive Watch Surface

Displays the lakes as a three-dimensional surface of risk scores. Users can rotate the visualisation, inspect individual lakes, and compare their scores against the watch threshold.

### 2. Time Scrubber

Allows users to move through the 288 historical observation windows. Playback controls support temporal exploration, including examination of the South Lhonak Lake outburst period.

### 3. Ranked Watch List

Presents lakes in descending order of their current assessed risk. It includes severity indicators, assessment status, relevant event or potential lake flags, and recent risk traces.

### 4. Lake Detail View

Displays the selected lake's historical risk series, assessment thresholds, unavailable observation periods, and the outburst event marker where applicable. Users can toggle individual environmental indicators to explore their contributions.

### 5. Provenance and Observability Panel

Shows contributing indicators, optical and SAR/thermal observability information, and lake inventory provenance for the selected observation window.

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

- **Frontend:** HTML, CSS, JavaScript.
- **Visualisation:** Canvas-based interactive graphics and 3D-style watch surface.
- **Data Format:** JSON.
- **Geospatial and Satellite Data:** Sentinel-1, Sentinel-2, MODIS, Copernicus GLO-30, ITS_LIVE, and glacial lake inventories.
- **Data Processing:** Python-based analytical pipeline.
- **Risk Analysis:** Fused environmental indicators and fixed, configuration-defined thresholds.
- **Version Control:** Git and GitHub.

The dashboard is a static website and does not require a dedicated application server, backend API, or frontend build process.

## Installation and Local Usage

### Prerequisites

- A modern web browser.
- Git, if cloning the repository.
- Python 3, if serving the console locally.

### Clone the Repository

```bash
git clone https://github.com/Brijesh-001/glof-early-warning.git
cd glof-early-warning
```

### Run the Console Locally

Because `index.html` fetches `data.json`, the two files must be served over HTTP rather than opened directly using the `file://` protocol.

Run the following command from the directory containing the files:

```bash
python -m http.server 8000
```

Open the following address in your browser:

```text
http://localhost:8000
```

Alternatively, open `GEWS_Watch_Console.html` directly in a browser to use the standalone offline version.

## Updating the Data Feed

The console separates the interface from the processed data. To refresh the historical records:

1. Update or regenerate the analytical pipeline outputs.
2. Generate the revised `data.json` using the appropriate processing scripts.
3. Verify the JSON structure and the generated observation period.
4. Replace the existing `data.json` file.
5. Publish the updated file alongside `index.html`.

The `meta.generated` field records the data-generation timestamp used by the console to indicate the freshness of the feed.

Extending the study beyond the current observation period requires an updated data-processing run and a new data version. The fixed thresholds should remain unchanged when reproducing the current study's results.

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
