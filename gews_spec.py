"""
GEWS — Model Development (Student B), built to the GEWS_Project_Concise spec.
=============================================================================
Faithful to the design pages:
  p13  five signals + observability (observability gates, is NOT a feature)
  p14  every lake compared only to itself  -> per-lake fitting
  p15  deseasonalise against the lake's OWN CAUSAL climatology (earlier years only)
  p16  one-class only; n=1 positive; four detectors, IF is production
  p17  detectors + hyperparameters (IF 300 trees / 256 samples / contam 0.02, etc.)
  p18  "names the reason": per-signal scores -> top-3 contributing_signals = DRIVER
  p19  walk-forward: fit on the past only, score forward, never score seen data
  p20  fusion = weighted p-norm, p = 3
  p23  pipeline: abstain(obs<0.30 OR <24 history) -> per-signal score -> fuse ->
       threshold(watch .50 / concern .70 / high .85) -> sort; abstainers not ranked
  p24  watch-list shows RISK, STATUS, DRIVER

Interpretation note (defend this at viva): the spec's flow is fixed —
"one score per signal (0-1)" -> weighted p-norm -> risk, and the reason is
"leave one signal out, re-score, measure the drop". We realise the per-signal
score with the chosen detector run per signal; the IF "5-D cloud" picture is its
concept, the per-signal score is its product. Swapping the detector = the p21
ablation; removing a signal = the p22 ablation.
"""
import sys, os, glob, json
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.svm import OneClassSVM
from sklearn.linear_model import Ridge

RS = 42
# --- spec constants -------------------------------------------------------
SIGNALS = ["lake_area_km2", "velocity_trend", "velocity_accel",
           "sar_backscatter_change", "thermal_index"]
WEIGHTS = {"lake_area_km2": 0.30, "velocity_trend": 0.20, "velocity_accel": 0.20,
           "sar_backscatter_change": 0.20, "thermal_index": 0.10}        # p20
DESEASON = ["lake_area_km2", "thermal_index"]           # p13: others already diffs
OBS_FLOOR = 0.30                                         # p23 step 1
MIN_HISTORY = 24                                         # p23 step 1
MIN_TRAIN = 20                                           # need some normal to fit
REFIT_YEARS = 2         # p19 walk-forward refit cadence (spec 1yr; 2 for compute)
P = 3                                                    # p20 p-norm
THRESH = {"watch": 0.50, "concern": 0.70, "high": 0.85}  # p23 step 4
PRETTY = {"lake_area_km2": "lake area", "velocity_trend": "glacier speed",
          "velocity_accel": "glacier accel", "sar_backscatter_change": "radar change",
          "thermal_index": "thermal"}
EVENT_LAKE, EVENT_DATE = "south_lhonak", pd.Timestamp("2023-10-04")


