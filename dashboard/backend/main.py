"""
GEWS Watch Console — backend (Student D).

A thin FastAPI layer over the committed pipeline outputs. It never recomputes model scores
itself: every number comes from data/, models/outputs/ or evaluation/outputs/, so a value on
screen can always be traced back to the stage that wrote it.

    uvicorn dashboard.backend.main:app --port 8000      # from the repo root
    python dashboard/run.py                             # same, with a friendlier wrapper
"""
import json, os, subprocess, sys, tempfile, threading, time
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(ROOT, "data")
LAKES = os.path.join(DATA, "lake_data")
MODEL_OUT = os.path.join(ROOT, "models", "outputs")
EVAL_OUT = os.path.join(ROOT, "evaluation", "outputs")
FRONTEND = os.path.join(ROOT, "dashboard", "frontend")

SIGNALS = ["lake_area_km2", "velocity_trend", "velocity_accel",
           "sar_backscatter_change", "thermal_index"]
BANDS = ["high", "concern", "watch", "ok", "cannot_assess"]

app = FastAPI(title="GEWS Watch Console API", version="2.1.0")


# ---------- helpers ----------

def _records(df):
    """DataFrame -> JSON-safe list of dicts (NaN -> null)."""
    return json.loads(df.to_json(orient="records", date_format="iso"))


def _csv(*parts):
    path = os.path.join(*parts)
    if not os.path.exists(path):
        raise HTTPException(404, f"missing pipeline output: {os.path.relpath(path, ROOT)}")
    return pd.read_csv(path)


def _json(*parts):
    path = os.path.join(*parts)
    if not os.path.exists(path):
        raise HTTPException(404, f"missing pipeline output: {os.path.relpath(path, ROOT)}")
    with open(path) as f:
        return json.load(f)


def _mtime(path):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path)))


_cache = {}


def scores():
    """anomaly_scores_all_lakes.csv, cached until the file changes on disk."""
    path = os.path.join(MODEL_OUT, "anomaly_scores_all_lakes.csv")
    m = os.path.getmtime(path)
    if _cache.get("scores_mtime") != m:
        _cache["scores"] = pd.read_csv(path, parse_dates=["date"])
        _cache["scores_mtime"] = m
    return _cache["scores"]


def lake_windows(lake):
    path = os.path.join(LAKES, f"{lake}_windows.csv")
    if not os.path.exists(path):
        raise HTTPException(404, f"unknown lake: {lake}")
    return pd.read_csv(path, parse_dates=["window"])


# ---------- overview / watch-list ----------

@app.get("/api/summary")
def summary():
    s = scores()
    log = _json(MODEL_OUT, "experiment_log.json")
    rep = _json(EVAL_OUT, "evaluation_report.json")
    wl = _csv(MODEL_OUT, "watchlist_latest.csv")
    return {
        "model_version": app.version,
        "data_version": "v3-final",
        "n_lakes": int(s["lake"].nunique()),
        "n_windows": int(len(s)),
        "n_assessed": int((s["status"] == "assessed").sum()),
        "n_abstained": int((s["status"] == "cannot_assess").sum()),
        "date_range": [s["date"].min().date().isoformat(), s["date"].max().date().isoformat()],
        "latest_date": str(wl["date"].max()),
        "latest_bands": wl["band"].value_counts().reindex(BANDS, fill_value=0).to_dict(),
        "thresholds": log["thresholds"],
        "lead_time_weeks": rep["sikkim_lead_time_weeks"],
        "event": {"lake": rep["event_lake"], "date": rep["event_date"]},
        "outputs_updated": {
            "models": _mtime(os.path.join(MODEL_OUT, "anomaly_scores_all_lakes.csv")),
            "evaluation": _mtime(os.path.join(EVAL_OUT, "evaluation_report.json")),
        },
    }


@app.get("/api/watchlist")
def watchlist():
    wl = _csv(MODEL_OUT, "watchlist_latest.csv")
    # assessed lakes ranked by risk; abstaining lakes last, never mixed in as "low"
    wl["_abst"] = (wl["status"] == "cannot_assess").astype(int)
    wl = wl.sort_values(["_abst", "risk_score"], ascending=[True, False]).drop(columns="_abst")
    return _records(wl)


