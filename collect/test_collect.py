"""Offline tests for the data updater: a fake satellite source stands in for Planetary Computer / ITS_LIVE,
so the window grid, merge rules, idempotence and failure handling are checked without any network."""
import os
import shutil
import sys

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import gews_collect as C
import sources as S

TODAY = pd.Timestamp("2026-10-31")


class FakeSource:
    """Deterministic scenes: S2 every 5 days, S1 every 6, MODIS every 2, velocity per year."""

    def __init__(self, fail_lakes=(), no_velocity=False):
        self.fail, self.no_vel, self.calls = set(fail_lakes), no_velocity, []

    def _dates(self, start, end, step, off):
        """Acquisition dates sit on a fixed calendar (like real scenes), whatever range is asked for."""
        d = pd.date_range("2017-01-01", "2027-12-31", freq=f"{step}D") + pd.Timedelta(days=off)
        return [x for x in d if pd.Timestamp(start) <= x <= pd.Timestamp(end)]

    def _check(self, cfg):
        if cfg.lake in self.fail:
            raise RuntimeError("STAC unreachable")

    def resolve_tile(self, cfg, start, end):
        self._check(cfg); return cfg.tile or "45RXL"

    def s1_track(self, cfg, start, end):
        return ("ascending", 12)

    def s2(self, cfg, start, end, known):
        self._check(cfg); self.calls.append(("s2", cfg.lake, start, end))
        rows = [{"scene_id": f"{cfg.lake}-s2-{d.date()}", "date": str(d.date()), "area_km2": 0.9 + 0.01 * d.month,
                 "area_scl_km2": 0.9, "snow_frac": 0.0, "cloud_frac": 0.1, "valid_frac": 1.0, "baseline": "05.00"}
                for d in self._dates(start, end, 5, 0)]
        return pd.DataFrame([r for r in rows if r["scene_id"] not in known])

    def s1(self, cfg, start, end, known, track):
        rows = [{"scene_id": f"{cfg.lake}-s1-{d.date()}", "date": str(d.date()), "vv_db": -12.0 + 0.1 * d.dayofyear / 10,
                 "vh_db": -20.0, "area_sar_km2": 0.5, "orbit_state": "ascending", "rel_orbit": 12}
                for d in self._dates(start, end, 6, 1)]
        return pd.DataFrame([r for r in rows if r["scene_id"] not in known])

    def lst(self, cfg, start, end, known):
        rows = [{"scene_id": f"{cfg.lake}-lst-{d.date()}", "date": str(d.date()), "lst_c": 5.0, "valid_frac": 1.0}
                for d in self._dates(start, end, 2, 0)]
        return pd.DataFrame([r for r in rows if r["scene_id"] not in known])

    def velocity(self, cfg, y0, y1):
        if self.no_vel:
            raise RuntimeError("ITS_LIVE down")
        return pd.DataFrame({"year": list(range(y0, y1 + 1)), "v": [10.0 + 2 * (y - y0) for y in range(y0, y1 + 1)],
                             "n_pairs": 50})


def cfg_for(lake):
    cfgs, _ = S.load_lake_configs(os.path.join(ROOT, "data", "lake_coordinates.csv"))
    return cfgs[lake]


@pytest.fixture
def workdir(tmp_path):
    """A scratch copy of two real lake files (one ISO dates, one M/D/YYYY) and the coordinates table."""
    lake_dir = tmp_path / "lake_data"; lake_dir.mkdir()
    for lake in ("mundiksar_lake", "south_lhonak"):
        shutil.copy(os.path.join(ROOT, "data", "lake_data", f"{lake}_windows.csv"), lake_dir / f"{lake}_windows.csv")
    shutil.copy(os.path.join(ROOT, "data", "lake_coordinates.csv"), tmp_path / "lake_coordinates.csv")
    return tmp_path


def run_update(workdir, lake, source, today=TODAY, **kw):
    return C.update_lake(cfg_for(lake), source, today, lake_dir=str(workdir / "lake_data"),
                         cache_root=str(workdir / "raw_cache"), log=lambda *a: None, **kw)


def read_lines(path):
    with open(path, newline="") as fh:
        return fh.read().split("\r\n" if "\r\n" in open(path, newline="").read() else "\n")


# ------------------------------------------------------------------ grid ----
def test_every_committed_window_is_on_the_grid():
    for lake in ("mundiksar_lake", "south_lhonak"):
        f = C.WindowFile(os.path.join(ROOT, "data", "lake_data", f"{lake}_windows.csv"))
        for ts in f.index:
            assert C.window_of(ts) == ts


