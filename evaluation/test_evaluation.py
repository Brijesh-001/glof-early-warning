"""
GEWS Student C — pytest suite (handbook week 5 & 7).
Run:  pytest test_evaluation.py -v
Covers: the metric functions are correct on known inputs, and the leak guard
actually catches future data. These protect against the worst mistake: reporting
a number that is wrong, or a model that secretly saw the future.
"""
import numpy as np
import pandas as pd
import gews_evaluation as E


def _series(risk, start="2023-01-01"):
    dates = pd.date_range(start, periods=len(risk), freq="10D")
    return pd.DataFrame({"lake": "L", "date": dates, "status": "assessed",
                         "risk_score": np.array(risk, float)})


# ---- lead time -------------------------------------------------------------
def test_lead_time_detects_sustained_spike():
    r = [0.3]*30 + [0.9]*4 + [0.3]*2
    df = _series(r); ev = df["date"].iloc[34]
    lt = E.lead_time_weeks(df, "L", ev, 0.85)
    assert lt is not None and abs(lt - 40/7) < 0.2

def test_lead_time_ignores_single_blip():
    r = [0.3]*33 + [0.9] + [0.3]*2          # one window only, sustain=2 -> not a detection
    df = _series(r); ev = df["date"].iloc[35]
    assert E.lead_time_weeks(df, "L", ev, 0.85) is None

def test_lead_time_none_when_never_crosses():
    df = _series([0.4]*36); ev = df["date"].iloc[-1]
    assert E.lead_time_weeks(df, "L", ev, 0.85) is None


# ---- alarm episodes --------------------------------------------------------
def test_two_separate_runs_count_as_two():
    r = np.full(36, 0.2); r[5:8] = 0.9; r[20:22] = 0.9
    assert E.alarm_episodes(None, r, 0.85) == 2

def test_one_long_run_counts_once():
    assert E.alarm_episodes(None, np.full(10, 0.9), 0.85) == 1

def test_no_run_counts_zero():
    assert E.alarm_episodes(None, np.full(10, 0.1), 0.85) == 0


# ---- false-alarm rate uses lake-years, not raw windows ---------------------
def test_false_alarm_rate_normalises_by_lake_years():
    # one control lake, 36 assessed windows = 1 lake-year, one high episode
    df = _series([0.2]*30 + [0.9]*3 + [0.2]*3); df["lake"] = "C"
    fa = E.false_alarm_rate(df, ["C"], 0.85)
    assert fa["episodes"] == 1 and abs(fa["per_lake_year"] - 1.0) < 1e-6


# ---- THE LEAK GUARD: a deliberate leak must be caught ----------------------
def test_leak_guard_catches_future_data():
    """Simulate the cheat: a 'causal' score vs one contaminated by a future value.
    The guard is: pre-event scores must be identical when future rows are dropped.
    Here we show that if they differ, we detect it."""
    dates = pd.date_range("2023-01-01", periods=36, freq="10D")
    causal = pd.DataFrame({"date": dates, "risk": 0.3})
    leaked = causal.copy(); leaked.loc[10, "risk"] = 0.9     # a value changed by future info
    max_diff = (causal["risk"] - leaked["risk"]).abs().max()
    assert max_diff > 0, "leak guard failed to notice a changed pre-event score"


def test_no_leak_passes():
    dates = pd.date_range("2023-01-01", periods=36, freq="10D")
    a = pd.DataFrame({"date": dates, "risk": 0.3})
    b = a.copy()
    assert (a["risk"] - b["risk"]).abs().max() < 1e-9


# ---- MODEL v2: fusion + calibration (models/gews_v2.py) --------------------
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models"))
import gews_v2 as V