@app.get("/api/lakes")
def lakes():
    s = scores()
    g = s.groupby("lake")
    out = pd.DataFrame({
        "windows": g.size(),
        "assessed_pct": g["status"].apply(lambda x: round(100 * (x == "assessed").mean(), 1)),
        "mean_risk": g["risk_score"].mean().round(3),
        "max_risk": g["risk_score"].max().round(3),
        "high_windows": g["band"].apply(lambda x: int((x == "high").sum())),
    }).reset_index()
    dem = pd.read_csv(os.path.join(DATA, "dem_static.csv"))
    return _records(out.merge(dem, on="lake", how="left"))


@app.get("/api/lakes/{lake}/scores")
def lake_scores(lake: str):
    s = scores()
    d = s[s["lake"] == lake]
    if d.empty:
        raise HTTPException(404, f"unknown lake: {lake}")
    return _records(d)


# ---------- triage board (all lakes x all windows in one payload) ----------

REGION = {
    "Himachal Pradesh": ["chandratal", "gepang_gath", "ndma0", "ndma4", "samudra_tapu", "sccc_"],
    "Sikkim": ["changsang", "cwc_sk", "gurudongmar", "khangchung", "khecheopalri", "shako_cho",
               "south_lhonak", "tso_lhamo"],
    "Ladakh": ["cwc_jk", "shaushar", "suru_glacial"],
    "Jammu and Kashmir": ["kausar_nag", "mundiksar"],
    "Uttarakhand": ["basudhara", "satopanth"],
}
REGIONAL_SHARE = 0.40          # >= 40 % of assessed lakes at/above Concern at once = regional signal
TIERS = ["clear", "watch", "concern", "high", "regional", "cannot_assess"]


def region_of(lake):
    for region, keys in REGION.items():
        if any(lake.startswith(k) for k in keys):
            return region
    return "Other"


def nice(lake):
    return lake.replace("_", " ").title()


def fetch_info():
    """Result of the last data fetch (data/update_log.json), or None if the updater has never run."""
    p = os.path.join(DATA, "update_log.json")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        log = json.load(f)
    failed = [{"lake": k, "error": v.get("error", "")} for k, v in log.get("lakes", {}).items()
              if v.get("status") in ("failed", "no_coordinates")]
    return {"finished": log.get("finished"), "mode": log.get("mode"), "summary": log.get("summary", {}),
            "last_finished_window": log.get("last_finished_window"), "failed": failed}


def lake_coords():
    """Seed coordinates per lake from data/lake_coordinates.csv (None where unknown)."""
    p = os.path.join(DATA, "lake_coordinates.csv")
    if not os.path.exists(p):
        return {}
    c = pd.read_csv(p)
    out = {}
    for r in c.to_dict("records"):
        ok = pd.notna(r["lon"]) and pd.notna(r["lat"])
        out[r["lake"]] = {"lon": float(r["lon"]) if ok else None, "lat": float(r["lat"]) if ok else None,
                          "half_km": None if pd.isna(r["half_km"]) else float(r["half_km"]),
                          "tile": None if pd.isna(r["s2_tile"]) else str(r["s2_tile"])}
    return out


