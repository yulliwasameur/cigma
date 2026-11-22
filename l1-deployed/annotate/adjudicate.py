#!/usr/bin/env python3
"""Accord entre annotateurs (κ de Cohen sur l'ensemble des items proposés par A ou B) et fusion avec l'arbitrage.
Usage : adjudicate.py            -> rapport d'accord + liste des désaccords
        adjudicate.py --finalize -> écrit out/oracle/{entities,edges,migration_targets}.csv"""
import csv, pathlib, sys
base = pathlib.Path(__file__).parent
def load(who, name, key):
    with open(base / who / name, newline="") as f:
        return {key(r): r for r in csv.DictReader(f)}
specs = {"entities.csv": lambda r: r["entity_id"].strip(),
         "edges.csv": lambda r: (r["subject_id"].strip(), r["predicate"].strip().upper(), r["object_id"].strip())}
def kappa(a: set, b: set):
    items = a | b
    if not items: return float("nan")
    po = len(a & b) / len(items)               # accord observé sur l'union (présence/absence)
    pa, pb = len(a) / len(items), len(b) / len(items)
    pe = pa * pb + (1 - pa) * (1 - pb)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0
decisions = {}
dpath = base / "C" / "decisions.csv"
if dpath.exists():
    with open(dpath, newline="") as f:
        decisions = {(r["item_kind"], r["item_key"]): r["decision"].strip().lower() for r in csv.DictReader(f)}
out = pathlib.Path(base.parent / "out" / "oracle")
for name, key in specs.items():
    A, B = load("A", name, key), load("B", name, key)
    sa, sb = set(A), set(B)
    print(f"{name}: A={len(sa)} B={len(sb)} accord={len(sa & sb)} κ={kappa(sa, sb):.3f}")
    disagreements = sorted(map(str, sa ^ sb))
    for d in disagreements: print("   désaccord:", d)
    if "--finalize" in sys.argv:
        keep = (sa & sb) | {k for k in sa ^ sb if decisions.get((name, str(k))) == "keep"}
        missing = [k for k in sa ^ sb if (name, str(k)) not in decisions]
        if missing: sys.exit(f"Arbitrage manquant pour {len(missing)} item(s) de {name}")
        out.mkdir(parents=True, exist_ok=True)
        rows = [A.get(k) or B.get(k) for k in sorted(keep, key=str)]
        with open(out / name, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["empty"]); w.writeheader(); w.writerows(rows)