# ---------------------------------------------------------------- load -----
def load(data_dir):
    fr = []
    for f in sorted(glob.glob(os.path.join(data_dir, "*_windows.csv"))):
        d = pd.read_csv(f)
        d["lake"] = os.path.basename(f).replace("_windows.csv", "")
        d["date"] = pd.to_datetime(d["window"], format="mixed")
        d["year"] = d["date"].dt.year
        d["dekad"] = ((d["date"].dt.dayofyear - 1) // 10).clip(upper=35)
        fr.append(d)
    df = pd.concat(fr, ignore_index=True).sort_values(["lake", "date"])
    return df.reset_index(drop=True)


def add_causal_deseason(df):
    """p15: subtract each dekad's climatology built from EARLIER YEARS ONLY.
    Vectorised once for the whole frame: within each (lake, dekad) ordered by
    year, the climatology is the expanding median shifted by one (past years)."""
    df = df.sort_values(["lake", "dekad", "year"]).copy()
    for c in DESEASON:
        clim = df.groupby(["lake", "dekad"])[c].transform(
            lambda s: s.expanding().median().shift(1))
        df[c + "_f"] = df[c] - clim            # causal seasonal anomaly
    for c in SIGNALS:
        if c not in DESEASON:
            df[c + "_f"] = df[c]               # already a difference
    return df.sort_values(["lake", "date"]).reset_index(drop=True)


# ---------------------------------------------- per-signal detectors -------
def _cdf(sorted_tr, x):
    """percentile of x within sorted training scores, vectorised; NaN stays NaN."""
    out = np.full(x.shape, np.nan)
    fin = ~np.isnan(x)
    out[fin] = np.searchsorted(sorted_tr, x[fin], side="right") / max(len(sorted_tr), 1)
    return out


def score_signal(detector, train, allv):
    """Fit `detector` on 1-D train values, return per-window score in [0,1].
    Only finite windows are scored; NaN windows return NaN."""
    train = train[~np.isnan(train)]
    if len(train) < MIN_TRAIN:
        return np.full(len(allv), np.nan)
    fin = ~np.isnan(allv)
    Xf = allv[fin].reshape(-1, 1)
    raw = np.full(len(allv), np.nan)
    if detector == "zscore":                                   # p17 baseline
        med = np.median(train); mad = np.median(np.abs(train - med)) * 1.4826 + 1e-9
        raw_tr = np.abs(train - med) / mad
        raw[fin] = np.abs(allv[fin] - med) / mad
    elif detector == "isolation_forest":                       # p17 production
        m = IsolationForest(n_estimators=300, max_samples=min(256, len(train)),
                            contamination=0.02, random_state=RS, n_jobs=-1
                            ).fit(train.reshape(-1, 1))
        raw_tr = -m.score_samples(train.reshape(-1, 1)); raw[fin] = -m.score_samples(Xf)
    elif detector == "one_class_svm":                          # p17 ablation
        m = OneClassSVM(nu=0.02, gamma="scale").fit(train.reshape(-1, 1))
        raw_tr = -m.decision_function(train.reshape(-1, 1)); raw[fin] = -m.decision_function(Xf)
    else:
        raise ValueError(detector)
    return _cdf(np.sort(raw_tr), raw)


def score_ridge_ar(train_series, full_series, train_mask, L=12, alpha=1.0):
    """p17 ridge_ar: predict a window from the previous L; anomaly = |residual|."""
    y, X = [], []
    for i in range(L, len(full_series)):
        lags = full_series[i - L:i]
        if np.isnan(full_series[i]) or np.isnan(lags).any():
            continue
        if train_mask[i]:
            y.append(full_series[i]); X.append(lags)
    out = np.full(len(full_series), np.nan)
    if len(y) < MIN_TRAIN:
        return out
    m = Ridge(alpha=alpha).fit(np.array(X), np.array(y))
    res_tr = np.sort(np.abs(np.array(y) - m.predict(np.array(X))))
    for i in range(L, len(full_series)):
        lags = full_series[i - L:i]
        if np.isnan(full_series[i]) or np.isnan(lags).any():
            continue
        r = abs(full_series[i] - m.predict(lags.reshape(1, -1))[0])
        out[i] = np.searchsorted(res_tr, r, side="right") / max(len(res_tr), 1)
    return out


# ------------------------------------------------- fuse + drive ------------
def cal(s):
    """Calibrate a per-signal percentile to an outlier score: a window at this
    lake's own median -> 0, at its upper extreme -> 1. Keeps 'normal' near zero
    so the watch/concern/high thresholds and contamination 0.02 are meaningful."""
    return min(1.0, max(0.0, (s - 0.5) * 2.0))


def fuse_and_drive(srow):
    """p20 weighted p-norm (renormalised over available signals) + p18 driver."""
    num = den = 0.0
    contrib = {}; scal = {}
    for c in SIGNALS:
        s = srow[c]
        if s is None or np.isnan(s):
            continue
        sc = cal(s); scal[c] = sc
        w = WEIGHTS[c]
        term = w * (sc ** P)
        num += term; den += w; contrib[c] = term
    if den == 0:
        return np.nan, "", 0
    risk = (num / den) ** (1.0 / P)
    top = sorted(contrib, key=contrib.get, reverse=True)[:3]          # p18 top-3
    driver = " · ".join(PRETTY[c] for c in top if scal[c] >= 0.5) or "—"
    n_contrib = int(sum(1 for c in top if scal[c] >= 0.5))
    return risk, driver, n_contrib


# ----------------------- walk-forward PER-SIGNAL scores for one lake -------
def per_signal_lake(g, detector):
    """p19 walk-forward: refit on past-only every REFIT_YEARS, score forward.
    Returns one 0-1 score per signal per window (NaN where unscorable)."""
    g = g.reset_index(drop=True); n = len(g)
    yr = g["year"].values; obs = g["observability"].fillna(0).values
    years = sorted(set(yr))
    per = {c: np.full(n, np.nan) for c in SIGNALS}
    for c in SIGNALS:
        feat = g[c + "_f"].values.astype(float)
        last, cur = None, None
        for Y in years:
            if last is None or (Y - last) >= REFIT_YEARS:            # refit on past only
                trmask = (yr < Y) & (obs >= 0.5)
                if detector == "ridge_ar":
                    cur = score_ridge_ar(feat[trmask], feat, trmask)
                else:
                    cur = score_signal(detector, feat[trmask], feat)
                last = Y if not np.all(np.isnan(cur)) else None
            if cur is not None:
                tgt = yr == Y; per[c][tgt] = cur[tgt]
    out = g[["lake", "date", "year", "observability"]].copy()
    out["obs_hist"] = (pd.Series(obs > 0).cumsum().shift(1).fillna(0)).values
    for c in SIGNALS:
        out["s_" + c] = per[c]
    return out


def per_signal_scores(df, detector):
    return pd.concat([per_signal_lake(g, detector) for _, g in df.groupby("lake")],
                     ignore_index=True)


def band(r):
    if pd.isna(r): return "cannot_assess"
    if r >= THRESH["high"]: return "high"
    if r >= THRESH["concern"]: return "concern"
    if r >= THRESH["watch"]: return "watch"
    return "ok"


# ----------------------- gate + fuse a score table (fast; no refitting) ----
def assemble(ps, drop_signal=None):
    """p23: abstain -> fuse (p-norm) -> driver -> band. Reuses a score table,
    so ablation (drop a signal) and detector swaps need no refitting."""
    use = [c for c in SIGNALS if c != drop_signal]
    risk = np.full(len(ps), np.nan); driver = [""] * len(ps)
    ncon = np.zeros(len(ps), int); status = ["assessed"] * len(ps); reason = [""] * len(ps)
    obsv = ps["observability"].values; hist = ps["obs_hist"].values
    scols = {c: ps["s_" + c].values for c in use}
    for i in range(len(ps)):
        if pd.isna(obsv[i]) or obsv[i] < OBS_FLOOR:
            status[i] = "cannot_assess"; reason[i] = "low observability (cloud / no data)"; continue
        if hist[i] < MIN_HISTORY:
            status[i] = "cannot_assess"; reason[i] = "too little history (<24 windows)"; continue
        srow = {c: scols[c][i] for c in use}
        for c in SIGNALS:
            srow.setdefault(c, np.nan)
        r, dr, nc = fuse_and_drive(srow)
        if np.isnan(r):
            status[i] = "cannot_assess"; reason[i] = "no signal available this window"; continue
        risk[i] = r; driver[i] = dr; ncon[i] = nc
    out = ps[["lake", "date", "observability"]].copy()
    out["risk_score"] = risk; out["status"] = status; out["band"] = [band(x) for x in risk]
    out["driver"] = driver; out["n_contributing_signals"] = ncon; out["reason"] = reason
    out["year"] = pd.to_datetime(ps["date"]).dt.year
    return out


def peak_runup(res, lake=EVENT_LAKE, days=40):
    m = ((res.lake == lake) & (res.date >= EVENT_DATE - pd.Timedelta(days=days)) &
         (res.date < EVENT_DATE))
    return res.loc[m, "risk_score"].max()


def false_alarm_rate(res, exclude=EVENT_LAKE):
    sub = res[(res.lake != exclude) & (res.status == "assessed")]
    return float((sub["risk_score"] >= THRESH["high"]).mean() * 100)


def main():
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "lake_data"
    outdir = sys.argv[2] if len(sys.argv) > 2 else "spec_outputs"
    os.makedirs(outdir, exist_ok=True)
    cache = os.path.join(outdir, "_cache"); os.makedirs(cache, exist_ok=True)

    def cached_scores(detector):
        fp = os.path.join(cache, f"ps_{detector}.csv")
        if os.path.exists(fp):
            d = pd.read_csv(fp); d["date"] = pd.to_datetime(d["date"]); return d
        d = per_signal_scores(df, detector); d.to_csv(fp, index=False); return d

    df = load(data_dir)
    df = add_causal_deseason(df)            # compute causal climatology ONCE
    print(f"[load] {df.lake.nunique()} lakes, {len(df)} windows")

    # per-signal scores for the production detector (cached after first compute)
    ps_if = cached_scores("isolation_forest")
    res = assemble(ps_if)                   # production run (Isolation Forest)
    keep = ["lake", "date", "observability", "status", "band", "risk_score",
            "driver", "n_contributing_signals", "reason"]
    res[keep].to_csv(f"{outdir}/anomaly_scores_all_lakes.csv", index=False)
    n_assess = (res.status == "assessed").sum()
    print(f"[production] {n_assess} assessed, {(res.status=='cannot_assess').sum()} abstained")

    # watch-list: each lake's latest ASSESSED window (fall back to its last window
    # if it is currently unseen); ranked, abstainers last (p23/p24)
    res_s = res.sort_values("date")
    assessed_latest = (res_s[res_s.status == "assessed"].groupby("lake").tail(1))
    seen = set(assessed_latest.lake)
    abst_latest = res_s[~res_s.lake.isin(seen)].groupby("lake").tail(1)
    wl = pd.concat([assessed_latest.sort_values("risk_score", ascending=False), abst_latest])
    wl[keep].to_csv(f"{outdir}/watchlist_latest.csv", index=False)

    # p21 detector comparison (IF reuses the table already computed)
    comp = []
    for det in ["zscore", "isolation_forest", "one_class_svm", "ridge_ar"]:
        ps = ps_if if det == "isolation_forest" else cached_scores(det)
        r = assemble(ps)
        comp.append({"detector": det, "peak_runup_southlhonak": round(float(peak_runup(r)), 3),
                     "false_alarm_pct_other_lakes": round(false_alarm_rate(r), 2)})
        print(f"[detector] {det:16s} run-up={comp[-1]['peak_runup_southlhonak']:.3f} "
              f"false-alarm={comp[-1]['false_alarm_pct_other_lakes']:.2f}%")
    pd.DataFrame(comp).to_csv(f"{outdir}/detector_comparison.csv", index=False)

    # p22 signal ablation = re-fuse the SAME IF table with a signal removed (no refit)
    abl = [{"config": "all_signals", "peak_runup": round(float(peak_runup(res)), 3)}]
    for s in SIGNALS:
        r = assemble(ps_if, drop_signal=s)
        abl.append({"config": "drop_" + s, "peak_runup": round(float(peak_runup(r)), 3)})
        print(f"[ablation] drop {s:24s} run-up={abl[-1]['peak_runup']:.3f}")
    pd.DataFrame(abl).to_csv(f"{outdir}/ablation_results.csv", index=False)

    # South Lhonak 2023 trajectory (production, walk-forward)
    sl = res[(res.lake == EVENT_LAKE) & (res.year == 2023)].copy()
    sl["weeks_before_burst"] = ((EVENT_DATE - sl["date"]).dt.days / 7).round(1)
    sl[keep + ["weeks_before_burst"]].to_csv(f"{outdir}/sikkim_2023_southlhonak.csv", index=False)

    log = {"spec": "GEWS_Project_Concise", "detector": "isolation_forest",
           "if_params": {"n_estimators": 300, "max_samples": 256, "contamination": 0.02},
           "weights": WEIGHTS, "p_norm": P, "thresholds": THRESH,
           "abstain": {"obs_floor": OBS_FLOOR, "min_history": MIN_HISTORY},
           "detector_comparison": comp, "ablation": abl,
           "n_assessed": int(n_assess)}
    json.dump(log, open(f"{outdir}/experiment_log.json", "w"), indent=2, default=str)
    print(f"[done] -> {outdir}/")
    return res, comp, abl, sl


if __name__ == "__main__":
    main()
