"""
GEWS v2: better fusion and calibration on top of the v1 per-signal scores.
==========================================================================
v1 (gews_spec.py) scores every signal of every lake against that lake's own past with an
Isolation Forest. That part is unchanged. v2 only changes what happens AFTER the per-signal
scores exist, fixing three weaknesses the v1 methodology note already admits to:

1. COMMON-MODE NOISE. In 2019-2020 about 98 % of all lakes scored High/Concern at the same
   time. A flag shared by nearly every lake says nothing about any one lake (sensor artefact,
   shared season, annual velocity step). v2 subtracts the fleet median of the same signal in the
   same window, so a lake has to stand out from its peers, not just from its own history.
   Uses only the current window's cross-section, so it stays causal.

2. LONE-SIGNAL FLAGS. v1 divides by the weights of the signals that happen to be present, so a
   single thermal reading at 0.7 became a Concern. v2 divides by the full weight sum: a missing
   signal is "no evidence", not "evidence of anomaly". A flag needs corroboration.

3. HOT THRESHOLDS. v1's 0.50 / 0.70 / 0.85 sat on an uncalibrated scale (64 % of calm-lake
   windows reached Watch). v2 maps the fused score onto the SAME 0.50 / 0.70 / 0.85 tiers, but
   anchors them to explicit false-alarm budgets measured on calm lakes:
       Watch   = top 10 % of calm-lake windows
       Concern = top  3 %
       High    = top  1 %
   The budgets are chosen a priori (not searched against the outburst). Calibration is
   WALK-FORWARD like the detectors: each calendar year is calibrated on control lakes only (never
   South Lhonak) and only windows BEFORE 1 January of that year. The 2023 outburst is therefore
   scored with a calibration that has seen nothing from 2023 on. (A single fixed calibration was
   tried first: calm lakes then exceeded the High budget by 14-16x in 2023-24 because behaviour
   drifts, so the calibration is refreshed yearly.)

4. ANNUAL-SIGNAL PLATEAUS. Glacier speed and acceleration come from yearly ITS_LIVE data: one odd
   yearly value flags all 36 windows of that year (in 2022 eight calm lakes sat at High for the whole
   year on velocity alone). v2 lets the two annual signals raise a lake to Watch but not to Concern
   or High unless at least one fast signal (lake area, radar, thermal) is also elevated.

Tried and rejected (hurt the event signal with no matching gain): a 3-window rolling median.

Honest limit: there is one confirmed outburst. v2 is measured against v1 on that event AND on
false alarms / common-mode behaviour, but one event cannot prove predictive skill. See
MODEL_V2_NOTE.md.

    python gews_v2.py ../data/lake_data outputs        # reads outputs/per_signal_cache/
"""
import os, sys, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gews_spec as G

MIN_PEERS = 8                         # lakes needed in a window to trust the fleet median
PEER_FILL = 6                         # carry the last fleet median forward at most this many windows
MIN_CAL = 200                         # calm-lake windows needed before a calibration is trusted
BUDGETS = {"watch": 0.90, "concern": 0.97, "high": 0.99}   # quantiles of calm-lake windows
FAST = ["lake_area_km2", "sar_backscatter_change", "thermal_index"]   # observed every window
CAP_NO_FAST = 0.69                    # without a fast signal, risk cannot reach Concern (0.70)
DRIVER_MIN = 0.25                     # a signal is named as a driver above this adjusted score
VERSION = "v2"


# ---------------------------------------------------------------- stage 1 ----
def signal_scores(ps):
    """Per-signal outlier score in [0,1] (same calibration as v1: own median -> 0, extreme -> 1)."""
    return pd.DataFrame({c: ((ps["s_" + c] - 0.5) * 2.0).clip(0, 1) for c in G.SIGNALS}, index=ps.index)


def gate(ps):
    """v1's abstention rule: low observability or too little history -> cannot assess."""
    obs = ps["observability"].fillna(0).values
    return (obs >= G.OBS_FLOOR) & (ps["obs_hist"].values >= G.MIN_HISTORY)


