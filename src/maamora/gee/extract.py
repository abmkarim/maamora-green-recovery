"""Extraction Earth Engine par lots de cellules, avec cache parquet idempotent dans `data/`."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from maamora.config import Config
from maamora.gee import aoi as aoi_mod
from maamora.gee.auth import init_ee
from maamora.retry import RequestTooLargeError, with_retry

log = logging.getLogger(__name__)
MAX_WORKERS = 4


# --------------------------------------------------------------------------- utilitaires mois
def month_list(end: str, n: int) -> list[str]:
    """Les `n` mois consécutifs ('YYYY-MM') se terminant à `end` inclus."""
    end_p = pd.Period(end, freq="M")
    return [str(end_p - k) for k in range(n - 1, -1, -1)]


def month_bounds(month: str) -> tuple[str, str]:
    """Début inclus et fin exclue d'un mois, au format 'YYYY-MM-DD'."""
    p = pd.Period(month, freq="M")
    return p.start_time.strftime("%Y-%m-%d"), (p + 1).start_time.strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- cache
def cached_parquet(path: Path, producer: Callable[[], pd.DataFrame]) -> pd.DataFrame:
    """Relit `path` s'il existe, sinon le produit et l'écrit (écriture atomique)."""
    if path.exists():
        return pd.read_parquet(path)
    df = producer()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)
    return df


# --------------------------------------------------------------------------- fenêtre
def resolve_window(cfg: Config) -> dict[str, Any]:
    """Fenêtre d'étude : figée dans data/window.json après la première détermination."""
    path = cfg.data_dir / "window.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if cfg.window.end_month:
        end = cfg.window.end_month
        chirps_last = s2_last = None
    else:
        from maamora.gee.chirps import last_complete_month

        init_ee(cfg)
        chirps_last = last_complete_month(cfg.gee)
        s2_last = str(pd.Timestamp.utcnow().tz_localize(None).to_period("M") - 1)
        end = min(chirps_last, s2_last)
    months = month_list(end, cfg.window.n_months)
    win = {"start": months[0], "end": end, "months": months,
           "chirps_last_complete": chirps_last, "s2_last_complete": s2_last}
    path.write_text(json.dumps(win, indent=2), encoding="utf-8")
    return win


# --------------------------------------------------------------------------- réduction par lots
def reduce_cells(image: Any, grid: gpd.GeoDataFrame, reducer: Any, scale: float,
                 cfg: Config, label: str) -> pd.DataFrame:
    """`reduceRegions` sur les cellules, par lots ; un lot trop lourd est coupé en deux."""
    import ee

    def run(sub: gpd.GeoDataFrame) -> list[dict]:
        fc = ee.FeatureCollection(aoi_mod.grid_to_ee_features(sub))
        red = image.reduceRegions(collection=fc, reducer=reducer, scale=scale,
                                  tileScale=cfg.gee.tile_scale)
        red = red.map(lambda f: ee.Feature(None, f.toDictionary()))
        try:
            res = with_retry(lambda: red.getInfo(), max_retries=cfg.gee.max_retries,
                             base=cfg.gee.backoff_base_s, label=label)
        except RequestTooLargeError:
            if len(sub) <= 50:
                raise
            half = len(sub) // 2
            log.info("%s : lot de %d coupé en deux", label, len(sub))
            return run(sub.iloc[:half]) + run(sub.iloc[half:])
        return [f["properties"] for f in res["features"]]

    rows: list[dict] = []
    bs = cfg.gee.batch_size
    for i in range(0, len(grid), bs):
        rows.extend(run(grid.iloc[i:i + bs]))
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- grille + statiques
def get_grid(cfg: Config) -> gpd.GeoDataFrame:
    """Grille filtrée sur la végétation, avec altitude et pente (cache data/grid.parquet)."""
    path = cfg.data_dir / "grid.parquet"
    if path.exists():
        return gpd.read_parquet(path)
    import ee

    from maamora.gee.covariates import static_image

    aoi = aoi_mod.build_aoi(cfg)
    full = aoi_mod.build_grid(aoi, cfg.grid.resolution_m, cfg.aoi.utm_epsg,
                              cfg.grid.spatial_block_m)
    init_ee(cfg)
    img = static_image(cfg.gee)
    stats = reduce_cells(img, full, ee.Reducer.mean().forEachBand(img), 30, cfg, "statiques")
    full = full.merge(stats, on="cell_id", how="left")
    full["n_cells_bbox"] = len(full)
    grid = full[full.veg_fraction >= cfg.grid.min_veg_fraction].reset_index(drop=True)
    log.info("Grille : %d cellules sur %d retenues (végétation >= %.0f %%)", len(grid),
             len(full), 100 * cfg.grid.min_veg_fraction)
    full.drop(columns="geometry").to_parquet(cfg.data_dir / "grid_full_stats.parquet")
    grid.to_parquet(path)
    return grid


