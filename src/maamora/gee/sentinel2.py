"""NDVI Sentinel-2 mensuel avec masque nuages Cloud Score+ (SCL en secours)."""

from __future__ import annotations

from typing import Any

from maamora.config import GeeConfig

# Classes SCL considérées comme valides : végétation, sol nu, eau, non classé.
SCL_VALID = (4, 5, 6, 7)


def vegetation_mask(cfg: GeeConfig) -> Any:
    """Masque binaire WorldCover (arbres + arbustes)."""
    import ee

    wc = ee.ImageCollection(cfg.worldcover).first().select("Map")
    mask = wc.eq(cfg.worldcover_classes[0])
    for c in cfg.worldcover_classes[1:]:
        mask = mask.Or(wc.eq(c))
    return mask.rename("veg")


def _mask_image(img: Any, cfg: GeeConfig) -> Any:
    """Applique Cloud Score+ si la bande est présente, sinon la SCL."""
    import ee

    # ee.Algorithms.If n'évalue que la branche retenue côté serveur.
    has_cs = img.bandNames().contains(cfg.cs_band)
    cs_mask = img.select([cfg.cs_band]).gte(cfg.cs_threshold)
    scl = img.select("SCL")
    scl_mask = scl.eq(SCL_VALID[0])
    for c in SCL_VALID[1:]:
        scl_mask = scl_mask.Or(scl.eq(c))
    mask = ee.Image(ee.Algorithms.If(has_cs, cs_mask, scl_mask))
    ndvi = img.normalizedDifference(["B8", "B4"]).rename("ndvi")
    return ndvi.updateMask(mask).copyProperties(img, ["system:time_start"])


def monthly_s2_collection(cfg: GeeConfig, region: Any, start: str, end: str) -> Any:
    """Collection S2 SR filtrée et liée à Cloud Score+."""
    import ee

    s2 = ee.ImageCollection(cfg.s2_collection).filterBounds(region).filterDate(start, end)
    cs = ee.ImageCollection(cfg.cloud_score_collection)
    return s2.linkCollection(cs, [cfg.cs_band])


def monthly_ndvi_image(cfg: GeeConfig, region: Any, start: str, end: str) -> Any:
    """Composite mensuel : médiane NDVI, nombre d'observations valides, pixel valide (0/1).

    Les bandes `n_obs` et `valid` sont définies sur tous les pixels végétation
    (0 quand aucune observation), afin que leur moyenne par cellule donne la part
    de pixels valides.
    """
    import ee

    veg = vegetation_mask(cfg)
    coll = monthly_s2_collection(cfg, region, start, end).map(lambda i: _mask_image(i, cfg))
    ndvi = coll.select("ndvi").median().rename("ndvi")
    n_obs = coll.select("ndvi").count().unmask(0).rename("n_obs")
    valid = n_obs.gt(0).rename("valid")
    empty = ee.Image.constant([0, 0, 0]).rename(["ndvi", "n_obs", "valid"]).updateMask(
        ee.Image.constant([0, 1, 1]))
    img = ee.Image(ee.Algorithms.If(coll.size().gt(0),
                                    ndvi.addBands([n_obs, valid]), empty))
    return img.updateMask(veg).toFloat()


def monthly_cloud_stats(cfg: GeeConfig, region: Any, start: str, end: str) -> Any:
    """Statistiques nuageuses d'un mois : nombre d'images et couverture nuageuse moyenne."""
    import ee

    s2 = ee.ImageCollection(cfg.s2_collection).filterBounds(region).filterDate(start, end)
    return ee.Dictionary({
        "n_images": s2.size(),
        "cloud_pct_mean": s2.aggregate_mean("CLOUDY_PIXEL_PERCENTAGE"),
    })
