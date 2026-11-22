# Protocole d'annotation de l'oracle (lot L1)

**But :** construire la « vérité » du système déployé sans que les annotateurs voient ce que CIGMA ou les autres méthodes ont prédit.

## Qui
- **Deux annotateurs indépendants** (A et B), qui n'ont pas construit CIGMA et n'ont pas accès au dossier `out/predictions/`.
- **Un arbitre** (C) qui ne tranche que les désaccords.

## Sur quoi
Les annotateurs travaillent sur le système lui-même (manifestes Kubernetes, code et README d'Online Boutique, certificats, télémétrie brute), pas sur les sorties des méthodes.

## Quoi
1. `entities.csv` : chaque entité canonique (service, endpoint, certificat, algorithme, composant logiciel, pipeline, classe de données, équipement) avec ses identifiants.
2. `edges.csv` : chaque relation typée (HOSTS, PRESENTS, USES, ISSUED-BY, DEPENDS-ON, DEPLOYS, PROCESSES, PROTECTS), avec la preuve qui la justifie (fichier et chemin).
3. `migration_targets.csv` : les cibles critiques de migration post-quantique et leur priorité (1 = la plus urgente), avec une justification d'une phrase.

## Comment
- A et B remplissent chacun leurs fichiers dans `annotate/A/` et `annotate/B/`, **sans se parler**.
- `adjudicate.py` calcule l'accord (κ de Cohen) et liste les désaccords.
- C tranche chaque désaccord dans `annotate/C/decisions.csv`.
- `adjudicate.py --finalize` produit l'oracle final dans `out/oracle/` (dossier séparé, ouvert seulement après `verify_seal.py`).

## Format des identifiants

Dans `entities.csv`, la colonne `identifiers` contient une ou plusieurs paires `clé=valeur`, séparées par `;`. On utilise ces clés :

| Type d'entité | Clé à donner (au moins une) |
|---|---|
| service | `service_name` (nom du Deployment Kubernetes, ex. `cartservice`) |
| endpoint | `endpoint_uri` (ex. `cartservice.default.svc.cluster.local:7070`, ou `shop.cigma.local:443`) |
| certificate | `certificate_fingerprint` (SHA-256 en minuscules, sans deux-points) |
| algorithm | `algorithm_id` (ex. `RSA-2048`, `RSA-3072`, `ECDSA-P256`, `X25519`) |
| software_component | `purl` (tel qu'écrit dans le SBOM) |
| pipeline | `pipeline_uid` (ex. `github:GoogleCloudPlatform/microservices-demo:skaffold.yaml#app`) |

On n'annote que ce qui existe vraiment dans le système **en fonctionnement**. Un service décrit dans le dépôt mais jamais déployé n'est pas une entité du système. Une bibliothèque n'est retenue que si elle sert à la cryptographie ou au TLS.

## Exemple

Le service `frontend` appelle `cartservice` en gRPC, protégé par le mTLS d'Istio.
- Entités : `svc_frontend` (`service_name=frontend`), `svc_cart` (`service_name=cartservice`), `ep_cart` (`endpoint_uri=cartservice.default.svc.cluster.local:7070`), `cert_cart` (`certificate_fingerprint=<empreinte du certificat de charge de travail de cartservice>`), `alg_rsa2048` (`algorithm_id=RSA-2048`).
- Arêtes : `svc_frontend DEPENDS-ON svc_cart` ; `svc_cart HOSTS ep_cart` ; `ep_cart PRESENTS cert_cart` ; `cert_cart USES alg_rsa2048` ; `svc_cart USES alg_rsa2048` (déduite de la chaîne précédente).
- Preuves : `telemetry/istio-edges.json`, `k8s/workloads.json`, `pki/certificates.jsonl` (ligne dont le locator contient `mtls-cartservice`).

## Après l'arbitrage

`adjudicate.py --finalize`, puis, **seulement après** `verify_seal.py`, `to_oracle.py` convertit l'oracle au format de l'évaluateur de CIGMA.
