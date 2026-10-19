"""Le bloc résultats du README reprend exactement les valeurs des JSON."""

from __future__ import annotations

from maamora.reporting.report import results_markdown


def _metric(r2: float) -> dict:
    return {"r2": r2, "rmse": 0.05, "mae": 0.04, "n": 100}


def test_results_markdown_uses_json_values():
    models = ["climate_only", "climate_persistence", "climatology", "persistence"]
    metrics = {
        "window": {"start": "2023-10", "end": "2026-09", "n_months": 36},
        "split": {"train_months": ["2023-10", "2025-12"], "test_months": ["2026-01", "2026-09"],
                  "n_train_rows": 10, "n_test_rows": 5, "n_test_common_rows": 4},
        "n_cells": 12,
        "test": {"common_rows": {m: _metric(0.123) for m in models},
                 "all_valid_rows": {m: _metric(0.456) for m in models},
                 "aoi_monthly_mean": {m: _metric(0.789) for m in models}},
        "variants": {v: {"cv_random_train": {"pooled": _metric(0.9)},
                         "cv_spatial_blocks_train": {"pooled": _metric(0.7)}}
                     for v in models[:2]},
    }
    pr = {"pure_premium": 12345.0, "pure_rate_pct": 1.2345, "risk_loading": 50000.0,
          "technical_premium": 62345.0, "std": 1.0, "var": 2.0, "tvar": 3.0,
          "prob_payout": 0.2}
    ins = {"contract": {"trigger_percentile": 30, "exit_percentile": 5, "trigger_mm": 300.0,
                        "exit_mm": 200.0, "sum_insured_mad": 1e6},
           "pricing": {"gamma": pr, "bootstrap": pr},
           "index": {"definition": "x", "n_seasons": 45, "first_season": 1982,
                     "last_season": 2026, "mean_mm": 400.0},
           "parameters": {"cost_of_capital": 0.06},
           "gamma_fit": {"ks_pvalue": 0.5},
           "trend_test": {"mann_kendall_tau": -0.1, "mann_kendall_pvalue": 0.3,
                          "ols_slope_mm_per_year": -1.0, "ols_pvalue": 0.2,
                          "significant_5pct": False},
           "burning_cost": {"mean_payout_mad": 10.0, "rate_pct": 0.001, "n_payout_years": 3}}
    md = results_markdown(metrics, ins)
    assert "0.123" in md and "0.456" in md and "0.789" in md
    assert "12 345 MAD" in md and "62 345 MAD" in md
    assert "0.200" in md  # écart CV aléatoire − spatial
    assert "pas de tendance significative" in md
