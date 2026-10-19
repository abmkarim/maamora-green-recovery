# Données

> Fichier généré par `python -m maamora.cli report` à partir du cache `data/` (non versionné).

## Sources (Google Earth Engine)

| Donnée | Collection | Usage |
|---|---|---|
| Sentinel-2 L2A harmonisé | `COPERNICUS/S2_SR_HARMONIZED` | NDVI = (B8 − B4)/(B8 + B4), échelle 20 m |
| Cloud Score+ | `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED` | masque nuages `cs_cdf` ≥ 0.6 (SCL en secours) |
| ESA WorldCover 2021 | `ESA/WorldCover/v200` | masque végétation, classes [10, 20] |
| CHIRPS journalier | `UCSB-CHG/CHIRPS/DAILY` | pluie mensuelle par cellule et historique AOI depuis 1981-01 |
| ERA5-Land mensuel | `ECMWF/ERA5_LAND/MONTHLY_AGGR` | `temperature_2m` (°C) |
| SRTM 30 m | `USGS/SRTMGL1_003` | altitude, pente |
| OpenStreetMap (Overpass) | `landuse=forest`, nom « Maâmora » | contour de référence (ODbL) |

L'existence de chaque collection est vérifiée à chaque exécution (`data/collections_check.json`).

## Fenêtre et grille

- Fenêtre NDVI : **2023-10 → 2026-09** (36 mois) ; dernier mois complet CHIRPS : 2026-09, Sentinel-2 : 2026-09.
- Grille UTM 29N de 500 m sur l'emprise : 8786 cellules, dont **2157** retenues (≥ 50 % arbres/arbustes WorldCover), soit 539 km².
- Altitude moyenne 103 m, pente moyenne 3.1°.

## Validité de la cible NDVI

Un mois est valide pour une cellule si ≥ 30 % des pixels végétation ont au moins une observation non nuageuse et si le nombre moyen d'observations est ≥ 1. Aucune interpolation.

- Part globale de couples cellule × mois valides : **99.4 %**.
- Part de mois valides par cellule : P10 = 97 %, médiane = 100 %, P90 = 100 %.

## Couverture nuageuse par mois

`CLOUDY_PIXEL_PERCENTAGE` moyen des scènes Sentinel-2 intersectant l'AOI, et part des cellules valides.

| Mois | Scènes S2 | Nuages moyens (%) | Cellules valides (%) |
|---|---|---|---|
| 2023-10 | 60 | 48.6 | 100.0 |
| 2023-11 | 59 | 21.5 | 100.0 |
| 2023-12 | 57 | 30.4 | 100.0 |
| 2024-01 | 63 | 39.9 | 100.0 |
| 2024-02 | 53 | 37.5 | 100.0 |
| 2024-03 | 68 | 60.4 | 100.0 |
| 2024-04 | 60 | 32.7 | 100.0 |
| 2024-05 | 59 | 49.1 | 87.9 |
| 2024-06 | 60 | 36.8 | 100.0 |
| 2024-07 | 64 | 5.3 | 100.0 |
| 2024-08 | 59 | 10.9 | 100.0 |
| 2024-09 | 60 | 23.3 | 100.0 |
| 2024-10 | 59 | 51.0 | 100.0 |
| 2024-11 | 54 | 35.5 | 100.0 |
| 2024-12 | 72 | 37.2 | 100.0 |
| 2025-01 | 56 | 42.9 | 100.0 |
| 2025-02 | 54 | 34.9 | 100.0 |
| 2025-03 | 80 | 48.8 | 99.8 |
| 2025-04 | 93 | 57.2 | 92.0 |
| 2025-05 | 92 | 16.3 | 100.0 |
| 2025-06 | 91 | 28.1 | 100.0 |
| 2025-07 | 104 | 9.3 | 100.0 |
| 2025-08 | 89 | 12.2 | 100.0 |
| 2025-09 | 86 | 32.2 | 100.0 |
| 2025-10 | 87 | 28.8 | 100.0 |
| 2025-11 | 85 | 31.1 | 100.0 |
| 2025-12 | 93 | 47.6 | 100.0 |
| 2026-01 | 63 | 62.3 | 97.2 |
| 2026-02 | 73 | 50.2 | 100.0 |
| 2026-03 | 88 | 31.7 | 100.0 |
| 2026-04 | 90 | 33.2 | 100.0 |
| 2026-05 | 89 | 38.8 | 100.0 |
| 2026-06 | 92 | 17.6 | 100.0 |
| 2026-07 | 94 | 8.7 | 100.0 |
| 2026-08 | 90 | 10.2 | 100.0 |
| 2026-09 | 90 | 15.4 | 100.0 |
