#!/usr/bin/env python
"""
GEWS data updater: bring every lake's window table up to the newest FINISHED 10-day window.

    python collect/gews_collect.py --verify --lake south_lhonak   # 1. check it reproduces your committed numbers
    python collect/gews_collect.py --dry-run                      # 2. see what would change, write nothing
    python collect/gews_collect.py                                # 3. update all lakes
    python collect/gews_collect.py --lake kausar_nag --lake tso_lhamo

For each lake it (a) finds the newest window that already has data, (b) fetches only the scenes from two
windows earlier up to the last finished window, (c) rebuilds those windows with the notebook's rules and
(d) merges them into data/lake_data/<lake>_windows.csv. Rows for older windows are never rewritten, so the
history the model was validated on cannot drift. Raw per-scene measurements are cached in data/raw_cache/ so
a re-run (or a crash halfway) never downloads a scene twice. Every run writes data/update_log.json.

A window is "finished" once its last day plus --margin-days (default 3) has passed. Sentinel and MODIS scenes appear
a few days after acquisition, so the newest window is usually thin; the next run re-fetches the last two windows and
fills it in. Windows are the notebook's: Jan 1 + 10 d steps, 36 per year.
"""
import argparse
import json
import os
import sys
import time
import traceback

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
LAKE_DIR = os.path.join(DATA, "lake_data")
CACHE_DIR = os.path.join(DATA, "raw_cache")
LOG_PATH = os.path.join(DATA, "update_log.json")

FEATURES = ["lake_area_km2", "lake_area_min_km2", "vv_db", "sar_backscatter_change",
            "thermal_index", "velocity_trend", "velocity_accel"]
MAX_CLOUD, MIN_VALID, MIN_LST_VALID = 0.5, 0.9, 0.5      # notebook cell 9
MIN_AREA_FRAC = 0.10             # notebook: MIN_AREA 0.15 km2 against a 1.47 km2 summer median (~10 %)
REWIND_WINDOWS = 2               # re-fetch this many windows before the newest one with data (late scenes)
VELOCITY_MAX_AGE_DAYS = 30       # ITS_LIVE changes slowly and the pull is heavy: refresh monthly


