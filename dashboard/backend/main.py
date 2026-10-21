"""
GEWS Watch Console — backend (Student D).

A thin FastAPI layer over the committed pipeline outputs. It never recomputes model scores
itself: every number comes from data/, models/outputs/ or evaluation/outputs/, so a value on
screen can always be traced back to the stage that wrote it.

    uvicorn dashboard.backend.main:app --port 8000      # from the repo root
    python dashboard/run.py                             # same, with a friendlier wrapper
"""
import json, os, subprocess, sys, tempfile, time
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
