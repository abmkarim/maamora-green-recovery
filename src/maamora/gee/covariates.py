"""Covariables : température ERA5-Land mensuelle, relief SRTM, part de végétation WorldCover."""

from __future__ import annotations

from typing import Any

from maamora.config import GeeConfig
from maamora.gee.sentinel2 import vegetation_mask


def monthly_temperature_image(cfg: GeeConfig, start: str, end: str) -> Any:
    """Température de l'air à 2 m (°C) du mois ; image masquée si le mois n'est pas publié."""
    import ee

    coll = ee.ImageCollection(cfg.era5).filterDate(start, end).select(cfg.era5_band)
    masked = ee.Image.constant(0).rename("t2m_c").updateMask(ee.Image.constant(0))
    img = ee.Image(ee.Algorithms.If(coll.size().gt(0),
                                    coll.first().subtract(273.15).rename("t2m_c"), masked))
    return img.toFloat()


def static_image(cfg: GeeConfig) -> Any:
    """Altitude (m), pente (degrés) et masque végétation (0/1, non masqué)."""
    import ee

    dem = ee.Image(cfg.srtm).select("elevation")
    slope = ee.Terrain.slope(dem).rename("slope")
    veg = vegetation_mask(cfg).unmask(0).rename("veg_fraction")
    return dem.rename("elevation").toFloat().addBands([slope.toFloat(), veg.toFloat()])
