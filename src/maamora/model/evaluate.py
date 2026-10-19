"""Métriques et validations croisées (aléatoire vs blocs spatiaux)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, KFold


def regression_metrics(y_true: np.ndarray | pd.Series, y_pred: np.ndarray | pd.Series
                       ) -> dict[str, float]:
    """R², RMSE, MAE et effectif sur les paires non manquantes."""
    yt, yp = np.asarray(y_true, dtype=float), np.asarray(y_pred, dtype=float)
    ok = np.isfinite(yt) & np.isfinite(yp)
    yt, yp = yt[ok], yp[ok]
    if len(yt) < 2:
        return {"r2": float("nan"), "rmse": float("nan"), "mae": float("nan"), "n": int(len(yt))}
    return {
        "r2": float(r2_score(yt, yp)),
        "rmse": float(np.sqrt(mean_squared_error(yt, yp))),
        "mae": float(mean_absolute_error(yt, yp)),
        "n": int(len(yt)),
    }


def cross_validate(df: pd.DataFrame, features: list[str], target: str, make_model: Any,
                   n_folds: int, groups: pd.Series | None, seed: int) -> dict[str, Any]:
    """Validation croisée K-fold ; par groupes (blocs spatiaux) si `groups` est fourni.

    Renvoie les métriques par fold et leur moyenne (sur les prédictions hors-fold groupées).
    """
    X, y = df[features], df[target].to_numpy()
    if groups is not None:
        splitter = GroupKFold(n_splits=n_folds)
        splits = splitter.split(X, y, groups)
    else:
        splitter = KFold(n_splits=n_folds, shuffle=True, random_state=seed)
        splits = splitter.split(X, y)
    oof = np.full(len(y), np.nan)
    folds = []
    for tr, te in splits:
        model = make_model()
        model.fit(X.iloc[tr], y[tr])
        oof[te] = model.predict(X.iloc[te])
        folds.append(regression_metrics(y[te], oof[te]))
    pooled = regression_metrics(y, oof)
    return {
        "pooled": pooled,
        "fold_r2_mean": float(np.mean([f["r2"] for f in folds])),
        "fold_r2_std": float(np.std([f["r2"] for f in folds])),
        "folds": folds,
    }
