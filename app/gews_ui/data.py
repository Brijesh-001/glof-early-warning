"""Data contract between the pipeline (L3/L4) and the dashboard.

The dashboard only READS these files. Put them in ``data/processed/`` (or point
``GEWS_DATA_DIR`` elsewhere). If they are missing, the app runs on synthetic
demo data and says so on every page.

lakes.csv            one row per register lake
    lake_id, name, region, lat, lon            required
    elevation_m, area_ref_km2                  optional
    watch, concern, high                       optional per-lake threshold overrides

features.parquet     L3 output, one row per lake × 10-day window
    lake_id, window_start, <5 signals>, observability,
    obs_optical, obs_radar, obs_velocity, obs_thermal   (each 0–1)

scores.parquet       L4 output, one row per lake × 10-day window
    lake_id, window_start, risk (NaN when abstaining), abstain_reason,
    score_<signal> for each of the 5 signals (0–1, NaN if unavailable),
    contributing_signals  (";"-separated, most important first)

evaluation.json      optional, written by the evaluation harness
events.csv           optional: lake_id, date, description
manifest.json        optional: {"data_version": "..."}
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "processed"

LAKE_COLS = ["lake_id", "name", "region", "lat", "lon"]
FEATURE_COLS = ["lake_id", "window_start", *C.SIGNALS, "observability",
                "obs_optical", "obs_radar", "obs_velocity", "obs_thermal"]
SCORE_COLS = ["lake_id", "window_start", "risk", "abstain_reason",
              *[f"score_{s}" for s in C.SIGNALS], "contributing_signals"]


class SchemaError(ValueError):
    """Raised when a pipeline file does not match the declared contract."""


@dataclass
class Dataset:
    lakes: pd.DataFrame
    features: pd.DataFrame
    scores: pd.DataFrame
    evaluation: dict
    events: pd.DataFrame
    data_version: str
    is_demo: bool
    source: str
    warnings: list[str] = field(default_factory=list)

    @property
    def windows(self) -> list[pd.Timestamp]:
        return sorted(self.scores["window_start"].unique())


def _require(df: pd.DataFrame, cols: list[str], name: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise SchemaError(f"{name} is missing columns: {', '.join(missing)}")


def validate(lakes: pd.DataFrame, features: pd.DataFrame, scores: pd.DataFrame) -> list[str]:
    """Check the contract. Raises on hard errors, returns soft warnings."""
    _require(lakes, LAKE_COLS, "lakes.csv")
    _require(features, FEATURE_COLS, "features.parquet")
    _require(scores, SCORE_COLS, "scores.parquet")
    warnings: list[str] = []

    # The central rule: an abstaining window carries NaN, never a number.
    abst = scores["abstain_reason"].notna() & (scores["abstain_reason"].astype(str) != "")
    bad = scores.loc[abst & scores["risk"].notna()]
    if len(bad):
        raise SchemaError(f"{len(bad)} abstaining rows carry a numeric risk. "
                          "Abstention must be NaN, never a number.")
    silent = scores.loc[~abst & scores["risk"].isna()]
    if len(silent):
        warnings.append(f"{len(silent)} rows have NaN risk but no abstain_reason; "
                        "they are shown as 'cannot assess (reason not given)'.")
    if ((scores["risk"] < 0) | (scores["risk"] > 1)).any():
        raise SchemaError("risk must lie in [0, 1].")
    unknown = set(scores["lake_id"]) - set(lakes["lake_id"])
    if unknown:
        warnings.append(f"{len(unknown)} lake_id(s) in scores are not in lakes.csv.")
    return warnings


def _normalise(scores: pd.DataFrame, features: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    for df in (scores, features):
        df["window_start"] = pd.to_datetime(df["window_start"]).dt.normalize()
    scores["abstain_reason"] = scores["abstain_reason"].replace("", np.nan)
    silent = scores["risk"].isna() & scores["abstain_reason"].isna()
    scores.loc[silent, "abstain_reason"] = "reason not given"
    scores["contributing_signals"] = scores["contributing_signals"].fillna("")
    return scores, features


def load(data_dir: str | os.PathLike | None = None) -> Dataset:
    data_dir = Path(data_dir or os.environ.get("GEWS_DATA_DIR", DEFAULT_DATA_DIR))
    needed = [data_dir / "lakes.csv", data_dir / "features.parquet", data_dir / "scores.parquet"]
    if not all(p.exists() for p in needed):
        from .demo import make_demo_dataset
        return make_demo_dataset()

    lakes = pd.read_csv(data_dir / "lakes.csv")
    features = pd.read_parquet(data_dir / "features.parquet")
    scores = pd.read_parquet(data_dir / "scores.parquet")
    warnings = validate(lakes, features, scores)
    scores, features = _normalise(scores, features)

    evaluation = {}
    if (data_dir / "evaluation.json").exists():
        evaluation = json.loads((data_dir / "evaluation.json").read_text())
    events = pd.DataFrame(columns=["lake_id", "date", "description"])
    if (data_dir / "events.csv").exists():
        events = pd.read_csv(data_dir / "events.csv", parse_dates=["date"])
    version = "unversioned"
    if (data_dir / "manifest.json").exists():
        version = json.loads((data_dir / "manifest.json").read_text()).get("data_version", version)

    return Dataset(lakes, features, scores, evaluation, events, version,
                   is_demo=False, source=str(data_dir), warnings=warnings)


# ---- Views used by the pages ---------------------------------------------

def thresholds_for(lakes: pd.DataFrame, lake_id: str) -> dict:
    t = dict(C.THRESHOLDS)
    row = lakes.loc[lakes["lake_id"] == lake_id]
    if len(row):
        for k in t:
            if k in row.columns and pd.notna(row.iloc[0][k]):
                t[k] = float(row.iloc[0][k])
    return t


def watchlist(ds: Dataset, window: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (ranked, cannot_assess) for one window.

    Abstaining lakes are returned separately and are NEVER sorted in with
    numbered lakes — a NaN cannot be ranked, and must not be ranked as zero.
    """
    snap = ds.scores.loc[ds.scores["window_start"] == window]
    snap = snap.merge(ds.lakes, on="lake_id", how="left")
    # Lakes in the register with no row at all for this window are blind too.
    absent = ds.lakes.loc[~ds.lakes["lake_id"].isin(snap["lake_id"])].copy()
    if len(absent):
        absent["risk"] = np.nan
        absent["abstain_reason"] = "no record for this window"
        absent["contributing_signals"] = ""
        snap = pd.concat([snap, absent], ignore_index=True)

    snap["level"] = [C.level_for(r, thresholds_for(ds.lakes, lid))
                     for r, lid in zip(snap["risk"], snap["lake_id"])]
    ranked = (snap.loc[snap["risk"].notna()]
              .sort_values("risk", ascending=False, kind="mergesort")
              .reset_index(drop=True))
    ranked.insert(0, "rank", range(1, len(ranked) + 1))
    blind = snap.loc[snap["risk"].isna()].sort_values("name").reset_index(drop=True)
    return ranked, blind