# =============================================================== the 10-day grid ===
def window_of(ts):
    """Start of the 10-day window containing ts (notebook to_window; the last slot is 15-16 days)."""
    ts = pd.Timestamp(ts).normalize()
    slot = min((ts.dayofyear - 1) // 10, 35)
    return pd.Timestamp(ts.year, 1, 1) + pd.Timedelta(days=10 * slot)


def window_end(start):
    start = pd.Timestamp(start)
    slot = (start.dayofyear - 1) // 10
    return pd.Timestamp(start.year, 12, 31) if slot >= 35 else start + pd.Timedelta(days=9)


def window_grid(first_year, last_year):
    return pd.DatetimeIndex([pd.Timestamp(y, 1, 1) + pd.Timedelta(days=10 * s)
                             for y in range(first_year, last_year + 1) for s in range(36)], name="window")


def last_finished_window(today, margin_days=3):
    """Newest window whose last day + margin has passed."""
    today = pd.Timestamp(today).normalize()
    w = window_of(today)
    while window_end(w) + pd.Timedelta(days=margin_days) > today:
        w = window_of(w - pd.Timedelta(days=1))
    return w


# ================================================================ window files ===
class WindowFile:
    """A lake's CSV, kept as text so untouched rows stay byte-identical (dates, decimals, line endings)."""

    def __init__(self, path):
        self.path = path
        with open(path, newline="") as fh:
            raw = fh.read()
        self.eol = "\r\n" if "\r\n" in raw else "\n"
        lines = raw.split(self.eol)
        self.trailing = lines[-1] == ""
        if self.trailing:
            lines = lines[:-1]
        self.header, self.lines = lines[0], lines[1:]
        self.cols = self.header.split(",")[1:]
        keys = [l.split(",", 1)[0] for l in self.lines]
        self.iso = (not keys) or "-" in keys[0]
        self.index = {pd.Timestamp(k): i for i, k in enumerate(pd.to_datetime(keys, format="mixed"))} if keys else {}

    def key(self, ts):
        ts = pd.Timestamp(ts)
        return ts.strftime("%Y-%m-%d") if self.iso else f"{ts.month}/{ts.day}/{ts.year}"

    def frame(self):
        d = pd.read_csv(self.path)
        d.index = pd.to_datetime(d.pop("window"), format="mixed")
        d.index.name = "window"
        return d

    @staticmethod
    def fmt(v):
        if v is None or (isinstance(v, float) and np.isnan(v)) or pd.isna(v):
            return ""
        return repr(round(float(v), 10))

    def line(self, ts, row, old=None):
        """CSV text for one window. With `old`, fields whose numeric value is unchanged keep their exact
        original text, so a refresh never rewrites digits it did not change."""
        fields = [self.fmt(row.get(c)) for c in self.cols]
        if old is not None:
            prev = old.split(",")[1:]
            if len(prev) == len(fields):
                for i, (p, n) in enumerate(zip(prev, fields)):
                    try:
                        same = (p == "" and n == "") or (p != "" and n != "" and abs(float(p) - float(n)) < 1e-9)
                    except ValueError:
                        same = False
                    if same:
                        fields[i] = p
                return ",".join([old.split(",", 1)[0]] + fields)
        return ",".join([self.key(ts)] + fields)

    def write_rows(self, frame, windows):
        """Set the given windows from `frame` (appending any that are missing). Returns how many lines changed."""
        changed = 0
        for w in windows:
            new = self.line(w, frame.loc[w], self.lines[self.index[w]] if w in self.index else None)
            if w in self.index:
                if self.lines[self.index[w]] != new:
                    self.lines[self.index[w]] = new; changed += 1
            else:
                self.lines.append(new); self.index[w] = len(self.lines) - 1; changed += 1
        order = sorted(self.index, key=lambda t: t)           # keep the file in date order
        if [self.index[t] for t in order] != list(range(len(order))):
            by_ts = {t: self.lines[self.index[t]] for t in order}
            self.lines = [by_ts[t] for t in order]
            self.index = {t: i for i, t in enumerate(order)}
        text = self.eol.join([self.header] + self.lines) + (self.eol if self.trailing else "")
        tmp = self.path + ".tmp"
        with open(tmp, "w", newline="") as fh:
            fh.write(text)
        os.replace(tmp, self.path)
        return changed


# ================================================================ build windows ===
def derive_min_area(frame):
    """Smallest plausible lake reading: 10 % of the lake's own summer median (history only)."""
    summer = frame.loc[frame.index.month.isin([7, 8, 9]), "lake_area_km2"].dropna()
    return float(summer.median() * MIN_AREA_FRAC) if len(summer) >= 3 else 0.0


def build_window_values(wins, s2, s1, lst, vel, min_area):
    """Notebook cell 9, restricted to `wins`. Returns window-indexed frame incl. n_s2 / n_s1 / n_lst."""
    df = pd.DataFrame(index=pd.DatetimeIndex(wins, name="window"))
    first, last = df.index.min(), window_end(df.index.max())

    def in_range(t):
        t = t.copy(); t["window"] = t["date"].map(window_of)
        return t[(t["date"] >= first) & (t["date"] <= last)]

    if s2 is not None and len(s2):
        s2 = in_range(s2.assign(date=pd.to_datetime(s2["date"])))
        s2 = s2[(s2["cloud_frac"] <= MAX_CLOUD) & (s2["valid_frac"] >= MIN_VALID) & (s2["area_km2"] >= min_area)]
        df = df.join(s2.groupby("window").agg(lake_area_km2=("area_km2", "median"),
                                              lake_area_min_km2=("area_km2", "min"), n_s2=("area_km2", "count")))
    if s1 is not None and len(s1):
        s1 = in_range(s1.assign(date=pd.to_datetime(s1["date"])))
        df = df.join(s1.groupby("window").agg(vv_db=("vv_db", "median"), n_s1=("vv_db", "count")))
    if lst is not None and len(lst):
        lst = in_range(lst.assign(date=pd.to_datetime(lst["date"])))
        lst = lst[lst["valid_frac"] >= MIN_LST_VALID].copy()
        lst["dd"] = lst["lst_c"].clip(lower=0)
        g = lst.groupby("window").agg(pos_mean=("dd", "mean"), n_lst=("lst_c", "count"))
        g["thermal_index"] = g["pos_mean"] * 10
        df = df.join(g.drop(columns="pos_mean"))
    for c in ["lake_area_km2", "lake_area_min_km2", "n_s2", "vv_db", "n_s1", "thermal_index", "n_lst"]:
        if c not in df.columns:
            df[c] = np.nan
    return df


def velocity_by_year(vel, years):
    """v per year, then differenced twice (notebook): velocity_trend, velocity_accel."""
    if vel is None or not len(vel):
        return None
    v = vel.set_index("year")["v"].reindex(range(min(min(years), int(vel["year"].min())), max(years) + 1))
    out = pd.DataFrame({"v": v})
    out["velocity_trend"] = out["v"].diff()
    out["velocity_accel"] = out["velocity_trend"].diff()
    return out


def observability(n_s2, n_s1, n_lst, v_ok):
    f = lambda x: (pd.Series(x).fillna(0) > 0).astype(float)
    return 0.40 * f(n_s2) + 0.30 * f(n_s1) + 0.15 * f(n_lst) + 0.15 * pd.Series(v_ok).astype(float)


def has_evidence(frame):
    return frame["lake_area_km2"].notna() | frame["vv_db"].notna()


def merge_windows(committed, new, rebuild, last_data_win, vel_years, today_year, vel_until=None):
    """Combine committed rows with freshly built ones. Returns (merged frame, windows that were set).

    * windows at or before the newest committed data are 'rewound': replaced only if the new pull saw scenes
    * later windows are filled from the new pull
    * radar change is recomputed from the merged radar level, so it is continuous across the seam
    * velocity columns of the CURRENT year's FINISHED windows are refreshed (only those two columns) when a fresh
      ITS_LIVE table is supplied; unfinished windows are left empty until they finish
    """
    out = committed.copy()
    for c in FEATURES + ["observability"]:
        if c not in out.columns:
            out[c] = np.nan
    touched = []
    for w in rebuild:
        if w not in out.index:
            out.loc[w] = np.nan
        seen = bool(pd.Series([new.loc[w, "n_s2"], new.loc[w, "n_s1"], new.loc[w, "n_lst"]]).fillna(0).gt(0).any())
        if w <= last_data_win and not seen:
            continue                                       # keep the committed values
        for c in ["lake_area_km2", "lake_area_min_km2", "vv_db", "thermal_index"]:
            out.loc[w, c] = new.loc[w, c]
        touched.append(w)
    out = out.sort_index()
    # radar change continuity
    diff = out["vv_db"].diff()
    for w in touched:
        out.loc[w, "sar_backscatter_change"] = diff.loc[w]
    # observability of the windows that were rebuilt from scenes
    for w in touched:
        if vel_years is not None and w.year in vel_years.index:
            v_ok = bool(pd.notna(vel_years.loc[w.year, "v"]))
        else:
            v_ok = bool(pd.notna(out.loc[w, "velocity_trend"]))          # no fresh table: infer from what is there
        n = new.loc[w]
        out.loc[w, "observability"] = float(observability([n["n_s2"]], [n["n_s1"]], [n["n_lst"]], [v_ok]).iloc[0])
    # velocity of the CURRENT year changes as new image pairs arrive: refresh just those two columns,
    # leaving every other value (including observability) of those older windows untouched
    vel_only = []
    if vel_years is not None and today_year in vel_years.index:
        v_new = bool(pd.notna(vel_years.loc[today_year, "v"]))
        cur = out.index[(out.index.year == today_year) & ((out.index <= vel_until) if vel_until is not None else True)]
        for w in cur:
            v_old = bool(pd.notna(out.loc[w, "velocity_trend"]))                 # what the row had before
            out.loc[w, "velocity_trend"] = vel_years.loc[today_year, "velocity_trend"]
            out.loc[w, "velocity_accel"] = vel_years.loc[today_year, "velocity_accel"]
            if w not in touched and v_new != v_old and pd.notna(out.loc[w, "observability"]):
                # keep the notebook formula true: velocity is worth 0.15 of observability
                out.loc[w, "observability"] = round(float(out.loc[w, "observability"]) + (0.15 if v_new else -0.15), 10)
            vel_only.append(w)
    return out, sorted(set(touched) | set(vel_only))


# ================================================================== raw caches ===
class RawCache:
    def __init__(self, lake, root=CACHE_DIR):
        os.makedirs(root, exist_ok=True)
        self.lake, self.root = lake, root

    def p(self, kind, ext="csv"):
        return os.path.join(self.root, f"{self.lake}_{kind}.{ext}")

    def read(self, kind):
        p = self.p(kind)
        return pd.read_csv(p) if os.path.exists(p) and os.path.getsize(p) > 0 else None

    def append(self, kind, rows):
        if rows is None or not len(rows):
            return
        old = self.read(kind)
        new = pd.concat([old, rows], ignore_index=True) if old is not None else rows
        new = new.drop_duplicates("scene_id", keep="last") if "scene_id" in new else new
        new.to_csv(self.p(kind), index=False)

    def ids(self, kind):
        d = self.read(kind)
        return set(d["scene_id"]) if d is not None else set()

    def meta(self):
        p = self.p("meta", "json")
        return json.load(open(p)) if os.path.exists(p) else {}

    def save_meta(self, m):
        json.dump(m, open(self.p("meta", "json"), "w"), indent=2, default=str)


# ================================================================= one lake ===
def update_lake(cfg, source, today, margin_days=3, dry_run=False, refresh_velocity=False,
                lake_dir=LAKE_DIR, cache_root=CACHE_DIR, log=print):
    path = os.path.join(lake_dir, f"{cfg.lake}_windows.csv")
    wf = WindowFile(path)
    committed = wf.frame()
    ev = has_evidence(committed)
    last_data = committed.index[ev.values].max() if ev.any() else None
    fin = last_finished_window(today, margin_days)
    first_grid = committed.index.min()
    since = first_grid if last_data is None else max(first_grid, last_data - pd.Timedelta(days=10 * REWIND_WINDOWS))
    rebuild = [w for w in window_grid(first_grid.year, today.year) if since <= w <= fin]
    res = {"lake": cfg.lake, "newest_before": None if last_data is None else last_data.date().isoformat(),
           "last_finished_window": fin.date().isoformat()}
    if not rebuild:
        return {**res, "status": "up_to_date", "windows_set": 0, "newest_after": res["newest_before"]}

    start, end = since.date().isoformat(), window_end(fin).date().isoformat()
    cache = RawCache(cfg.lake, cache_root)
    meta = cache.meta()
    full_start = first_grid.date().isoformat()
    if "tile" not in meta:
        meta["tile"] = source.resolve_tile(cfg, full_start, end)
    if "s1_track" not in meta:
        meta["s1_track"] = source.s1_track(cfg, full_start, end)
    cfg.tile = meta["tile"]
    log(f"  {cfg.lake}: {start} -> {end} | tile {meta['tile']} | radar track {meta['s1_track']}")
    cache.append("s2", source.s2(cfg, start, end, cache.ids("s2")))
    cache.append("s1", source.s1(cfg, start, end, cache.ids("s1"), meta["s1_track"]))
    cache.append("lst", source.lst(cfg, start, end, cache.ids("lst")))

    vel_years = None
    age = (time_now() - pd.Timestamp(meta["vel_fetched"])).days if meta.get("vel_fetched") else None
    if refresh_velocity or age is None or age >= VELOCITY_MAX_AGE_DAYS:
        try:
            vel = source.velocity(cfg, first_grid.year, today.year)
            vel.to_csv(cache.p("vel"), index=False)
            meta["vel_fetched"] = time_now().isoformat()
        except Exception as e:                                # velocity is optional: keep what is committed
            log(f"  {cfg.lake}: velocity refresh failed ({type(e).__name__}: {e}); keeping committed velocity")
    vel = cache.read("vel")
    if vel is not None:
        vel_years = velocity_by_year(vel, [first_grid.year, today.year])
    cache.save_meta(meta)

    min_area = derive_min_area(committed)
    new = build_window_values(rebuild, cache.read("s2"), cache.read("s1"), cache.read("lst"), vel, min_area)
    merged, touched = merge_windows(committed, new, rebuild, last_data if last_data is not None else since - pd.Timedelta(days=1),
                                    vel_years, today.year, vel_until=fin)
    after = merged.index[has_evidence(merged).values].max() if has_evidence(merged).any() else None
    changed = 0 if dry_run else wf.write_rows(merged, touched)
    return {**res, "status": "dry_run" if dry_run else "ok", "windows_set": len(touched), "lines_changed": changed,
            "newest_after": None if after is None else after.date().isoformat(), "min_area_km2": round(min_area, 4)}


def time_now():
    return pd.Timestamp.now().tz_localize(None)


# ================================================================== verify ===
def verify_lake(cfg, source, today, n_windows=6, margin_days=3, lake_dir=LAKE_DIR, cache_root=CACHE_DIR, log=print):
    """Re-derive the last windows that already have data and compare with the committed CSV. Writes no CSV."""
    committed = WindowFile(os.path.join(lake_dir, f"{cfg.lake}_windows.csv")).frame()
    fin = last_finished_window(today, margin_days)
    done = committed.index[has_evidence(committed).values]
    done = done[done <= fin][-n_windows:]
    if not len(done):
        return {"lake": cfg.lake, "verdict": "no committed data to compare"}
    cache = RawCache(cfg.lake, cache_root)
    meta = cache.meta()
    start, end = done.min().date().isoformat(), window_end(done.max()).date().isoformat()
    full_start = committed.index.min().date().isoformat()
    meta.setdefault("tile", source.resolve_tile(cfg, full_start, end))
    meta.setdefault("s1_track", source.s1_track(cfg, full_start, end))
    cfg.tile = meta["tile"]
    cache.append("s2", source.s2(cfg, start, end, cache.ids("s2")))
    cache.append("s1", source.s1(cfg, start, end, cache.ids("s1"), meta["s1_track"]))
    cache.append("lst", source.lst(cfg, start, end, cache.ids("lst")))
    cache.save_meta(meta)
    new = build_window_values(list(done), cache.read("s2"), cache.read("s1"), cache.read("lst"), None, derive_min_area(committed))
    rows, ok_flags = [], []
    for col, tol in [("lake_area_km2", 0.15), ("vv_db", 0.5), ("thermal_index", 0.15)]:
        a, b = committed.loc[done, col], new[col].reindex(done)
        both = a.notna() & b.notna()
        if both.any():
            if col == "vv_db":
                err = float((a[both] - b[both]).abs().median())
            else:
                err = float(((a[both] - b[both]).abs() / a[both].abs().clip(lower=1e-6)).median())
            ok = err <= tol
        else:
            err, ok = float("nan"), False
        rows.append({"column": col, "windows_compared": int(both.sum()), "median_error": round(err, 4),
                     "tolerance": tol, "ok": ok})
        ok_flags.append(ok)
    return {"lake": cfg.lake, "compared_windows": [d.date().isoformat() for d in done], "checks": rows,
            "verdict": "REPRODUCES committed values" if all(ok_flags) else "DIFFERS: see checks (do not update this lake yet)"}


# ====================================================================== CLI ===
def write_log(entry):
    json.dump(entry, open(LOG_PATH, "w"), indent=2, default=str)


def main(argv=None, source=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lake", action="append", help="lake id (repeatable); default: every lake with coordinates")
    ap.add_argument("--dry-run", action="store_true", help="fetch and report, write no CSV")
    ap.add_argument("--verify", action="store_true", help="re-derive recent committed windows and compare; writes no CSV")
    ap.add_argument("--margin-days", type=int, default=3, help="days after a window ends before it counts as finished")
    ap.add_argument("--refresh-velocity", action="store_true", help="re-pull ITS_LIVE even if the cache is recent")
    ap.add_argument("--today", help="pretend today is YYYY-MM-DD (testing)")
    ap.add_argument("--workers", type=int, default=4, help="parallel scene reads per lake")
    a = ap.parse_args(argv)

    sys.path.insert(0, HERE)
    import sources
    today = pd.Timestamp(a.today).normalize() if a.today else pd.Timestamp.today().normalize()
    cfgs, no_coords = sources.load_lake_configs(os.path.join(DATA, "lake_coordinates.csv"))
    names = a.lake or (sorted(cfgs) + sorted(no_coords))      # lakes without coordinates are reported, not hidden
    unknown = [n for n in names if n not in cfgs and n not in no_coords]
    if unknown:
        sys.exit(f"unknown lake(s): {unknown}")
    if source is None:
        try:
            source = sources.PlanetaryComputerSource(workers=a.workers)
        except ImportError as e:
            print(f"missing package ({e}). Install the collection requirements: pip install -r requirements-collect.txt")
            sys.exit(2)

    fin = last_finished_window(today, a.margin_days)
    print(f"today {today.date()} | newest finished window starts {fin.date()} (ends {window_end(fin).date()}, margin {a.margin_days} d)")
    run = {"started": time_now().isoformat(), "today": today.date().isoformat(), "mode": "verify" if a.verify else "dry_run" if a.dry_run else "update",
           "last_finished_window": fin.date().isoformat(), "lakes": {}}
    for n in names:
        t0 = time.time()
        if n in no_coords:
            run["lakes"][n] = {"status": "no_coordinates", "error": "no coordinates in data/lake_coordinates.csv"}
            print(f"  {n}: skipped (no coordinates)"); continue
        try:
            r = (verify_lake(cfgs[n], source, today, margin_days=a.margin_days) if a.verify else
                 update_lake(cfgs[n], source, today, a.margin_days, a.dry_run, a.refresh_velocity))
            r.setdefault("status", "verified")
        except Exception as e:                                 # one lake failing must not stop the rest
            r = {"status": "failed", "error": f"{type(e).__name__}: {e}"}
            print(f"  {n}: FAILED {r['error']}"); traceback.print_exc(limit=2)
        r["seconds"] = round(time.time() - t0, 1)
        run["lakes"][n] = r
        if a.verify:
            print(json.dumps(r, indent=2, default=str))
        else:
            print(f"  {n}: {r['status']} | windows set {r.get('windows_set', 0)} | newest data {r.get('newest_after')}")
    run["finished"] = time_now().isoformat()
    run["summary"] = {k: sum(1 for v in run["lakes"].values() if v["status"] == k) for k in
                      sorted({v["status"] for v in run["lakes"].values()})}
    if not a.verify and not a.dry_run:
        write_log(run)
    print("summary:", run["summary"])
    return 1 if run["summary"].get("failed") else 0


if __name__ == "__main__":
    sys.exit(main())
