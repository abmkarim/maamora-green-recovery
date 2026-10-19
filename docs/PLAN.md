# Plan d'exécution

Chaque case n'est cochée qu'après exécution réussie de sa commande de validation dans la session.

| # | Étape | Validation | Fait |
|---|---|---|---|
| 1 | Squelette : `pyproject.toml`, `tasks.ps1`, `.gitignore`, `configs/default.yaml`, `.env.example` | `.\tasks.ps1 setup` termine sans erreur | [ ] |
| 2 | Config (`config.py`) + CLI (`cli.py`) | `python -m maamora.cli --help` | [ ] |
| 3 | Modules GEE (auth, aoi, sentinel2, chirps, covariates, extract) avec retry + cache | tests unitaires hors réseau (retry, cache, grille) | [ ] |
| 4 | Features (lags, cumuls, SPI-3, saisonnalité, persistance) | `pytest tests/test_features.py` (dont test anti-fuite) | [ ] |
| 5 | Modèle (split temporel, XGBoost, baselines, CV blocs spatiaux, SHAP) | `pytest tests/test_split.py tests/test_metrics.py` | [ ] |
| 6 | Assurance (indice, paiement, Monte Carlo, prix, risque de base) | `pytest tests/test_insurance.py` | [ ] |
| 7 | Reporting (figures, JSON) | `pytest tests/test_reporting.py` | [ ] |
| 8 | DAG Airflow + docker-compose | `pytest tests/test_dag.py` (import du DAG) | [ ] |
| 9 | Suite complète + lint | `.\tasks.ps1 test` vert, `ruff` propre | [ ] |
| 10 | Connexion Earth Engine | `python -c` init + opération triviale | [ ] |
| 11 | Pipeline complet | `.\tasks.ps1 run` (logs dans `logs/`) produit `reports/metrics.json` et `reports/insurance_pricing.json` | [ ] |
| 12 | Vérification visuelle de l'AOI | lecture de `reports/figures/aoi_map.png` | [ ] |
| 13 | Docs (README, METHODOLOGY, DATA) avec chiffres lus dans les JSON | script de génération du README + relecture | [ ] |
| 14 | Hygiène : `detect-secrets`, fichiers suivis < 5 Mo, aucun `data/` suivi | `.\tasks.ps1 secrets`, `git ls-files` | [ ] |
| 15 | Push final | `git push origin main`, `git status` propre | [ ] |
