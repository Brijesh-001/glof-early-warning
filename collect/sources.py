"""
Satellite sources for the GEWS updater: a port of the Colab notebook (golf.ipynb) to any lake.

Everything here talks to the network (Microsoft Planetary Computer STAC and ITS_LIVE), so the
heavy libraries are imported lazily: the dashboard, the tests and `--help` never need them.
Install them with:  pip install -r requirements-collect.txt

Per-lake settings come from data/lake_coordinates.csv (seed point, box half-width, seed radius,
Sentinel-2 tile, USE_SCL_WATER), exactly the columns of the project's lake table.

The measuring code (water mask, seed-connected lake component, radar level, MODIS thermal) is
copied from the notebook so a refreshed window is computed the way the committed ones were.
This module could not be run against the live services where it was written; use
`python collect/gews_collect.py --lake <name> --verify` first (see collect/README.md).
"""
import os
import re
import warnings
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import numpy as np
import pandas as pd

SCL_CLOUD = [3, 8, 9, 10]
SCL_WATER = 6
SCL_SNOW = 11
PIXEL_KM2 = 0.0001                 # one 10 m x 10 m pixel
S1_WATER_DB = -18.0                # only feeds area_sar_km2, which the window table does not use
STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
ITSLIVE_STAC = "https://stac.itslive.cloud"


# ----------------------------------------------------------------- config ---
@dataclass
class LakeCfg:
    lake: str
    lon: float
    lat: float
    half_km: float
    radius_m: float
    tile: str | None            # normalised 5-character MGRS code, or None = pick automatically
    use_scl: bool

    @property
    def seed(self):
        return (self.lon, self.lat)

    @property
    def bbox(self):
        """Square box around the seed: [lon_min, lat_min, lon_max, lat_max] (notebook make_bbox)."""
        dlat = self.half_km / 111.0
        dlon = self.half_km / (111.0 * np.cos(np.radians(self.lat)))
        return [round(self.lon - dlon, 4), round(self.lat - dlat, 4),
                round(self.lon + dlon, 4), round(self.lat + dlat, 4)]


def normalise_tile(raw):
    """'45RXL / 45RXM' -> '45RXL' (first listed); '43UFT*' -> '43UFT'; '44R*' / 'unresolved' -> None."""
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None
    first = str(raw).split("/")[0].strip().rstrip("*").strip()
    return first if re.fullmatch(r"\d{2}[A-Z]{3}", first) else None


def load_lake_configs(coords_csv):
    """Lakes that have coordinates, as LakeCfg. Lakes without coordinates are returned separately."""
    t = pd.read_csv(coords_csv)
    cfgs, missing = {}, []
    for r in t.to_dict("records"):
        if pd.isna(r["lon"]) or pd.isna(r["lat"]):
            missing.append(r["lake"]); continue
        cfgs[r["lake"]] = LakeCfg(
            lake=r["lake"], lon=float(r["lon"]), lat=float(r["lat"]),
            half_km=float(r["half_km"]) if pd.notna(r["half_km"]) else 1.5,
            radius_m=float(r["seed_radius_m"]) if pd.notna(r["seed_radius_m"]) else 150.0,
            tile=normalise_tile(r.get("s2_tile")),
            use_scl=str(r.get("use_scl_water", "")).strip().upper() == "TRUE")
    return cfgs, missing


# ------------------------------------------------------------ pixel helpers ---
def _rio():
    import rasterio
    from rasterio.warp import transform_bounds
    from rasterio.windows import Window, from_bounds
    return rasterio, transform_bounds, Window, from_bounds


