# Méthodologie

## 1. Zone et grille

- Contour : recherche Overpass des polygones `landuse=forest` / `natural=wood` / aires protégées nommés « Maâmora ». Le contour est jugé fiable s'il couvre au moins 650 km² (la moitié de la surface connue du massif, ~1 300 km²). Sinon : emprise rectangulaire de repli (lon −6,80 → −6,20, lat 34,00 → 34,35).
- Grille carrée de 500 m alignée en UTM 29N (EPSG:32629). Une cellule est conservée si au moins 50 % de ses pixels ESA WorldCover 2021 sont des arbres (10) ou des arbustes (20).
- Blocs spatiaux de 5 km × 5 km (100 cellules) pour la validation croisée.

## 2. NDVI Sentinel-2

1. `COPERNICUS/S2_SR_HARMONIZED` filtrée sur l'AOI et le mois, liée à Cloud Score+ par `linkCollection`.
2. Masque par image : `cs_cdf ≥ 0,60` ; si l'image n'a pas de score Cloud Score+, repli sur la SCL (classes 4, 5, 6, 7 conservées).
3. NDVI = (B8 − B4)/(B8 + B4) par image, puis **médiane temporelle** par pixel sur le mois, masquée par WorldCover.
4. Par cellule (`reduceRegions`, échelle 20 m, lots de 1 500 cellules, `tileScale` 4) : médiane spatiale du NDVI, nombre moyen d'observations valides, part de pixels végétation ayant au moins une observation valide.
5. Cible manquante si part valide < 30 % ou observations moyennes < 1. Pas d'interpolation.

## 3. Pluie, température, relief

- CHIRPS journalier sommé par mois ; valeur par cellule obtenue à 250 m (rééchantillonnage au plus proche : chaque cellule reçoit le pixel CHIRPS qui la recouvre). Série longue moyenne sur l'AOI depuis janvier 1981 pour le SPI et l'assurance.
- ERA5-Land `temperature_2m` mensuel (converti en °C).
- SRTM 30 m : altitude et pente moyennes par cellule.

## 4. Features et absence de fuite

| Groupe | Features |
|---|---|
| Pluie | `rain_lag0` … `rain_lag6`, `rain_cum3`, `rain_cum6`, `rain_cum12`, `spi3` |
| Température | `t2m_lag0` … `t2m_lag2` |
| Saison, relief | `month_sin`, `month_cos`, `elevation`, `slope` |
| Persistance (variante 2) | `ndvi_lag1`, `ndvi_lag12` |

- Les décalages sont calculés sur un tableau mois × cellule réindexé sur un calendrier mensuel complet : un mois manquant ne « glisse » pas d'une ligne.
- `rain_lag0` et `t2m_lag0` correspondent au mois cible lui-même (information contemporaine, connue à la fin du mois), jamais à un mois postérieur.
- Le SPI-3 est ajusté (loi gamma avec probabilité de zéro, par mois calendaire) uniquement sur les mois **antérieurs à la fenêtre** : aucune donnée de la fenêtre n'entre dans sa normalisation.
- `ndvi_lag12` est manquant pour les 12 premiers mois de la fenêtre (XGBoost gère les valeurs manquantes nativement).
- Le test `test_no_future_information` remplace toutes les données postérieures à un mois t par du bruit et vérifie que toutes les features des mois ≤ t sont identiques.

## 5. Modèle et évaluation

- Découpe temporelle : 27 premiers mois = entraînement, 9 derniers = test.
- Hyperparamètres (grille `max_depth` × `learning_rate` × `min_child_weight`, early stopping) choisis sur les 6 derniers mois de l'entraînement, puis modèle réentraîné sur les 27 mois avec le nombre d'arbres retenu. Le test n'intervient dans aucun choix.
- Baselines : climatologie (moyenne de la cellule pour le mois calendaire sur l'entraînement, replis : moyenne de la cellule puis moyenne globale) et persistance (NDVI t−1).
- Métriques test (R², RMSE, MAE) rapportées (a) sur les lignes où tous les modèles sont définis (la persistance exige un NDVI valide en t−1), (b) sur toutes les lignes valides de chaque modèle, (c) sur la moyenne mensuelle de l'AOI.
- Robustesse : K-fold aléatoire vs GroupKFold par blocs de 5 km, sur l'entraînement uniquement. L'écart mesure l'optimisme lié à l'autocorrélation spatiale.
- SHAP : `TreeExplainer` sur 5 000 lignes tirées du test, pour les deux variantes ; importance globale (moyenne des |SHAP|), beeswarm, dépendance des décalages de pluie.

## 6. Assurance paramétrique

- Indice : cumul CHIRPS d'octobre à avril (saison étiquetée par l'année d'avril), moyenné sur l'AOI, saisons complètes uniquement.
- Paiement : `capital × clip((déclencheur − indice)/(déclencheur − sortie), 0, 1)`, déclencheur = P30 historique, sortie = P5, capital notionnel 1 000 000 MAD.
- Monte Carlo : 100 000 saisons, graine 42 ; (1) loi gamma (loc = 0) ajustée par maximum de vraisemblance (adéquation testée par Kolmogorov-Smirnov), (2) bootstrap des saisons observées.
- Prix : prime pure = E[paiement] ; capital de risque = VaR 99 % − prime pure ; chargement = 6 % × capital (coût du capital standard Solvabilité II) ; prime technique = prime pure + chargement. Écart-type, VaR 99 %, TVaR 99 % et probabilité de paiement sont rapportés.
- Burning cost : paiements que le contrat aurait déclenchés à chaque saison historique.
- Tendance : Mann-Kendall (tau de Kendall vs année) et OLS.
- Sensibilité : prime pure pour des déclencheurs P15 → P45 et des sorties P1 → P10.
- Risque de base : (a) cumul de pluie glissant de 7 mois vs anomalie mensuelle du NDVI moyen de l'AOI, observée et prédite par le modèle « climat seul » ; (b) indice de chaque saison complète de la fenêtre vs anomalie NDVI du pic (mars → mai).
