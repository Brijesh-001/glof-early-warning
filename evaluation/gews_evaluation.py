"""
GEWS — Model Testing & Evaluation (Student C).
==============================================
Reads Student B's scores and judges the system honestly, per the Student C handbook.

Metrics follow the handbook's rule: NOT accuracy (one flood in years of data makes
"always safe" 99.9% accurate). We use lead time, false alarms per lake-year, and the
cannot-assess rate, plus a threshold sweep that trades one against the other.

Truth list: inside the study window (2017-2026) and our 42 lakes there is ONE confirmed
moraine-dam outburst — South Lhonak, 4 Oct 2023. The other 41 are calm controls. (The
full HMA GLOF database, Zenodo 10.5281/zenodo.7271187, is the week-3 manual cross-check.)
"""
import sys, os, json
import numpy as np
import pandas as pd

EVENT_LAKE = "south_lhonak"
EVENT_DATE = pd.Timestamp("2023-10-04")
BANDS = {"watch": 0.50, "concern": 0.70, "high": 0.85}     # spec thresholds
MONSOON = (6, 9)                                            # Jun–Sep


# ------------------------------------------------------------------ load ----
def load_scores(path):
    d = pd.read_csv(path)
    d["date"] = pd.to_datetime(d["date"])
    d["month"] = d["date"].dt.month
    return d


def controls(d):
    return [l for l in d["lake"].unique() if l != EVENT_LAKE]


# -------------------------------------------------------------- metrics -----
def lead_time_weeks(d, lake, event_date, thr, lookback_days=182, sustain=2):
    """Earliest sustained crossing (>=thr for `sustain` consecutive assessed
    windows) within `lookback_days` before the event. Returns weeks early, or None."""
    w = d[(d.lake == lake) & (d.status == "assessed") &
          (d.date < event_date) & (d.date >= event_date - pd.Timedelta(days=lookback_days))]
    w = w.sort_values("date")
    r = w["risk_score"].values; dates = w["date"].values
    run = 0
    for i in range(len(r)):
        run = run + 1 if r[i] >= thr else 0
        if run >= sustain:
            first = dates[i - sustain + 1]
            return round((event_date - pd.Timestamp(first)).days / 7, 1)
    return None


def alarm_episodes(series_dates, series_risk, thr):
    """Count runs of consecutive windows at/above thr as ONE alarm each."""
    ep, prev = 0, False
    for v in series_risk:
        hot = v >= thr
        if hot and not prev:
            ep += 1
        prev = hot
    return ep


def false_alarm_rate(d, control_lakes, thr):
    """Alarm episodes per control lake per year (lake-years = assessed windows / 36)."""
    sub = d[(d.lake.isin(control_lakes)) & (d.status == "assessed")]
    episodes = 0
    for lk, g in sub.groupby("lake"):
        g = g.sort_values("date")
        episodes += alarm_episodes(g["date"].values, g["risk_score"].values, thr)
    lake_years = len(sub) / 36.0
    pct_windows = (sub["risk_score"] >= thr).mean() * 100
    return {"episodes": episodes, "lake_years": round(lake_years, 1),
            "per_lake_year": round(episodes / lake_years, 2) if lake_years else float("nan"),
            "pct_windows": round(pct_windows, 1)}


def cannot_assess_rate(d):
    overall = (d.status == "cannot_assess").mean() * 100
    mon = d[d.month.between(*MONSOON)]
    dry = d[~d.month.between(*MONSOON)]
    return {"overall_pct": round(overall, 1),
            "monsoon_pct": round((mon.status == "cannot_assess").mean() * 100, 1),
            "dry_pct": round((dry.status == "cannot_assess").mean() * 100, 1)}


def detection_precision(d, control_lakes, thr):
    """Event-level: did South Lhonak fire (sustained) pre-event? vs control FP episodes."""
    tp = 1 if lead_time_weeks(d, EVENT_LAKE, EVENT_DATE, thr) is not None else 0
    fp = sum(alarm_episodes(g.sort_values("date")["date"].values,
                            g.sort_values("date")["risk_score"].values, thr)
             for _, g in d[(d.lake.isin(control_lakes)) & (d.status == "assessed")].groupby("lake"))
    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    return {"detected": bool(tp), "control_false_alarms": int(fp),
            "precision": round(precision, 4), "recall": float(tp)}  # recall out of 1 event


