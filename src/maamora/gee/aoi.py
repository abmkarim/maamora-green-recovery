"""Zone d'étude : contour OSM (Overpass) ou emprise de repli, et grille d'analyse."""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import requests
from shapely.geometry import LineString, Polygon, box, mapping
from shapely.ops import polygonize, unary_union

from maamora.config import Config
from maamora.retry import with_retry

log = logging.getLogger(__name__)
USER_AGENT = "maamora-green-recovery/0.1 (recherche non commerciale)"


def _overpass_query(name_regex: str, bbox: tuple[float, float, float, float]) -> str:
    lon0, lat0, lon1, lat1 = bbox
    b = f"{lat0 - 0.1},{lon0 - 0.1},{lat1 + 0.1},{lon1 + 0.1}"
    return (
        "[out:json][timeout:90];("
        f'way["name"~"{name_regex}",i]["landuse"="forest"]({b});'
        f'way["name"~"{name_regex}",i]["natural"="wood"]({b});'
        f'relation["name"~"{name_regex}",i]["landuse"="forest"]({b});'
        f'relation["name"~"{name_regex}",i]["boundary"="protected_area"]({b});'
        ");out geom;"
    )


def _element_to_polygon(el: dict) -> Polygon | None:
    """Convertit un élément Overpass (`out geom`) en polygone."""
    if el["type"] == "way" and "geometry" in el:
        coords = [(p["lon"], p["lat"]) for p in el["geometry"]]
        if len(coords) >= 4 and coords[0] == coords[-1]:
            return Polygon(coords)
        return None
    if el["type"] == "relation":
        lines = [
            LineString([(p["lon"], p["lat"]) for p in m["geometry"]])
            for m in el.get("members", [])
            if m.get("role") == "outer" and m.get("geometry")
        ]
        polys = list(polygonize(unary_union(lines))) if lines else []
        return unary_union(polys) if polys else None
    return None


def fetch_osm_polygons(cfg: Config) -> gpd.GeoDataFrame:
    """Récupère les polygones forestiers nommés Maâmora via l'API Overpass."""
    query = _overpass_query(cfg.aoi.osm_name_regex, cfg.aoi.fallback_bbox)
    last_exc: Exception | None = None
    for url in cfg.aoi.overpass_urls:
        def call(u: str = url) -> dict:
            r = requests.post(u, data={"data": query}, headers={"User-Agent": USER_AGENT},
                              timeout=180)
            r.raise_for_status()
            return r.json()
        try:
            data = with_retry(call, max_retries=3, label=f"Overpass {url}")
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            log.warning("Overpass %s indisponible : %s", url, exc)
    else:
        raise RuntimeError(f"Overpass injoignable : {last_exc}")
    rows = []
    for el in data.get("elements", []):
        geom = _element_to_polygon(el)
        if geom is not None and not geom.is_empty:
            rows.append({"osm_id": f"{el['type']}/{el['id']}",
                         "name": el.get("tags", {}).get("name:fr", el.get("tags", {}).get("name")),
                         "geometry": geom})
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


def area_km2(gdf: gpd.GeoDataFrame, epsg: int) -> float:
    """Surface totale (union) en km²."""
    if gdf.empty:
        return 0.0
    return float(unary_union(gdf.to_crs(epsg).geometry).area / 1e6)


def build_aoi(cfg: Config, force: bool = False) -> gpd.GeoDataFrame:
    """Construit (ou relit) le contour de l'AOI ; repli sur l'emprise si OSM est incomplet."""
    aoi_path = cfg.path("aoi_file")
    if aoi_path.exists() and not force:
        return gpd.read_file(aoi_path)
    aoi_path.parent.mkdir(parents=True, exist_ok=True)
    source, note = "fallback_bbox", ""
    try:
        osm = fetch_osm_polygons(cfg)
        osm_area = area_km2(osm, cfg.aoi.utm_epsg)
        log.info("OSM : %d polygones, %.0f km²", len(osm), osm_area)
        if not osm.empty:
            osm.to_file(cfg.path("osm_reference_file"), driver="GeoJSON")
        if osm_area >= cfg.aoi.osm_min_area_km2:
            source = "osm"
            geom = unary_union(osm.geometry)
        else:
            note = (f"OSM incomplet ({len(osm)} polygones, {osm_area:.0f} km² < "
                    f"{cfg.aoi.osm_min_area_km2:.0f} km²)")
    except Exception as exc:  # noqa: BLE001
        note = f"Overpass indisponible : {exc}"
    if source != "osm":
        geom = box(*cfg.aoi.fallback_bbox)
        log.warning("AOI : emprise de repli (%s)", note)
    gdf = gpd.GeoDataFrame(
        [{"name": "Forêt de la Maâmora (AOI d'étude)", "source": source, "note": note,
          "vegetation_mask": "ESA WorldCover v200 classes 10/20", "geometry": geom}],
        geometry="geometry", crs="EPSG:4326",
    )
    gdf.to_file(aoi_path, driver="GeoJSON")
    return gdf


def build_grid(aoi: gpd.GeoDataFrame, resolution_m: float, epsg: int,
               block_m: float) -> gpd.GeoDataFrame:
    """Grille carrée alignée en UTM couvrant l'AOI ; cellules intersectant l'AOI conservées.

    Colonnes : cell_id, ix, iy, x, y (centre UTM), lon, lat, block_id, geometry (EPSG:4326).
    """
    shape = unary_union(aoi.to_crs(epsg).geometry)
    minx, miny, maxx, maxy = shape.bounds
    x0 = math.floor(minx / resolution_m) * resolution_m
    y0 = math.floor(miny / resolution_m) * resolution_m
    nx = int(math.ceil((maxx - x0) / resolution_m))
    ny = int(math.ceil((maxy - y0) / resolution_m))
    rows = []
    for iy in range(ny):
        for ix in range(nx):
            cx0, cy0 = x0 + ix * resolution_m, y0 + iy * resolution_m
            cell = box(cx0, cy0, cx0 + resolution_m, cy0 + resolution_m)
            if cell.intersects(shape):
                rows.append({"ix": ix, "iy": iy, "x": cx0 + resolution_m / 2,
                             "y": cy0 + resolution_m / 2, "geometry": cell})
    grid = gpd.GeoDataFrame(rows, geometry="geometry", crs=f"EPSG:{epsg}")
    grid["cell_id"] = [f"c{iy:04d}_{ix:04d}" for iy, ix in zip(grid.iy, grid.ix, strict=True)]
    bx = np.floor((grid.x - x0) / block_m).astype(int)
    by = np.floor((grid.y - y0) / block_m).astype(int)
    grid["block_id"] = by * 1000 + bx
    grid = grid.to_crs("EPSG:4326")
    cent = grid.geometry.to_crs(epsg).centroid.to_crs("EPSG:4326")
    grid["lon"], grid["lat"] = cent.x.round(6), cent.y.round(6)
    return grid[["cell_id", "ix", "iy", "x", "y", "lon", "lat", "block_id", "geometry"]]


def grid_to_ee_features(grid: gpd.GeoDataFrame) -> list[dict]:
    """Convertit la grille en liste de Features GeoJSON (pour ee.FeatureCollection)."""
    return [
        {"type": "Feature", "geometry": json.loads(json.dumps(mapping(g))),
         "properties": {"cell_id": cid}}
        for cid, g in zip(grid.cell_id, grid.geometry, strict=True)
    ]


def load_aoi_geometry(path: Path) -> dict:
    """Géométrie GeoJSON (dict) de l'AOI."""
    gdf = gpd.read_file(path)
    return mapping(unary_union(gdf.geometry))
