"""Indice paramétrique : cumul de pluie CHIRPS sur la saison des pluies, moyenné sur l'AOI."""

from __future__ import annotations

import pandas as pd


def season_months(start_month: int, end_month: int) -> list[int]:
    """Mois calendaires de la saison (peut chevaucher le changement d'année)."""
    if start_month <= end_month:
        return list(range(start_month, end_month + 1))
    return list(range(start_month, 13)) + list(range(1, end_month + 1))


def season_label(period: pd.Period, start_month: int, end_month: int) -> int:
    """Année de la saison = année du mois de fin (ex. oct. 2020 → avr. 2021 = 2021)."""
    if start_month > end_month and period.month >= start_month:
        return period.year + 1
    return period.year


def seasonal_index(monthly: pd.DataFrame, start_month: int, end_month: int) -> pd.Series:
    """Cumul saisonnier (mm) des saisons complètes uniquement.

    `monthly` : colonnes `month` ('YYYY-MM' ou Period) et `rain_mm`.
    """
    df = monthly.assign(month=pd.PeriodIndex(monthly["month"], freq="M"))
    months = season_months(start_month, end_month)
    df = df[df.month.dt.month.isin(months)].dropna(subset=["rain_mm"])
    df["season"] = [season_label(p, start_month, end_month) for p in df.month]
    g = df.groupby("season")["rain_mm"].agg(["sum", "count"])
    full = g[g["count"] == len(months)]["sum"]
    full.index.name = "season"
    return full.rename("index_mm")
