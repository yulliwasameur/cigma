#!/usr/bin/env python3
"""Extrait de chaque certificat (fichiers .crt et sorties `istioctl proxy-config secret`) :
empreinte SHA-256, empreinte SPKI, sujet, émetteur, algorithme de clé, taille, dates.
Une ligne JSON par certificat, avec le chemin du fichier source (= le « locator » de CIGMA)."""
import base64, hashlib, json, pathlib, subprocess, sys

def info(pem: bytes, locator: str):
    def ossl(*args):
        return subprocess.run(["openssl", "x509", *args], input=pem, capture_output=True).stdout.decode()
    der = subprocess.run(["openssl", "x509", "-outform", "DER"], input=pem, capture_output=True).stdout
    spki = subprocess.run(["openssl", "x509", "-pubkey", "-noout"], input=pem, capture_output=True).stdout
    spki_der = subprocess.run(["openssl", "pkey", "-pubin", "-outform", "DER"], input=spki, capture_output=True).stdout
    text = ossl("-noout", "-text")
    alg = next((l.split(":", 1)[1].strip() for l in text.splitlines() if "Public Key Algorithm" in l), "")
    bits = next((l.strip() for l in text.splitlines() if "Public-Key:" in l), "")
    return {"locator": locator, "fingerprint_sha256": hashlib.sha256(der).hexdigest(),
            "spki_sha256": hashlib.sha256(spki_der).hexdigest(), "subject": ossl("-noout", "-subject").strip(),
            "issuer": ossl("-noout", "-issuer").strip(), "key_algorithm": alg, "key_size": bits,
            "not_before": ossl("-noout", "-startdate").strip(), "not_after": ossl("-noout", "-enddate").strip()}

root = pathlib.Path(sys.argv[1])
for f in sorted(root.glob("*.crt")):
    print(json.dumps(info(f.read_bytes(), str(f.relative_to(root.parent)))))
for f in sorted(root.glob("mtls-*.json")):
    try:
        d = json.loads(f.read_text())
    except Exception:
        continue
    for i, s in enumerate(d.get("dynamicActiveSecrets", [])):
        tc = s.get("secret", {}).get("tlsCertificate") or {}
        chain = tc.get("certificateChain", {}).get("inlineBytes")
        if chain:
            pem = base64.b64decode(chain)
            for j, block in enumerate(pem.split(b"-----END CERTIFICATE-----")[:-1]):
                print(json.dumps(info(block + b"-----END CERTIFICATE-----\n", f"{f.relative_to(root.parent)}#/dynamicActiveSecrets/{i}/chain/{j}")))
