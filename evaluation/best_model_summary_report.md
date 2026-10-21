# 📊 Model Evaluation & Performance Summary Report

This report summarizes the comparative results of our anomaly detection testing suite to identify the optimal model configuration for operational deployment.

## 📈 Model Metrics Overview
Based on historical test runs compiled in `detector_comparison.csv`:

* **Ridge Autoregressive (`ridge_ar`)**: **0.943** Run-Up | **41.43%** False Alarm Rate
* **One-Class Support Vector Machine (`one_class_svm`)**: **0.911** Run-Up | **36.19%** False Alarm Rate
* **Isolation Forest (`isolation_forest`)**: **0.765** Run-Up | **18.12%** False Alarm Rate
* **Z-Score Baseline (`zscore`)**: **0.724** Run-Up | **21.39%** False Alarm Rate

---

## ⚡ Scope of Validation & Dataset Coverage
To ensure strict academic transparency, we draw a clear distinction between the two core analytics components:
1. **Model Anomaly Scores**: Fully evaluated across **all 42 lakes** within the regional study area.
2. **DEM Terrain Profiles**: Currently executed as a **two-lake proof-of-concept** (specifically targeting *South Lhonak* and *Gurudongmar Lake 4*) due to geographical coordinates currently being unavailable for the remaining 40 lakes.

---

## 🏆 Top-Performing Model Recommendation

### Option A: **Isolation Forest** (Recommended for Automated Watchlists)
* **Why it wins:** It offers the most robust real-world performance by maintaining the **lowest false alarm rate (18.12%)** while preserving a highly reliable detection rate (**76.5%**).
* **Operational Impact:** Highly suited for standard monitoring pipelines to prevent alarm fatigue among analysts, ensuring that flagged anomalies are highly likely to be real events.

### Option B: **Ridge Autoregressive (Ridge AR)** (Recommended for High-Sensitivity Early Warning)
* **Why it wins:** It achieves the **absolute highest sensitivity (94.3%)**, detecting almost all anomalous trends far ahead of actual events.
* **Operational Impact:** Ideal for high-risk critical regions where failing to detect an anomaly has catastrophic consequences, provided you have the capacity to manually filter out the higher volume of false alarms (41.43%).
