"""Figures de synthèse, docs/DATA.md et bloc « Résultats » du README, lus depuis les JSON."""

from __future__ import annotations

import json
import logging
from typing import Any

import geopandas as gpd
import pandas as pd

from maamora.config import PROJECT_ROOT, Config
from maamora.features.build import TARGET
from maamora.reporting.figures import plot_model, plot_timeseries

log = logging.getLogger(__name__)
START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"
LABELS = {"climate_only": "XGBoost climat seul",
          "climate_persistence": "XGBoost climat + persistance",
          "climatology": "Baseline climatologie", "persistence": "Baseline persistance (t−1)"}


def _f(x: Any, nd: int = 3) -> str:
    if x is None or (isinstance(x, float) and x != x):
        return "n/d"
    return f"{x:,.{nd}f}".replace(",", " ")


def _mad(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ") + " MAD"


def results_markdown(metrics: dict[str, Any], ins: dict[str, Any]) -> str:
    """Bloc Markdown des résultats ; chaque nombre provient des JSON."""
    t = metrics["test"]
    sp = metrics["split"]
    lines = [
        f"Fenêtre : **{metrics['window']['start']} → {metrics['window']['end']}** "
        f"({metrics['window']['n_months']} mois), **{metrics['n_cells']} cellules** de 500 m. "
        f"Entraînement {sp['train_months'][0]} → {sp['train_months'][1]} "
        f"({sp['n_train_rows']} lignes), test {sp['test_months'][0]} → {sp['test_months'][1]} "
        f"({sp['n_test_rows']} lignes valides, dont {sp['n_test_common_rows']} où tous les "
        "modèles sont définis).",
        "",
        "### Prédiction du NDVI sur la période de test (9 derniers mois)",
        "",
        "| Modèle | R² | RMSE | MAE | n | R² (toutes lignes valides) |",
        "|---|---|---|---|---|---|",
    ]
    for m, lab in LABELS.items():
        c, a = t["common_rows"][m], t["all_valid_rows"][m]
        lines.append(f"| {lab} | {_f(c['r2'])} | {_f(c['rmse'], 4)} | {_f(c['mae'], 4)} | "
                     f"{c['n']} | {_f(a['r2'])} (n={a['n']}) |")
    lines += ["", "R² de la moyenne mensuelle de l'AOI (9 points) : " + ", ".join(
        f"{LABELS[m]} {_f(v['r2'])}" for m, v in t["aoi_monthly_mean"].items()) + ".", "",
        "### Validation croisée sur l'entraînement : aléatoire vs blocs spatiaux de 5 km", "",
        "| Variante | R² KFold aléatoire | R² blocs spatiaux | Écart |", "|---|---|---|---|"]
    for name, v in metrics["variants"].items():
        r, s = v["cv_random_train"]["pooled"]["r2"], v["cv_spatial_blocks_train"]["pooled"]["r2"]
        lines.append(f"| {LABELS[name]} | {_f(r)} | {_f(s)} | {_f(r - s)} |")
    if "shap" in metrics:
        lines += ["", "### SHAP (échantillon du test)", ""]
        for name, v in metrics["shap"].items():
            lines.append(
                f"- **{LABELS[name]}** : feature la plus importante `{v['top_feature_overall']}`"
                f" ; décalage de pluie dominant `{v['dominant_rain_lag']}` "
                f"({v['dominant_rain_lag_months']} mois, rang {v['rank_of_dominant_rain_lag']}"
                f" toutes features confondues) ; feature pluie la plus importante "
                f"`{v['top_rain_feature']}`.")
    c, p = ins["contract"], ins["pricing"]
    g, b = p["gamma"], p["bootstrap"]
    tr = ins["trend_test"]
    bc = ins["burning_cost"]
    lines += [
        "", "### Assurance paramétrique sécheresse (illustratif)", "",
        f"Indice : {ins['index']['definition']}, {ins['index']['n_seasons']} saisons "
        f"({ins['index']['first_season']} → {ins['index']['last_season']}), moyenne "
        f"{_f(ins['index']['mean_mm'], 0)} mm. Déclencheur P{c['trigger_percentile']:g} = "
        f"**{_f(c['trigger_mm'], 0)} mm**, sortie P{c['exit_percentile']:g} = "
        f"**{_f(c['exit_mm'], 0)} mm**, capital **notionnel** {_mad(c['sum_insured_mad'])}.",
        "",
        "| Mesure | Loi gamma | Bootstrap |", "|---|---|---|",
        f"| Prime pure E[paiement] | {_mad(g['pure_premium'])} | {_mad(b['pure_premium'])} |",
        f"| Taux de prime pure | {_f(g['pure_rate_pct'], 2)} % | {_f(b['pure_rate_pct'], 2)} % |",
        f"| Chargement (CoC {100 * ins['parameters']['cost_of_capital']:g} % × "
        f"(VaR − E)) | {_mad(g['risk_loading'])} | {_mad(b['risk_loading'])} |",
        f"| **Prime technique** | **{_mad(g['technical_premium'])}** | "
        f"**{_mad(b['technical_premium'])}** |",
        f"| Écart-type | {_mad(g['std'])} | {_mad(b['std'])} |",
        f"| VaR 99 % | {_mad(g['var'])} | {_mad(b['var'])} |",
        f"| TVaR 99 % | {_mad(g['tvar'])} | {_mad(b['tvar'])} |",
        f"| Probabilité de paiement | {_f(100 * g['prob_payout'], 1)} % | "
        f"{_f(100 * b['prob_payout'], 1)} % |",
        "",
        f"Burning cost historique : {_mad(bc['mean_payout_mad'])} par an "
        f"({_f(bc['rate_pct'], 2)} %), {bc['n_payout_years']} saisons avec paiement. "
        f"Ajustement gamma : test KS p = {_f(ins['gamma_fit']['ks_pvalue'], 2)}. "
        f"Tendance de l'indice : Mann-Kendall τ = {_f(tr['mann_kendall_tau'], 2)} "
        f"(p = {_f(tr['mann_kendall_pvalue'], 3)}), pente OLS "
        f"{_f(tr['ols_slope_mm_per_year'], 2)} mm/an (p = {_f(tr['ols_pvalue'], 3)}) — "
        + ("tendance significative à 5 %." if tr["significant_5pct"]
           else "pas de tendance significative à 5 %."),
    ]
    br = ins.get("basis_risk", {})
    if br.get("available"):
        mo = br["monthly_rolling_index_vs_obs_ndvi_anomaly"]
        mm = br["monthly_rolling_index_vs_model_ndvi_anomaly"]
        lines += ["", f"Risque de base (fenêtre de 36 mois) : corrélation entre le cumul de pluie "
                  f"glissant sur {br['rolling_window_months']} mois et l'anomalie de NDVI "
                  f"observée r = {_f(mo['pearson_r'], 2)} (p = {_f(mo['pearson_p'], 3)}, "
                  f"n = {mo['n']}) ; avec l'anomalie prédite par le modèle climat seul "
                  f"r = {_f(mm['pearson_r'], 2)} (n = {mm['n']}). "
                  f"Seulement {len(br['seasons_in_window'])} saisons complètes dans la "
                  "fenêtre : ces corrélations sont indicatives."]
    return "\n".join(lines)


def data_markdown(cfg: Config) -> str:
    """docs/DATA.md : sources, cellules, mois valides, nuages."""
    d = cfg.data_dir
    grid = gpd.read_parquet(d / "grid.parquet")
    full = pd.read_parquet(d / "grid_full_stats.parquet")
    feats = pd.read_parquet(d / "features.parquet")
    clouds = pd.read_parquet(d / "clouds.parquet")
    win = json.loads((d / "window.json").read_text(encoding="utf-8"))
    per_cell = feats.groupby("cell_id")[TARGET].apply(lambda s: s.notna().mean())
    per_month = feats.groupby("month")[TARGET].apply(lambda s: s.notna().mean())
    cm = clouds.set_index("month").join(per_month.rename("valid_share"))
    rows = "\n".join(
        f"| {m} | {int(r.n_images)} | {_f(r.cloud_pct_mean, 1)} | {_f(100 * r.valid_share, 1)} |"
        for m, r in cm.iterrows())
    q = per_cell.quantile([0.1, 0.5, 0.9])
    return f"""# Données

> Fichier généré par `python -m maamora.cli report` à partir du cache `data/` (non versionné).

## Sources (Google Earth Engine)

| Donnée | Collection | Usage |
|---|---|---|
| Sentinel-2 L2A harmonisé | `{cfg.gee.s2_collection}` | NDVI = (B8 − B4)/(B8 + B4), échelle {cfg.gee.s2_scale_m:g} m |
| Cloud Score+ | `{cfg.gee.cloud_score_collection}` | masque nuages `{cfg.gee.cs_band}` ≥ {cfg.gee.cs_threshold} (SCL en secours) |
| ESA WorldCover 2021 | `{cfg.gee.worldcover}` | masque végétation, classes {cfg.gee.worldcover_classes} |
| CHIRPS journalier | `{cfg.gee.chirps}` | pluie mensuelle par cellule et historique AOI depuis {cfg.gee.chirps_history_start} |
| ERA5-Land mensuel | `{cfg.gee.era5}` | `{cfg.gee.era5_band}` (°C) |
| SRTM 30 m | `{cfg.gee.srtm}` | altitude, pente |
| OpenStreetMap (Overpass) | `landuse=forest`, nom « Maâmora » | contour de référence (ODbL) |

L'existence de chaque collection est vérifiée à chaque exécution (`data/collections_check.json`).

## Fenêtre et grille

- Fenêtre NDVI : **{win['start']} → {win['end']}** ({len(win['months'])} mois) ; dernier mois complet CHIRPS : {win.get('chirps_last_complete')}, Sentinel-2 : {win.get('s2_last_complete')}.
- Grille UTM 29N de {cfg.grid.resolution_m:g} m sur l'emprise : {len(full)} cellules, dont **{len(grid)}** retenues (≥ {100 * cfg.grid.min_veg_fraction:.0f} % arbres/arbustes WorldCover), soit {len(grid) * (cfg.grid.resolution_m / 1000) ** 2:.0f} km².
- Altitude moyenne {grid.elevation.mean():.0f} m, pente moyenne {grid.slope.mean():.1f}°.

## Validité de la cible NDVI

Un mois est valide pour une cellule si ≥ {100 * cfg.target.min_valid_fraction:.0f} % des pixels végétation ont au moins une observation non nuageuse et si le nombre moyen d'observations est ≥ {cfg.target.min_mean_obs:g}. Aucune interpolation.

- Part globale de couples cellule × mois valides : **{100 * feats[TARGET].notna().mean():.1f} %**.
- Part de mois valides par cellule : P10 = {100 * q.loc[0.1]:.0f} %, médiane = {100 * q.loc[0.5]:.0f} %, P90 = {100 * q.loc[0.9]:.0f} %.

## Couverture nuageuse par mois

`CLOUDY_PIXEL_PERCENTAGE` moyen des scènes Sentinel-2 intersectant l'AOI, et part des cellules valides.

| Mois | Scènes S2 | Nuages moyens (%) | Cellules valides (%) |
|---|---|---|---|
{rows}
"""


def run_report(cfg: Config) -> None:
    """Produit les figures de synthèse, DATA.md et met à jour le README."""
    d = cfg.data_dir
    metrics = json.loads((cfg.reports_dir / "metrics.json").read_text(encoding="utf-8"))
    ins = json.loads((cfg.reports_dir / "insurance_pricing.json").read_text(encoding="utf-8"))
    preds = pd.read_parquet(d / "predictions.parquet")
    plot_model(cfg, preds, TARGET)

    from xgboost import XGBRegressor

    from maamora.features.build import climate_features, persistence_features
    from maamora.model.train import MODELS_DIR, climatology_baseline

    feats = pd.read_parquet(d / "features.parquet")
    valid = feats[feats[TARGET].notna()].copy()
    for name, fn in [("climate_only", climate_features),
                     ("climate_persistence", persistence_features)]:
        m = XGBRegressor()
        m.load_model(MODELS_DIR / f"xgb_{name}.json")
        valid[name] = m.predict(valid[fn(cfg)])
    train_end = metrics["split"]["train_months"][1]
    valid["climatology"] = climatology_baseline(valid[valid.month <= train_end], valid)
    panel = valid.groupby("month")[[TARGET, "climate_only", "climate_persistence",
                                    "climatology"]].mean().rename(columns={TARGET: "observed"})
    plot_timeseries(cfg, panel, metrics["split"]["test_months"][0])

    (PROJECT_ROOT / "docs" / "DATA.md").write_text(data_markdown(cfg), encoding="utf-8")
    readme = PROJECT_ROOT / "README.md"
    block = f"{START}\n{results_markdown(metrics, ins)}\n{END}"
    if readme.exists():
        text = readme.read_text(encoding="utf-8")
        if START in text and END in text:
            text = text[: text.index(START)] + block + text[text.index(END) + len(END):]
            readme.write_text(text, encoding="utf-8")
            log.info("README : bloc résultats mis à jour")
            return
    (cfg.reports_dir / "results_block.md").write_text(block, encoding="utf-8")
    log.warning("README sans marqueurs : bloc écrit dans reports/results_block.md")
