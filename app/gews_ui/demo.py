"""Synthetic demo data with the same schema as the real pipeline output.

Used only when data/processed/ is empty, so the dashboard can be developed and
demonstrated before L3/L4 have run. Every page shows a demo banner when this
is in use. Nothing here is satellite-derived. Coordinates are approximate.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from .data import Dataset

# (lake_id, name, region, lat, lon, elevation_m, area_ref_km2)
NAMED = [
    ("IN-SK-001", "South Lhonak", "Sikkim", 27.91, 88.20, 5200, 1.60),
    ("IN-SK-002", "Gurudongmar", "Sikkim", 28.02, 88.71, 5150, 1.18),
    ("IN-SK-003", "Shako Cho", "Sikkim", 27.99, 88.63, 5050, 0.72),
    ("IN-SK-004", "Khangchung Chho", "Sikkim", 27.96, 88.60, 5100, 0.55),
    ("IN-HP-001", "Gepang Gath", "Himachal", 32.52, 77.22, 4070, 0.98),
    ("IN-HP-002", "Samudra Tapu", "Himachal", 32.50, 77.55, 4260, 1.24),
    ("IN-LA-001", "Gya", "Ladakh", 33.05, 77.93, 5300, 0.34),
    ("IN-UK-001", "Vasudhara Tal", "Uttarakhand", 30.80, 79.48, 4700, 0.62),
    ("IN-UK-002", "Chorabari Tal", "Uttarakhand", 30.75, 79.06, 3900, 0.18),
]
REGION_BOX = {  # rough bounding boxes for the unnamed demo lakes
    "Sikkim": (27.7, 28.1, 88.1, 88.8),
    "Himachal": (31.9, 32.8, 76.9, 78.0),
    "Ladakh": (32.9, 34.6, 76.2, 78.6),
    "Uttarakhand": (30.3, 31.1, 78.6, 80.2),
    "Arunachal": (27.5, 28.2, 91.6, 92.5),
}

# Final-window values that mirror the watch-list mock-up in the deck.
LAST_WINDOW = {
    "IN-SK-001": 0.68, "IN-HP-001": 0.61, "IN-HP-002": 0.54, "IN-SK-002": 0.31,
    "IN-LA-001": "cloud cover, 4 windows running",
    "IN-UK-001": "no radar pass this window",
}


def window_grid(start="2017-01-01", end="2024-12-31") -> pd.DatetimeIndex:
    days = pd.date_range(start, end, freq="D")
    return days[days.day.isin([1, 11, 21])]


def _lakes(rng) -> pd.DataFrame:
    rows = list(NAMED)
    regions = list(REGION_BOX)
    n = 1
    while len(rows) < 41:
        reg = regions[len(rows) % len(regions)]
        la0, la1, lo0, lo1 = REGION_BOX[reg]
        rows.append((f"DEMO-{n:02d}", f"Demo lake {n:02d}", reg,
                     round(rng.uniform(la0, la1), 3), round(rng.uniform(lo0, lo1), 3),
                     int(rng.uniform(4200, 5500)), round(rng.uniform(0.1, 2.5), 2)))
        n += 1
    return pd.DataFrame(rows, columns=["lake_id", "name", "region", "lat", "lon",
                                       "elevation_m", "area_ref_km2"])


def _coverage(rng, windows, blind_prone: bool):
    monsoon = np.asarray(windows.month.isin(list(C.MONSOON_MONTHS)))
    n = len(windows)
    clear_p = np.where(monsoon, 0.46, 0.62) - (0.15 if blind_prone else 0)
    optical = np.where(rng.random(n) < clear_p, rng.uniform(0.5, 1.0, n), rng.uniform(0, 0.08, n))
    radar = np.where(rng.random(n) < (0.93 if blind_prone else 0.995), rng.uniform(0.8, 1.0, n), 0.0)
    velocity = np.where(rng.random(n) < 0.55, rng.uniform(0.4, 1.0, n), 0.0)
    thermal = np.where(rng.random(n) < np.where(monsoon, 0.45, 0.8), rng.uniform(0.5, 1.0, n), 0.0)
    return optical, radar, velocity, thermal


def _signal_scores(rng, n, episodes):
    s = {k: np.clip(rng.beta(2, 9, n), 0, 1) for k in C.SIGNALS}
    for centre, width, strength, sigs in episodes:
        bump = strength * np.exp(-0.5 * ((np.arange(n) - centre) / width) ** 2)
        for k in sigs:
            s[k] = np.clip(np.maximum(s[k], bump * rng.uniform(0.85, 1.05, n)), 0, 1)
    return s


def make_demo_dataset(seed: int = 7) -> Dataset:
    rng = np.random.default_rng(seed)
    lakes = _lakes(rng)
    windows = window_grid()
    n = len(windows)
    t = np.arange(n)
    doy = np.asarray(windows.dayofyear)
    feat_rows, score_rows = [], []

    for _, lake in lakes.iterrows():
        lid = lake.lake_id
        optical, radar, velocity, thermal = _coverage(rng, windows, lid in {"IN-LA-001", "IN-UK-001"})
        obs = (C.OBSERVABILITY_WEIGHTS["optical"] * optical + C.OBSERVABILITY_WEIGHTS["radar"] * radar
               + C.OBSERVABILITY_WEIGHTS["velocity"] * velocity + C.OBSERVABILITY_WEIGHTS["thermal"] * thermal)

        # Raw features (L3-like)
        area = (lake.area_ref_km2 * (1 + 0.06 * np.sin(2 * np.pi * (doy - 120) / 365))
                * (1 + 0.004 * t / 36) + rng.normal(0, 0.012 * lake.area_ref_km2, n))
        feats = {
            "lake_area_km2": np.where(optical > 0.1, area, np.nan),
            "velocity_trend": np.where(velocity > 0, rng.normal(0, 1.5, n), np.nan),
            "velocity_accel": np.where(velocity > 0, rng.normal(0, 0.8, n), np.nan),
            "thermal_index": np.where(thermal > 0, rng.normal(0, 40, n), np.nan),
            "sar_backscatter_change": np.where(radar > 0, rng.normal(0, 0.9, n), np.nan),
        }

        # Episodes of unusual behaviour
        episodes = []
        for _ in range(rng.integers(1, 4)):
            episodes.append((rng.integers(30, n), rng.uniform(1.5, 4), rng.uniform(0.35, 0.8),
                             list(rng.choice(C.SIGNALS, size=rng.integers(1, 4), replace=False))))
        if lid == "IN-SK-001":  # shape of the published run-up: peak ~Mar 2023, then falling
            i = int(np.argmin(np.abs(windows - pd.Timestamp("2023-03-01"))))
            episodes.append((i, 2.2, 0.88, ["lake_area_km2", "thermal_index", "sar_backscatter_change"]))
        sc = _signal_scores(rng, n, episodes)
        avail = {"lake_area_km2": optical > 0.1, "velocity_trend": velocity > 0,
                 "velocity_accel": velocity > 0, "thermal_index": thermal > 0,
                 "sar_backscatter_change": radar > 0}
        for k in C.SIGNALS:
            sc[k] = np.where(avail[k], sc[k], np.nan)

        history_start = 0 if lid != "IN-UK-002" else n - 10  # Chorabari: short record
        for i, ws in enumerate(windows):
            s_i = {k: float(sc[k][i]) for k in C.SIGNALS}
            reason = None
            if i - history_start < C.MIN_HISTORY_WINDOWS:
                reason = "too little history"
            elif obs[i] < C.OBSERVABILITY_FLOOR:
                reason = "cloud cover" if radar[i] > 0 else "no radar pass this window"

            if i == n - 1 and lid in LAST_WINDOW:
                v = LAST_WINDOW[lid]
                if isinstance(v, str):
                    reason = v
                    obs[i] = 0.12
                else:
                    reason = None
                    obs[i] = max(obs[i], 0.8)
                    for k in C.SIGNALS:
                        if np.isnan(s_i[k]):
                            s_i[k] = float(rng.beta(2, 9))
                    k_ = v / C.fuse(s_i)
                    s_i = {k: min(1.0, x * k_) for k, x in s_i.items()}

            risk = np.nan if reason else C.fuse(s_i)
            contrib = sorted((k for k in C.SIGNALS if not np.isnan(s_i[k])),
                             key=lambda k: -C.FUSION_WEIGHTS[k] * s_i[k] ** 3)[:3]
            score_rows.append({
                "lake_id": lid, "window_start": ws, "risk": risk, "abstain_reason": reason,
                **{f"score_{k}": (np.nan if reason else s_i[k]) for k in C.SIGNALS},
                "contributing_signals": "" if reason else ";".join(contrib),
            })
            feat_rows.append({
                "lake_id": lid, "window_start": ws,
                **{k: feats[k][i] for k in C.SIGNALS},
                "observability": obs[i], "obs_optical": optical[i], "obs_radar": radar[i],
                "obs_velocity": velocity[i], "obs_thermal": thermal[i],
            })

    events = pd.DataFrame([{"lake_id": "IN-SK-001", "date": pd.Timestamp("2023-10-04"),
                            "description": "Moraine-dam outburst"}])
    return Dataset(lakes, pd.DataFrame(feat_rows), pd.DataFrame(score_rows), {}, events,
                   data_version="demo-synthetic", is_demo=True, source="synthetic demo generator")