# --------------------------------------------------------- self-test --------
def self_test():
    """Handbook week 5: prove the harness is correct on fake scores before real ones."""
    dates = pd.date_range("2023-01-01", periods=36, freq="10D")
    # fake positive lake: quiet, then a sustained spike 5 windows before 'event'
    risk = np.full(36, 0.3); risk[30:34] = 0.9
    ev = dates[34]
    fake = pd.DataFrame({"lake": "L_pos", "date": dates, "status": "assessed",
                         "risk_score": risk})
    lt = lead_time_weeks(fake, "L_pos", ev, 0.85)
    assert lt is not None and abs(lt - (40/7)) < 0.2, f"lead_time wrong: {lt}"
    # fake control: two separate high runs -> 2 episodes
    cr = np.full(36, 0.2); cr[5:8] = 0.9; cr[20:22] = 0.9
    assert alarm_episodes(dates.values, cr, 0.85) == 2, "episode count wrong"
    # a window below threshold between runs must break the episode
    assert alarm_episodes(dates.values, np.full(36, 0.9), 0.85) == 1, "single run wrong"
    print("[self-test] harness metric functions PASS")


# --------------------------------------------------------------- driver -----
def main():
    scores = sys.argv[1] if len(sys.argv) > 1 else \
        "../models/outputs/anomaly_scores_all_lakes.csv"
    outdir = sys.argv[2] if len(sys.argv) > 2 else "outputs"
    os.makedirs(outdir, exist_ok=True)
    self_test()

    d = load_scores(scores)
    ctrl = controls(d)
    report = {"n_lakes": int(d.lake.nunique()), "n_controls": len(ctrl),
              "event_lake": EVENT_LAKE, "event_date": str(EVENT_DATE.date())}

    # 1. Sikkim retrospective — lead time to each threshold
    lead = {b: lead_time_weeks(d, EVENT_LAKE, EVENT_DATE, t) for b, t in BANDS.items()}
    report["sikkim_lead_time_weeks"] = lead
    print("[sikkim] lead time (weeks early):", lead)

    # 2. False-alarm rate on controls + cannot-assess
    fa = {b: false_alarm_rate(d, ctrl, t) for b, t in BANDS.items()}
    report["false_alarm"] = fa
    report["cannot_assess"] = cannot_assess_rate(d)
    print("[false alarm per lake-year]", {b: fa[b]["per_lake_year"] for b in fa})
    print("[cannot-assess]", report["cannot_assess"])

    # 3. detection precision/recall (n=1 positive — caveat in report)
    report["detection"] = {b: detection_precision(d, ctrl, t) for b, t in BANDS.items()}

    # 4. threshold sweep — the trade-off curve
    sweep = []
    for t in np.round(np.arange(0.50, 0.96, 0.05), 2):
        lt = lead_time_weeks(d, EVENT_LAKE, EVENT_DATE, t)
        far = false_alarm_rate(d, ctrl, t)
        sweep.append({"threshold": float(t),
                      "sikkim_lead_weeks": lt if lt is not None else 0,
                      "sikkim_detected": lt is not None,
                      "control_false_alarms_per_lake_year": far["per_lake_year"]})
    pd.DataFrame(sweep).to_csv(f"{outdir}/threshold_sweep.csv", index=False)
    report["threshold_sweep"] = sweep

    # 5. failure cases — biggest control-lake alarms (one row per lake, its worst window)
    ca = d[(d.lake.isin(ctrl)) & (d.status == "assessed")].copy()
    worst = (ca.sort_values("risk_score", ascending=False)
             .groupby("lake").head(1).sort_values("risk_score", ascending=False).head(8))
    worst[["lake", "date", "risk_score", "band", "driver"]].to_csv(
        f"{outdir}/failure_cases.csv", index=False)
    report["top_false_alarms"] = worst[["lake", "date", "risk_score", "driver"]].head(5)\
        .assign(date=lambda x: x.date.dt.strftime("%Y-%m-%d")).to_dict("records")

    # South Lhonak full 2023 trajectory for the headline chart
    sl = d[(d.lake == EVENT_LAKE) & (d.date.dt.year == 2023)].sort_values("date").copy()
    sl["weeks_before"] = ((EVENT_DATE - sl["date"]).dt.days / 7).round(1)
    sl[["date", "weeks_before", "observability", "status", "band", "risk_score", "driver"]]\
        .to_csv(f"{outdir}/sikkim_trajectory_2023.csv", index=False)

    json.dump(report, open(f"{outdir}/evaluation_report.json", "w"), indent=2, default=str)
    print(f"[done] wrote evaluation outputs to {outdir}/")
    return d, report, pd.DataFrame(sweep)


if __name__ == "__main__":
    main()
