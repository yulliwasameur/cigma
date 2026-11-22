#!/usr/bin/env python3
"""Reviewer-requested experiments for the ICISSP camera-ready.

E17  Equal-access comparators: exact / TF-IDF / Fellegi-Sunter (Splink-style EM) / any-shared-identifier
     rules, all given CIGMA's quality gate and path rules, on L0 and under seeded deletion.
E18  Recoverable-edge oracle: under deletion, recall is also reported against the truth edges that are
     still recoverable from the surviving observations (a surviving relation observation maps to the
     edge, or the edge is derived and its path components are recoverable).
E19  Noisy identifiers: k decoy services that reuse the name of a real service but carry a different
     service UID (a distinct real entity, added to a copy of the oracle).

Usage (from cigma/): PYTHONPATH=src python scripts/run_equal_access.py --output ../results/equal_access
"""
from __future__ import annotations

import argparse
import copy
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from cigma.config import load_config
from cigma.evaluation import load_oracle
from cigma.experiment import _drop_observations, _evaluate
from cigma.io import load_observations

METHODS = ["exact_direct", "exact_direct_paths", "tfidf_cosine_paths", "fellegi_sunter_paths",
           "rules_any_id_paths", "cigma_no_paths", "cigma", "cigma_guard"]


def recoverable_edges(oracle, relations, entities):
    """Truth triples recoverable from the surviving observations."""
    o2t = oracle["observation_to_truth"]
    r2t = oracle["relation_to_truth"]
    by_id = {e["edge_id"]: e for e in oracle["edges"]}
    kept_truth_nodes = {o2t.get(e.observation_id) for e in entities} - {None}
    direct = set()
    for r in relations:
        eid = r2t.get(r.observation_id)
        if eid and eid in by_id:
            e = by_id[eid]
            if e["subject"] in kept_truth_nodes and e["object"] in kept_truth_nodes:
                direct.add((e["subject"], e["predicate"], e["object"]))
    rec = set(direct)
    changed = True
    while changed:                       # close under the two declared path rules
        changed = False
        for e in oracle["edges"]:
            t = (e["subject"], e["predicate"], e["object"])
            if t in rec or not e.get("derived"):
                continue
            s, o = e["subject"], e["object"]
            hosts = {b for (a, p, b) in rec if a == s and p == "HOSTS"}
            pres = {b for (a, p, b) in rec if a in hosts and p == "PRESENTS"}
            uses_c = {b for (a, p, b) in rec if a in pres and p == "USES"}
            comp = {b for (a, p, b) in rec if a == s and p == "USES"}
            uses_s = {b for (a, p, b) in rec if a in comp and p == "USES"}
            if o in uses_c or o in uses_s:
                rec.add(t)
                changed = True
    return rec


def edge_recall_on(graph, res, truth_subset):
    found = set()
    for edge in graph.edges:
        s, o = res.node_truth_map.get(edge.subject), res.node_truth_map.get(edge.object)
        if s is not None and o is not None and (s, edge.predicate.value, o) in truth_subset:
            found.add((s, edge.predicate.value, o))
    return len(found) / max(1, len(truth_subset))


def add_decoys(entities, relations, oracle, k, seed):
    """k decoy services reusing a real service name with a different UID (distinct truth entities)."""
    rng = np.random.default_rng(seed)
    services = [e for e in entities if e.entity_type.value == "service" and e.identifiers.get("service_name")
                and oracle["observation_to_truth"].get(e.observation_id)]
    names = sorted({e.identifiers["service_name"] for e in services})
    ents, orc = list(entities), copy.deepcopy(oracle)
    for i in range(k):
        name = names[int(rng.integers(len(names)))]
        base = next(e for e in services if e.identifiers["service_name"] == name)
        oid = f"decoy-{seed}-{i}"
        ids = {"service_name": name, "service_uid": f"svc-decoy-{seed}-{i}"}
        decoy = replace(base, observation_id=oid, local_key=f"decoy:{seed}:{i}", identifiers=ids)
        ents.append(decoy)
        tid = f"truth-decoy-{seed}-{i}"
        orc["nodes"].append({"truth_id": tid, "entity_type": "service"})
        orc["observation_to_truth"][oid] = tid
    return ents, relations, orc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/cigma_lab")
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--output", required=True)
    ap.add_argument("--seeds", type=int, default=32)
    a = ap.parse_args()
    out = Path(a.output); out.mkdir(parents=True, exist_ok=True)
    cfg = load_config(a.config)
    E, R = load_observations(Path(a.data) / "public/entities.jsonl", Path(a.data) / "public/relations.jsonl")
    O = load_oracle(Path(a.data) / "oracle")
    all_truth = {(e["subject"], e["predicate"], e["object"]) for e in O["edges"]}

    rows = []
    for m in METHODS:
        g, rk, res = _evaluate(E, R, config=cfg, oracle=O, method=m)
        x = res.metrics
        rows.append({"method": m, **{k: x[k] for k in ("asset_f1", "pairwise_f1", "b3_f1", "edge_f1", "edge_fp_rate")}})
    pd.DataFrame(rows).to_csv(out / "e17_complete.csv", index=False)

    rob = []
    base_seed = int(cfg["evaluation"]["statistics_seed"])
    for p in (0.0, 0.10, 0.25, 0.50):
        for s in range(a.seeds if p > 0 else 1):
            seed = base_seed + int(p * 10000) + s
            e2, r2, _ = _drop_observations(E, R, probability=p, seed=seed)
            rec = recoverable_edges(O, r2, e2)
            for m in METHODS:
                g, rk, res = _evaluate(e2, r2, config=cfg, oracle=O, method=m)
                x = res.metrics
                rr = edge_recall_on(g, res, rec)
                prec = x["edge_precision"]
                rob.append({"p": p, "seed": s, "method": m, "edge_f1": x["edge_f1"], "edge_precision": prec,
                            "edge_recall_full": x["edge_recall"], "edge_recall_recoverable": rr,
                            "edge_f1_recoverable": 2 * prec * rr / max(1e-12, prec + rr),
                            "recoverable_share": len(rec) / len(all_truth), "pairwise_f1": x["pairwise_f1"]})
    pd.DataFrame(rob).to_csv(out / "e17_e18_deletion.csv", index=False)

    noisy = []
    for k in (0, 1, 2, 4):
        for s in range(10 if k else 1):
            e3, r3, o3 = add_decoys(E, R, O, k, 1000 + s)
            for m in METHODS:
                g, rk, res = _evaluate(e3, r3, config=cfg, oracle=o3, method=m)
                x = res.metrics
                noisy.append({"decoys": k, "seed": s, "method": m, "pairwise_f1": x["pairwise_f1"],
                              "b3_f1": x["b3_f1"], "edge_f1": x["edge_f1"], "edge_fp_rate": x["edge_fp_rate"]})
    pd.DataFrame(noisy).to_csv(out / "e19_noisy_identifiers.csv", index=False)
    print("done")


if __name__ == "__main__":
    main()