@app.get("/api/board")
def board():
    """Everything the triage board needs, computed once here so the browser only draws.

    Tier rules (thresholds come from models/outputs/experiment_log.json):
      cannot_assess  no valid assessment (never shown as clear)
      high           risk >= high (0.85)
      concern        risk >= concern (0.70)
      watch          risk >= watch (0.50)
      clear          risk below watch
      regional       high/concern lake in a window where >= 40 % of assessed lakes are
                     at/above Concern at once, i.e. a seasonal or regional signal, discounted
    """
    s = scores()
    coords = lake_coords()
    th = _json(MODEL_OUT, "experiment_log.json")["thresholds"]
    rep = _json(EVAL_OUT, "evaluation_report.json")
    has_data = s[s["status"] == "assessed"].groupby("date").size()
    last = has_data.index.max()
    s = s[s["date"] <= last]
    dates = sorted(s["date"].unique())
    lakes = sorted(s["lake"].unique(), key=lambda l: (region_of(l), l))
    risk = s.pivot(index="lake", columns="date", values="risk_score").reindex(lakes)[dates]
    stat = s.pivot(index="lake", columns="date", values="status").reindex(lakes)[dates]
    obs = s.pivot(index="lake", columns="date", values="observability").reindex(lakes)[dates]
    drv = s.pivot(index="lake", columns="date", values="driver").reindex(lakes)[dates]
    why = s.pivot(index="lake", columns="date", values="reason").reindex(lakes)[dates]
    ok = (stat == "assessed") & risk.notna()
    n_ok = ok.sum()
    share_watch = ((risk >= th["watch"]) & ok).sum() / n_ok.replace(0, np.nan)
    share_conc = ((risk >= th["concern"]) & ok).sum() / n_ok.replace(0, np.nan)
    regional_win = (share_conc >= REGIONAL_SHARE) & (n_ok >= 10)
    median = risk.where(ok).median()

    code = np.zeros(risk.shape, dtype=int)
    r = risk.to_numpy()
    code[(r >= th["watch"])] = 1
    code[(r >= th["concern"])] = 2
    code[(r >= th["high"])] = 3
    reg = (code >= 2) & regional_win.to_numpy()[None, :]
    code[reg] = 4
    code[~ok.to_numpy()] = 5

    def grid(df, nd=None):
        a = df.astype(object).where(df.notna(), None)
        out = a.to_numpy().tolist()
        return [[(round(v, nd) if (nd is not None and v is not None) else v) for v in row] for row in out]

    drivers = sorted({v for v in drv.to_numpy().ravel() if isinstance(v, str)})
    reasons = sorted({v for v in why.to_numpy().ravel() if isinstance(v, str)})
    drv_i = [[(drivers.index(v) if isinstance(v, str) else -1) for v in row] for row in drv.to_numpy().tolist()]
    why_i = [[(reasons.index(v) if isinstance(v, str) else -1) for v in row] for row in why.to_numpy().tolist()]

    # "current" = lakes whose newest assessed window is the board's newest window
    wl = _csv(MODEL_OUT, "watchlist_latest.csv")
    newest = pd.Timestamp(dates[-1])
    n_current = int((pd.to_datetime(wl["date"]) >= newest).sum())
    has_half = n_ok[n_ok >= len(lakes) / 2]
    latest_idx = dates.index(has_half.index.max()) if len(has_half) else len(dates) - 1
    window_end = newest + pd.Timedelta(days=9)
    days_behind = max(0, (pd.Timestamp.now().normalize() - window_end).days)
    feed = os.path.join(MODEL_OUT, "anomaly_scores_all_lakes.csv")

    return {
        "dates": [pd.Timestamp(d).date().isoformat() for d in dates],
        "latest_idx": int(latest_idx),
        "lakes": [{"id": l, "name": nice(l), "region": region_of(l), **coords.get(l, {})} for l in lakes],
        "risk": grid(risk, 3), "obs": grid(obs, 2), "code": code.tolist(),
        "driver": drv_i, "reason": why_i, "drivers": drivers, "reasons": reasons,
        "share_watch": [None if pd.isna(v) else round(float(v), 3) for v in share_watch],
        "share_concern": [None if pd.isna(v) else round(float(v), 3) for v in share_conc],
        "median": [None if pd.isna(v) else round(float(v), 3) for v in median],
        "assessed": n_ok.astype(int).tolist(),
        "tiers": TIERS, "thresholds": th, "regional_share": REGIONAL_SHARE,
        "event": {"lake": rep["event_lake"], "date": rep["event_date"]},
        "meta": {
            "n_lakes": len(lakes), "n_windows": len(dates), "newest_window": pd.Timestamp(newest).date().isoformat(),
            "newest_window_end": window_end.date().isoformat(), "n_current": n_current,
            "n_behind": len(lakes) - n_current, "days_behind": int(days_behind),
            "learned_from": f"{pd.Timestamp(dates[0]).year}-2024",
            "refreshed": _mtime(feed),
            "fetch": fetch_info(),
            "model": (lambda lg: lg["detector"].replace("_", " ") + " " + lg.get("model_version", ""))(_json(MODEL_OUT, "experiment_log.json")).strip(),
        },
    }


# ---------- data stage (Student A) ----------

@app.get("/api/data/overview")
def data_overview():
    rows = []
    for f in sorted(os.listdir(LAKES)):
        if not f.endswith("_windows.csv"):
            continue
        df = pd.read_csv(os.path.join(LAKES, f))
        row = {"lake": f.replace("_windows.csv", ""), "windows": len(df),
               "start": df["window"].min(), "end": df["window"].max(),
               "mean_observability": round(df["observability"].mean(), 3)}
        for c in SIGNALS:
            row[f"{c}_coverage_pct"] = round(100 * df[c].notna().mean(), 1)
        rows.append(row)
    ov = pd.DataFrame(rows)
    dem = pd.read_csv(os.path.join(DATA, "dem_static.csv"))
    totals = {
        "lakes": len(ov),
        "windows": int(ov["windows"].sum()),
        "dem_lakes": len(dem),
        "signal_coverage_pct": {c: round(ov[f"{c}_coverage_pct"].mean(), 1) for c in SIGNALS},
    }
    return {"totals": totals, "lakes": _records(ov), "dem": _records(dem)}


