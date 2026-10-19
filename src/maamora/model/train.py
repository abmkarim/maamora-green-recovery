"""Entraînement XGBoost (deux variantes), baselines et métriques sur la période de test."""

from __future__ import annotations

import itertools
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from maamora.config import PROJECT_ROOT, Config
from maamora.features.build import TARGET, climate_features, persistence_features
from maamora.model.evaluate import cross_validate, regression_metrics
from maamora.model.split import inner_split, temporal_split

log = logging.getLogger(__name__)
VARIANTS = {"climate_only": climate_features, "climate_persistence": persistence_features}
MODELS_DIR = PROJECT_ROOT / "models"


def make_xgb(cfg: Config, **params: Any) -> XGBRegressor:
    """Régresseur XGBoost avec la graine et les paramètres fixes du projet."""
    return XGBRegressor(
        objective="reg:squarederror", tree_method="hist", n_jobs=-1,
        random_state=cfg.seed, subsample=cfg.model.subsample,
        colsample_bytree=cfg.model.colsample_bytree, **params,
    )


def tune(train: pd.DataFrame, features: list[str], cfg: Config) -> dict[str, Any]:
    """Recherche en grille sur la validation interne temporelle (derniers mois du train)."""
    months = sorted(train["month"].unique())
    fit_m, val_m = inner_split(months, cfg.model.n_inner_val_months)
    fit, val = train[train.month.isin(fit_m)], train[train.month.isin(val_m)]
    grid = cfg.model.param_grid
    keys = sorted(grid)
    results = []
    for combo in itertools.product(*(grid[k] for k in keys)):
        params = dict(zip(keys, combo, strict=True))
        params["max_depth"] = int(params.get("max_depth", 6))
        model = make_xgb(cfg, n_estimators=cfg.model.n_estimators_max,
                         early_stopping_rounds=cfg.model.early_stopping_rounds, **params)
        model.fit(fit[features], fit[TARGET], eval_set=[(val[features], val[TARGET])],
                  verbose=False)
        m = regression_metrics(val[TARGET], model.predict(val[features]))
        results.append({**params, "n_estimators": int(model.best_iteration) + 1, **m})
    best = min(results, key=lambda r: r["rmse"])
    log.info("Meilleurs hyperparamètres (validation interne) : %s", best)
    return {"best": best, "fit_months": fit_m, "val_months": val_m, "grid": results}


def best_params(tuning: dict[str, Any], cfg: Config) -> dict[str, Any]:
    """Hyperparamètres retenus (sans les métriques)."""
    keys = [*cfg.model.param_grid, "n_estimators"]
    return {k: tuning["best"][k] for k in keys}


def climatology_baseline(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    """Moyenne de la cellule pour le mois calendaire, apprise sur l'entraînement.

    Repli : moyenne de la cellule, puis moyenne globale.
    """
    tr = train.assign(cal=pd.PeriodIndex(train.month, freq="M").month)
    te = test.assign(cal=pd.PeriodIndex(test.month, freq="M").month)
    by_cal = tr.groupby(["cell_id", "cal"])[TARGET].mean().rename("clim")
    by_cell = tr.groupby("cell_id")[TARGET].mean().rename("cell_mean")
    out = te.join(by_cal, on=["cell_id", "cal"]).join(by_cell, on="cell_id")
    pred = out["clim"].fillna(out["cell_mean"]).fillna(tr[TARGET].mean())
    return pred.to_numpy()


def run_training(cfg: Config) -> dict[str, Any]:
    """Entraîne, évalue et écrit reports/metrics.json + data/predictions.parquet."""
    feats = pd.read_parquet(cfg.data_dir / "features.parquet")
    window = json.loads((cfg.data_dir / "window.json").read_text(encoding="utf-8"))
    train_m, test_m = temporal_split(window["months"], cfg.model.n_train_months,
                                     cfg.model.n_test_months)
    data = feats[feats[TARGET].notna()].copy()
    train = data[data.month.isin(train_m)].reset_index(drop=True)
    test = data[data.month.isin(test_m)].reset_index(drop=True)
    log.info("Train : %d lignes, test : %d lignes", len(train), len(test))
    MODELS_DIR.mkdir(exist_ok=True)

    preds = test[["cell_id", "month", "block_id", TARGET]].copy()
    preds["climatology"] = climatology_baseline(train, test)
    preds["persistence"] = test["ndvi_lag1"].to_numpy()
    variants: dict[str, Any] = {}
    for name, feat_fn in VARIANTS.items():
        features = feat_fn(cfg)
        tuning = tune(train, features, cfg)
        params = best_params(tuning, cfg)
        model = make_xgb(cfg, **params)
        model.fit(train[features], train[TARGET])
        model.save_model(MODELS_DIR / f"xgb_{name}.json")
        preds[name] = model.predict(test[features])
        log.info("CV spatiale vs aléatoire (%s)", name)
        cv_params = {**params}
        spatial = cross_validate(train, features, TARGET, lambda p=cv_params: make_xgb(cfg, **p),
                                 cfg.model.n_spatial_folds, train["block_id"], cfg.seed)
        random_cv = cross_validate(train, features, TARGET,
                                   lambda p=cv_params: make_xgb(cfg, **p),
                                   cfg.model.n_spatial_folds, None, cfg.seed)
        variants[name] = {
            "features": features,
            "hyperparameters": params,
            "inner_validation": {k: tuning["best"][k] for k in ("r2", "rmse", "mae", "n")},
            "cv_random_train": {k: random_cv[k] for k in ("pooled", "fold_r2_mean",
                                                          "fold_r2_std")},
            "cv_spatial_blocks_train": {k: spatial[k] for k in ("pooled", "fold_r2_mean",
                                                                "fold_r2_std")},
        }
    preds.to_parquet(cfg.data_dir / "predictions.parquet", index=False)

    models = ["climate_only", "climate_persistence", "climatology", "persistence"]
    common = preds[models].notna().all(axis=1)
    test_metrics = {
        "all_valid_rows": {m: regression_metrics(preds[TARGET], preds[m]) for m in models},
        "common_rows": {m: regression_metrics(preds.loc[common, TARGET], preds.loc[common, m])
                        for m in models},
    }
    agg = preds.groupby("month")[[TARGET, *models]].mean()
    test_metrics["aoi_monthly_mean"] = {m: regression_metrics(agg[TARGET], agg[m])
                                        for m in models}
    metrics = {
        "window": {"start": window["start"], "end": window["end"],
                   "n_months": len(window["months"])},
        "split": {"train_months": [train_m[0], train_m[-1]], "test_months": [test_m[0],
                                                                             test_m[-1]],
                  "n_train_rows": int(len(train)), "n_test_rows": int(len(test)),
                  "n_test_common_rows": int(common.sum())},
        "n_cells": int(feats.cell_id.nunique()),
        "target_valid_share": float(feats[TARGET].notna().mean()),
        "test": test_metrics,
        "variants": variants,
    }
    write_json(cfg.reports_dir / "metrics.json", metrics, merge=True)
    log.info("Test (lignes communes) : %s", json.dumps(test_metrics["common_rows"], indent=1))
    return metrics


def write_json(path: Path, payload: dict[str, Any], merge: bool = False) -> None:
    """Écrit un JSON (fusion clé à clé avec l'existant si `merge`)."""
    data: dict[str, Any] = {}
    if merge and path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    data.update(payload)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=_default),
                    encoding="utf-8")


def _default(o: Any) -> Any:
    if isinstance(o, np.integer | np.floating):
        return o.item()
    return str(o)
