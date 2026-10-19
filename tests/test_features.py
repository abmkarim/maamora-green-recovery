"""Features : décalages corrects, cumuls, SPI, et absence de fuite temporelle."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from maamora.features.build import (
    TARGET,
    build_features,
    clean_target,
    climate_features,
    lag_features,
    persistence_features,
    spi,
)


def _build(s: dict, cfg) -> pd.DataFrame:
    return build_features(s["ndvi"], s["rain"], s["temp"], s["hist"], s["static"],
                          s["window"], cfg)


def test_lag_values_are_past_values():
    df = pd.DataFrame({"cell_id": "a", "month": [str(pd.Period("2020-01", "M") + k)
                                                 for k in range(10)],
                       "v": np.arange(10.0)})
    f = lag_features(df, "v", [0, 1, 3], "v", cumuls=[3]).xs("a", level="cell_id")
    assert f.loc[pd.Period("2020-05", "M"), "v_lag0"] == 4
    assert f.loc[pd.Period("2020-05", "M"), "v_lag1"] == 3
    assert f.loc[pd.Period("2020-05", "M"), "v_lag3"] == 1
    assert f.loc[pd.Period("2020-05", "M"), "v_cum3"] == 4 + 3 + 2
    assert np.isnan(f.loc[pd.Period("2020-02", "M"), "v_lag3"])


def test_lag_respects_calendar_gaps():
    """Un mois absent ne doit pas décaler les lags d'une ligne mais d'un mois."""
    df = pd.DataFrame({"cell_id": "a", "month": ["2020-01", "2020-02", "2020-04"],
                       "v": [1.0, 2.0, 4.0]})
    f = lag_features(df, "v", [1], "v").xs("a", level="cell_id")
    assert np.isnan(f.loc[pd.Period("2020-04", "M"), "v_lag1"])


def test_no_future_information(synthetic, cfg):
    """Perturber toutes les données postérieures au mois t ne change aucune feature <= t."""
    base = _build(synthetic, cfg)
    cut = synthetic["window"][20]
    pert = {k: (v.copy() if isinstance(v, pd.DataFrame) else v) for k, v in synthetic.items()}
    rng = np.random.default_rng(1)
    for key, col in [("rain", "rain_mm"), ("temp", "t2m_c"), ("ndvi", "ndvi"),
                     ("hist", "rain_mm")]:
        df = pert[key]
        fut = df["month"] > cut
        df.loc[fut, col] = rng.uniform(0, 500, fut.sum())
    pert["ndvi"].loc[pert["ndvi"].month > cut, "valid_fraction"] = 1.0
    after = _build(pert, cfg)
    feats = persistence_features(cfg)
    mask = base["month"].astype(str) <= cut
    pd.testing.assert_frame_equal(base.loc[mask, feats], after.loc[mask, feats])
    # Contrôle : la perturbation a bien modifié des features postérieures.
    assert not base.loc[~mask, feats].equals(after.loc[~mask, feats])


def test_target_not_interpolated(synthetic, cfg):
    t = clean_target(synthetic["ndvi"], 0.3, 1.0)
    bad = (synthetic["ndvi"].valid_fraction < 0.3) | (synthetic["ndvi"].n_obs < 1)
    assert t.loc[bad, TARGET].isna().all()
    assert t.loc[~bad, TARGET].notna().all()


def test_panel_shape_and_columns(synthetic, cfg):
    f = _build(synthetic, cfg)
    assert len(f) == 6 * 36
    for c in persistence_features(cfg):
        assert c in f.columns
    assert set(climate_features(cfg)) < set(persistence_features(cfg))
    assert not any(c.startswith("ndvi") for c in climate_features(cfg))
    # Les cumuls 12 mois sont définis dès le début de la fenêtre (historique extrait).
    assert f["rain_cum12"].notna().all()


def test_spi_standardised():
    rng = np.random.default_rng(3)
    idx = pd.period_range("1981-01", "2020-12", freq="M")
    s = pd.Series(rng.gamma(2, 25, len(idx)), index=idx)
    out = spi(s, 3, fit_end=idx[-1])
    assert out.iloc[:2].isna().all()
    assert out.mean() == pytest.approx(0, abs=0.1)
    assert out.std() == pytest.approx(1, abs=0.1)
