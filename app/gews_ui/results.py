"""Evaluation results. Read from evaluation.json when the harness has written
it; otherwise fall back to the values reported in the project deck."""
from __future__ import annotations

REPORTED = {
    "source": "values reported in the project deck",
    "event": {"lake_id": "IN-SK-001", "name": "South Lhonak", "date": "2023-10-04"},
    "detectors": [
        {"key": "zscore", "label": "Robust z-score (baseline)", "peak_risk": 0.706, "false_alarm_pct": 4.01, "production": False},
        {"key": "isolation_forest", "label": "Isolation Forest", "peak_risk": 0.769, "false_alarm_pct": 0.00, "production": True},
        {"key": "one_class_svm", "label": "One-class SVM", "peak_risk": 0.737, "false_alarm_pct": 0.11, "production": False},
        {"key": "ridge_ar", "label": "Ridge AR", "peak_risk": 0.745, "false_alarm_pct": 1.24, "production": False},
    ],
    "ablation": [
        {"run": "all five signals", "peak_risk": 0.769},
        {"run": "without lake area", "peak_risk": 0.608},
        {"run": "without glacier speed-up", "peak_risk": 0.721},
        {"run": "without melt pressure", "peak_risk": 0.796},
        {"run": "without speed-up acceleration", "peak_risk": 0.828},
        {"run": "without radar texture change", "peak_risk": 0.828},
    ],
    "retrospective": {
        "high": {"crossed": False},
        "concern": {"crossed": False},
        "watch": {"crossed": True, "lead_days": 245, "false_alarm_days_per_lake_year": 24},
        "peak_months_before": 7,
    },
    "radar": {
        "monsoon_optical_only_pct": 42.1, "monsoon_combined_pct": 97.7,
        "recovered_windows": 2197, "monsoon_windows": 3936,
        "mean_gain": 0.177, "gain_ci": [0.174, 0.179], "worst_blind_days": 130,
    },
    "precursor": {"documented_mm_per_yr": [70, 80], "insar_resolves_mm_per_yr": 10,
                  "its_live_noise_mm_per_yr": 2000, "reference": "Yu et al. 2024, SBAS-InSAR"},
    "deseasonalisation_warmup_cost_pct": 9.8,
    "tests": 77,
}


def get_results(evaluation: dict) -> dict:
    if not evaluation:
        return REPORTED
    merged = dict(REPORTED)
    merged.update(evaluation)
    merged["source"] = evaluation.get("source", "evaluation.json from the evaluation harness")
    return merged
