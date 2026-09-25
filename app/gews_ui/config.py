"""Frozen decision parameters, mirrored from the modelling layer.

These values were frozen before the retrospective test. The UI only *displays*
them; it must never be used to tune them.
"""
from __future__ import annotations

import math
from typing import Mapping

# ---- Signals (L3 features) ------------------------------------------------
SIGNALS = [
    "lake_area_km2",
    "velocity_trend",
    "velocity_accel",
    "thermal_index",
    "sar_backscatter_change",
]

SIGNAL_LABELS = {
    "lake_area_km2": "Lake area",
    "velocity_trend": "Glacier speed-up",
    "velocity_accel": "Speed-up acceleration",
    "thermal_index": "Melt pressure",
    "sar_backscatter_change": "Radar texture change",
}

SIGNAL_UNITS = {
    "lake_area_km2": "km²",
    "velocity_trend": "m/yr per yr",
    "velocity_accel": "m/yr²",
    "thermal_index": "°C-days",
    "sar_backscatter_change": "dB",
}

# ---- Fusion (L4) ----------------------------------------------------------
FUSION_P = 3
FUSION_WEIGHTS = {
    "lake_area_km2": 0.30,
    "velocity_trend": 0.20,
    "velocity_accel": 0.20,
    "sar_backscatter_change": 0.20,
    "thermal_index": 0.10,
}

# ---- Abstention -----------------------------------------------------------
OBSERVABILITY_FLOOR = 0.30
MIN_HISTORY_WINDOWS = 24
# Sensor weights inside the observability score.
OBSERVABILITY_WEIGHTS = {"optical": 0.40, "radar": 0.30, "velocity": 0.15, "thermal": 0.15}

# ---- Thresholds (overridable per lake in lakes.csv) -----------------------
THRESHOLDS = {"watch": 0.50, "concern": 0.70, "high": 0.85}

LEVELS = ["normal", "watch", "concern", "high"]
LEVEL_LABELS = {
    "normal": "Normal",
    "watch": "Watch",
    "concern": "Concern",
    "high": "High",
    "abstain": "Cannot assess",
}

WINDOWS_PER_YEAR = 36
MONSOON_MONTHS = {6, 7, 8, 9}


def fuse(scores: Mapping[str, float], weights: Mapping[str, float] = FUSION_WEIGHTS,
         p: int = FUSION_P) -> float:
    """Weighted p-norm: risk = (Σ wᵢ·sᵢᵖ / Σ wᵢ)^(1/p) over available signals.

    Missing (NaN/None) signals are dropped and the weights renormalise.
    If no signal is available the result is NaN — never 0.0.
    """
    num = den = 0.0
    for name, w in weights.items():
        s = scores.get(name)
        if s is None or (isinstance(s, float) and math.isnan(s)):
            continue
        num += w * float(s) ** p
        den += w
    if den == 0:
        return float("nan")
    return (num / den) ** (1.0 / p)


def level_for(risk: float, thresholds: Mapping[str, float] = THRESHOLDS) -> str:
    """Map a risk score to a level. NaN maps to 'abstain', never 'normal'."""
    if risk is None or (isinstance(risk, float) and math.isnan(risk)):
        return "abstain"
    if risk >= thresholds["high"]:
        return "high"
    if risk >= thresholds["concern"]:
        return "concern"
    if risk >= thresholds["watch"]:
        return "watch"
    return "normal"