def test_last_slot_of_the_year_is_long_and_finishes_on_dec_31():
    assert C.window_of(pd.Timestamp("2026-12-31")) == pd.Timestamp("2026-12-17")
    assert C.window_end(pd.Timestamp("2026-12-17")) == pd.Timestamp("2026-12-31")
    assert C.window_end(pd.Timestamp("2026-10-18")) == pd.Timestamp("2026-10-27")


@pytest.mark.parametrize("today,expect", [("2026-10-31", "2026-10-18"), ("2026-10-28", "2026-10-08"),
                                          ("2026-11-06", "2026-10-18"), ("2026-11-08", "2026-10-18"), ("2026-11-09", "2026-10-28"),
                                          ("2027-01-02", "2026-12-07")])
def test_newest_finished_window(today, expect):
    assert C.last_finished_window(pd.Timestamp(today), 3) == pd.Timestamp(expect)


def test_window_not_finished_until_margin_has_passed():
    assert C.last_finished_window(pd.Timestamp("2026-10-27"), 3) == pd.Timestamp("2026-10-08")
    assert C.last_finished_window(pd.Timestamp("2026-10-30"), 3) == pd.Timestamp("2026-10-18")


# ------------------------------------------------------------- config / tile ---
def test_tile_normalisation():
    assert S.normalise_tile("45RXL / 45RXM") == "45RXL"
    assert S.normalise_tile("43UFT*") == "43UFT"
    assert S.normalise_tile("44R*") is None and S.normalise_tile("unresolved") is None
    assert S.normalise_tile(float("nan")) is None


def test_lake_without_coordinates_is_reported_not_crashed():
    cfgs, missing = S.load_lake_configs(os.path.join(ROOT, "data", "lake_coordinates.csv"))
    assert missing == ["shaushar_lake"] and len(cfgs) == 41


def test_bbox_is_square_around_seed():
    b = cfg_for("south_lhonak").bbox
    assert b[0] < 88.18 < b[2] and b[1] < 27.91 < b[3]


def test_scl_water_flag_is_read_from_the_table():
    assert cfg_for("kausar_nag").use_scl and not cfg_for("south_lhonak").use_scl


# ---------------------------------------------------------------- the update ---
@pytest.mark.parametrize("lake", ["mundiksar_lake", "south_lhonak"])
def test_update_fills_missing_windows_and_leaves_history_byte_identical(workdir, lake):
    path = workdir / "lake_data" / f"{lake}_windows.csv"
    before = C.WindowFile(str(path))
    old = dict(zip(before.index, before.lines))
    last_data = C.has_evidence(before.frame())
    last_data = last_data.index[last_data.values].max()
    r = run_update(workdir, lake, FakeSource())
    assert r["status"] == "ok" and r["windows_set"] > 0
    after = C.WindowFile(str(path))
    assert after.eol == before.eol and after.iso == before.iso and len(after.lines) == len(before.lines)
    cutoff = last_data - pd.Timedelta(days=10 * C.REWIND_WINDOWS)
    vel_cols = [1 + before.cols.index("velocity_trend"), 1 + before.cols.index("velocity_accel")]
    obs_col = 1 + before.cols.index("observability")
    for w, line in old.items():
        if w >= cutoff:
            continue
        got = after.lines[after.index[w]]
        if w.year < TODAY.year:
            assert got == line, f"history row {w.date()} was rewritten"
        else:                       # current year: only the two velocity columns (and the 0.15 they add) may change
            a, b = line.split(","), got.split(",")
            for i, (x, y) in enumerate(zip(a, b)):
                if i not in vel_cols and i != obs_col:
                    assert x == y, f"{w.date()} column {i} was rewritten"
    new = after.frame()
    fin = C.last_finished_window(TODAY, 3)
    assert new.loc[fin, "lake_area_km2"] > 0 and new.loc[fin, "vv_db"] < 0
    assert pd.isna(new.loc[fin + pd.Timedelta(days=10), "lake_area_km2"])     # unfinished window stays empty
    assert pd.isna(new.loc[fin + pd.Timedelta(days=10), "velocity_trend"])    # ... including velocity
    assert r["newest_after"] == fin.date().isoformat()


def test_second_run_is_idempotent(workdir):
    run_update(workdir, "south_lhonak", FakeSource())
    p = workdir / "lake_data" / "south_lhonak_windows.csv"
    snap = p.read_bytes()
    src = FakeSource()
    r = run_update(workdir, "south_lhonak", src)
    assert p.read_bytes() == snap and r["lines_changed"] == 0
    # raw scenes are cached: the fake source is asked, but returns nothing new to download
    assert all(len(c) == 4 for c in src.calls)


def test_dry_run_writes_no_csv(workdir):
    p = workdir / "lake_data" / "mundiksar_lake_windows.csv"
    snap = p.read_bytes()
    r = run_update(workdir, "mundiksar_lake", FakeSource(), dry_run=True)
    assert r["status"] == "dry_run" and p.read_bytes() == snap


