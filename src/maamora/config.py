"""Chargement de la configuration (YAML unique + variables d'environnement .env)."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "default.yaml"


class PathsConfig(BaseModel):
    """Chemins relatifs à la racine du projet."""

    data_dir: str = "data"
    reports_dir: str = "reports"
    figures_dir: str = "reports/figures"
    aoi_file: str = "aoi/maamora.geojson"
    osm_reference_file: str = "aoi/osm_maamora_partial.geojson"


class AoiConfig(BaseModel):
    """Paramètres de la zone d'étude."""

    osm_name_regex: str = "Ma[âa]?mora"
    overpass_urls: list[str] = Field(default_factory=list)
    osm_min_area_km2: float = 650.0
    fallback_bbox: tuple[float, float, float, float] = (-6.80, 34.00, -6.20, 34.35)
    utm_epsg: int = 32629


class GridConfig(BaseModel):
    """Grille d'analyse."""

    resolution_m: float = 500.0
    min_veg_fraction: float = 0.5
    spatial_block_m: float = 5000.0


class GeeConfig(BaseModel):
    """Collections et paramètres Earth Engine."""

    max_retries: int = 6
    backoff_base_s: float = 2.0
    batch_size: int = 1500
    tile_scale: int = 4
    s2_collection: str = "COPERNICUS/S2_SR_HARMONIZED"
    cloud_score_collection: str = "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"
    cs_band: str = "cs_cdf"
    cs_threshold: float = 0.60
    worldcover: str = "ESA/WorldCover/v200"
    worldcover_classes: list[int] = Field(default_factory=lambda: [10, 20])
    chirps: str = "UCSB-CHG/CHIRPS/DAILY"
    era5: str = "ECMWF/ERA5_LAND/MONTHLY_AGGR"
    era5_band: str = "temperature_2m"
    srtm: str = "USGS/SRTMGL1_003"
    s2_scale_m: float = 20.0
    chirps_scale_m: float = 5566.0
    era5_scale_m: float = 11132.0
    chirps_history_start: str = "1981-01"


class WindowConfig(BaseModel):
    """Fenêtre d'étude NDVI."""

    n_months: int = 36
    end_month: str | None = None


class TargetConfig(BaseModel):
    """Règles de validité de la cible NDVI."""

    min_valid_fraction: float = 0.3
    min_mean_obs: float = 1.0


class FeaturesConfig(BaseModel):
    """Paramètres des features."""

    rain_lags: list[int] = Field(default_factory=lambda: list(range(7)))
    rain_cumuls: list[int] = Field(default_factory=lambda: [3, 6, 12])
    temp_lags: list[int] = Field(default_factory=lambda: [0, 1, 2])
    ndvi_persistence_lags: list[int] = Field(default_factory=lambda: [1, 12])


class ModelConfig(BaseModel):
    """Paramètres du modèle et de l'évaluation."""

    n_train_months: int = 27
    n_test_months: int = 9
    n_inner_val_months: int = 6
    param_grid: dict[str, list[float | int]] = Field(default_factory=dict)
    n_estimators_max: int = 1500
    early_stopping_rounds: int = 50
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    n_spatial_folds: int = 5
    shap_sample: int = 5000


class InsuranceConfig(BaseModel):
    """Paramètres de l'assurance paramétrique."""

    season_start_month: int = 10
    season_end_month: int = 4
    trigger_percentile: float = 30.0
    exit_percentile: float = 5.0
    sum_insured_mad: float = 1_000_000.0
    n_simulations: int = 100_000
    cost_of_capital: float = 0.06
    var_level: float = 0.99
    sensitivity_triggers: list[float] = Field(default_factory=lambda: [20, 25, 30, 35, 40])
    sensitivity_exits: list[float] = Field(default_factory=lambda: [1, 3, 5, 8, 10])
    ndvi_peak_months: list[int] = Field(default_factory=lambda: [3, 4, 5])


class Config(BaseModel):
    """Configuration complète du projet."""

    seed: int = 42
    paths: PathsConfig = Field(default_factory=PathsConfig)
    aoi: AoiConfig = Field(default_factory=AoiConfig)
    grid: GridConfig = Field(default_factory=GridConfig)
    gee: GeeConfig = Field(default_factory=GeeConfig)
    window: WindowConfig = Field(default_factory=WindowConfig)
    target: TargetConfig = Field(default_factory=TargetConfig)
    features: FeaturesConfig = Field(default_factory=FeaturesConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    insurance: InsuranceConfig = Field(default_factory=InsuranceConfig)

    def path(self, name: str) -> Path:
        """Renvoie le chemin absolu d'une entrée de `paths`."""
        return PROJECT_ROOT / getattr(self.paths, name)

    @property
    def data_dir(self) -> Path:
        """Répertoire de cache des données (créé si besoin)."""
        p = self.path("data_dir")
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def reports_dir(self) -> Path:
        """Répertoire des rapports (créé si besoin)."""
        p = self.path("reports_dir")
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def figures_dir(self) -> Path:
        """Répertoire des figures (créé si besoin)."""
        p = self.path("figures_dir")
        p.mkdir(parents=True, exist_ok=True)
        return p


def load_config(path: Path | str | None = None) -> Config:
    """Charge la configuration YAML et le fichier .env (sans jamais l'afficher)."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    cfg_path = Path(path) if path else Path(os.environ.get("MAAMORA_CONFIG", DEFAULT_CONFIG))
    with cfg_path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return Config.model_validate(raw)


def gee_project() -> str:
    """Identifiant du projet Earth Engine lu dans l'environnement."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    project = os.environ.get("GEE_PROJECT", "").strip()
    if not project:
        raise RuntimeError("GEE_PROJECT absent : renseignez-le dans .env (voir .env.example)")
    return project
