"""Fixtures synthétiques (aucun accès réseau ni Earth Engine)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from maamora.config import Config


@pytest.fixture
def cfg() -> Config:
    """Configuration par défaut (valeurs du code, sans YAML)."""
    return Config()


def _months(start: str, n: int) -> list[str]:
    p = pd.Period(start, freq="M")
    return [str(p + k) for k in range(n)]


@pytest.fixture
def synthetic(cfg: Config) -> dict:
    """Jeu synthétique : 6 cellules, 36 mois de fenêtre, pluie depuis 1990."""
    rng = np.random.default_rng(0)
    cells = [f"c{i}" for i in range(6)]
    window = _months("2021-01", 36)
    rain_months = _months("2020-01", 48)
    hist_months = _months("1990-01", 31 * 12 + 12 + 36)
    rain = pd.DataFrame([{"cell_id": c, "month": m, "rain_mm": float(rng.gamma(2, 20))}
                         for c in cells for m in rain_months])
    temp = pd.DataFrame([{"cell_id": c, "month": m, "t2m_c": float(15 + rng.normal(0, 5))}
                         for c in cells for m in _months("2020-11", 38)])
    ndvi = pd.DataFrame([{"cell_id": c, "month": m, "ndvi": float(0.5 + rng.normal(0, 0.05)),
                          "n_obs": float(rng.integers(0, 6)),
                          "valid_fraction": float(rng.uniform(0, 1))}
                         for c in cells for m in window])
    hist = pd.DataFrame({"month": hist_months,
                         "rain_mm": rng.gamma(1.5, 30, size=len(hist_months))})
    static = pd.DataFrame({"cell_id": cells, "elevation": rng.uniform(50, 200, 6),
                           "slope": rng.uniform(1, 5, 6), "block_id": [0, 0, 1, 1, 2, 2],
                           "x": np.arange(6) * 500.0, "y": np.zeros(6)})
    return {"rain": rain, "temp": temp, "ndvi": ndvi, "hist": hist, "static": static,
            "window": window}