@app.get("/api/data/{lake}")
def data_lake(lake: str):
    """Raw transformed 10-day windows for one lake + the per-signal anomaly scores."""
    w = lake_windows(lake)
    ps_path = os.path.join(MODEL_OUT, "per_signal_cache", "ps_isolation_forest.csv")
    ps = pd.read_csv(ps_path)
    ps = ps[ps["lake"] == lake].drop(columns=["lake", "year"], errors="ignore")
    desc = w[SIGNALS + ["observability"]].describe().T.round(4).reset_index()
    desc = desc.rename(columns={"index": "signal"})
    return {"windows": _records(w), "per_signal": _records(ps), "stats": _records(desc)}


# ---------- modelling stage (Student B) ----------

@app.get("/api/model")
def model():
    log = _json(MODEL_OUT, "experiment_log.json")
    s = scores()
    a = s[s["status"] == "assessed"]
    hist, edges = np.histogram(a["risk_score"].dropna(), bins=40, range=(0, 1))
    by_year = (s.assign(year=s["date"].dt.year)
                 .groupby(["year", "band"]).size().unstack(fill_value=0)
                 .reindex(columns=BANDS, fill_value=0).reset_index())
    drivers = (a["driver"].fillna("(no single driver)").str.split(" · ").explode()
                 .value_counts().head(10).rename_axis("driver").reset_index(name="count"))
    return {
        "config": {k: v for k, v in log.items() if k not in ("detector_comparison", "ablation")},
        "detector_comparison": _records(_csv(MODEL_OUT, "detector_comparison.csv")),
        "v1_vs_v2": _records(_csv(MODEL_OUT, "v1_vs_v2.csv")) if os.path.exists(os.path.join(MODEL_OUT, "v1_vs_v2.csv")) else [],
        "ablation": _records(_csv(MODEL_OUT, "ablation_results.csv")),
        "band_counts": s["band"].value_counts().reindex(BANDS, fill_value=0).to_dict(),
        "risk_histogram": {"counts": hist.tolist(), "edges": edges.round(3).tolist()},
        "bands_by_year": _records(by_year),
        "top_drivers": _records(drivers),
        "abstain_reasons": (s["reason"].dropna().value_counts()
                            .rename_axis("reason").reset_index(name="count")
                            .pipe(_records)),
        "sikkim_2023": _records(_csv(MODEL_OUT, "sikkim_2023_southlhonak.csv")),
    }


# ---------- evaluation stage (Student C) ----------

@app.get("/api/evaluation")
def evaluation():
    rep = _json(EVAL_OUT, "evaluation_report.json")
    return {
        "report": rep,
        "threshold_sweep": _records(_csv(EVAL_OUT, "threshold_sweep.csv")),
        "sikkim_trajectory": _records(_csv(EVAL_OUT, "sikkim_trajectory_2023.csv")),
        "failure_cases": _records(_csv(EVAL_OUT, "failure_cases.csv")),
        "leak_and_generalisation": _json(EVAL_OUT, "leak_and_generalisation.json"),
    }


# ---------- testing: run the real harness on demand ----------

