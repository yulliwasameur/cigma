#!/usr/bin/env python3
"""Build the private witness inputs of policy.circom from a CIGMA graph.

Scenario "current": the fixture as it is (exposed endpoints still use RSA/ECDSA without
hybrid) -> rule 1 is violated, so no valid proof can exist (witness generation fails).
Scenario "after_plan": the exposed, vulnerable assets have been switched to hybrid key
establishment by the first windows of the certified plan -> a proof exists.

Usage (from cigma/): PYTHONPATH=src python zk/make_inputs.py --out zk/build
"""
import argparse
import json
import secrets
from pathlib import Path

from cigma.config import load_config
from cigma.io import load_observations
from cigma.pipeline import build_graph
from cigma.scoring import rank_assets

N = 32
FIELD = 21888242871839275222246405745257275088548364400416034343698204186575808495617

ap = argparse.ArgumentParser()
ap.add_argument("--data", default="data/cigma_lab")
ap.add_argument("--out", default="zk/build")
a = ap.parse_args()
cfg = load_config("configs/default.yaml")
E, R = load_observations(Path(a.data) / "public/entities.jsonl", Path(a.data) / "public/relations.jsonl")
g = build_graph(E, R, config=cfg, method="cigma")
rk = sorted(rank_assets(g, config=cfg), key=lambda r: r.primary_rank)

records = []
for r in rk:
    records.append({"node_id": r.node_id,
                    "exposed": int((r.impact.get("X") or 0) >= 0.5),
                    "vulnerable": int((r.impact.get("Q") or 0) >= 1.0),
                    "hybrid": 0,
                    "highrisk": int(r.upper_tier >= 3)})
while len(records) < N:
    records.append({"node_id": None, "exposed": 0, "vulnerable": 0, "hybrid": 0, "highrisk": 0})
salts = [secrets.randbelow(FIELD) for _ in range(N)]


def witness(recs, threshold):
    return {"exposed": [x["exposed"] for x in recs], "vulnerable": [x["vulnerable"] for x in recs],
            "hybrid": [x["hybrid"] for x in recs], "highrisk": [x["highrisk"] for x in recs],
            "salt": [str(s) for s in salts], "threshold": str(threshold)}


out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
after = [dict(x) for x in records]
for x in after:
    if x["exposed"] and x["vulnerable"]:
        x["hybrid"] = 1
hv = sum(x["highrisk"] * x["vulnerable"] for x in after)
(out / "input_current.json").write_text(json.dumps(witness(records, hv)))
(out / "input_after_plan.json").write_text(json.dumps(witness(after, hv)))
(out / "input_after_plan_tight.json").write_text(json.dumps(witness(after, max(0, hv - 1))))
stats = {"assets": len(rk), "padded_to": N,
         "exposed_and_vulnerable_without_hybrid_current": sum(x["exposed"] * x["vulnerable"] for x in records),
         "highrisk_and_vulnerable": hv, "public_threshold": hv}
(out / "inputs_stats.json").write_text(json.dumps(stats, indent=1))
print(json.dumps(stats))
