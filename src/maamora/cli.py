"""Interface en ligne de commande : `python -m maamora.cli <commande>`."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Callable

from maamora.config import PROJECT_ROOT, Config, load_config

log = logging.getLogger("maamora")


def cmd_check_gee(cfg: Config) -> None:
    """Teste la connexion Earth Engine et l'existence des collections."""
    from maamora.gee.auth import check_collections, check_connection

    log.info("Connexion Earth Engine : 1 + 1 = %s", check_connection())
    check_collections(cfg, cfg.data_dir / "collections_check.json")
    log.info("Toutes les collections existent")


def cmd_build_aoi(cfg: Config) -> None:
    """Contour, grille et covariables statiques."""
    from maamora.gee.extract import get_grid, resolve_window
    from maamora.reporting.figures import plot_aoi

    cmd_check_gee(cfg)
    grid = get_grid(cfg)
    resolve_window(cfg)
    plot_aoi(cfg, grid)


def cmd_extract_s2(cfg: Config) -> None:
    """NDVI Sentinel-2 mensuel."""
    from maamora.gee.extract import extract_s2

    extract_s2(cfg)


def cmd_extract_chirps(cfg: Config) -> None:
    """Pluie CHIRPS par cellule et historique AOI."""
    from maamora.gee.extract import extract_chirps

    extract_chirps(cfg)


def cmd_extract_covariates(cfg: Config) -> None:
    """Température ERA5-Land."""
    from maamora.gee.extract import extract_covariates

    extract_covariates(cfg)


def cmd_build_features(cfg: Config) -> None:
    """Table de features."""
    from maamora.features.build import build_from_cache

    build_from_cache(cfg)


def cmd_train(cfg: Config) -> None:
    """Entraînement, baselines, CV spatiale, métriques."""
    from maamora.model.train import run_training

    run_training(cfg)


def cmd_shap(cfg: Config) -> None:
    """Analyse SHAP."""
    from maamora.model.shap_analysis import run_shap

    run_shap(cfg)


def cmd_price(cfg: Config) -> None:
    """Tarification de l'assurance paramétrique."""
    from maamora.insurance.pricing import run_pricing

    run_pricing(cfg)


def cmd_report(cfg: Config) -> None:
    """Figures de synthèse, DATA.md et section résultats du README."""
    from maamora.reporting.report import run_report

    run_report(cfg)


STEPS: dict[str, Callable[[Config], None]] = {
    "check-gee": cmd_check_gee,
    "build-aoi": cmd_build_aoi,
    "extract-s2": cmd_extract_s2,
    "extract-chirps": cmd_extract_chirps,
    "extract-covariates": cmd_extract_covariates,
    "build-features": cmd_build_features,
    "train": cmd_train,
    "shap": cmd_shap,
    "price": cmd_price,
    "report": cmd_report,
}
PIPELINE = ["build-aoi", "extract-s2", "extract-chirps", "extract-covariates",
            "build-features", "train", "shap", "price", "report"]


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée."""
    parser = argparse.ArgumentParser(prog="maamora", description=__doc__)
    parser.add_argument("command", choices=[*STEPS, "all"])
    parser.add_argument("--config", default=None, help="chemin du YAML de configuration")
    args = parser.parse_args(argv)
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s",
        handlers=[logging.StreamHandler(sys.stdout),
                  logging.FileHandler(log_dir / "pipeline.log", encoding="utf-8")],
    )
    cfg = load_config(args.config)
    steps = PIPELINE if args.command == "all" else [args.command]
    for name in steps:
        t0 = time.time()
        log.info("=== %s ===", name)
        STEPS[name](cfg)
        log.info("=== %s terminé en %.0fs ===", name, time.time() - t0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
