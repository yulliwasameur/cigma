# Préinscription — extension de CIGMA pour ICISSP 2027 (version du 21/11/2026)

Ce document fige les questions, les mesures et les règles **avant** de voir les résultats nouveaux. Tout changement ultérieur va dans `DEVIATIONS.md`.

## Questions nouvelles

- **RQ4 — Système réel.** Sur un système déployé que les auteurs n'ont pas conçu (Online Boutique, 11 microservices, Istio en mTLS strict, passerelle TLS avec PKI à deux niveaux), CIGMA reconstruit-il les entités et les dépendances typées mieux que les méthodes de comparaison ?
- **RQ5 — Effet sur la migration.** Un graphe mieux reconstruit donne-t-il un meilleur ordre de migration post-quantique ?
- **RQ3 étendue — Plusieurs modèles.** La validation déterministe contient-elle les candidats non fondés quel que soit le modèle ouvert (6 modèles, 7B à 70B, deux températures) ?

## Mesures principales (fixées maintenant)

| Question | Mesure principale | Mesures secondaires |
|---|---|---|
| RQ4 | F1 des arêtes typées contre l'oracle annoté | F1 des actifs, F1 par paires et B³ des entités, taux d'assertions sans preuve, F1 contre l'oracle restreint aux liens récupérables |
| RQ5 | Taux de violation de l'ordre de migration (MOVR, équation 3 du papier) | Exposition cumulée au risque quantique, rappel des chemins chiffrés critiques |
| RQ3 étendue | Nombre de triplets faux de l'oracle acceptés après validation (avec intervalle exact) | P/R/F1 brut et validé, Jaccard entre appels, comparaison au graphe CIGMA complet |

## Méthodes comparées (fixées maintenant)

TLS seul, CBOM seul, union des observations, identifiants exacts, TF–IDF cosinus (seuil 0,80), **les mêmes bases avec filtre qualité et composition de chemins (« à armes égales »)**, au moins une méthode moderne de résolution d'entités (Splink ou JedAI, réglages par défaut documentés), et CIGMA complet.

## Règles

1. Les prédictions sont **scellées** (`l1-deployed/seal/seal.py`) avant l'ouverture de l'oracle ; l'empreinte du scellement est publiée dans un commit horodaté.
2. L'oracle est annoté par **deux personnes indépendantes** qui ne voient pas les prédictions ; un arbitre tranche les désaccords ; l'accord (κ de Cohen) est rapporté.
3. Les qualités q, les fiabilités r, λ et les seuils sont ceux du papier d'origine, **non réajustés** sur le système réel.
4. Aucun résultat n'est retiré : un échec de CIGMA sur le système réel est rapporté tel quel.
5. Modèles de RQ3 : révisions Hugging Face figées dans `rq3-lumi/models.yaml` avant le premier appel ; graines fixes.

## Seuil de succès (annoncé à l'avance)

L'extension sera dite positive seulement si, sur le système réel, CIGMA améliore le F1 des arêtes typées par rapport aux bases « à armes égales » **et** améliore au moins une mesure de migration sans augmenter les décisions sans preuve. Sinon, le papier le dit.