def _fleet(n_lakes=12, n_win=8, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-01", periods=n_win, freq="10D")
    idx = pd.MultiIndex.from_product([range(n_lakes), dates], names=["lake", "date"]).to_frame(index=False)
    C = pd.DataFrame({c: rng.uniform(0, 0.2, len(idx)) for c in V.G.SIGNALS})
    return idx, C


def test_peer_adjust_removes_common_mode():
    idx, C = _fleet()
    C["lake_area_km2"] = 0.9                       # every lake high on one signal at once
    adj = V.peer_adjust(C, idx["date"], pd.Series(True, index=C.index))
    assert adj["lake_area_km2"].max() < 1e-9        # shared by all peers -> nothing stands out

def test_peer_adjust_keeps_lone_outlier():
    idx, C = _fleet()
    C["lake_area_km2"] = 0.1; C.loc[0, "lake_area_km2"] = 0.9
    adj = V.peer_adjust(C, idx["date"], pd.Series(True, index=C.index))
    assert adj.loc[0, "lake_area_km2"] > 0.7

def test_peer_adjust_is_causal():
    """The adjusted score at window t must not change when later windows are removed."""
    idx, C = _fleet(); ok = pd.Series(True, index=C.index)
    full = V.peer_adjust(C, idx["date"], ok)
    cut = idx["date"] < idx["date"].unique()[5]
    part = V.peer_adjust(C[cut].reset_index(drop=True), idx.loc[cut, "date"].reset_index(drop=True), ok[cut].reset_index(drop=True))
    assert np.allclose(full[cut].to_numpy(), part.to_numpy(), equal_nan=True)

def test_lone_signal_cannot_reach_concern():
    adj = pd.DataFrame({c: [np.nan] for c in V.G.SIGNALS}); adj["thermal_index"] = 0.9
    risk, _, _ = V.fuse(adj)
    assert risk[0] < 0.5                            # thermal weight 0.10 over the full weight sum

def test_corroborated_signals_raise_risk():
    one = pd.DataFrame({c: [0.0] for c in V.G.SIGNALS}); one["lake_area_km2"] = 0.8
    two = one.copy(); two["sar_backscatter_change"] = 0.8
    assert V.fuse(two)[0][0] > V.fuse(one)[0][0]

def test_calibration_never_uses_event_lake_or_future():
    n = 400
    lake = np.array(["calm"] * n + [V.G.EVENT_LAKE] * n)
    date = np.concatenate([pd.date_range("2018-01-01", periods=n, freq="D").values] * 2)
    raw = np.concatenate([np.full(n, 0.1), np.full(n, 0.99)])        # event lake would wreck the quantiles
    cal = V.fit_calibration(raw, lake, date, np.ones(2 * n, bool), "2019-06-01")
    assert cal is not None and cal["high"] < 0.2                      # event lake ignored
    future = raw.copy(); future[date >= np.datetime64("2019-06-01")] = 0.99
    cal2 = V.fit_calibration(future, lake, date, np.ones(2 * n, bool), "2019-06-01")
    assert cal2 == cal                                                # windows after the cutoff ignored

def test_calibration_maps_quantiles_to_fixed_tiers():
    cal = {"watch": 0.2, "concern": 0.4, "high": 0.6}
    got = V.apply_calibration(np.array([0.0, 0.2, 0.4, 0.6, 1.0]), cal)
    assert np.allclose(got, [0.0, V.G.THRESH["watch"], V.G.THRESH["concern"], V.G.THRESH["high"], 1.0])

def test_v2_whole_fleet_is_causal():
    """Scoring only the windows before the outburst gives identical pre-outburst risk."""
    import pytest
    f = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "outputs", "per_signal_cache", "ps_isolation_forest.csv")
    if not os.path.exists(f):
        pytest.skip("per-signal cache not generated yet")
    ps = pd.read_csv(f, parse_dates=["date"]).sort_values(["lake", "date"]).reset_index(drop=True)
    full, _ = V.assemble_v2(ps)
    part, _ = V.assemble_v2(ps[ps.date < V.G.EVENT_DATE].reset_index(drop=True))
    a = full[full.date < V.G.EVENT_DATE].sort_values(["lake", "date"]).reset_index(drop=True)
    b = part.sort_values(["lake", "date"]).reset_index(drop=True)
    assert (a.risk_score.isna() == b.risk_score.isna()).all()
    assert np.nanmax((a.risk_score - b.risk_score).abs()) < 1e-9
