#!/usr/bin/env python3
"""Official evaluator of the CIGMA benchmark.

  python scripts/cigma_eval.py --submission my_method.json --data data/cigma_lab
  python scripts/cigma_eval.py --make-baseline cigma --data data/cigma_lab --out sub.json

The first form prints the leaderboard row. The second writes a valid submission
from one of CIGMA's built-in methods (useful as a template).
"""
import argparse, json
from pathlib import Path
from cigma.config import load_config
from cigma.io import load_observations
from cigma.pipeline import build_graph
from cigma.scoring import rank_assets
from cigma.ext.benchmark_api import evaluate_submission, SUBMISSION_SCHEMA_VERSION

ap = argparse.ArgumentParser()
ap.add_argument("--submission"); ap.add_argument("--data", default="data/cigma_lab")
ap.add_argument("--make-baseline"); ap.add_argument("--out", default="submission.json")
ap.add_argument("--config", default="configs/default.yaml")
a = ap.parse_args()
if a.make_baseline:
    d = Path(a.data) / "public"
    e, r = load_observations(d / "entities.jsonl", d / "relations.jsonl")
    cfg = load_config(a.config)
    g = build_graph(e, r, config=cfg, method=a.make_baseline)
    rk = rank_assets(g, config=cfg)
    Path(a.out).write_text(json.dumps({"schema": SUBMISSION_SCHEMA_VERSION, "method": a.make_baseline,
        "graph": g.to_dict(), "order": [x.node_id for x in sorted(rk, key=lambda x: x.primary_rank)],
        "rankings": [x.to_dict() for x in rk]}, indent=1))
    print(f"wrote {a.out}")
if a.submission:
    print(json.dumps(evaluate_submission(a.submission, a.data), indent=1))
