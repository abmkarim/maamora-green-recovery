"""Pluie CHIRPS journalière agrégée en cumul mensuel."""

from __future__ import annotations

from typing import Any

from maamora.config import GeeConfig


def monthly_rain_image(cfg: GeeConfig, start: str, end: str) -> Any:
    """Cumul de pluie (mm) entre `start` (inclus) et `end` (exclu)."""
    import ee

    return (ee.ImageCollection(cfg.chirps).filterDate(start, end).select("precipitation")
            .sum().rename("rain_mm").toFloat())


def aoi_monthly_history(cfg: GeeConfig, region: Any, months: list[str]) -> Any:
    """FeatureCollection (sans géométrie) : pluie mensuelle moyenne sur l'AOI pour chaque mois.

    `months` : liste de chaînes 'YYYY-MM'.
    """
    import ee

    def one(m: Any) -> Any:
        start = ee.Date.parse("yyyy-MM", m)
        img = (ee.ImageCollection(cfg.chirps).filterDate(start, start.advance(1, "month"))
               .select("precipitation").sum())
        val = img.reduceRegion(ee.Reducer.mean(), region, cfg.chirps_scale_m,
                               maxPixels=1e9).get("precipitation")
        return ee.Feature(None, {"month": m, "rain_mm": val})

    return ee.FeatureCollection(ee.List(months).map(one))


def last_complete_month(cfg: GeeConfig) -> str:
    """Dernier mois entièrement couvert par CHIRPS journalier ('YYYY-MM')."""
    import ee
    import pandas as pd

    from maamora.retry import with_retry

    now = pd.Timestamp.utcnow().tz_localize(None)
    coll = ee.ImageCollection(cfg.chirps).filterDate(
        (now - pd.Timedelta(days=200)).strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d"))
    last_ms = with_retry(lambda: coll.aggregate_max("system:time_start").getInfo(),
                         label="CHIRPS dernière date")
    last = pd.Timestamp(last_ms, unit="ms")
    if (last + pd.Timedelta(days=1)).month != last.month:
        return last.strftime("%Y-%m")
    return (last.to_period("M") - 1).strftime("%Y-%m")
