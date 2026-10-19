"""Construction des features : décalages, cumuls, SPI-3, saisonnalité, persistance NDVI.

Toutes les opérations temporelles se font sur un index mensuel complet (pas de saut de
mois), avec des décalages vers le passé uniquement : la feature du mois t n'utilise que
des données des mois <= t.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from scipy import stats

from maamora.config import Config

log = logging.getLogger(__name__)

RAIN_COL, TEMP_COL, NDVI_COL = "rain_mm", "t2m_c", "ndvi"
TARGET = "ndvi_target"


def _wide(df: pd.DataFrame, value: str, months: pd.PeriodIndex) -> pd.DataFrame:
    """Tableau mois × cellule sur un index mensuel complet."""
    w = df.assign(month=pd.PeriodIndex(df["month"], freq="M")).pivot_table(
        index="month", columns="cell_id", values=value, aggfunc="mean")
    return w.reindex(months)


def _long(w: pd.DataFrame, name: str) -> pd.Series:
    s = w.stack(future_stack=True)
    s.index = s.index.set_names(["month", "cell_id"])
    return s.rename(name)


def lag_features(df: pd.DataFrame, value: str, lags: list[int], prefix: str,
                 cumuls: list[int] | None = None) -> pd.DataFrame:
    """Décalages (t−k) et cumuls glissants terminés en t, par cellule.

    Renvoie un DataFrame indexé (month: Period, cell_id).
    """
    p = pd.PeriodIndex(df["month"], freq="M")
    months = pd.period_range(p.min(), p.max(), freq="M")
    w = _wide(df, value, months)
    cols = [_long(w.shift(k), f"{prefix}_lag{k}") for k in lags]
    for n in cumuls or []:
        cols.append(_long(w.rolling(n, min_periods=n).sum(), f"{prefix}_cum{n}"))
    return pd.concat(cols, axis=1)


def spi(series: pd.Series, scale: int, fit_end: pd.Period) -> pd.Series:
    """Indice standardisé de précipitation (SPI) sur `scale` mois.

    `series` : pluie mensuelle indexée par Period mensuelle (continue). La loi gamma
    (avec probabilité de zéro) est ajustée, par mois calendaire, sur les mois <= `fit_end`.
    """
    s = series.sort_index()
    acc = s.rolling(scale, min_periods=scale).sum()
    out = pd.Series(np.nan, index=acc.index, name=f"spi{scale}")
    cal = acc.index.month
    for m in range(1, 13):
        sel = cal == m
        fit = acc[sel & (acc.index <= fit_end)].dropna()
        x = acc[sel]
        if len(fit) < 10:
            continue
        q0 = float((fit <= 0).mean())
        pos = fit[fit > 0]
        if len(pos) >= 5 and pos.nunique() > 2:
            a, loc, sc = stats.gamma.fit(pos.to_numpy(), floc=0)
            cdf = q0 + (1 - q0) * stats.gamma.cdf(x.clip(lower=0), a, loc=loc, scale=sc)
        else:
            cdf = x.apply(lambda v, f=fit: (f <= v).mean())
        out[sel] = stats.norm.ppf(np.clip(np.asarray(cdf, dtype=float), 1e-6, 1 - 1e-6))
        out[sel & acc.isna().to_numpy()] = np.nan
    return out


def clean_target(ndvi: pd.DataFrame, min_valid_fraction: float, min_mean_obs: float
                 ) -> pd.DataFrame:
    """NDVI cible : manquant si observations insuffisantes (aucune interpolation)."""
    out = ndvi.copy()
    ok = (out["valid_fraction"] >= min_valid_fraction) & (out["n_obs"] >= min_mean_obs)
    out[TARGET] = out[NDVI_COL].where(ok)
    return out


def build_features(
    ndvi: pd.DataFrame,
    rain: pd.DataFrame,
    temp: pd.DataFrame,
    rain_history: pd.DataFrame,
    static: pd.DataFrame,
    window_months: list[str],
    cfg: Config,
) -> pd.DataFrame:
    """Table cellule × mois de la fenêtre avec cible et features.

    - `ndvi` : cell_id, month, ndvi, n_obs, valid_fraction
    - `rain` / `temp` : cell_id, month, rain_mm / t2m_c (historique avant fenêtre inclus)
    - `rain_history` : month, rain_mm (moyenne AOI, 1981 →)
    - `static` : cell_id, elevation, slope, block_id, ...
    """
    fc = cfg.features
    win = pd.PeriodIndex(window_months, freq="M")
    tgt = clean_target(ndvi, cfg.target.min_valid_fraction, cfg.target.min_mean_obs)

    rain_f = lag_features(rain, RAIN_COL, fc.rain_lags, "rain", fc.rain_cumuls)
    temp_f = lag_features(temp, TEMP_COL, fc.temp_lags, "t2m")
    ndvi_f = lag_features(tgt.rename(columns={TARGET: "ndvi_t"}), "ndvi_t",
                          fc.ndvi_persistence_lags, "ndvi")

    hist = rain_history.assign(month=pd.PeriodIndex(rain_history["month"], freq="M"))
    hist = hist.set_index("month")[RAIN_COL]
    hist = hist.reindex(pd.period_range(hist.index.min(), hist.index.max(), freq="M"))
    # Ajustement du SPI strictement avant la fenêtre : aucune information future.
    spi3 = spi(hist, 3, fit_end=win.min() - 1).rename("spi3")

    cells = static["cell_id"].unique()
    idx = pd.MultiIndex.from_product([win, cells], names=["month", "cell_id"])
    panel = pd.DataFrame(index=idx)
    target = tgt.assign(month=pd.PeriodIndex(tgt["month"], freq="M")).set_index(
        ["month", "cell_id"])[[TARGET, "valid_fraction", "n_obs"]]
    panel = panel.join(target).join(rain_f).join(temp_f).join(ndvi_f)
    panel = panel.reset_index()
    panel = panel.merge(spi3.reset_index().rename(columns={"index": "month"}), on="month",
                        how="left")
    mo = panel["month"].dt.month
    panel["month_sin"] = np.sin(2 * np.pi * mo / 12)
    panel["month_cos"] = np.cos(2 * np.pi * mo / 12)
    keep_static = [c for c in ["cell_id", "elevation", "slope", "block_id", "x", "y"]
                   if c in static]
    panel = panel.merge(static[keep_static], on="cell_id", how="left")
    return panel.sort_values(["month", "cell_id"]).reset_index(drop=True)


def climate_features(cfg: Config) -> list[str]:
    """Features de la variante « climat seul »."""
    fc = cfg.features
    return ([f"rain_lag{k}" for k in fc.rain_lags] + [f"rain_cum{n}" for n in fc.rain_cumuls]
            + ["spi3"] + [f"t2m_lag{k}" for k in fc.temp_lags]
            + ["month_sin", "month_cos", "elevation", "slope"])


def persistence_features(cfg: Config) -> list[str]:
    """Features de la variante « climat + persistance »."""
    return climate_features(cfg) + [f"ndvi_lag{k}" for k in cfg.features.ndvi_persistence_lags]


def build_from_cache(cfg: Config) -> pd.DataFrame:
    """Lit les extractions en cache et écrit data/features.parquet."""
    import json

    import geopandas as gpd

    d = cfg.data_dir
    win = json.loads((d / "window.json").read_text(encoding="utf-8"))
    static = pd.DataFrame(gpd.read_parquet(d / "grid.parquet").drop(columns="geometry"))
    feats = build_features(
        ndvi=pd.read_parquet(d / "ndvi.parquet"),
        rain=pd.read_parquet(d / "rain_cells.parquet"),
        temp=pd.read_parquet(d / "t2m_cells.parquet"),
        rain_history=pd.read_parquet(d / "rain_history.parquet"),
        static=static,
        window_months=win["months"],
        cfg=cfg,
    )
    out = feats.assign(month=feats["month"].astype(str))
    out.to_parquet(d / "features.parquet", index=False)
    log.info("Features : %d lignes, %d cibles valides", len(out), out[TARGET].notna().sum())
    return feats
