"""DAG Airflow `maamora_pipeline` : chaque tâche appelle la CLI idempotente du projet.

Le projet est monté dans le conteneur sous /opt/maamora (voir docker-compose.yml). Les
extractions reposent sur le cache parquet de data/ : relancer une tâche ne refait pas
les extractions déjà faites.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT_DIR = "/opt/maamora"
TASKS = [
    ("build_aoi", "build-aoi"),
    ("extract_s2_ndvi", "extract-s2"),
    ("extract_chirps", "extract-chirps"),
    ("extract_covariates", "extract-covariates"),
    ("build_features", "build-features"),
    ("train", "train"),
    ("shap", "shap"),
    ("price_insurance", "price"),
    ("report", "report"),
]

default_args = {
    "owner": "maamora",
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
}

with DAG(
    dag_id="maamora_pipeline",
    description="NDVI Maâmora, modèle pluie-végétation et assurance sécheresse",
    start_date=datetime(2024, 1, 1),
    schedule="@monthly",
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["maamora", "earth-engine"],
) as dag:
    previous = None
    for task_id, command in TASKS:
        op = BashOperator(
            task_id=task_id,
            bash_command=f"cd {PROJECT_DIR} && PYTHONPATH=src python -m maamora.cli {command}",
        )
        if previous is not None:
            previous >> op
        previous = op