# ---------------------------------------------------------------- stage 2 ----
def peer_adjust(C, dates, ok, min_peers=MIN_PEERS, fill=PEER_FILL):
    """Subtract the fleet median of each signal in the same window (causal: one window only).

    C: DataFrame of per-signal scores. dates: Series of window dates. ok: boolean gate mask.
    Windows with fewer than `min_peers` usable lakes reuse the most recent fleet median for up to
    `fill` windows; beyond that the signal is dropped for that window rather than left unadjusted.
    """
    out = pd.DataFrame(index=C.index, columns=C.columns, dtype=float)
    for c in C.columns:
        v = C[c].where(ok)
        grp = v.groupby(dates.values)
        med = grp.median().where(grp.count() >= min_peers)
        med = med.sort_index().ffill(limit=fill)
        out[c] = (C[c] - dates.map(med).values).clip(0, 1)
    return out


def fuse(adj, weights=None, p=G.P):
    """Weighted p-norm over the FULL weight sum: absent signals add nothing.

    Returns (risk, driver, n_contributing). risk is NaN only if no signal at all is available."""
    weights = weights or G.WEIGHTS
    w_all = sum(weights.values())
    cols = list(adj.columns)
    A = adj.to_numpy(dtype=float)
    W = np.array([weights[c] for c in cols])
    have = ~np.isnan(A)
    term = np.where(have, W * np.nan_to_num(A) ** p, 0.0)
    risk = np.where(have.any(axis=1), (term.sum(axis=1) / w_all) ** (1.0 / p), np.nan)
    drivers, ncon = [], []
    for i in range(len(A)):
        if np.isnan(risk[i]):
            drivers.append(""); ncon.append(0); continue
        order = np.argsort(-term[i])[:3]
        named = [G.PRETTY[cols[j]] for j in order if have[i, j] and A[i, j] >= DRIVER_MIN]
        drivers.append(" · ".join(named) or "—"); ncon.append(len(named))
    return risk, drivers, np.array(ncon)


# ---------------------------------------------------------------- stage 3 ----
def fit_calibration(risk_raw, lake, date, ok, before, event_lake=G.EVENT_LAKE, budgets=BUDGETS):
    """Quantiles of calm-lake raw scores from windows strictly before `before`. Excludes the event
    lake entirely. Returns None if there are too few windows to trust."""
    m = ok & (lake != event_lake) & (date < np.datetime64(before)) & ~np.isnan(risk_raw)
    vals = risk_raw[m]
    if len(vals) < MIN_CAL:
        return None
    return {k: float(np.quantile(vals, q)) for k, q in budgets.items()} | {"n_windows": int(len(vals))}


def walk_forward_calibration(risk_raw, lake, date, eligible=None):
    """One calibration per calendar year, each using only the past. Years with too little past use
    the first trusted calibration (those early windows are mostly abstentions anyway)."""
    years = sorted(set(pd.DatetimeIndex(date).year))
    cals, first = {}, None
    for y in years:
        c = fit_calibration(risk_raw, lake, date, ~np.isnan(risk_raw) if eligible is None else (~np.isnan(risk_raw) & eligible), f"{y}-01-01")
        if c is not None:
            cals[y] = c; first = first or c
    for y in years:
        cals.setdefault(y, first)
    return cals


def apply_calibration(risk_raw, cal):
    """Monotone map: raw quantiles -> the fixed 0.50 / 0.70 / 0.85 tiers, 0 -> 0, 1 -> 1."""
    xs = [0.0, cal["watch"], cal["concern"], cal["high"], 1.0]
    ys = [0.0, G.THRESH["watch"], G.THRESH["concern"], G.THRESH["high"], 1.0]
    for i in range(1, len(xs)):                       # keep knots strictly increasing
        xs[i] = max(xs[i], xs[i - 1] + 1e-6)
    return np.interp(risk_raw, xs, ys)


