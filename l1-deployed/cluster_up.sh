#!/usr/bin/env bash
# Lot L1 — crée le système déployé : cluster kind + Istio (mTLS strict) + Online Boutique.
# Online Boutique : application publique de Google (11 microservices), choisie pour ne PAS être conçue par les auteurs.
set -euo pipefail
OB_TAG="${OB_TAG:-v0.10.2}"          # version figée d'Online Boutique (vérifier la dernière release et l'écrire dans docs/VERSIONS.md)
CLUSTER=cigma-l1
kind get clusters | grep -qx "$CLUSTER" || kind create cluster --name "$CLUSTER" --config kind.yaml
kubectl config use-context "kind-$CLUSTER"

# Istio : mTLS STRICT entre services -> vrais certificats X.509 par charge de travail (famille PKI)
istioctl install -y --set profile=demo --set meshConfig.accessLogFile=/dev/stdout
kubectl label namespace default istio-injection=enabled --overwrite
kubectl apply -f - <<YAML
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata: { name: default, namespace: istio-system }
spec: { mtls: { mode: STRICT } }
YAML
# Télémétrie (arêtes de communication observées)
ISTIO_VER=$(istioctl version --remote=false -o json | jq -r '.clientVersion.version')
kubectl apply -f "https://raw.githubusercontent.com/istio/istio/${ISTIO_VER%.*}/samples/addons/prometheus.yaml" || \
kubectl apply -f "https://raw.githubusercontent.com/istio/istio/release-${ISTIO_VER%.*}/samples/addons/prometheus.yaml"

# Online Boutique à la version figée (le dépôt sert aussi de source CI/CD et de catalogue de services)
[ -d src-online-boutique ] || git clone --depth 1 --branch "$OB_TAG" https://github.com/GoogleCloudPlatform/microservices-demo.git src-online-boutique
kubectl apply -f src-online-boutique/release/kubernetes-manifests.yaml
kubectl wait --for=condition=available deploy --all -n default --timeout=900s

# Passerelle d'entrée en TLS avec une petite PKI à deux niveaux (step) -> famille TLS
bash pki_gateway.sh
echo "Système L1 prêt. Le générateur de charge d'Online Boutique crée le trafic ; attendre 15 min avant la collecte."
