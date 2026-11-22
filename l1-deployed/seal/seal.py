#!/usr/bin/env python3
"""Phase 1 — scelle les prédictions AVANT tout accès à l'oracle.
Écrit seal.json : empreintes SHA-256 des entrées publiques, des prédictions de chaque méthode,
de la configuration et du commit du code. Usage : seal.py <dossier_predictions> <dossier_public> <config.yaml>"""
import hashlib, json, pathlib, subprocess, sys, datetime

def tree_hash(p: pathlib.Path) -> dict:
    return {str(f.relative_to(p)): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in sorted(p.rglob("*")) if f.is_file()}

pred, pub, cfg = map(pathlib.Path, sys.argv[1:4])
try:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
except Exception:
    commit = "unknown"
seal = {"sealed_at_utc": datetime.datetime.utcnow().isoformat() + "Z", "code_commit": commit,
        "config_sha256": hashlib.sha256(cfg.read_bytes()).hexdigest(),
        "public_inputs": tree_hash(pub), "predictions": tree_hash(pred)}
seal["seal_sha256"] = hashlib.sha256(json.dumps(seal, sort_keys=True).encode()).hexdigest()
out = pathlib.Path("seal/seal.json"); out.write_text(json.dumps(seal, indent=2, sort_keys=True))
print(f"Scellé : {len(seal['predictions'])} fichiers de prédiction ; empreinte {seal['seal_sha256'][:16]}…")
print("Publier seal_sha256 (par ex. dans un commit horodaté) AVANT d'ouvrir l'oracle.")
