"""L1 (deployed Online Boutique) -> public CIGMA observations.

Reads ONLY the public collection tree written by l1-deployed/collect/collect_all.sh
(out/public/...) and emits entities.jsonl / relations.jsonl in the CIGMA schema.
It never reads annotations or any oracle file. The mapping rules below were fixed
before the annotators started (see docs/L1-ADAPTER-RULES.md); every observation keeps
the path of the raw file it comes from as its locator.

Source families:
  cmdb       Kubernetes runtime objects and Istio routing config (k8s/*.json)
  pki        certificates: gateway PKI files + Istio workload certificates (pki/*)
  tls        external TLS scan of the ingress gateway (tls/gateway-sslyze.json)
  cbom       software bill of materials of each running image (syft, cbom/*.json)
  cicd       build/deploy definition of the public repository (cicd/skaffold.yaml)
  telemetry  observed service-to-service calls (Istio/Prometheus, telemetry/*.json)
"""

from __future__ import annotations

import argparse
import base64
import json
import re
from pathlib import Path
from typing import Any

import yaml

from .adapters.base import AdapterOutput, ObservationFactory
from .io import write_jsonl
from .schema import EntityType, RelationType, SourceFamily

NS = "default"
QUALITY = {"cmdb": 0.95, "pki": 0.97, "tls": 0.98, "cbom": 0.88, "cicd": 0.91, "telemetry": 0.92}

# Crypto-relevant packages kept from the SBOM (explicit list; everything else is ignored).
# name regex -> short reason (kept in the evidence record)
CRYPTO_PACKAGES = [
    (r"^(libssl3|libcrypto3|openssl|libssl1\.1|libcrypto1\.1|libssl3t64|libssl-dev)$", "OpenSSL"),
    (r"^(boringssl|grpcio)$", "BoringSSL (bundled in grpcio)"),
    (r"^stdlib$", "Go standard library (crypto/tls, crypto/x509)"),
    (r"^golang\.org/x/crypto$", "Go x/crypto"),
    (r"^(cryptography|pyopenssl|pycryptodome|rsa)$", "Python crypto library"),
    (r"^(bcprov-jdk18on|bcprov-jdk15on|bcpkix-jdk18on|conscrypt-openjdk-uber)$", "Java crypto provider"),
    (r"^grpc-netty-shaded$", "Netty TLS (BoringSSL via netty-tcnative)"),
    (r"^(netty-tcnative-boringssl-static|netty-handler)$", "Netty TLS"),
    (r"^(node-forge|jsonwebtoken|jose|@grpc/grpc-js)$", "Node.js crypto/TLS user"),
    (r"^(System\.Security\.Cryptography\..*|Grpc\.Net\.Client|Grpc\.AspNetCore\.Server)$", ".NET crypto/TLS user"),
]


def _alg_from_cert(rec: dict[str, Any]) -> str | None:
    bits = re.search(r"\((\d+) bit\)", rec.get("key_size", "") or "")
    n = bits.group(1) if bits else None
    ka = rec.get("key_algorithm", "")
    if ka == "rsaEncryption" and n:
        return f"RSA-{n}"
    if ka == "id-ecPublicKey" and n == "256":
        return "ECDSA-P256"
    if ka == "id-ecPublicKey" and n == "384":
        return "ECDSA-P384"
    if ka in ("ED25519", "Ed25519"):
        return "Ed25519"
    return None


def _cn(dn: str) -> str:
    dn = dn.split("=", 1)[1].strip() if dn.startswith(("subject=", "issuer=")) else dn
    return dn


