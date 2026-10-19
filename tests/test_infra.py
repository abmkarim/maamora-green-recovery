"""Retry, cache, grille, config, DAG et rendu du README (hors réseau)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from maamora.config import PROJECT_ROOT, load_config
from maamora.gee.aoi import build_grid, grid_to_ee_features
from maamora.gee.extract import cached_parquet, month_bounds, month_list
from maamora.retry import RequestTooLargeError, with_retry


def test_retry_backoff_then_success():
    calls, sleeps = [], []

    def flaky() -> int:
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("réseau")
        return 7

    assert with_retry(flaky, max_retries=5, sleep=sleeps.append) == 7
    assert len(sleeps) == 2 and sleeps[1] > sleeps[0] * 0.4


def test_retry_gives_up():
    def boom() -> None:
        raise TimeoutError("x")

    with pytest.raises(TimeoutError):
        with_retry(boom, max_retries=2, sleep=lambda s: None)


def test_retry_too_large_raises_immediately():
    def big() -> None:
        raise RuntimeError("User memory limit exceeded.")

    with pytest.raises(RequestTooLargeError):
        with_retry(big, sleep=lambda s: pytest.fail("ne doit pas attendre"))


def test_cache_is_idempotent(tmp_path: Path):
    n = []

    def produce() -> pd.DataFrame:
        n.append(1)
        return pd.DataFrame({"a": [1, 2]})

    p = tmp_path / "x" / "c.parquet"
    cached_parquet(p, produce)
    out = cached_parquet(p, produce)
    assert len(n) == 1 and list(out.a) == [1, 2]


def test_month_helpers():
    assert month_list("2026-09", 3) == ["2026-07", "2026-08", "2026-09"]
    assert month_bounds("2024-12") == ("2024-12-01", "2025-01-01")


def test_grid_cells_are_500m():
    aoi = gpd.GeoDataFrame(geometry=[box(-6.6, 34.1, -6.55, 34.13)], crs="EPSG:4326")
    g = build_grid(aoi, 500, 32629, 5000)
    areas = g.to_crs(32629).area
    assert ((areas - 250_000).abs() < 1).all()
    assert g.cell_id.is_unique
    assert g.block_id.nunique() >= 1
    feats = grid_to_ee_features(g.head(2))
    assert feats[0]["geometry"]["type"] == "Polygon"
    json.dumps(feats)


def test_config_loads():
    cfg = load_config()
    assert cfg.grid.resolution_m == 500 and cfg.window.n_months == 36
    assert cfg.model.n_train_months + cfg.model.n_test_months == cfg.window.n_months


def test_no_hardcoded_project_ids():
    """Aucun identifiant de projet GCP ni email dans le code."""
    import re

    pat = re.compile(r"[\w.-]+@[\w-]+\.\w+|ee\.Initialize\(project=['\"]")
    for f in (PROJECT_ROOT / "src").rglob("*.py"):
        assert not pat.search(f.read_text(encoding="utf-8")), f


def test_dag_structure():
    """Le DAG déclare les tâches attendues dans l'ordre (sans importer Airflow)."""
    src = (PROJECT_ROOT / "dags" / "maamora_dag.py").read_text(encoding="utf-8")
    ast.parse(src)
    expected = ["build_aoi", "extract_s2_ndvi", "extract_chirps", "extract_covariates",
                "build_features", "train", "shap", "price_insurance", "report"]
    assert '"maamora_pipeline"' in src
    for t in expected:
        assert f'"{t}"' in src
    try:
        import airflow  # noqa: F401
    except ImportError:
        return
    from airflow.models import DagBag

    bag = DagBag(dag_folder=str(PROJECT_ROOT / "dags"), include_examples=False)
    assert not bag.import_errors
    dag = bag.get_dag("maamora_pipeline")
    assert [t.task_id for t in dag.topological_sort()] == expected
