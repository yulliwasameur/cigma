#!/usr/bin/env python3
"""Phase 2 — vérifie que rien n'a bougé depuis le scellement. Code de sortie 1 si une empreinte diffère :
l'évaluation contre l'oracle ne doit alors PAS être lancée."""
import hashlib, json, pathlib, sys
seal = json.loads(pathlib.Path("seal/seal.json").read_text())
pred, pub = map(pathlib.Path, sys.argv[1:3])
bad = []
for root, key in ((pred, "predictions"), (pub, "public_inputs")):
    for rel, h in seal[key].items():
        f = root / rel
        if not f.exists() or hashlib.sha256(f.read_bytes()).hexdigest() != h:
            bad.append(f"{key}/{rel}")
body = {k: v for k, v in seal.items() if k != "seal_sha256"}
if hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() != seal["seal_sha256"]:
    bad.append("seal.json lui-même")
if bad:
    print("SCELLEMENT ROMPU :", *bad, sep="\n  "); sys.exit(1)
print("Scellement intact. Évaluation autorisée.")