def lake_series(ds: Dataset, lake_id: str) -> pd.DataFrame:
    """Full, gap-preserving series for one lake on the fixed window grid."""
    grid = pd.DataFrame({"window_start": ds.windows})
    s = ds.scores.loc[ds.scores["lake_id"] == lake_id]
    f = ds.features.loc[ds.features["lake_id"] == lake_id].drop(columns=["lake_id"])
    out = grid.merge(s.drop(columns=["lake_id"]), on="window_start", how="left")
    out = out.merge(f, on="window_start", how="left")
    out.loc[out["risk"].isna() & out["abstain_reason"].isna(), "abstain_reason"] = "no record for this window"
    return out  # NaNs are kept on purpose; never interpolate.


def blind_spans(series: pd.DataFrame) -> list[tuple[pd.Timestamp, pd.Timestamp, str]]:
    """Merge consecutive abstaining windows into (start, end, reason) spans."""
    spans, start, reason, prev = [], None, None, None
    for ws, r, why in zip(series["window_start"], series["risk"], series["abstain_reason"]):
        if pd.isna(r):
            if start is None:
                start, reason = ws, why
            prev = ws
        elif start is not None:
            spans.append((start, window_end(prev), reason))
            start = None
    if start is not None:
        spans.append((start, window_end(prev), reason))
    return spans


def window_end(ws: pd.Timestamp) -> pd.Timestamp:
    """Windows are 1–10, 11–20 and 21–end of month."""
    ws = pd.Timestamp(ws)
    if ws.day < 21:
        return ws + pd.Timedelta(days=10)
    return (ws + pd.offsets.MonthBegin(1)).normalize()


def window_label(ws: pd.Timestamp) -> str:
    ws = pd.Timestamp(ws)
    end = window_end(ws) - pd.Timedelta(days=1)
    return f"{ws.day}–{end.day} {ws:%b %Y}"


WARMUP_REASON = "too little history"


def longest_blind_days(series: pd.DataFrame, include_warmup: bool = False) -> int:
    """Longest run of unscored windows, in days. The model warm-up at the start
    of a record is excluded by default: that is missing history, not cloud."""
    spans = [sp for sp in blind_spans(series) if include_warmup or sp[2] != WARMUP_REASON]
    return max(((e - s).days for s, e, _ in spans), default=0)
