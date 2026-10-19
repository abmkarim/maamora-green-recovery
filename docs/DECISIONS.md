# Journal des décisions

| Date | Décision | Raison |
|---|---|---|
| 2026-10-19 | Branche locale `master` renommée `main` avant le premier commit. | Le cahier des charges exige `git push origin main` ; le remote était vide. |
| 2026-10-19 | AOI = emprise rectangulaire lon −6,80 → −6,20, lat 34,00 → 34,35, restreinte aux cellules ≥ 50 % arbres/arbustes ESA WorldCover. | Overpass ne renvoie que 5 polygones `landuse=forest` « Forêt de la Maâmora » couvrant la partie ouest (≈ lon −6,72 → −6,55), soit une fraction de la forêt (~1 300 km²) : contour jugé non fiable, repli prévu au §3. Les polygones OSM sont conservés comme référence sur la carte. |
| 2026-10-19 | Projection de la grille : UTM 29N (EPSG:32629). | Zone UTM de la Maâmora (lon −6,5) ; cellules carrées de 500 m exactes. |
| 2026-10-19 | NDVI Sentinel-2 réduit à 20 m d'échelle (`s2_scale_m`). | Divise par 4 le calcul Earth Engine (quotas Community Tier) ; une cellule de 500 m garde ~600 pixels. |
| 2026-10-19 | Composite mensuel = médiane temporelle par pixel, puis médiane spatiale par cellule ; mois manquant si < 30 % des pixels végétation ont une observation valide ou < 1 observation en moyenne. | Robuste aux résidus de nuages ; seuils configurables. |
| 2026-10-19 | SPI-3 calculé sur la série CHIRPS moyenne de l'AOI (1981 →), loi gamma par mois calendaire, appliqué identiquement à toutes les cellules. | CHIRPS à 0,05° : peu de variabilité intra-AOI ; évite 5 000 ajustements sur 45 ans. |
| 2026-10-19 | CHIRPS par cellule extrait sur 36 + 12 mois, ERA5 sur 36 + 2 mois. | Nécessaire pour cumul 12 mois et décalages sans perdre le début de la fenêtre. |
| 2026-10-19 | NDVI t−12 manquant (NaN) pour les 12 premiers mois ; XGBoost gère les NaN nativement. | Pas d'extraction NDVI hors fenêtre de 36 mois imposée. |
| 2026-10-19 | Hyperparamètres choisis sur les 6 derniers mois de l'entraînement (grille + early stopping), puis réentraînement sur les 27 mois avec le nombre d'arbres retenu. | Validation temporelle interne ; le test n'est jamais vu. |
| 2026-10-19 | CV spatiale : blocs de 5 km, 5 folds (GroupKFold) sur la période d'entraînement, comparée à un KFold aléatoire. | Mesure l'optimisme dû à l'autocorrélation spatiale sans toucher au test. |
| 2026-10-19 | SHAP calculé sur un échantillon de 5 000 lignes du test pour les deux variantes ; figures principales sur « climat seul ». | Dans la variante persistance, le NDVI t−1 écrase les effets climatiques. |
| 2026-10-19 | Chargement de risque = 6 % × (VaR 99 % − prime pure). | Taux de coût du capital standard de Solvabilité II. |
| 2026-10-19 | Test de tendance : Mann-Kendall (tau de Kendall vs année) et OLS (statsmodels) sur l'indice saisonnier. | Tests usuels, non paramétrique + paramétrique. |