class Builder:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.at = (root / "COLLECTED_AT").read_text().strip()
        if "T" in self.at and not self.at.endswith("+00:00"):
            self.at = self.at.replace("Z", "+00:00")
        self.out = AdapterOutput()
        self.f = {fam: ObservationFactory(SourceFamily(fam), self.at) for fam in QUALITY}

    # ---- helpers -------------------------------------------------------------
    def ent(self, fam, key, etype, ids, attrs, locator, ev):
        return self.out.add_entity(self.f[fam].entity(local_key=key, entity_type=etype, identifiers=ids,
                                                      attributes=attrs, quality=QUALITY[fam], locator=locator,
                                                      evidence_record=ev))

    def rel(self, fam, s, pred, o, locator, ev):
        key = f"{s.local_key}:{pred.value}:{o.local_key}"
        oid = self.f[fam]._id("relation", key)
        if oid in self.out.relations:          # same claim seen again (e.g. Istio root in every pod file): keep the first
            return self.out.relations[oid]
        return self.out.add_relation(self.f[fam].relation(local_key=f"{s.local_key}:{pred.value}:{o.local_key}", subject=s,
                                                          predicate=pred, object_=o, quality=QUALITY[fam],
                                                          locator=locator, evidence_record=ev))

    def service(self, fam, name, locator, ev, extra_ids=None):
        ids = {"service_name": name, "deployment_name": name}
        ids.update(extra_ids or {})
        return self.ent(fam, f"{fam}:svc:{name}", EntityType.SERVICE, ids, {}, locator, ev)

    def endpoint(self, fam, uri, locator, ev, attrs=None):
        return self.ent(fam, f"{fam}:ep:{uri}", EntityType.ENDPOINT, {"endpoint_uri": uri}, attrs or {}, locator, ev)

    def cert(self, fam, rec, locator):
        attrs = {"subject": _cn(rec.get("subject", "")), "key_bits": None, "not_after": rec.get("not_after")}
        bits = re.search(r"\((\d+) bit\)", rec.get("key_size", "") or "")
        attrs["key_bits"] = int(bits.group(1)) if bits else None
        ids = {"certificate_fingerprint": rec["fingerprint_sha256"]}
        if rec.get("spki_sha256"):
            ids["spki_fingerprint"] = rec["spki_sha256"]
        return self.ent(fam, f"{fam}:cert:{rec['fingerprint_sha256'][:24]}", EntityType.CERTIFICATE, ids, attrs, locator, rec)

    def alg(self, fam, alg_id, locator, ev):
        return self.ent(fam, f"{fam}:alg:{alg_id}", EntityType.ALGORITHM, {"algorithm_id": alg_id}, {}, locator, ev)

    # ---- families --------------------------------------------------------------
    def k8s(self) -> dict[str, list[str]]:
        w = json.loads((self.root / "k8s/workloads.json").read_text())
        items = w["items"]
        deps = {i["metadata"]["name"]: i for i in items if i["kind"] == "Deployment" and i["metadata"].get("namespace", NS) == NS}
        svc_eps: dict[str, list[str]] = {}
        for idx, it in enumerate(items):
            if it["kind"] != "Deployment":
                continue
            name = it["metadata"]["name"]
            image = it["spec"]["template"]["spec"]["containers"][0]["image"]
            self.service("cmdb", name, f"k8s/workloads.json#/items/{idx}",
                         {"kind": "Deployment", "name": name, "image": image, "uid": it["metadata"].get("uid")})
        for idx, it in enumerate(items):
            if it["kind"] != "Service":
                continue
            sel = (it["spec"].get("selector") or {}).get("app")
            if sel not in deps:
                continue
            svc = self.service("cmdb", sel, f"k8s/workloads.json#/items/{idx}", {"kind": "Service", "selector": sel})
            for p in it["spec"].get("ports", []):
                uri = f"{it['metadata']['name']}.{NS}.svc.cluster.local:{p['port']}"
                ep = self.endpoint("cmdb", uri, f"k8s/workloads.json#/items/{idx}/spec/ports",
                                   {"kind": "Service", "name": it["metadata"]["name"], "port": p, "type": it["spec"].get("type")},
                                   {"exposure": "external" if it["spec"].get("type") in ("LoadBalancer", "NodePort") else "internal"})
                self.rel("cmdb", svc, RelationType.HOSTS, ep, f"k8s/workloads.json#/items/{idx}/spec/selector",
                         {"service": it["metadata"]["name"], "selector": sel, "port": p["port"]})
                svc_eps.setdefault(sel, []).append(uri)
        # Istio routing: the ingress gateway hosts the public endpoint and forwards to its destination.
        cfg = json.loads((self.root / "k8s/istio-config.json").read_text())
        for idx, it in enumerate(cfg["items"]):
            if it["kind"] == "VirtualService":
                hosts = it["spec"].get("hosts", [])
                gw = self.service("cmdb", "istio-ingressgateway", f"k8s/istio-config.json#/items/{idx}",
                                  {"kind": "VirtualService", "name": it["metadata"]["name"], "gateways": it["spec"].get("gateways")})
                for h in hosts:
                    ep = self.endpoint("cmdb", f"{h}:443", f"k8s/istio-config.json#/items/{idx}/spec/hosts",
                                       {"host": h, "gateway": it["spec"].get("gateways")}, {"exposure": "external"})
                    self.rel("cmdb", gw, RelationType.HOSTS, ep, f"k8s/istio-config.json#/items/{idx}", {"host": h})
                for r_i, route in enumerate(it["spec"].get("http", [])):
                    for d in route.get("route", []):
                        dest = d["destination"]["host"].split(".")[0]
                        if dest in deps:
                            dst = self.service("cmdb", dest, f"k8s/istio-config.json#/items/{idx}/spec/http/{r_i}", {"route_to": dest})
                            self.rel("cmdb", gw, RelationType.DEPENDS_ON, dst, f"k8s/istio-config.json#/items/{idx}/spec/http/{r_i}",
                                     {"virtualservice": it["metadata"]["name"], "destination": dest})
        self.pod_app = {i["metadata"]["name"]: (i["metadata"].get("labels") or {}).get("app")
                        for i in items if i["kind"] == "Pod"}
        return svc_eps

    def pki(self, svc_eps: dict[str, list[str]]) -> None:
        recs = [json.loads(l) for l in (self.root / "pki/certificates.jsonl").read_text().splitlines() if l.strip()]
        by_subject: dict[str, dict] = {}
        for r in recs:
            by_subject.setdefault(_cn(r.get("subject", "")), r)
        for i, r in enumerate(recs):
            loc = r["locator"]
            c = self.cert("pki", r, f"pki/certificates.jsonl#/{i}")
            a_id = _alg_from_cert(r)
            if a_id:
                self.rel("pki", c, RelationType.USES, self.alg("pki", a_id, f"pki/certificates.jsonl#/{i}/key_algorithm", r),
                         f"pki/certificates.jsonl#/{i}/key_algorithm", r)
            iss = _cn(r.get("issuer", ""))
            parent = by_subject.get(iss)
            if parent and parent["fingerprint_sha256"] != r["fingerprint_sha256"]:
                j = recs.index(parent)
                self.rel("pki", c, RelationType.ISSUED_BY, self.cert("pki", parent, f"pki/certificates.jsonl#/{j}"),
                         f"pki/certificates.jsonl#/{i}/issuer", {"issuer": iss, "parent": parent["locator"]})
            # Istio workload certificate presented by the sidecar of each endpoint of that workload
            m = re.match(r"pki/mtls-(.+)-[a-z0-9]{8,10}-[a-z0-9]{5}\.json#/dynamicActiveSecrets/0/chain/0$", loc)
            if m:
                app = m.group(1)
                for uri in svc_eps.get(app, []):
                    ep = self.endpoint("pki", uri, f"{loc.split('#')[0]}", {"workload": app, "endpoint": uri})
                    self.rel("pki", ep, RelationType.PRESENTS, c, loc, {"workload": app, "endpoint": uri, "source": "istioctl proxy-config secret"})
            if loc.endswith("shop.crt"):
                ep = self.endpoint("pki", "shop.cigma.local:443", "pki/shop.crt", {"secret": "istio-system/shop-tls"})
                self.rel("pki", ep, RelationType.PRESENTS, c, "pki/shop.crt", {"secret": "istio-system/shop-tls"})

    def tls(self) -> None:
        p = self.root / "tls/gateway-sslyze.json"
        if not p.exists():
            return
        d = json.loads(p.read_text())
        for s_i, srv in enumerate(d.get("server_scan_results", [])):
            if srv.get("scan_status") != "COMPLETED":
                continue
            host = srv["server_location"]["hostname"]
            uri = f"{host}:443"
            base = f"tls/gateway-sslyze.json#/server_scan_results/{s_i}"
            sr = srv["scan_result"]
            groups, versions = set(), []
            for key, ver in (("tls_1_3_cipher_suites", "TLS1.3"), ("tls_1_2_cipher_suites", "TLS1.2")):
                res = (sr.get(key) or {}).get("result") or {}
                acc = res.get("accepted_cipher_suites", [])
                if acc:
                    versions.append(ver)
                for cs in acc:
                    ek = cs.get("ephemeral_key") or {}
                    if ek.get("curve_name"):
                        groups.add(ek["curve_name"])
            ep = self.endpoint("tls", uri, base, {"hostname": host, "tls_versions": versions, "key_exchange": sorted(groups)},
                               {"exposure": "external", "protocol": "/".join(versions), "key_exchange": ",".join(sorted(groups))})
            ci = (sr.get("certificate_info") or {}).get("result") or {}
            for dep in ci.get("certificate_deployments", [])[:1]:
                chain = dep.get("received_certificate_chain", [])
                prev = None
                for k, crt in enumerate(chain):
                    pk = crt.get("public_key", {})
                    algname = {"RSAPublicKey": "rsaEncryption", "EllipticCurvePublicKey": "id-ecPublicKey"}.get(pk.get("algorithm"), pk.get("algorithm"))
                    fp = crt.get("fingerprint_sha256", "")
                    if fp and not re.fullmatch(r"[0-9a-fA-F]{64}", fp):
                        fp = base64.b64decode(fp).hex()          # sslyze 6 writes base64
                    rec = {"fingerprint_sha256": fp.lower(), "subject": (crt.get("subject") or {}).get("rfc4514_string", ""),
                           "key_algorithm": algname, "key_size": f"({pk.get('key_size')} bit)", "not_after": crt.get("not_valid_after")}
                    if not rec["fingerprint_sha256"]:
                        continue
                    c = self.cert("tls", rec, f"{base}/certificate_info/chain/{k}")
                    a = _alg_from_cert(rec)
                    if a:
                        self.rel("tls", c, RelationType.USES, self.alg("tls", a, f"{base}/certificate_info/chain/{k}", rec), f"{base}/certificate_info/chain/{k}/public_key", rec)
                    if k == 0:
                        self.rel("tls", ep, RelationType.PRESENTS, c, f"{base}/certificate_info/chain/0", rec)
                    if prev is not None:
                        self.rel("tls", prev, RelationType.ISSUED_BY, c, f"{base}/certificate_info/chain/{k}", {"chain_index": k})
                    prev = c

    def cbom(self) -> None:
        for path in sorted((self.root / "cbom").glob("sbom-*.json")):
            rel_path = f"cbom/{path.name}"
            m = re.search(r"microservices-demo_(.+)_v[\d.]+\.json$", path.name)
            app = m.group(1) if m else ("redis-cart" if "redis" in path.name else None)
            if not app:
                continue
            d = json.loads(path.read_text())
            svc = None
            for c_i, comp in enumerate(d.get("components", [])):
                name, purl = comp.get("name") or "", comp.get("purl")
                if not purl:
                    continue
                reason = next((why for rx, why in CRYPTO_PACKAGES if re.match(rx, name)), None)
                if not reason:
                    continue
                if svc is None:
                    svc = self.service("cbom", app, f"{rel_path}#/metadata", {"image_sbom": path.name, "service": app})
                ev = {"name": name, "version": comp.get("version"), "purl": purl, "why_crypto": reason}
                sc = self.ent("cbom", f"cbom:comp:{purl}", EntityType.SOFTWARE_COMPONENT, {"purl": purl},
                              {"name": name, "version": comp.get("version")}, f"{rel_path}#/components/{c_i}", ev)
                self.rel("cbom", svc, RelationType.USES, sc, f"{rel_path}#/components/{c_i}", ev)

    def cicd(self) -> None:
        y = next(d for d in yaml.safe_load_all((self.root / "cicd/skaffold.yaml").read_text()) if d and d.get("build"))   # first Config document
        commit = (self.root / "cicd/SOURCE_COMMIT").read_text().strip() if (self.root / "cicd/SOURCE_COMMIT").exists() else None
        pipe = self.ent("cicd", "cicd:pipe:skaffold-app", EntityType.PIPELINE,
                        {"pipeline_uid": "github:GoogleCloudPlatform/microservices-demo:skaffold.yaml#app"},
                        {"platform": "skaffold", "commit": commit}, "cicd/skaffold.yaml#/build/artifacts",
                        {"file": "skaffold.yaml", "commit": commit})
        for a_i, art in enumerate(y.get("build", {}).get("artifacts", [])):
            name = art["image"]
            svc = self.service("cicd", name, f"cicd/skaffold.yaml#/build/artifacts/{a_i}", {"image": name, "context": art.get("context")})
            self.rel("cicd", pipe, RelationType.DEPLOYS, svc, f"cicd/skaffold.yaml#/build/artifacts/{a_i}", {"image": name, "context": art.get("context")})

    def telemetry(self) -> None:
        for fname in ("istio-edges.json", "istio-tcp-edges.json"):
            p = self.root / "telemetry" / fname
            if not p.exists():
                continue
            res = json.loads(p.read_text()).get("data", {}).get("result", [])
            for r_i, r in enumerate(res):
                m = r["metric"]
                s, d = m.get("source_workload"), m.get("destination_workload")
                if not s or not d or "unknown" in (s, d) or float(r["value"][1]) <= 0:
                    continue
                loc = f"telemetry/{fname}#/data/result/{r_i}"
                ev = {"source": s, "destination": d, "protocol": m.get("request_protocol"),
                      "security_policy": m.get("connection_security_policy"), "requests_15min": round(float(r["value"][1]), 1)}
                self.rel("telemetry", self.service("telemetry", s, loc, ev), RelationType.DEPENDS_ON,
                         self.service("telemetry", d, loc, ev), loc, ev)

    def run(self) -> AdapterOutput:
        eps = self.k8s()
        self.pki(eps)
        self.tls()
        self.cbom()
        self.cicd()
        self.telemetry()
        return self.out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="convert the L1 public collection to CIGMA observations")
    ap.add_argument("--public", required=True, help="l1-deployed/out/public")
    ap.add_argument("--output", required=True, help="directory for entities.jsonl and relations.jsonl")
    a = ap.parse_args(argv)
    out = Builder(Path(a.public)).run()
    o = Path(a.output)
    o.mkdir(parents=True, exist_ok=True)
    write_jsonl(o / "entities.jsonl", [e.to_dict() for e in out.ordered_entities()])
    write_jsonl(o / "relations.jsonl", [r.to_dict() for r in out.ordered_relations()])
    fams: dict[str, int] = {}
    for e in out.entities.values():
        fams[e.source.value] = fams.get(e.source.value, 0) + 1
    print(json.dumps({"entities": len(out.entities), "relations": len(out.relations), "entities_by_family": fams}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
