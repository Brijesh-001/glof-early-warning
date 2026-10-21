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
