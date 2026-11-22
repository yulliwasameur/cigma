# CIGMA — artefact public (ICISSP 2027, papier n° 21)

**CIGMA : Provenance-Preserving Cryptographic Dependency Reconstruction for Post-Quantum Network Migration.**
Y. Ameur, I. I. Lasledj, S. Bouzefrane, S. Banerjee — ICISSP 2027, Valletta (Malte).

Ce dépôt rassemble **tout ce qu'il faut pour refaire les résultats du papier** : le code, les données, les sorties brutes, les scripts d'analyse et la source LaTeX du papier. Chaque chiffre du papier doit pouvoir être régénéré par un script de ce dépôt.

## Contenu

| Dossier | Ce qu'il contient | État |
|---|---|---|
| `cigma/` | Le pipeline CIGMA (graphe typé avec provenance, résolution d'identité, composition de chemins, ordre de migration) | **à verser** (code d'origine à récupérer) |
| `cigma-lab/` | Le banc contrôlé CIGMA-Lab (générateur, entrées publiques, oracle séparé) | **à verser** |
| `l1-deployed/` | **Nouveau.** Validation sur un vrai système déployé : Online Boutique (Google) sur Kubernetes local, avec Istio (mTLS) ; collecte, scellement des prédictions, annotation indépendante de l'oracle | prêt à lancer |
| `rq3-lumi/` | **Nouveau.** Étude du modèle optionnel (RQ3) étendue à plusieurs modèles ouverts, servis par vLLM sur LUMI-G | prêt à lancer |
| `paper/` | Source LaTeX du papier (gabarit SCITEPRESS) | reconstruite le 21/11/2026 |
| `docs/` | Préinscription, protocole d'annotation, journal des écarts | en cours |

## Reproduire

```bash
# 1. Environnement Python
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Banc contrôlé (résultats du papier, tables 3 et figure 3)
make cigma-lab            # régénère tous les chiffres dans results/cigma-lab/

# 3. Système déployé (lot L1) — sur une machine avec Docker
make l1-up                # crée le cluster kind, installe Istio et Online Boutique
make l1-collect           # collecte les six familles de sources
make l1-seal              # scelle les prédictions (empreintes SHA-256) AVANT tout accès à l'oracle
make l1-evaluate          # ne s'exécute que si le scellement est intact

# 4. Étude du modèle (RQ3) — sur LUMI-G
cd rq3-lumi && sbatch run_rq3.sbatch
```

## Règles de reproductibilité

1. **Prédictions scellées avant l'oracle.** `l1-seal` écrit un manifeste d'empreintes. `l1-evaluate` refuse de tourner si une empreinte a changé.
2. **Oracle annoté par deux personnes qui n'ont pas vu les prédictions**, désaccords arbitrés par une troisième (`l1-deployed/annotate/`).
3. **Versions figées** : images Docker par empreinte (`@sha256:`), versions de Helm, d'Istio et des modèles ouverts écrites dans `docs/VERSIONS.md`.
4. **Graines fixes** pour tout tirage aléatoire.
5. **Écarts déclarés** : tout changement après la préinscription est noté dans `docs/DEVIATIONS.md`.

## Licences

- Code : MIT (`LICENSE`).
- Données et sorties : CC BY 4.0 (`LICENSE-DATA`).

## Citer

Voir `CITATION.cff`. Un DOI Zenodo sera associé à la version taguée `icissp2027-camera-ready`.

## Remerciements

We acknowledge the EuroHPC Joint Undertaking for awarding this project access to the EuroHPC supercomputer LUMI, hosted by CSC (Finland) and the LUMI consortium through a EuroHPC Benchmark Access call (EHPC-BEN-2026B11-194).

## Provenance du code (important)

Le code d'origine de CIGMA (2026) est perdu. Le dossier `cigma/` contient la **reconstruction clean-room v0.1.0** (août 2026), refaite à partir de la spécification publiée. Ce n'est pas le code d'origine. Tous les chiffres de la version finale du papier sont régénérés par `make cigma-lab` ; les écarts avec la version soumise sont listés dans `docs/ECARTS-PAPIER-SOUMIS.md`.
