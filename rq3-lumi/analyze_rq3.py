#!/usr/bin/env python3
"""Analyse the LUMI runs: validate every call with CIGMA's fail-closed validator, score against
the oracle, and build the k-of-n consensus curve.  Usage (from cigma/):
  PYTHONPATH=src python ../rq3-lumi/analyze_rq3.py --runs ../rq3-lumi/runs --out ../results/rq3
"""
import argparse, json
from collections import defaultdict
from pathlib import Path
import pandas as pd
from cigma.config import load_config
from cigma.evaluation import load_oracle, evaluate_method
from cigma.io import load_observations
from cigma.openai_adapter import validate_candidate_batch
from cigma.pipeline import build_graph
from cigma.scoring import rank_assets
from cigma.ext import consensus

ap = argparse.ArgumentParser(); ap.add_argument("--runs", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--data", default="data/cigma_lab"); a = ap.parse_args()
cfg = load_config("configs/default.yaml")
E, R = load_observations(Path(a.data) / "public/entities.jsonl", Path(a.data) / "public/relations.jsonl")
O = load_oracle(Path(a.data) / "oracle")
truth = {(str(e["subject"]), str(e["predicate"]), str(e["object"])) for e in O["edges"]}
graphs = {"cigma-lab-complete": "cigma", "cigma-lab-no-path": "cigma_no_paths", "cigma-lab-injected": "cigma"}
rows, batches = [], defaultdict(lambda: defaultdict(list))
for f in sorted(Path(a.runs).rglob("call-*.json")):
    model, inp, temp = f.parts[-4], f.parts[-3], f.parts[-2]
    if inp not in graphs: continue
    g = build_graph(E, R, config=cfg, method=graphs[inp]); res = evaluate_method(g, rank_assets(g, config=cfg), O, entity_observations=E, relation_observations=R)
    rec = json.loads(f.read_text()); content = rec["response"]["choices"][0]["message"]["content"]
    try: raw = json.loads(content); audit = validate_candidate_batch(raw, graph=g, relation_observations=R)
    except Exception as exc: rows.append({"model": model, "input": inp, "temperature": temp, "call": f.name, "parse_error": str(exc)[:80]}); continue
    batches[(inp, temp)][model].append(raw)
    proposed = raw.get("candidates", [])
    sc = consensus.score_against_truth([[c.subject, c.predicate.value, c.object] for c in audit.accepted], res.node_truth_map, truth)
    rows.append({"model": model, "input": inp, "temperature": temp, "call": f.name, "proposed": len(proposed),
                 "accepted": len(audit.accepted), "rejected": len(audit.rejected), **sc, "graph_mutated": audit.graph_mutated})
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
pd.DataFrame(rows).to_csv(out / "rq3_calls.csv", index=False)
crow = []
for (inp, temp), per_model in batches.items():
    g = build_graph(E, R, config=cfg, method=graphs[inp]); res = evaluate_method(g, rank_assets(g, config=cfg), O, entity_observations=E, relation_observations=R)
    for k in range(1, len(per_model) + 1):
        c = consensus.consensus(per_model, graph=g, relation_observations=R, k=k)
        crow.append({"input": inp, "temperature": temp, "k": k, **consensus.score_against_truth(c["kept_triples"], res.node_truth_map, truth)})
pd.DataFrame(crow).to_csv(out / "rq3_consensus.csv", index=False)
print(f"{len(rows)} calls analysed; consensus rows: {len(crow)}")
