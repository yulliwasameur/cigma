#!/usr/bin/env bash
# PKI à deux niveaux (racine RSA-3072 -> intermédiaire ECDSA P-256 -> feuille RSA-2048)
# Mélange volontaire d'algorithmes classiques vulnérables au quantique, comme dans un SI réel.
set -euo pipefail
mkdir -p pki && cd pki
[ -f root.crt ] || step certificate create "CIGMA-L1 Root CA" root.crt root.key --profile root-ca --kty RSA --size 3072 --no-password --insecure --not-after 87600h
[ -f int.crt ]  || step certificate create "CIGMA-L1 Issuing CA" int.crt int.key --profile intermediate-ca --ca root.crt --ca-key root.key --kty EC --curve P-256 --no-password --insecure --not-after 43800h
[ -f shop.crt ] || step certificate create shop.cigma.local shop.crt shop.key --profile leaf --ca int.crt --ca-key int.key --kty RSA --size 2048 --san shop.cigma.local --no-password --insecure --not-after 2160h
cat shop.crt int.crt > shop-chain.crt
kubectl -n istio-system create secret tls shop-tls --cert=shop-chain.crt --key=shop.key --dry-run=client -o yaml | kubectl apply -f -
cd ..
kubectl apply -f - <<YAML
apiVersion: networking.istio.io/v1
kind: Gateway
metadata: { name: shop-gw, namespace: default }
spec:
  selector: { istio: ingressgateway }
  servers:
    - port: { number: 443, name: https, protocol: HTTPS }
      tls: { mode: SIMPLE, credentialName: shop-tls }
      hosts: ["shop.cigma.local"]
---
apiVersion: networking.istio.io/v1
kind: VirtualService
metadata: { name: shop-vs, namespace: default }
spec:
  hosts: ["shop.cigma.local"]
  gateways: [shop-gw]
  http: [{ route: [{ destination: { host: frontend, port: { number: 80 } } }] }]
YAML
kubectl -n istio-system patch svc istio-ingressgateway --type=json -p='[{"op":"replace","path":"/spec/ports/2/nodePort","value":30443}]' || true
