"""Risque de base : lien entre l'indice pluie et le déficit de NDVI observé/modélisé."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from maamora.insurance.index import season_label, season_months


def monthly_anomaly(series: pd.Series) -> pd.Series:
    """Anomalie mensuelle = valeur − moyenne du mois calendaire sur la série."""
    idx = pd.PeriodIndex(series.index, freq="M")
    s = pd.Series(series.to_numpy(), index=idx)
    return s - s.groupby(s.index.month).transform("mean")


def correlations(x: pd.Series, y: pd.Series) -> dict[str, Any]:
    """Corrélations de Pearson et Spearman sur les paires valides."""
    df = pd.concat([x, y], axis=1).dropna()
    if len(df) < 3:
        return {"n": int(len(df)), "pearson_r": None, "pearson_p": None,
                "spearman_rho": None, "spearman_p": None}
    p = stats.pearsonr(df.iloc[:, 0], df.iloc[:, 1])
    s = stats.spearmanr(df.iloc[:, 0], df.iloc[:, 1])
    return {"n": int(len(df)), "pearson_r": float(p.statistic), "pearson_p": float(p.pvalue),
            "spearman_rho": float(s.statistic), "spearman_p": float(s.pvalue)}


def basis_risk(rain_history: pd.DataFrame, ndvi_obs: pd.Series, ndvi_pred: pd.Series,
               start_month: int, end_month: int, peak_months: list[int]) -> dict[str, Any]:
    """Compare l'indice (version glissante mensuelle et saisonnière) au déficit de NDVI.

    - `ndvi_obs` / `ndvi_pred` : NDVI moyen de l'AOI par mois ('YYYY-MM'), observé et
      prédit par le modèle « climat seul ».
    - Mensuel : cumul de pluie glissant de la longueur de la saison vs anomalie NDVI.
    - Saisonnier : indice de chaque saison de la fenêtre vs anomalie NDVI moyenne des
      mois de pic `peak_months` qui suivent.
    """
    n_season = len(season_months(start_month, end_month))
    hist = rain_history.assign(month=pd.PeriodIndex(rain_history["month"], freq="M"))
    rain = hist.set_index("month")["rain_mm"]
    rolling = rain.rolling(n_season, min_periods=n_season).sum()
    obs_anom = monthly_anomaly(ndvi_obs)
    pred_anom = monthly_anomaly(ndvi_pred)
    roll_w = rolling.reindex(obs_anom.index)

    seasons = []
    obs_p = pd.Series(obs_anom.to_numpy(), index=obs_anom.index)
    pred_p = pd.Series(pred_anom.to_numpy(), index=pred_anom.index)
    for season in sorted({season_label(p, start_month, end_month) for p in obs_p.index}):
        sm = [pd.Period(f"{season - 1 if m >= start_month > end_month else season}-{m:02d}",
                        freq="M") for m in season_months(start_month, end_month)]
        if not all(m in rain.index for m in sm):
            continue
        peaks = [pd.Period(f"{season}-{m:02d}", freq="M") for m in peak_months]
        if not all(p in obs_p.index for p in peaks):
            continue
        seasons.append({
            "season": int(season), "index_mm": float(rain.loc[sm].sum()),
            "ndvi_anomaly_obs_peak": float(np.nanmean(obs_p.loc[peaks])),
            "ndvi_anomaly_pred_peak": float(np.nanmean(pred_p.loc[peaks])),
        })
    return {
        "monthly_rolling_index_vs_obs_ndvi_anomaly": correlations(roll_w, obs_anom),
        "monthly_rolling_index_vs_model_ndvi_anomaly": correlations(roll_w, pred_anom),
        "model_vs_obs_ndvi_anomaly": correlations(pred_anom, obs_anom),
        "seasons_in_window": seasons,
        "rolling_window_months": n_season,
        "limitations": (
            "Fenêtre NDVI de 36 mois : seulement quelques saisons complètes, corrélations "
            "saisonnières non significatives par construction ; anomalies calculées sur la "
            "même fenêtre courte ; NDVI moyen de l'AOI masque l'hétérogénéité spatiale ; "
            "le NDVI d'une forêt de chêne-liège réagit avec retard et partiellement à la pluie."
        ),
    }
