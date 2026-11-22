# Règles de l'adaptateur L1 (fixées avant l'annotation, 22/11/2026)

Code : `cigma/src/cigma/l1_convert.py`. Entrée : `l1-deployed/out/public/` seulement. Sortie : `out/observations/{entities,relations}.jsonl`.

| Famille | Fichier brut | Ce qui devient une observation |
|---|---|---|
| cmdb (0.95) | `k8s/workloads.json`, `k8s/istio-config.json` | un service par Deployment ; un point d'accès par port de Service ; HOSTS service→point d'accès (sélecteur `app`) ; la passerelle Istio HOSTS `shop.cigma.local:443` et DEPENDS-ON la destination de sa VirtualService |
| pki (0.97) | `pki/certificates.jsonl` | un certificat par empreinte ; USES vers l'algorithme de sa clé ; ISSUED-BY quand le DN de l'émetteur est le sujet d'un autre certificat ; le certificat de charge de travail Istio d'un pod est PRÉSENTÉ par chaque point d'accès de son service ; `shop.crt` est présenté par `shop.cigma.local:443` |
| tls (0.98) | `tls/gateway-sslyze.json` | la chaîne reçue (PRESENTS, ISSUED-BY, USES) et les groupes d'échange de clés acceptés |
| cbom (0.88) | `cbom/sbom-*.json` (syft) | service USES composant, uniquement pour une liste fermée de bibliothèques cryptographiques ou TLS (`CRYPTO_PACKAGES`) ; aucun algorithme n'est inventé à partir d'un nom de bibliothèque |
| cicd (0.91) | `cicd/skaffold.yaml` | un pipeline ; DEPLOYS vers chaque image construite (y compris celles qui ne tournent pas) |
| telemetry (0.92) | `telemetry/istio-*.json` | DEPENDS-ON source→destination pour chaque paire observée avec plus de 0 requête en 15 min (`unknown` exclu) |

Une même affirmation vue plusieurs fois (par exemple la racine Istio dans chaque pod) ne donne qu'une observation. Configuration : `configs/l1.yaml` (fiabilité `telemetry` ajoutée ; politique d'algorithmes étendue à RSA-3072, X25519, ECDH-P256, et 0 pour ML-KEM).