# --------------------------------------------------------------------------- Sentinel-2
def extract_s2(cfg: Config) -> pd.DataFrame:
    """NDVI mensuel par cellule sur la fenêtre (cache par mois)."""
    import ee

    from maamora.gee.sentinel2 import monthly_cloud_stats, monthly_ndvi_image

    win = resolve_window(cfg)
    grid = get_grid(cfg)
    init_ee(cfg)
    region = ee.Geometry(aoi_mod.load_aoi_geometry(cfg.path("aoi_file")))
    reducer = ee.Reducer.median().combine(ee.Reducer.mean(), sharedInputs=True)
    out_dir = cfg.data_dir / "s2"

    def one(month: str) -> pd.DataFrame:
        start, end = month_bounds(month)

        def produce() -> pd.DataFrame:
            img = monthly_ndvi_image(cfg.gee, region, start, end)
            df = reduce_cells(img, grid, reducer, cfg.gee.s2_scale_m, cfg, f"S2 {month}")
            df["month"] = month
            return df

        df = cached_parquet(out_dir / f"ndvi_{month}.parquet", produce)

        def clouds() -> pd.DataFrame:
            d = with_retry(lambda: monthly_cloud_stats(cfg.gee, region, start, end).getInfo(),
                           label=f"nuages {month}")
            return pd.DataFrame([{"month": month, **d}])

        cached_parquet(out_dir / f"cloud_{month}.parquet", clouds)
        log.info("S2 %s : %d cellules", month, len(df))
        return df

    with ThreadPoolExecutor(MAX_WORKERS) as ex:
        frames = list(ex.map(one, win["months"]))
    ndvi = pd.concat(frames, ignore_index=True)
    ndvi = ndvi.rename(columns={"ndvi_median": "ndvi", "n_obs_mean": "n_obs",
                                "valid_mean": "valid_fraction"})
    keep = ["cell_id", "month", "ndvi", "n_obs", "valid_fraction"]
    for c in keep:
        if c not in ndvi:
            ndvi[c] = float("nan")
    ndvi = ndvi[keep]
    ndvi.to_parquet(cfg.data_dir / "ndvi.parquet", index=False)
    clouds = pd.concat([pd.read_parquet(out_dir / f"cloud_{m}.parquet") for m in win["months"]])
    clouds.to_parquet(cfg.data_dir / "clouds.parquet", index=False)
    return ndvi