# ----------------------------------------------------------------- driver ----
def assemble_v2(ps, cal=None):
    """Full v2 table with the same columns as v1's assemble(). Returns (table, calibration)."""
    base = G.assemble(ps)                              # gating, status, reasons (unchanged)
    ok = gate(ps)
    C = signal_scores(ps)
    adj = peer_adjust(C, ps["date"], pd.Series(ok, index=ps.index))
    raw, drivers, ncon = fuse(adj)
    raw = np.where(ok, raw, np.nan)
    lake, date = ps["lake"].values, ps["date"].values
    fast_ok = (adj[FAST].fillna(0).max(axis=1) >= DRIVER_MIN).values      # a fast signal agrees
    cal = cal or walk_forward_calibration(raw, lake, date, eligible=fast_ok)
    yrs = pd.DatetimeIndex(date).year
    risk = np.full(len(raw), np.nan)
    for y in sorted(set(yrs)):
        m = (yrs == y) & ~np.isnan(raw)
        risk[m] = apply_calibration(raw[m], cal[y])
    risk = np.where(fast_ok, risk, np.minimum(risk, CAP_NO_FAST))

    out = base.copy()
    has = ~np.isnan(risk)
    still_ok = (base["status"] == "assessed").values
    out["risk_score"] = np.where(still_ok & has, risk, np.nan)
    newly_empty = still_ok & ~has
    out["status"] = np.where(newly_empty, "cannot_assess", base["status"])
    out["reason"] = np.where(newly_empty, "no signal available this window", base["reason"])
    out["band"] = [G.band(x) for x in out["risk_score"]]
    out["driver"] = np.where(out["risk_score"].notna(), drivers, "")
    out["n_contributing_signals"] = np.where(out["risk_score"].notna(), ncon, 0)
    out["raw_fused"] = np.where(out["risk_score"].notna(), raw, np.nan)
    return out, cal


# -------------------------------------------------------------- comparison ----
def event_rank(res, horizon_days, lake=G.EVENT_LAKE, event=G.EVENT_DATE):
    """Rank (1 = highest) of the event lake's peak score among all lakes over the run-up."""
    w = res[(res.date >= event - pd.Timedelta(days=horizon_days)) & (res.date < event)
            & (res.status == "assessed")]
    peaks = w.groupby("lake")["risk_score"].max().sort_values(ascending=False)
    return (int(list(peaks.index).index(lake) + 1), int(len(peaks))) if lake in peaks.index else (None, int(len(peaks)))


def common_mode(res, min_lakes=10):
    a = res[res.status == "assessed"]
    n = a.groupby("date").size()
    share = a.groupby("date")["risk_score"].apply(lambda x: (x >= G.THRESH["concern"]).mean())
    share = share[n >= min_lakes]
    return {"share_sd": float(share.std()), "pct_windows_ge40": float((share >= 0.4).mean() * 100),
            "mean_share_2019_2020": float(share["2019":"2020"].mean())}


def compare(v1, v2):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "evaluation"))
    import gews_evaluation as E
    rows = []
    for name, r in (("v1", v1), ("v2", v2)):
        r = r.copy(); r["month"] = r["date"].dt.month
        ctrl = E.controls(r)
        row = {"model": name, "event_peak_runup_40d": round(float(G.peak_runup(r)), 3)}
        for h in (40, 90, 180):
            k, n = event_rank(r, h); row[f"event_rank_{h}d"] = f"{k}/{n}"
        for b, t in E.BANDS.items():
            fa = E.false_alarm_rate(r, ctrl, t)
            row[f"lead_wk_{b}"] = E.lead_time_weeks(r, E.EVENT_LAKE, E.EVENT_DATE, t)
            row[f"false_alarms_per_lake_year_{b}"] = fa["per_lake_year"]
            row[f"pct_control_windows_{b}"] = fa["pct_windows"]
        cm = common_mode(r)
        row.update({"common_mode_pct_windows_ge40pct_lakes": round(cm["pct_windows_ge40"], 1),
                    "mean_share_lakes_concern_2019_2020": round(cm["mean_share_2019_2020"], 3)})
        rows.append(row)
    return pd.DataFrame(rows)


