"""Initialisation Earth Engine (identifiants stockés hors du repo, dans le profil utilisateur)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from maamora.config import Config, gee_project
from maamora.retry import with_retry

log = logging.getLogger(__name__)
_INITIALIZED = False


def init_ee(cfg: Config | None = None) -> None:
    """Initialise Earth Engine avec le projet de `GEE_PROJECT` (une seule fois)."""
    global _INITIALIZED
    if _INITIALIZED:
        return
    import ee

    retries = cfg.gee.max_retries if cfg else 6
    with_retry(lambda: ee.Initialize(project=gee_project()), max_retries=retries,
               label="ee.Initialize")
    _INITIALIZED = True


def check_connection() -> float:
    """Évalue une opération triviale côté serveur (1 + 1)."""
    import ee

    init_ee()
    return with_retry(lambda: ee.Number(1).add(1).getInfo(), label="test connexion")


def check_collections(cfg: Config, out: Path) -> dict[str, bool]:
    """Vérifie l'existence de chaque collection/image utilisée et écrit le résultat en JSON."""
    import ee

    init_ee(cfg)
    ids = {
        "s2": cfg.gee.s2_collection,
        "cloud_score_plus": cfg.gee.cloud_score_collection,
        "worldcover": cfg.gee.worldcover,
        "chirps": cfg.gee.chirps,
        "era5": cfg.gee.era5,
        "srtm": cfg.gee.srtm,
    }
    result: dict[str, bool] = {}
    for key, asset in ids.items():
        try:
            with_retry(lambda a=asset: ee.data.getAsset(a), max_retries=cfg.gee.max_retries,
                       label=f"getAsset {asset}")
            result[asset] = True
        except Exception as exc:  # noqa: BLE001
            log.error("Collection %s (%s) introuvable : %s", key, asset, exc)
            result[asset] = False
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    missing = [a for a, ok in result.items() if not ok]
    if missing:
        raise RuntimeError(f"Collections introuvables : {missing}")
    return result
