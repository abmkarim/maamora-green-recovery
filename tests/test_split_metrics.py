"""Découpe temporelle, métriques, baselines et validation croisée."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LinearRegression

from maamora.features.build import TARGET
from maamora.model.evaluate import cross_validate, regression_metrics
from maamora.model.split import inner_split, temporal_split
from maamora.model.train import climatology_baseline

MONTHS = [str(pd.Period("2023-10", "M") + k) for k in range(36)]


def test_temporal_split_27_9():
    train, test = temporal_split(MONTHS[::-1], 27, 9)
    assert len(train) == 27 and len(test) == 9
    assert max(train) < min(test)
    assert test == MONTHS[-9:]
    assert not set(train) & set(test)


def test_temporal_split_rejects_wrong_length():
    with pytest.raises(ValueError):
        temporal_split(MONTHS[:30], 27, 9)


def test_inner_split_uses_last_train_months():
    train, _ = temporal_split(MONTHS, 27, 9)
    fit, val = inner_split(train, 6)
    assert val == train[-6:] and max(fit) < min(val)


def test_metrics_perfect_and_known():
    y = np.array([1.0, 2.0, 3.0, 4.0])
    m = regression_metrics(y, y)
    assert m["r2"] == 1 and m["rmse"] == 0 and m["mae"] == 0 and m["n"] == 4
    m = regression_metrics(y, y + 1)
    assert m["rmse"] == pytest.approx(1) and m["mae"] == pytest.approx(1)
    assert m["r2"] == pytest.approx(1 - 4 / 5)


def test_metrics_ignore_nan():
    m = regression_metrics([1.0, 2.0, np.nan, 4.0], [1.0, 2.0, 3.0, np.nan])
    assert m["n"] == 2


def test_climatology_baseline():
    train = pd.DataFrame({"cell_id": ["a", "a", "b"], "month": ["2020-01", "2021-01", "2020-02"],
                          TARGET: [0.4, 0.6, 0.3]})
    test = pd.DataFrame({"cell_id": ["a", "b", "c"], "month": ["2022-01", "2022-01", "2022-01"]})
    pred = climatology_baseline(train, test)
    assert pred[0] == pytest.approx(0.5)      # même cellule, même mois calendaire
    assert pred[1] == pytest.approx(0.3)      # repli : moyenne de la cellule
    assert pred[2] == pytest.approx(13 / 30)  # repli : moyenne globale


def test_spatial_cv_groups_disjoint():
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"x": rng.normal(size=200), "g": np.repeat(np.arange(10), 20)})
    df[TARGET] = 2 * df.x + rng.normal(0, 0.1, 200)
    res = cross_validate(df, ["x"], TARGET, LinearRegression, 5, df["g"], seed=0)
    assert res["pooled"]["n"] == 200 and res["pooled"]["r2"] > 0.95
    assert len(res["folds"]) == 5
