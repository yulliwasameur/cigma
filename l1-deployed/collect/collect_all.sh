#!/usr/bin/env bash
# Lot L1 — collecte des six familles de sources sur le système déployé.
# Sortie : ../out/public/<famille>/...  (entrées PUBLIQUES de CIGMA ; aucun fichier d'oracle ici)
set -euo pipefail
cd "$(dirname "$0")"
PY=../.venv/bin/python; [ -x "$PY" ] || PY=python3
OUT=../out/public; mkdir -p "$OUT"/{k8s,tls,pki,cbom,cicd,catalog,telemetry}
date -u +%FT%TZ > "$OUT/COLLECTED_AT"

echo "[1/6] Identités Kubernetes / Helm (équivalent CMDB d'exécution)"
kubectl get deploy,svc,sa,pods,replicasets -n default -o json > "$OUT/k8s/workloads.json"
kubectl get gateway,virtualservice,peerauthentication -A -o json > "$OUT/k8s/istio-config.json"
kubectl get secrets -A -o json | jq '[.items[] | {ns:.metadata.namespace,name:.metadata.name,type:.type}]' > "$OUT/k8s/secrets-metadata.json"   # métadonnées seulement, jamais les clés

echo "[2/6] TLS de la passerelle d'entrée (sslyze)"
kubectl -n istio-system port-forward svc/istio-ingressgateway 9443:443 >/dev/null 2>&1 & PF=$!; sleep 4
$PY -m sslyze --json_out="$OUT/tls/gateway-sslyze.json" "shop.cigma.local{127.0.0.1}:9443" || $PY -m sslyze --json_out="$OUT/tls/gateway-sslyze.json" 127.0.0.1:9443 --sni shop.cigma.local
kill $PF || true

echo "[3/6] PKI : certificats mTLS de chaque charge de travail (Istio) + PKI de la passerelle"
for p in $(kubectl get pods -n default -o jsonpath='{.items[*].metadata.name}'); do
  istioctl proxy-config secret "$p" -n default -o json > "$OUT/pki/mtls-$p.json" 2>/dev/null || true
done
cp ../pki/root.crt ../pki/int.crt ../pki/shop.crt "$OUT/pki/" 2>/dev/null || true
$PY pki_extract.py "$OUT/pki" > "$OUT/pki/certificates.jsonl"

echo "[4/6] CBOM / SBOM des images (syft ; cbomkit-theia si disponible)"
for img in $(kubectl get pods -n default -o jsonpath='{range .items[*]}{range .spec.containers[*]}{.image}{"\n"}{end}{end}' | sort -u); do
  safe=$(echo "$img" | tr '/:@' '___')
  syft "$img" -o cyclonedx-json > "$OUT/cbom/sbom-$safe.json" || echo "syft a échoué pour $img" >&2
  if docker image inspect ghcr.io/ibm/cbomkit-theia >/dev/null 2>&1; then
    docker run --rm -v /var/run/docker.sock:/var/run/docker.sock ghcr.io/ibm/cbomkit-theia image "$img" > "$OUT/cbom/cbom-$safe.json" || true
  fi
done

echo "[5/6] CI/CD et catalogue de services : pris dans le dépôt public d'Online Boutique (version figée)"
cp -r ../src-online-boutique/.github/workflows "$OUT/cicd/github-workflows" 2>/dev/null || true
cp ../src-online-boutique/skaffold.yaml "$OUT/cicd/" 2>/dev/null || true
cp ../src-online-boutique/README.md "$OUT/catalog/online-boutique-README.md"
(cd ../src-online-boutique && git rev-parse HEAD) > "$OUT/cicd/SOURCE_COMMIT"

echo "[6/6] Arêtes de communication observées (télémétrie Istio / Prometheus)"
kubectl -n istio-system port-forward svc/prometheus 9090:9090 >/dev/null 2>&1 & PF=$!; sleep 4
curl -s 'http://127.0.0.1:9090/api/v1/query' --data-urlencode \
 'query=sum by (source_workload,destination_workload,request_protocol,connection_security_policy) (increase(istio_requests_total[15m]))' \
 > "$OUT/telemetry/istio-edges.json"
curl -s 'http://127.0.0.1:9090/api/v1/query' --data-urlencode \
 'query=sum by (source_workload,destination_workload,connection_security_policy) (increase(istio_tcp_connections_opened_total[15m]))' \
 > "$OUT/telemetry/istio-tcp-edges.json"
kill $PF || true

( cd "$OUT" && find . -type f -print0 | sort -z | xargs -0 shasum -a 256 ) > "$OUT/../PUBLIC_MANIFEST.sha256"
echo "Collecte terminée : $(wc -l < "$OUT/../PUBLIC_MANIFEST.sha256") fichiers, manifeste out/PUBLIC_MANIFEST.sha256"
