"""Simulation Monte Carlo de l'indice saisonnier : loi gamma ajustée et bootstrap empirique."""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt
from scipy import stats


def fit_gamma(history: npt.ArrayLike) -> dict[str, float]:
    """Ajuste une loi gamma (loc = 0) par maximum de vraisemblance, avec test KS."""
    x = np.asarray(history, dtype=float)
    a, loc, scale = stats.gamma.fit(x, floc=0)
    ks = stats.kstest(x, "gamma", args=(a, loc, scale))
    return {"shape": float(a), "loc": float(loc), "scale": float(scale),
            "ks_stat": float(ks.statistic), "ks_pvalue": float(ks.pvalue)}


def simulate_gamma(history: npt.ArrayLike, n: int, seed: int) -> tuple[np.ndarray, dict]:
    """`n` saisons tirées dans la loi gamma ajustée sur l'historique."""
    params = fit_gamma(history)
    rng = np.random.default_rng(seed)
    sims = stats.gamma.rvs(params["shape"], loc=params["loc"], scale=params["scale"],
                           size=n, random_state=rng)
    return sims, params


def simulate_bootstrap(history: npt.ArrayLike, n: int, seed: int) -> np.ndarray:
    """`n` saisons tirées avec remise dans l'historique observé."""
    rng = np.random.default_rng(seed)
    return rng.choice(np.asarray(history, dtype=float), size=n, replace=True)


def trend_test(years: npt.ArrayLike, values: npt.ArrayLike) -> dict[str, Any]:
    """Tendance de l'indice : Mann-Kendall (tau de Kendall) et régression OLS."""
    import statsmodels.api as sm

    y = np.asarray(values, dtype=float)
    t = np.asarray(years, dtype=float)
    tau = stats.kendalltau(t, y)
    ols = sm.OLS(y, sm.add_constant(t)).fit()
    return {
        "mann_kendall_tau": float(tau.statistic), "mann_kendall_pvalue": float(tau.pvalue),
        "ols_slope_mm_per_year": float(ols.params[1]), "ols_pvalue": float(ols.pvalues[1]),
        "ols_slope_ci95": [float(v) for v in ols.conf_int()[1]],
        "significant_5pct": bool(min(tau.pvalue, ols.pvalues[1]) < 0.05),
    }
