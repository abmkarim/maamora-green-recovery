"""Figures PNG (matplotlib, rendu hors écran) : carte, modèle, SHAP, assurance."""

from __future__ import annotations

from typing import Any

import matplotlib

matplotlib.use("Agg")
import geopandas as gpd  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from maamora.config import Config  # noqa: E402

# Palette catégorielle de référence (ordre fixe), encre et surface.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6"]
INK, INK_2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
SEQ = "Blues"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK_2, "xtick.color": INK_2,
    "ytick.color": INK_2, "text.color": INK, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
    "lines.linewidth": 2, "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
    "legend.frameon": False, "figure.dpi": 110,
})


def _save(fig: plt.Figure, cfg: Config, name: str) -> None:
    fig.tight_layout()
    fig.savefig(cfg.figures_dir / name, dpi=130)
    plt.close(fig)


# --------------------------------------------------------------------------- carte
def plot_aoi(cfg: Config, grid: gpd.GeoDataFrame) -> None:
    """Emprise d'étude, cellules retenues (part de végétation) et polygones OSM de référence."""
    aoi = gpd.read_file(cfg.path("aoi_file"))
    fig, ax = plt.subplots(figsize=(9, 6.5))
    grid.plot(ax=ax, column="veg_fraction", cmap=SEQ, vmin=0, vmax=1, linewidth=0.1,
              edgecolor=SURFACE, legend=True,
              legend_kwds={"label": "Part arbres + arbustes (WorldCover)", "shrink": 0.7})
    aoi.boundary.plot(ax=ax, color=INK, linewidth=1.2)
    osm_path = cfg.path("osm_reference_file")
    handles = [plt.Line2D([], [], color=INK, lw=1.2, label="Emprise d'étude")]
    if osm_path.exists():
        gpd.read_file(osm_path).boundary.plot(ax=ax, color=SERIES[1], linewidth=1.5)
        handles.append(plt.Line2D([], [], color=SERIES[1], lw=1.5,
                                  label="Polygones OSM « Forêt de la Maâmora »"))
    for name, lon, lat in [("Rabat-Salé", -6.80, 34.03), ("Kénitra", -6.58, 34.26)]:
        ax.plot(lon, lat, "o", color=INK, ms=4)
        ax.annotate(name, (lon, lat), xytext=(4, 4), textcoords="offset points", color=INK)
    ax.legend(handles=handles, loc="lower right")
    ax.set_title(f"Zone d'étude : {len(grid)} cellules de {cfg.grid.resolution_m:.0f} m")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect(1 / np.cos(np.deg2rad(34.15)))
    ax.annotate("Fond : © contributeurs OpenStreetMap (ODbL), ESA WorldCover 2021",
                (0, -0.12), xycoords="axes fraction", fontsize=7, color=INK_2)
    _save(fig, cfg, "aoi_map.png")


# --------------------------------------------------------------------------- modèle
def plot_model(cfg: Config, preds: pd.DataFrame, target: str) -> None:
    """Observé vs prédit (test) et séries mensuelles moyennes de l'AOI."""
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharex=True, sharey=True)
    for ax, (name, label) in zip(axes, [("climate_only", "Climat seul"),
                                        ("climate_persistence", "Climat + persistance")],
                                 strict=True):
        d = preds[[target, name]].dropna()
        ax.hexbin(d[target], d[name], gridsize=60, cmap=SEQ, mincnt=1, bins="log")
        lo, hi = np.nanpercentile(d.to_numpy(), [0.5, 99.5])
        ax.plot([lo, hi], [lo, hi], color=SERIES[1], lw=1.5, label="y = x")
        ax.set_title(f"{label} (test)")
        ax.set_xlabel("NDVI observé")
        ax.legend(loc="upper left")
    axes[0].set_ylabel("NDVI prédit")
    _save(fig, cfg, "observed_vs_predicted.png")