def test_radar_change_is_continuous_across_the_seam(workdir):
    run_update(workdir, "south_lhonak", FakeSource())
    f = C.WindowFile(str(workdir / "lake_data" / "south_lhonak_windows.csv")).frame()
    fin = C.last_finished_window(TODAY, 3)
    seg = f.loc[:fin]
    ok = seg["vv_db"].notna() & seg["vv_db"].shift().notna() & (seg.index > fin - pd.Timedelta(days=60))
    assert np.allclose(seg.loc[ok, "sar_backscatter_change"], seg["vv_db"].diff()[ok], atol=1e-6)


def test_observability_follows_the_notebook_formula(workdir):
    run_update(workdir, "mundiksar_lake", FakeSource())
    f = C.WindowFile(str(workdir / "lake_data" / "mundiksar_lake_windows.csv")).frame()
    fin = C.last_finished_window(TODAY, 3)
    assert f.loc[fin, "observability"] == pytest.approx(1.0)       # optical + radar + thermal + velocity


def test_velocity_failure_keeps_committed_velocity_and_still_updates(workdir):
    before = C.WindowFile(str(workdir / "lake_data" / "south_lhonak_windows.csv")).frame()
    r = run_update(workdir, "south_lhonak", FakeSource(no_velocity=True))
    after = C.WindowFile(str(workdir / "lake_data" / "south_lhonak_windows.csv")).frame()
    assert r["status"] == "ok"
    assert after["velocity_trend"].equals(before["velocity_trend"])


def test_rewound_window_without_new_scenes_keeps_committed_values(workdir):
    p = workdir / "lake_data" / "mundiksar_lake_windows.csv"
    before = C.WindowFile(str(p)).frame()
    ev = C.has_evidence(before); last = ev.index[ev.values].max()

    class Empty(FakeSource):
        def s2(self, *a, **k): return pd.DataFrame()
        def s1(self, *a, **k): return pd.DataFrame()
        def lst(self, *a, **k): return pd.DataFrame()
    run_update(workdir, "mundiksar_lake", Empty())
    after = C.WindowFile(str(p)).frame()
    assert after.loc[last, "lake_area_km2"] == before.loc[last, "lake_area_km2"] or (
        pd.isna(after.loc[last, "lake_area_km2"]) and pd.isna(before.loc[last, "lake_area_km2"]))


def test_min_area_comes_from_the_lakes_own_history():
    f = C.WindowFile(os.path.join(ROOT, "data", "lake_data", "south_lhonak_windows.csv")).frame()
    m = C.derive_min_area(f)
    assert 0 < m < f["lake_area_km2"].median()


def test_year_rollover_appends_a_new_year_in_the_files_own_date_style(workdir):
    p = workdir / "lake_data" / "mundiksar_lake_windows.csv"
    wf = C.WindowFile(str(p))
    frame = wf.frame()
    w = pd.Timestamp("2027-01-01")
    frame.loc[w] = np.nan
    wf.write_rows(frame, [w])
    again = C.WindowFile(str(p))
    assert w in again.index and again.lines[again.index[w]].startswith("2027-01-01,")
    assert again.lines[-1].startswith("2027-01-01")


# ------------------------------------------------------------------- the CLI ---
def test_one_failing_lake_does_not_stop_the_others_and_is_logged(workdir, monkeypatch):
    monkeypatch.setattr(C, "DATA", str(workdir)); monkeypatch.setattr(C, "LAKE_DIR", str(workdir / "lake_data"))
    monkeypatch.setattr(C, "CACHE_DIR", str(workdir / "raw_cache")); monkeypatch.setattr(C, "LOG_PATH", str(workdir / "log.json"))
    real = C.update_lake

    def patched(cfg, source, today, margin_days=3, dry_run=False, refresh_velocity=False, **kw):
        return real(cfg, source, today, margin_days, dry_run, refresh_velocity, lake_dir=str(workdir / "lake_data"),
                    cache_root=str(workdir / "raw_cache"), log=lambda *a: None)
    monkeypatch.setattr(C, "update_lake", patched)
    code = C.main(["--lake", "mundiksar_lake", "--lake", "south_lhonak", "--lake", "shaushar_lake",
                   "--today", "2026-10-31"], source=FakeSource(fail_lakes={"south_lhonak"}))
    log = pd.read_json(workdir / "log.json", typ="series")
    lakes = log["lakes"]
    assert code == 1
    assert lakes["mundiksar_lake"]["status"] == "ok"
    assert lakes["south_lhonak"]["status"] == "failed" and "STAC unreachable" in lakes["south_lhonak"]["error"]
    assert lakes["shaushar_lake"]["status"] == "no_coordinates"
    assert log["last_finished_window"] == "2026-10-18"
