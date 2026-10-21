"""
GEWS Student C — the two tests that need re-scoring:
  (A) LEAK / CHEATING CHECK  — prove the pipeline is causal (handbook week 7)
  (B) UNSEEN-LAKE TEST       — does it generalise to a lake it never fit (week 11)
Imports Student B's pipeline (gews_spec) so we test the real model, not a copy.
"""
import sys, os, json
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gews_spec as G
from sklearn.ensemble import IsolationForest

EVENT_LAKE, EVENT_DATE = "south_lhonak", pd.Timestamp("2023-10-04")
DATA = "../data/lake_data"
RS = 42


# ============================================================ (A) LEAK ======
def leak_check(df):
    """Score South Lhonak with the FULL series vs a series truncated at the event.
    If the pipeline is causal (walk-forward, past-only), every pre-event score is
    identical either way. Any difference = future data leaking backward."""
    one = df[df.lake == EVENT_LAKE].copy()
    full = G.assemble(G.per_signal_scores(G.add_causal_deseason(one), "isolation_forest"))
    trunc_src = one[one.date < EVENT_DATE].copy()
    trunc = G.assemble(G.per_signal_scores(G.add_causal_deseason(trunc_src), "isolation_forest"))

    m = full[full.date < EVENT_DATE][["date", "risk_score"]].rename(columns={"risk_score": "full"})
    t = trunc[["date", "risk_score"]].rename(columns={"risk_score": "trunc"})
    cmp = m.merge(t, on="date", how="inner").dropna()
    max_diff = float((cmp["full"] - cmp["trunc"]).abs().max()) if len(cmp) else float("nan")
    causal_ok = max_diff < 1e-9
    print(f"[leak] pre-event windows compared: {len(cmp)} | max score diff full-vs-truncated = {max_diff:.2e}")
    print(f"[leak] CAUSAL (no future leaked backward): {causal_ok}")

    # Deliberate-leak demo: deseasonalise/normalise using ALL years (incl. post-event),
    # the classic cheat. Show the pre-event score CHANGES -> this is what leakage does.
    leaked = _noncausal_score(one)
    jn = full[full.date < EVENT_DATE][["date", "risk_score"]].rename(columns={"risk_score": "causal"})\
        .merge(leaked, on="date").dropna()
    leak_shift = float((jn["leaked"] - jn["causal"]).abs().mean()) if len(jn) else float("nan")
    print(f"[leak] deliberate-leak demo: mean pre-event score shift when future is used = {leak_shift:.3f}")
    return {"pre_event_windows": int(len(cmp)), "max_diff_causal": max_diff,
            "causal_ok": bool(causal_ok), "deliberate_leak_mean_shift": leak_shift}


def _noncausal_score(one):
    """WRONG on purpose: fit each signal's model on ALL years (future included),
    no walk-forward. Returns pre-event risk, to contrast with the causal version."""
    g = G.add_causal_deseason(one).reset_index(drop=True)
    per = {}
    for c in G.SIGNALS:
        feat = g[c + "_f"].values.astype(float)
        tr = feat[(g["observability"].fillna(0).values >= 0.5)]  # ALL years, incl. post-event
        per[c] = G.score_signal("isolation_forest", tr, feat)
    rows = []
    for i in range(len(g)):
        srow = {c: per[c][i] for c in G.SIGNALS}
        r, _, _ = G.fuse_and_drive(srow)
        rows.append(r)
    out = g[["date"]].copy(); out["leaked"] = rows
    return out[g["date"].values < EVENT_DATE]


# ================================================= (B) UNSEEN-LAKE ==========
def _lake_z(df):
    """Per-lake causal-deseasonalised, then z-scored to that lake's own normal."""
    g = G.add_causal_deseason(df)
    for c in G.SIGNALS:
        grp = g.groupby("lake")[c + "_f"]
        g[c + "_z"] = (g[c + "_f"] - grp.transform("mean")) / (grp.transform("std") + 1e-9)
    return g


def unseen_lake_test(df, held_out):
    """Train one pooled model per signal on the OTHER lakes, score each held-out lake
    it never saw. Tests spatial generalisation (the model is per-lake by design, so this
    is the pooled variant). For South Lhonak we train only on pre-event data too."""
    gz = _lake_z(df)
    results = []
    for lake in held_out:
        others = gz[gz.lake != lake]
        if lake == EVENT_LAKE:
            others = others[others.date < EVENT_DATE]        # time-fair for the event lake
        target = gz[gz.lake == lake].sort_values("date").copy()
        per = {}
        for c in G.SIGNALS:
            tr = others[c + "_z"].dropna().values
            tgt = target[c + "_z"].values
            if np.isfinite(tgt).sum() == 0 or len(tr) < G.MIN_TRAIN:
                per[c] = np.full(len(tgt), np.nan)        # nothing to score for this signal
            else:
                per[c] = G.score_signal("isolation_forest", tr, tgt)
        risk = []
        for i in range(len(target)):
            r, _, _ = G.fuse_and_drive({c: per[c][i] for c in G.SIGNALS})
            risk.append(r)
        target["risk_unseen"] = risk
        if lake == EVENT_LAKE:
            pre = target[(target.date < EVENT_DATE) &
                         (target.date >= EVENT_DATE - pd.Timedelta(days=182))]
            peak = float(np.nanmax(pre["risk_unseen"])) if len(pre) else float("nan")
            results.append({"lake": lake, "role": "event", "peak_preburst_risk_unseen": round(peak, 3)})
        else:
            fa = float((target["risk_unseen"] >= 0.70).mean() * 100)
            results.append({"lake": lake, "role": "control", "pct_windows_concern_unseen": round(fa, 1)})
    return results


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "outputs"
    os.makedirs(outdir, exist_ok=True)
    df = G.load(DATA)
    out = {}

    print("=== (A) leak / cheating check ===")
    out["leak_check"] = leak_check(df)

    print("\n=== (B) unseen-lake generalisation ===")
    sample = [EVENT_LAKE, "khecheopalri", "gurudongmar_lake4", "chandratal",
              "samudra_tapu", "tso_lhamo"]
    sample = [l for l in sample if l in df.lake.unique()]
    gen = unseen_lake_test(df, sample)
    for r in gen:
        print("  ", r)
    out["unseen_lake"] = gen

    json.dump(out, open(f"{outdir}/leak_and_generalisation.json", "w"), indent=2, default=str)
    print(f"\n[done] -> {outdir}/leak_and_generalisation.json")
    return out


if __name__ == "__main__":
    main()
