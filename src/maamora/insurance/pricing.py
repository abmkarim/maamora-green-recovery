"""Tarification : prime pure, chargement de risque (coût du capital), mesures de risque."""

from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from maamora.config import Config
from maamora.insurance.basis_risk import basis_risk
from maamora.insurance.index import seasonal_index
from maamora.insurance.montecarlo import simulate_bootstrap, simulate_gamma, trend_test
from maamora.insurance.payout import payout

log = logging.getLogger(__name__)


def risk_measures(payouts: npt.ArrayLike, var_level: float) -> dict[str, float]:
    """Espérance, écart-type, VaR, TVaR et probabilité de paiement."""
    x = np.asarray(payouts, dtype=float)
    var = float(np.quantile(x, var_level))
    tail = x[x >= var]
    return {
        "expected_payout": float(x.mean()),
        "std": float(x.std(ddof=1)),
        "var": var,
        "tvar": float(tail.mean()) if len(tail) else var,
        "prob_payout": float((x > 0).mean()),
        "prob_full_payout": float((x >= x.max()).mean()) if x.max() > 0 else 0.0,
    }


def price(payouts: npt.ArrayLike, sum_insured: float, cost_of_capital: float,
          var_level: float) -> dict[str, float]:
    """Prime pure = E[paiement] ; prime technique = pure + CoC × (VaR − prime pure)."""
    rm = risk_measures(payouts, var_level)
    capital = max(rm["var"] - rm["expected_payout"], 0.0)
    loading = cost_of_capital * capital
    technical = rm["expected_payout"] + loading
    return {**rm, "pure_premium": rm["expected_payout"], "risk_capital": capital,
            "risk_loading": loading, "technical_premium": technical,
            "pure_rate_pct": 100 * rm["expected_payout"] / sum_insured,
            "technical_rate_pct": 100 * technical / sum_insured}


def burning_cost(index: pd.Series, trigger: float, exit_: float, sum_insured: float
                 ) -> pd.DataFrame:
    """Paiements qu'aurait déclenchés la couverture chaque saison historique."""
    return pd.DataFrame({"season": index.index.astype(int), "index_mm": index.to_numpy(),
                         "payout_mad": payout(index.to_numpy(), trigger, exit_, sum_insured)})


def sensitivity(index: pd.Series, sims: dict[str, np.ndarray], triggers: list[float],
                exits: list[float], sum_insured: float) -> list[dict[str, Any]]:
    """Prime pure selon les percentiles historiques du déclencheur et de la sortie."""
    rows = []
    for tp in triggers:
        for ep in exits:
            if ep >= tp:
                continue
            t, e = np.percentile(index, tp), np.percentile(index, ep)
            row: dict[str, Any] = {"trigger_pct": tp, "exit_pct": ep, "trigger_mm": float(t),
                                   "exit_mm": float(e)}
            for name, s in sims.items():
                row[f"pure_premium_{name}"] = float(payout(s, t, e, sum_insured).mean())
            rows.append(row)
    return rows


def run_pricing(cfg: Config) -> dict[str, Any]:
    """Pipeline assurance complet ; écrit reports/insurance_pricing.json et les figures."""
    from maamora.model.train import write_json
    from maamora.reporting.figures import plot_insurance

    ic = cfg.insurance
    hist = pd.read_parquet(cfg.data_dir / "rain_history.parquet")
    index = seasonal_index(hist, ic.season_start_month, ic.season_end_month)
    trigger = float(np.percentile(index, ic.trigger_percentile))
    exit_ = float(np.percentile(index, ic.exit_percentile))
    si = ic.sum_insured_mad

    gamma_sims, gamma_params = simulate_gamma(index.to_numpy(), ic.n_simulations, cfg.seed)
    boot_sims = simulate_bootstrap(index.to_numpy(), ic.n_simulations, cfg.seed)
    sims = {"gamma": gamma_sims, "bootstrap": boot_sims}
    pays = {k: payout(v, trigger, exit_, si) for k, v in sims.items()}
    pricing = {k: price(v, si, ic.cost_of_capital, ic.var_level) for k, v in pays.items()}
    bc = burning_cost(index, trigger, exit_, si)
    sens = sensitivity(index, sims, ic.sensitivity_triggers, ic.sensitivity_exits, si)
    trend = trend_test(index.index.to_numpy(), index.to_numpy())

    br = _basis_risk(cfg, hist)
    result = {
        "disclaimer": "Illustratif : capital assuré notionnel, ceci n'est pas une offre "
                      "d'assurance.",
        "index": {"definition": f"Cumul CHIRPS mois {ic.season_start_month} → "
                                f"{ic.season_end_month}, moyenne AOI",
                  "n_seasons": int(len(index)), "first_season": int(index.index.min()),
                  "last_season": int(index.index.max()), "mean_mm": float(index.mean()),
                  "std_mm": float(index.std()), "min_mm": float(index.min()),
                  "max_mm": float(index.max())},
        "contract": {"sum_insured_mad": si, "sum_insured_is_notional": True,
                     "trigger_percentile": ic.trigger_percentile,
                     "exit_percentile": ic.exit_percentile,
                     "trigger_mm": trigger, "exit_mm": exit_},
        "parameters": {"n_simulations": ic.n_simulations, "seed": cfg.seed,
                       "cost_of_capital": ic.cost_of_capital, "var_level": ic.var_level},
        "gamma_fit": gamma_params,
        "trend_test": trend,
        "pricing": pricing,
        "burning_cost": {"mean_payout_mad": float(bc.payout_mad.mean()),
                         "rate_pct": float(100 * bc.payout_mad.mean() / si),
                         "n_payout_years": int((bc.payout_mad > 0).sum()),
                         "by_season": bc.to_dict(orient="records")},
        "sensitivity": sens,
        "basis_risk": br,
    }
    write_json(cfg.reports_dir / "insurance_pricing.json", result)
    plot_insurance(cfg, index, pays, bc, sens, trigger, exit_, br)
    log.info("Prime pure gamma = %.0f MAD, bootstrap = %.0f MAD",
             pricing["gamma"]["pure_premium"], pricing["bootstrap"]["pure_premium"])
    return result


def _basis_risk(cfg: Config, hist: pd.DataFrame) -> dict[str, Any]:
    """NDVI moyen AOI observé et prédit (modèle « climat seul ») sur toute la fenêtre."""
    from xgboost import XGBRegressor

    from maamora.features.build import TARGET, climate_features
    from maamora.model.train import MODELS_DIR

    feats_path = cfg.data_dir / "features.parquet"
    model_path = MODELS_DIR / "xgb_climate_only.json"
    if not (feats_path.exists() and model_path.exists()):
        return {"available": False, "reason": "features ou modèle absents"}
    feats = pd.read_parquet(feats_path)
    model = XGBRegressor()
    model.load_model(model_path)
    valid = feats[feats[TARGET].notna()].copy()
    valid["pred"] = model.predict(valid[climate_features(cfg)])
    agg = valid.groupby("month")[[TARGET, "pred"]].mean()
    window = json.loads((cfg.data_dir / "window.json").read_text(encoding="utf-8"))
    agg = agg.reindex(window["months"])
    out = basis_risk(hist, agg[TARGET], agg["pred"], cfg.insurance.season_start_month,
                     cfg.insurance.season_end_month, cfg.insurance.ndvi_peak_months)
    out["available"] = True
    out["note"] = ("Prédictions du modèle « climat seul » : en-échantillon sur les 27 mois "
                   "d'entraînement, hors-échantillon sur les 9 mois de test.")
    return out
