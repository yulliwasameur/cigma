# Écarts entre le papier ICISSP soumis (n° 21) et la reconstruction clean-room v0.1.0

Le code d'origine est perdu. Les chiffres de la version finale doivent venir de `results/cigma-lab/` (régénérés par `make cigma-lab`, déterministes : empreinte des métriques `6581404b2b70…`).

## Tableau 1 (reconstruction sur le banc complet)

| Méthode | Asset (soumis → nouveau) | Entité | B³ | Arêtes | FP | Cibles manquées |
|---|---|---|---|---|---|---|
| tls_inventory | **.5161 → 0.5625** | **.0526 → 0.0000** | **.1259 → 1.0000** | .3000 | .0000 | **10 → 8** |
| cbom_inventory | **.5455 → 0.5000** | .0000 | **.1549 → 0.9412** | .2927 | .1429 | **10 → 11** |
| source_union | .6667 | .0000 | .6866 | .8529 | .1471 | 0 |
| exact_direct | **.8846 → 0.9200** | **.8788 → 0.8261** | .9419 | **.8923 → 0.9062** | **.0645 → 0.0333** | 0 |
| tfidf_cosine | **.8519 → 0.9200** | **.8438 → 0.8261** | **.9268 → 0.9419** | **.8923 → 0.9062** | **.0645 → 0.0333** | 0 |
| cigma | 1.0000 | 1.0000 | 1.0000 | 1.0000 | .0000 | 0 |

## Classement de migration

- CIGMA NDCG@5/10 : soumis 0,8948/0,8984 → **0.5968/0.7976** ; τ_b soumis 0,2737 → **0.3135**.
- Conséquence : la phrase « le comparateur pondéré est légèrement meilleur » doit être revérifiée avec les nouvelles valeurs.

## Ablations

- Identiques au papier : sans alias (asset 0,9200), sans chemins (arêtes 0,9206), sans filtre qualité (asset 0,9583 ; FP 0,0556).
- File VERIFY avec fiabilités uniformes : soumis « de 15 à 7 » → **15 à 14**.

## Non reproductible

- Les 30 réponses du modèle (RQ3, 19/08/2026) : à refaire (RQ3 étendue, 6 modèles, LUMI).
- La robustesse et les tests de sources retirées : reprendre les valeurs de `results/cigma-lab/metrics/robustness_aggregate.csv`, `leave_one_source_out.csv` et `statistics.csv`.
- La phrase « Data Sharing » (évaluation sur système réel « disponible ») : à corriger.
