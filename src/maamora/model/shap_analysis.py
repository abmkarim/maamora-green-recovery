"""Analyse SHAP (TreeExplainer) des deux variantes sur la période de test."""

from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np
import pandas as pd
import shap
from xgboost import XGBRegressor

from maamora.config import Config
from maamora.features.build import TARGET
from maamora.model.split import temporal_split
from maamora.model.train import MODELS_DIR, VARIANTS, write_json

log = logging.getLogger(__name__)


def shap_values(model: XGBRegressor, X: pd.DataFrame) -> np.ndarray:
    """Valeurs SHAP exactes pour un modèle d'arbres."""
    return shap.TreeExplainer(model).shap_values(X)


def importance(values: np.ndarray, features: list[str]) -> dict[str, float]:
    """Importance globale : moyenne des |SHAP|, triée décroissante."""
    imp = np.abs(values).mean(axis=0)
    order = np.argsort(-imp)
    return {features[i]: float(imp[i]) for i in order}


def dominant_rain_lag(imp: dict[str, float]) -> dict[str, Any]:
    """Décalage de pluie (rain_lagk) au plus fort |SHAP| moyen et rang des features pluie."""
    lags = {k: v for k, v in imp.items() if k.startswith("rain_lag")}
    best = max(lags, key=lags.get)
    rain_all = {k: v for k, v in imp.items() if k.startswith(("rain_", "spi"))}
    ranks = {k: i + 1 for i, k in enumerate(imp)}
    return {"dominant_rain_lag": best, "dominant_rain_lag_months": int(best.removeprefix(
        "rain_lag")), "rain_lag_importance": lags,
        "top_rain_feature": max(rain_all, key=rain_all.get),
        "top_feature_overall": next(iter(imp)),
        "rank_of_dominant_rain_lag": ranks[best]}


def run_shap(cfg: Config) -> dict[str, Any]:
    """Calcule SHAP, écrit les figures et la section `shap` de metrics.json."""
    from maamora.reporting.figures import plot_shap

    feats = pd.read_parquet(cfg.data_dir / "features.parquet")
    window = json.loads((cfg.data_dir / "window.json").read_text(encoding="utf-8"))
    _, test_m = temporal_split(window["months"], cfg.model.n_train_months,
                               cfg.model.n_test_months)
    test = feats[feats.month.isin(test_m) & feats[TARGET].notna()]
    sample = test.sample(min(cfg.model.shap_sample, len(test)), random_state=cfg.seed)
    out: dict[str, Any] = {}
    for name, feat_fn in VARIANTS.items():
        features = feat_fn(cfg)
        model = XGBRegressor()
        model.load_model(MODELS_DIR / f"xgb_{name}.json")
        X = sample[features]
        vals = shap_values(model, X)
        imp = importance(vals, features)
        out[name] = {"mean_abs_shap": imp, **dominant_rain_lag(imp), "n_sample": len(X)}
        plot_shap(cfg, name, vals, X)
        log.info("SHAP %s : top = %s, décalage pluie dominant = %s", name,
                 out[name]["top_feature_overall"], out[name]["dominant_rain_lag"])
    write_json(cfg.reports_dir / "metrics.json", {"shap": out}, merge=True)
    return out