# --------------------------------------------------------------------------- CHIRPS
def extract_chirps(cfg: Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pluie mensuelle par cellule (fenêtre + 12 mois) et historique AOI depuis 1981."""
    import ee

    from maamora.gee.chirps import aoi_monthly_history, monthly_rain_image

    win = resolve_window(cfg)
    grid = get_grid(cfg)
    init_ee(cfg)
    region = ee.Geometry(aoi_mod.load_aoi_geometry(cfg.path("aoi_file")))
    out_dir = cfg.data_dir / "chirps"
    extra = max(max(cfg.features.rain_cumuls), max(cfg.features.rain_lags) + 1)
    months = month_list(win["end"], cfg.window.n_months + extra)

    def one(month: str) -> pd.DataFrame:
        start, end = month_bounds(month)

        def produce() -> pd.DataFrame:
            img = monthly_rain_image(cfg.gee, start, end)
            # Échelle fine (rééchantillonnage au plus proche) : chaque petite cellule
            # reçoit la valeur du pixel CHIRPS qui la recouvre.
            df = reduce_cells(img, grid, ee.Reducer.mean().forEachBand(img), 250, cfg,
                              f"CHIRPS {month}")
            df["month"] = month
            return df

        return cached_parquet(out_dir / f"cells_{month}.parquet", produce)

    with ThreadPoolExecutor(MAX_WORKERS) as ex:
        cells = pd.concat(list(ex.map(one, months)), ignore_index=True)
    cells = cells[["cell_id", "month", "rain_mm"]]
    cells.to_parquet(cfg.data_dir / "rain_cells.parquet", index=False)

    # Historique long moyenné sur l'AOI, par année (cache par année).
    first = pd.Period(cfg.gee.chirps_history_start, freq="M")
    all_months = [str(p) for p in pd.period_range(first, pd.Period(win["end"], freq="M"))]
    by_year: dict[str, list[str]] = {}
    for m in all_months:
        by_year.setdefault(m[:4], []).append(m)

    def year(y: str) -> pd.DataFrame:
        ms = by_year[y]
        complete = len(ms) == 12
        path = out_dir / f"history_{y}.parquet"
        if not complete and path.exists():
            cached = pd.read_parquet(path)
            if len(cached) == len(ms):
                return cached
            path.unlink()

        def produce() -> pd.DataFrame:
            fc = aoi_monthly_history(cfg.gee, region, ms)
            res = with_retry(lambda: fc.getInfo(), max_retries=cfg.gee.max_retries,
                             label=f"CHIRPS historique {y}")
            return pd.DataFrame([f["properties"] for f in res["features"]])

        return cached_parquet(path, produce)

    with ThreadPoolExecutor(MAX_WORKERS) as ex:
        hist = pd.concat(list(ex.map(year, sorted(by_year))), ignore_index=True)
    hist = hist[["month", "rain_mm"]].sort_values("month").reset_index(drop=True)
    hist.to_parquet(cfg.data_dir / "rain_history.parquet", index=False)
    return cells, hist


# --------------------------------------------------------------------------- ERA5
def extract_covariates(cfg: Config) -> pd.DataFrame:
    """Température ERA5-Land mensuelle par cellule (fenêtre + décalages)."""
    import ee

    from maamora.gee.covariates import monthly_temperature_image

    win = resolve_window(cfg)
    grid = get_grid(cfg)
    init_ee(cfg)
    out_dir = cfg.data_dir / "era5"
    months = month_list(win["end"], cfg.window.n_months + max(cfg.features.temp_lags))

    def one(month: str) -> pd.DataFrame:
        start, end = month_bounds(month)
        path = out_dir / f"t2m_{month}.parquet"

        def produce() -> pd.DataFrame:
            img = monthly_temperature_image(cfg.gee, start, end)
            df = reduce_cells(img, grid, ee.Reducer.mean().forEachBand(img), 250, cfg,
                              f"ERA5 {month}")
            df["month"] = month
            if "t2m_c" not in df:
                df["t2m_c"] = float("nan")
            return df

        df = cached_parquet(path, produce)
        if df["t2m_c"].isna().all():
            # Mois pas encore publié : ne pas figer l'absence dans le cache.
            path.unlink(missing_ok=True)
        return df

    with ThreadPoolExecutor(MAX_WORKERS) as ex:
        t2m = pd.concat(list(ex.map(one, months)), ignore_index=True)
    t2m = t2m[["cell_id", "month", "t2m_c"]]
    t2m.to_parquet(cfg.data_dir / "t2m_cells.parquet", index=False)
    return t2m