def read_band(item, band, bbox, out_shape=None):
    """Read ONLY the pixels inside bbox from the remote file. Signed per read (tokens never expire)."""
    import planetary_computer
    rasterio, transform_bounds, Window, from_bounds = _rio()
    href = planetary_computer.sign(item.assets[band].href)
    with rasterio.open(href) as src:
        b = transform_bounds("EPSG:4326", src.crs, *bbox, densify_pts=21)
        w = from_bounds(*b, transform=src.transform)
        win = Window(int(round(w.col_off)), int(round(w.row_off)),
                     max(1, int(round(w.width))), max(1, int(round(w.height))))
        inside = (win.col_off >= 0 and win.row_off >= 0 and
                  win.col_off + win.width <= src.width and win.row_off + win.height <= src.height)
        arr = src.read(1, window=win, out_shape=out_shape,
                       boundless=not inside, fill_value=0 if not inside else None)
    return arr.astype("float32")


def safe_div(a, b):
    out = np.full(a.shape, np.nan, dtype="float32")
    np.divide(a, b, out=out, where=b > 0)
    return out


def _nanmean(a):
    a = a[np.isfinite(a)]
    return float(a.mean()) if a.size else np.nan


def _baseline(item):
    try:
        return float(item.properties.get("s2:processing_baseline", "0"))
    except (TypeError, ValueError):
        return 0.0


def to_db(power):
    db = np.full(power.shape, np.nan, dtype="float32")
    np.log10(power, out=db, where=power > 0)
    return db * 10


def item_date(item):
    """MODIS items have datetime=None and use start_datetime instead."""
    if item.datetime is not None:
        return item.datetime.date()
    p = item.properties
    return pd.Timestamp(p.get("start_datetime") or p.get("end_datetime")).date()


def lake_component(mask, bbox, seed, radius_m):
    """Keep only the connected water body touching the seed point (notebook version)."""
    from scipy import ndimage
    H, W = mask.shape
    c = (seed[0] - bbox[0]) / (bbox[2] - bbox[0]) * W
    r = (bbox[3] - seed[1]) / (bbox[3] - bbox[1]) * H
    closed = ndimage.binary_closing(mask, structure=np.ones((3, 3)), iterations=2)
    lab, n = ndimage.label(closed, structure=np.ones((3, 3)))
    if n == 0:
        return np.zeros_like(mask, dtype=bool)
    yy, xx = np.ogrid[:H, :W]
    disk = (yy - r) ** 2 + (xx - c) ** 2 <= (radius_m / 10.0) ** 2
    ids = lab[disk & (lab > 0)]
    if ids.size == 0:
        return np.zeros_like(mask, dtype=bool)
    component = lab == np.bincount(ids).argmax()
    return component & mask


# ------------------------------------------------------------------ measures ---
def measure_s2(item, cfg):
    bbox = cfg.bbox
    green = read_band(item, "B03", bbox)
    shape = green.shape
    nir = read_band(item, "B08", bbox, out_shape=shape)
    swir = read_band(item, "B11", bbox, out_shape=shape)
    scl = read_band(item, "SCL", bbox, out_shape=shape)
    valid_frac = float((green > 0).mean())
    if _baseline(item) >= 4.0:                        # post-Jan-2022 reflectance offset
        green, nir, swir = green - 1000.0, nir - 1000.0, swir - 1000.0
    ndwi = safe_div(green - nir, green + nir)
    mndwi = safe_div(green - swir, green + swir)
    water_all = (ndwi > 0.30) & (mndwi > 0.30)
    water = lake_component(water_all, bbox, cfg.seed, cfg.radius_m)
    scl_w = lake_component(scl == SCL_WATER, bbox, cfg.seed, cfg.radius_m)
    # USE_SCL_WATER lakes (snow / shadow confuse NDWI there) take the ESA scene-classification water
    area = float((scl_w if cfg.use_scl else water).sum()) * PIXEL_KM2
    if area == 0:
        area = np.nan
    return {"scene_id": item.id, "date": str(item_date(item)), "area_km2": area,
            "area_scl_km2": float(scl_w.sum()) * PIXEL_KM2,
            "snow_frac": float((scl == SCL_SNOW).mean()),
            "cloud_frac": float(np.isin(scl, SCL_CLOUD).mean()),
            "valid_frac": valid_frac, "baseline": item.properties.get("s2:processing_baseline")}