@app.post("/api/tests/run")
def run_tests():
    """Runs evaluation/test_evaluation.py with pytest and returns per-test results."""
    with tempfile.TemporaryDirectory() as tmp:
        xml_path = os.path.join(tmp, "junit.xml")
        t0 = time.time()
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "test_evaluation.py", "-q",
             f"--junitxml={xml_path}", "-p", "no:cacheprovider"],
            cwd=os.path.join(ROOT, "evaluation"), capture_output=True, text=True, timeout=300)
        elapsed = round(time.time() - t0, 2)
        cases = []
        if os.path.exists(xml_path):
            for tc in ET.parse(xml_path).getroot().iter("testcase"):
                # Element truthiness depends on children, so test for None explicitly
                failure = tc.find("failure")
                if failure is None:
                    failure = tc.find("error")
                skipped = tc.find("skipped")
                cases.append({
                    "name": tc.get("name"),
                    "time": float(tc.get("time", 0)),
                    "outcome": "failed" if failure is not None
                               else "skipped" if skipped is not None else "passed",
                    "message": failure.get("message") if failure is not None else None,
                })
    return {"returncode": proc.returncode, "elapsed_s": elapsed, "cases": cases,
            "passed": sum(c["outcome"] == "passed" for c in cases),
            "failed": sum(c["outcome"] == "failed" for c in cases),
            "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-2000:]}


@app.post("/api/pipeline/evaluate")
def rerun_evaluation():
    """Re-runs stage C (metrics + leak/generalisation) against the current model outputs."""
    logs = []
    for script in ("gews_evaluation.py", "gews_leak_gen.py"):
        p = subprocess.run([sys.executable, script], cwd=os.path.join(ROOT, "evaluation"),
                           capture_output=True, text=True, timeout=600)
        logs.append({"script": script, "returncode": p.returncode,
                     "output": (p.stdout + p.stderr)[-4000:]})
        if p.returncode != 0:
            return JSONResponse({"ok": False, "logs": logs}, status_code=500)
    return {"ok": True, "logs": logs}


# ---------- keep the whole system current: fetch -> re-score -> re-evaluate ----------

_UPDATE = {"proc": None, "state": "idle", "started": None, "finished": None, "returncode": None,
           "log": os.path.join(DATA, "update_run.log"), "skip_fetch": False}
_UPDATE_LOCK = threading.Lock()


def _watch(proc, logf):
    rc = proc.wait()
    logf.close()
    with _UPDATE_LOCK:
        _UPDATE.update(state="done" if rc == 0 else "failed", returncode=rc,
                       finished=time.strftime("%Y-%m-%d %H:%M:%S"), proc=None)


@app.post("/api/pipeline/update")
def start_update(skip_fetch: bool = False):
    """Runs `python run_pipeline.py --update` in the background (fetch new windows, re-score, re-evaluate).
    Poll /api/pipeline/update/status. Only one update can run at a time."""
    with _UPDATE_LOCK:
        if _UPDATE["state"] == "running":
            raise HTTPException(409, "an update is already running")
        cmd = [sys.executable, "-u", "run_pipeline.py", "--update"] + (["--skip-fetch"] if skip_fetch else [])
        logf = open(_UPDATE["log"], "w")
        proc = subprocess.Popen(cmd, cwd=ROOT, stdout=logf, stderr=subprocess.STDOUT, text=True)
        _UPDATE.update(proc=proc, state="running", started=time.strftime("%Y-%m-%d %H:%M:%S"), finished=None,
                       returncode=None, skip_fetch=skip_fetch)
    threading.Thread(target=_watch, args=(proc, logf), daemon=True).start()
    return {"ok": True, "state": "running"}


@app.get("/api/pipeline/update/status")
def update_status():
    tail, stage = [], None
    if os.path.exists(_UPDATE["log"]):
        with open(_UPDATE["log"], errors="replace") as f:
            lines = f.read().splitlines()
        tail = lines[-25:]
        for ln in lines:
            if "[stage]" in ln:
                stage = ln.split("[stage]", 1)[1].strip()
    with _UPDATE_LOCK:
        st = {k: _UPDATE[k] for k in ("state", "started", "finished", "returncode", "skip_fetch")}
    return {**st, "stage": stage, "tail": tail, "fetch": fetch_info()}


# ---------- static: chart images written by the pipeline + the frontend ----------

@app.get("/api/images/{name}")
def image(name: str):
    allowed = {
        "evaluation_dashboard": os.path.join(EVAL_OUT, "evaluation_dashboard.png"),
        "south_lhonak_2023": os.path.join(MODEL_OUT, "south_lhonak_2023.png"),
        "watch_console": os.path.join(ROOT, "dashboard", "watch_console_screenshot.png"),
    }
    if name not in allowed or not os.path.exists(allowed[name]):
        raise HTTPException(404, "no such image")
    return FileResponse(allowed[name])


@app.get("/vendor/plotly.min.js")
def plotly_js():
    # serve the copy bundled with the plotly pip package, so the console works offline
    import plotly
    return FileResponse(os.path.join(os.path.dirname(plotly.__file__), "package_data", "plotly.min.js"),
                        media_type="application/javascript")


app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