def plot_timeseries(cfg: Config, panel: pd.DataFrame, test_start: str) -> None:
    """NDVI moyen de l'AOI par mois : observé et modèles, période de test ombrée."""
    fig, ax = plt.subplots(figsize=(11, 4.4))
    x = pd.PeriodIndex(panel.index, freq="M").to_timestamp()
    series = [("observed", "Observé", INK), ("climate_only", "Climat seul", SERIES[0]),
              ("climate_persistence", "Climat + persistance", SERIES[1]),
              ("climatology", "Climatologie", SERIES[2])]
    for col, label, color in series:
        if col in panel:
            ax.plot(x, panel[col], label=label, color=color, marker="o", ms=4,
                    lw=2.4 if col == "observed" else 1.8)
    ax.axvspan(pd.Period(test_start, freq="M").to_timestamp(), x.max() + pd.Timedelta(days=20),
               color=GRID, alpha=0.6, lw=0, label="Période de test")
    ax.set_ylabel("NDVI moyen (cellules valides)")
    ax.set_title("NDVI mensuel moyen de l'AOI")
    ax.legend(ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    _save(fig, cfg, "ndvi_timeseries.png")


def plot_shap(cfg: Config, name: str, values: np.ndarray, X: pd.DataFrame) -> None:
    """Importance globale, beeswarm et dépendance des décalages de pluie."""
    import shap

    imp = pd.Series(np.abs(values).mean(axis=0), index=X.columns).sort_values()
    fig, ax = plt.subplots(figsize=(7, 0.32 * len(imp) + 1))
    colors = [SERIES[0] if c.startswith(("rain", "spi")) else INK_2 for c in imp.index]
    ax.barh(imp.index, imp.to_numpy(), color=colors, height=0.6)
    ax.set_xlabel("moyenne |SHAP| (NDVI)")
    ax.set_title(f"Importance SHAP — {name} (bleu = pluie)")
    ax.grid(axis="y", visible=False)
    _save(fig, cfg, f"shap_importance_{name}.png")

    plt.figure()
    shap.summary_plot(values, X, show=False, max_display=15, plot_size=(8, 6))
    fig = plt.gcf()
    fig.axes[0].set_title(f"SHAP beeswarm — {name}")
    _save(fig, cfg, f"shap_beeswarm_{name}.png")

    lags = [c for c in X.columns if c.startswith("rain_lag")]
    ncol = 4
    nrow = int(np.ceil(len(lags) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(12, 3 * nrow), sharey=True)
    axes = np.atleast_1d(axes).ravel()
    for ax, c in zip(axes, lags, strict=False):
        j = list(X.columns).index(c)
        ax.scatter(X[c], values[:, j], s=8, alpha=0.35, color=SERIES[0], lw=0)
        ax.axhline(0, color=INK_2, lw=0.8)
        ax.set_title(c)
        ax.set_xlabel("pluie (mm)")
    for ax in axes[len(lags):]:
        ax.set_visible(False)
    axes[0].set_ylabel("SHAP (NDVI)")
    fig.suptitle(f"Dépendance SHAP des décalages de pluie — {name}", fontweight="bold")
    _save(fig, cfg, f"shap_dependence_rain_{name}.png")


# --------------------------------------------------------------------------- assurance
def plot_insurance(cfg: Config, index: pd.Series, pays: dict[str, np.ndarray],
                   bc: pd.DataFrame, sens: list[dict[str, Any]], trigger: float,
                   exit_: float, br: dict[str, Any]) -> None:
    """Distribution des paiements, sensibilité, burning cost, indice historique."""
    si = cfg.insurance.sum_insured_mad
    # Distribution des paiements simulés (> 0).
    fig, ax = plt.subplots(figsize=(8, 4.4))
    bins = np.linspace(0, si, 41)
    for (name, p), color in zip(pays.items(), SERIES, strict=False):
        pos = p[p > 0]
        ax.hist(pos, bins=bins, histtype="step", lw=2, color=color,
                label=f"{name} : P(paiement) = {100 * (p > 0).mean():.1f} %",
                weights=np.full(len(pos), 1 / len(p)))
    ax.set_xlabel("Paiement (MAD, capital notionnel)")
    ax.set_ylabel("Probabilité (saisons simulées)")
    ax.set_title("Paiements simulés non nuls (100 000 saisons)")
    ax.legend()
    _save(fig, cfg, "payout_distribution.png")

    # Sensibilité.
    s = pd.DataFrame(sens)
    fig, ax = plt.subplots(figsize=(8, 4.4))
    for ep, color in zip(sorted(s.exit_pct.unique()), SERIES, strict=False):
        d = s[s.exit_pct == ep].sort_values("trigger_pct")
        ax.plot(d.trigger_pct, d.pure_premium_gamma, marker="o", ms=5, color=color,
                label=f"sortie P{ep:g}")
    ax.axvline(cfg.insurance.trigger_percentile, color=INK_2, lw=1, ls="--")
    ax.set_xlabel("Percentile historique du déclencheur")
    ax.set_ylabel("Prime pure (MAD, loi gamma)")
    ax.set_title("Sensibilité de la prime au déclencheur et à la sortie")
    ax.legend(ncol=3)
    _save(fig, cfg, "premium_sensitivity.png")

    # Burning cost + indice.
    fig, axes = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True,
                             gridspec_kw={"height_ratios": [3, 2]})
    ax = axes[0]
    ax.bar(bc.season, bc.index_mm, color=SERIES[0], width=0.8)
    ax.axhline(trigger, color=SERIES[1], lw=1.8, label=f"déclencheur {trigger:.0f} mm")
    ax.axhline(exit_, color=SERIES[3], lw=1.8, label=f"sortie {exit_:.0f} mm")
    ax.set_ylabel("Pluie oct.→avr. (mm)")
    ax.set_title("Indice saisonnier CHIRPS (moyenne AOI) et paiements historiques")
    ax.legend(loc="upper right")
    ax = axes[1]
    ax.bar(bc.season, bc.payout_mad / 1000, color=SERIES[1], width=0.8)
    ax.set_ylabel("Paiement (k MAD)")
    ax.set_xlabel("Saison (année de fin)")
    _save(fig, cfg, "burning_cost.png")

    seasons = br.get("seasons_in_window", []) if br.get("available") else []
    if seasons:
        d = pd.DataFrame(seasons)
        fig, ax = plt.subplots(figsize=(6, 4.4))
        ax.scatter(d.index_mm, d.ndvi_anomaly_obs_peak, s=60, color=SERIES[0],
                   label="NDVI observé (pic mars-mai)", zorder=3)
        ax.scatter(d.index_mm, d.ndvi_anomaly_pred_peak, s=60, color=SERIES[1],
                   marker="s", label="NDVI modèle climat seul", zorder=3)
        for _, r in d.iterrows():
            ax.annotate(str(int(r.season)), (r.index_mm, r.ndvi_anomaly_obs_peak),
                        xytext=(5, 5), textcoords="offset points")
        ax.axvline(trigger, color=INK_2, ls="--", lw=1, label="déclencheur")
        ax.axhline(0, color=INK_2, lw=0.8)
        ax.set_xlabel("Indice saisonnier (mm)")
        ax.set_ylabel("Anomalie NDVI (vs fenêtre)")
        ax.set_title("Risque de base : saisons de la fenêtre")
        ax.legend(fontsize=8)
        _save(fig, cfg, "basis_risk.png")