def load_per_signal(data_dir, outdir):
    """Per-signal scores for the CURRENT data. A cache built from different data is never used."""
    for name in ("_cache", "per_signal_cache"):
        d = os.path.join(outdir, name)
        f = os.path.join(d, "ps_isolation_forest.csv")
        if os.path.exists(f) and G.cache_is_fresh(d, data_dir):
            ps = pd.read_csv(f); ps["date"] = pd.to_datetime(ps["date"])
            return ps
    print("[v2] cached per-signal scores are missing or older than the data: recomputing (a few minutes)")
    df = G.add_causal_deseason(G.load(data_dir))
    ps = G.per_signal_scores(df, "isolation_forest", int(os.environ.get("GEWS_JOBS", "-1")))
    for name in ("_cache", "per_signal_cache"):
        d = os.path.join(outdir, name); os.makedirs(d, exist_ok=True)
        ps.to_csv(os.path.join(d, "ps_isolation_forest.csv"), index=False)
        G.stamp_cache(d, data_dir)
    return ps


def main(data_dir=None, outdir=None):
    data_dir = data_dir or (sys.argv[1] if len(sys.argv) > 1 else "../data/lake_data")
    outdir = outdir or (sys.argv[2] if len(sys.argv) > 2 else "outputs")
    ps = load_per_signal(data_dir, outdir)
    ps = ps.sort_values(["lake", "date"]).reset_index(drop=True)

    v1 = G.assemble(ps)
    v2, cal = assemble_v2(ps)
    keep = ["lake", "date", "observability", "status", "band", "risk_score", "driver",
            "n_contributing_signals", "reason"]
    v1[keep].to_csv(f"{outdir}/anomaly_scores_v1.csv", index=False)
    v2[keep].to_csv(f"{outdir}/anomaly_scores_all_lakes.csv", index=False)

    # watch-list: each lake's latest ASSESSED window, ranked; lakes with none last (same rule as v1)
    s = v2.sort_values("date")
    latest = s[s.status == "assessed"].groupby("lake").tail(1)
    seen = set(latest.lake)
    abst = s[~s.lake.isin(seen)].groupby("lake").tail(1)
    pd.concat([latest.sort_values("risk_score", ascending=False), abst])[keep].to_csv(
        f"{outdir}/watchlist_latest.csv", index=False)

    cmp = compare(v1, v2)
    cmp.to_csv(f"{outdir}/v1_vs_v2.csv", index=False)
    print(cmp.T.to_string(header=False))

    # record the settings next to v1's so the run is reproducible
    log_path = f"{outdir}/experiment_log.json"
    log = json.load(open(log_path)) if os.path.exists(log_path) else {}
    log.update({"model_version": VERSION, "n_assessed": int((v2.status == "assessed").sum()),
                "v2": {"peer_adjust": {"min_peers": MIN_PEERS, "fill_windows": PEER_FILL},
                       "fusion": "weighted p-norm over the full weight sum (missing signal = no evidence)",
                       "calibration": {"budgets_top_fraction": {k: round(1 - q, 3) for k, q in BUDGETS.items()},
                                       "scheme": "walk-forward, refreshed each January from control lakes' past windows only",
                                       "raw_quantiles_by_year": {str(y): {k: round(c[k], 4) for k in BUDGETS} | {"windows": c["n_windows"]}
                                                                 for y, c in cal.items()}}}})
    json.dump(log, open(log_path, "w"), indent=2, default=str)
    print(f"[v2] wrote {outdir}/anomaly_scores_all_lakes.csv (v2), anomaly_scores_v1.csv, v1_vs_v2.csv")
    return v1, v2, cal, cmp


if __name__ == "__main__":
    main()
