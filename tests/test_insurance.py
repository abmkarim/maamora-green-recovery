"""Assurance : indice saisonnier, paiement, Monte Carlo, tarification, risque de base."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from maamora.insurance.basis_risk import basis_risk, monthly_anomaly
from maamora.insurance.index import season_label, season_months, seasonal_index
from maamora.insurance.montecarlo import simulate_bootstrap, simulate_gamma, trend_test
from maamora.insurance.payout import payout
from maamora.insurance.pricing import burning_cost, price, risk_measures, sensitivity

SI = 1_000_000.0


def test_payout_bounds_and_linearity():
    x = np.array([0.0, 50.0, 100.0, 150.0, 200.0, 400.0])
    p = payout(x, trigger=200, exit_=100, sum_insured=SI)
    assert p.min() >= 0 and p.max() <= SI
    assert p[0] == SI and p[1] == SI and p[2] == SI      # sous la sortie : capital total
    assert p[3] == pytest.approx(SI / 2)                 # linéaire
    assert p[4] == 0 and p[5] == 0                       # au-dessus du déclencheur


def test_payout_monotone_decreasing():
    x = np.linspace(0, 500, 1001)
    p = payout(x, 300, 120, SI)
    assert np.all(np.diff(p) <= 0)


def test_payout_invalid_thresholds():
    with pytest.raises(ValueError):
        payout([1.0], trigger=100, exit_=100, sum_insured=SI)


def test_season_definition():
    assert season_months(10, 4) == [10, 11, 12, 1, 2, 3, 4]
    assert season_label(pd.Period("2020-11", "M"), 10, 4) == 2021
    assert season_label(pd.Period("2021-03", "M"), 10, 4) == 2021
    months = pd.period_range("1981-01", "1983-12", freq="M")
    df = pd.DataFrame({"month": months.astype(str), "rain_mm": 10.0})
    idx = seasonal_index(df, 10, 4)
    # Saisons complètes : 1982 (oct. 81 → avr. 82) et 1983 ; 1981 incomplète.
    assert list(idx.index) == [1982, 1983]
    assert (idx == 70.0).all()


def test_monte_carlo_reproducible():
    hist = np.random.default_rng(5).gamma(8, 40, 45)
    a, pa = simulate_gamma(hist, 10_000, seed=42)
    b, pb = simulate_gamma(hist, 10_000, seed=42)
    np.testing.assert_array_equal(a, b)
    assert pa == pb
    c, _ = simulate_gamma(hist, 10_000, seed=43)
    assert not np.array_equal(a, c)
    np.testing.assert_array_equal(simulate_bootstrap(hist, 1000, 1),
                                  simulate_bootstrap(hist, 1000, 1))
    assert set(simulate_bootstrap(hist, 1000, 1)) <= set(hist)


def test_gamma_fit_recovers_mean():
    hist = np.random.default_rng(5).gamma(8, 40, 2000)
    sims, params = simulate_gamma(hist, 100_000, seed=1)
    assert sims.mean() == pytest.approx(320, rel=0.03)
    assert params["shape"] == pytest.approx(8, rel=0.15)


def test_pricing_measures():
    p = np.array([0.0] * 90 + [SI] * 10)
    rm = risk_measures(p, 0.99)
    assert rm["expected_payout"] == pytest.approx(SI / 10)
    assert rm["prob_payout"] == pytest.approx(0.1)
    assert rm["var"] == SI and rm["tvar"] == SI
    pr = price(p, SI, 0.06, 0.99)
    assert pr["technical_premium"] == pytest.approx(SI / 10 + 0.06 * (SI - SI / 10))
    assert pr["technical_premium"] >= pr["pure_premium"]


def test_burning_cost_and_sensitivity():
    idx = pd.Series([100.0, 300.0, 500.0], index=[2000, 2001, 2002])
    bc = burning_cost(idx, trigger=300, exit_=100, sum_insured=SI)
    assert list(bc.payout_mad) == [SI, 0.0, 0.0]
    hist = pd.Series(np.random.default_rng(0).gamma(8, 40, 40))
    sims = {"bootstrap": simulate_bootstrap(hist, 5000, 0)}
    s = pd.DataFrame(sensitivity(hist, sims, [20, 30, 40], [5], SI))
    # Prime croissante avec le percentile du déclencheur.
    assert s.pure_premium_bootstrap.is_monotonic_increasing


def test_trend_detects_trend():
    years = np.arange(1981, 2026)
    vals = 500 - 5 * (years - 1981) + np.random.default_rng(0).normal(0, 10, len(years))
    t = trend_test(years, vals)
    assert t["ols_slope_mm_per_year"] == pytest.approx(-5, abs=0.5)
    assert t["significant_5pct"]


def test_basis_risk_runs():
    months = pd.period_range("2015-01", "2026-09", freq="M")
    rng = np.random.default_rng(0)
    hist = pd.DataFrame({"month": months.astype(str), "rain_mm": rng.gamma(2, 25, len(months))})
    win = [str(m) for m in months[-36:]]
    obs = pd.Series(rng.normal(0.5, 0.05, 36), index=win)
    out = basis_risk(hist, obs, obs * 0.9, 10, 4, [3, 4, 5])
    assert out["model_vs_obs_ndvi_anomaly"]["pearson_r"] == pytest.approx(1.0)
    assert len(out["seasons_in_window"]) == 3
    assert monthly_anomaly(obs).groupby(pd.PeriodIndex(win, freq="M").month).mean().abs().max() \
        < 1e-12