def measure_s1(item, cfg):
    bbox = cfg.bbox
    vv = read_band(item, "vv", bbox)
    vv_db = to_db(vv)
    if "vh" in item.assets:
        vh_db = to_db(read_band(item, "vh", bbox, out_shape=vv.shape))
    else:
        vh_db = np.full(vv.shape, np.nan, dtype="float32")
    return {"scene_id": item.id, "date": str(item_date(item)), "vv_db": _nanmean(vv_db),
            "vh_db": _nanmean(vh_db), "area_sar_km2": float((vv_db < S1_WATER_DB).sum()) * PIXEL_KM2,
            "orbit_state": item.properties.get("sat:orbit_state"),
            "rel_orbit": item.properties.get("sat:relative_orbit")}


def measure_lst(item, cfg):
    raw = read_band(item, "LST_Day_1km", cfg.bbox)
    raw[raw == 0] = np.nan                            # 0 = fill value
    celsius = raw * 0.02 - 273.15
    return {"scene_id": item.id, "date": str(item_date(item)), "lst_c": _nanmean(celsius),
            "valid_frac": float(np.isfinite(celsius).mean())}


# -------------------------------------------------------------------- source ---
class PlanetaryComputerSource:
    """Network access. Every method returns plain DataFrames so the rest of the updater is testable."""

    def __init__(self, workers=4, pc_key=None, log=print):
        import planetary_computer
        import pystac_client
        self.workers, self.log = workers, log
        key = pc_key or os.environ.get("GEWS_PC_KEY", "")
        if key:
            planetary_computer.settings.set_subscription_key(key)
        for k, v in {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.tiff",
                     "GDAL_HTTP_MAX_RETRY": "5", "GDAL_HTTP_RETRY_DELAY": "2", "VSI_CACHE": "TRUE"}.items():
            os.environ.setdefault(k, v)
        # no modifier=sign_inplace: read_band signs per read, so tokens never expire mid-pull
        self.catalog = pystac_client.Client.open(STAC_URL)

    # ---- metadata-only queries (cheap: no pixels are read)
    def resolve_tile(self, cfg, start, end):
        """The configured tile, or (when 'unresolved') the tile with the most scenes over the box."""
        if cfg.tile:
            return cfg.tile
        items = list(self.catalog.search(collections=["sentinel-2-l2a"], bbox=cfg.bbox,
                                         datetime=f"{start}/{end}").items())
        tiles = Counter(i.properties["s2:mgrs_tile"] for i in items)
        if not tiles:
            raise RuntimeError(f"{cfg.lake}: no Sentinel-2 scenes over the box, cannot pick a tile")
        return tiles.most_common(1)[0][0]

    def s1_track(self, cfg, start, end):
        """Most common (orbit_state, relative_orbit) over the whole record, as the notebook chose it."""
        items = list(self.catalog.search(collections=["sentinel-1-rtc"], bbox=cfg.bbox,
                                         datetime=f"{start}/{end}").items())
        if not items:
            return None
        tr = Counter((i.properties.get("sat:orbit_state"), i.properties.get("sat:relative_orbit")) for i in items)
        return tr.most_common(1)[0][0]

    # ---- pixel pulls
    def _pull(self, items, fn, cfg, known_ids):
        todo = [it for it in items if it.id not in known_ids]
        rows, failed = [], 0
        if not todo:
            return pd.DataFrame(rows)
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            futs = {ex.submit(fn, it, cfg): it for it in todo}
            for f in as_completed(futs):
                try:
                    rows.append(f.result())
                except Exception as e:                       # one bad scene must not sink the lake
                    failed += 1
                    if failed <= 3:
                        self.log(f"  skipped {futs[f].id}: {type(e).__name__} {e}")
                    if not rows and failed >= 5:
                        raise RuntimeError(f"first {failed} scenes all failed: {e}") from e
        if failed:
            self.log(f"  {failed} scene(s) failed, {len(rows)} ok")
        return pd.DataFrame(rows)

    def s2(self, cfg, start, end, known_ids):
        tile = self.resolve_tile(cfg, start, end)
        items = [i for i in self.catalog.search(collections=["sentinel-2-l2a"], bbox=cfg.bbox,
                                                datetime=f"{start}/{end}").items()
                 if i.properties["s2:mgrs_tile"] == tile]
        return self._pull(items, measure_s2, cfg, known_ids)

    def s1(self, cfg, start, end, known_ids, track):
        items = list(self.catalog.search(collections=["sentinel-1-rtc"], bbox=cfg.bbox,
                                         datetime=f"{start}/{end}").items())
        if track is not None:
            items = [i for i in items if (i.properties.get("sat:orbit_state"),
                                          i.properties.get("sat:relative_orbit")) == tuple(track)]
        return self._pull(items, measure_s1, cfg, known_ids)

    def lst(self, cfg, start, end, known_ids):
        items = list(self.catalog.search(collections=["modis-11A1-061"], bbox=cfg.bbox,
                                         datetime=f"{start}/{end}").items())
        return self._pull(items, measure_lst, cfg, known_ids)

    # ---- ITS_LIVE glacier velocity (one value per year)
    def velocity(self, cfg, year0, year1):
        import pystac_client
        import xarray as xr
        from pyproj import Transformer
        bbox = cfg.bbox
        lon_c, lat_c = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
        stac = pystac_client.Client.open(ITSLIVE_STAC)
        items = list(stac.search(collections=["itslive-cubes"],
                                 intersects={"type": "Point", "coordinates": [lon_c, lat_c]},
                                 max_items=5).items())
        if not items:
            raise RuntimeError("ITS_LIVE STAC returned no cube for this location")
        asset = items[0].assets.get("zarr") or next(
            a for a in items[0].assets.values() if str(a.href).rstrip("/").endswith(".zarr"))
        urls = [asset.href]
        alt = ((asset.extra_fields or {}).get("alternate") or {}).get("s3", {}).get("href")
        if alt:
            urls.append(alt)
        ds, last = None, None
        for u in urls:
            opts = {"anon": True} if u.startswith("s3://") else {}
            for cons in (True, False):
                try:
                    ds = xr.open_zarr(u, storage_options=opts, consolidated=cons); break
                except Exception as e:
                    last = e
            if ds is not None:
                break
        if ds is None:
            raise last
        crs = None
        for c in [ds.attrs.get("projection"), ds.attrs.get("spatial_epsg")] + (
                [ds["mapping"].attrs.get("spatial_epsg"), ds["mapping"].attrs.get("crs_wkt")] if "mapping" in ds else []):
            if c is not None:
                s = str(c).strip()
                try:
                    crs = f"EPSG:{int(float(s))}"
                except ValueError:
                    crs = s
                break
        if crs is None:
            raise RuntimeError("cannot find the CRS of the ITS_LIVE cube")
        tf = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        corners = [tf.transform(lon, lat) for lon in (bbox[0], bbox[2]) for lat in (bbox[1], bbox[3])]
        xs, ys = [c[0] for c in corners], [c[1] for c in corners]
        y_desc = float(ds["y"].values[0]) > float(ds["y"].values[-1])
        yslice = slice(max(ys), min(ys)) if y_desc else slice(min(ys), max(ys))
        v = ds["v"].sel(x=slice(min(xs), max(xs)), y=yslice)
        if v.sizes["x"] == 0 or v.sizes["y"] == 0:
            raise RuntimeError("box selected no ITS_LIVE pixels (x/y ordering or CRS mismatch)")
        yrs = v["mid_date"].dt.year.values
        v = v.isel(mid_date=np.where((yrs >= year0) & (yrs <= year1))[0]).load()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            q = v.quantile(0.9, dim=["x", "y"], skipna=True)
        annual = q.groupby("mid_date.year").max().rename("v")
        vel = annual.to_dataframe().reset_index()[["year", "v"]]
        vel["n_pairs"] = vel["year"].map(pd.Series(v["mid_date"].dt.year.values).value_counts())
        return vel
