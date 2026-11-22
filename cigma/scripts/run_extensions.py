#!/usr/bin/env python3
"""Run the ICISSP 2027 extension experiments on CIGMA-Lab.

Usage: PYTHONPATH=src python scripts/run_extensions.py --data data/cigma_lab \
           --config configs/default.yaml --output results/extensions

Every result here is computed on the controlled fixture. The language-model
consensus (ext.consensus) is not run here: it needs the real multi-model outputs
from LUMI (rq3-lumi/). Its behaviour is covered by tests only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from cigma.config import load_config
from cigma.evaluation import evaluate_method, load_oracle
from cigma.experiment import _evaluate
from cigma.io import load_observations, write_json
from cigma.pipeline import METHODS, build_graph
from cigma.scoring import rank_assets
from cigma.ext import active, commitment, exposure, multitool, ordering, reliability


def metrics_row(name, result, extra=None):
    m = result.metrics
    row = {"method": name}
    for k in ("asset_f1", "pairwise_f1", "b3_f1", "typed_edge_f1", "edge_fp_rate",
              "critical_misses", "verify_count", "ndcg_at_5", "ndcg_at_10", "kendall_tau_b"):
        row[k] = m.get(k)
    row.update(extra or {})
    return row


def truth_edge_set(oracle):
    return {(str(e["subject"]), str(e["predicate"]), str(e["object"])) for e in oracle["edges"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/cigma_lab")
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--output", default="results/extensions")
    a = ap.parse_args()
    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=True)
    config = load_config(a.config)
    entities, relations = load_observations(Path(a.data) / "public" / "entities.jsonl", Path(a.data) / "public" / "relations.jsonl")
    oracle = load_oracle(Path(a.data) / "oracle")
    summary: dict = {"notice": "Controlled-fixture results of the clean-room CIGMA extensions."}

    # 1 — learned source reliabilities on the base fixture --------------------------
    rel = reliability.learn_reliabilities(entities, relations, config=config)
    cfg_learned = reliability.config_with_learned_reliabilities(config, rel)
    rows = []
    for name, cfg in (("cigma_fixed_reliability", config), ("cigma_learned_reliability", cfg_learned)):
        _, _, res = _evaluate(entities, relations, config=cfg, oracle=oracle, method="cigma")
        rows.append(metrics_row(name, res))
    pd.DataFrame(rows).to_csv(out / "e1_learned_reliability.csv", index=False)
    write_json(out / "e1_reliabilities.json", {"fixed": config["source_reliabilities"], "learned": rel.to_dict()})
    summary["e1"] = {"learned": rel.reliabilities, "rows": rows}

    # 2 — several disagreeing CBOM tools ---------------------------------------------
    te, tr, toracle, info = multitool.build_tool_views(entities, relations, oracle)
    rel_mt = reliability.learn_reliabilities(te, tr, config=config)
    rel_nocopy = reliability.learn_reliabilities(te, tr, config=config, copy_threshold=1.01)
    variants = []
    for tool in info["tools"]:
        e2, r2 = multitool.restrict_to_tool(te, tr, tool)
        variants.append((f"only_{tool}", e2, r2, config, "cigma"))
    variants.append(("union_all_tools", te, tr, config, "source_union"))
    ve, vr = multitool.majority_vote_filter(te, tr)
    variants.append(("majority_vote_then_cigma", ve, vr, config, "cigma"))
    variants.append(("cigma_fixed_reliability", te, tr, config, "cigma"))
    variants.append(("cigma_learned_no_copy_detection", te, tr,
                     reliability.config_with_learned_reliabilities(config, rel_nocopy), "cigma"))
    variants.append(("cigma_learned_with_copy_detection", te, tr,
                     reliability.config_with_learned_reliabilities(config, rel_mt), "cigma"))
    variants.append(("cigma_learned_copy_aware_support", te, tr,
                     reliability.config_with_learned_reliabilities(config, rel_mt), "cigma+dep"))
    rows = []
    injected_e = set(info["injected"]["entities"])
    graphs_mt = {}
    for name, e2, r2, cfg, method in variants:
        if method == "cigma+dep":
            g0 = build_graph(e2, r2, config=cfg, method="cigma")
            g = reliability.dependence_aware_support(g0, r2, config=cfg, result=rel_mt)
            rk = rank_assets(g, config=cfg)
            res = evaluate_method(g, rk, toracle, entity_observations=e2, relation_observations=r2,
                                  ndcg_cutoffs=cfg["evaluation"]["ndcg_cutoffs"],
                                  ece_bins=int(cfg["evaluation"]["ece_bins"]))
        else:
            g, rk, res = _evaluate(e2, r2, config=cfg, oracle=toracle, method=method)
        graphs_mt[name] = (g, rk, res)
        fake_nodes = {nid for nid, node in g.nodes.items() if set(node.observation_ids) & injected_e}
        fake_edges = sum(1 for e in g.edges if e.subject in fake_nodes or e.object in fake_nodes)
        thr = float(cfg["verification_threshold"])
        inj = [e for e in g.edges if e.subject in fake_nodes or e.object in fake_nodes]
        others = [e for e in g.edges if e not in inj]
        rows.append(metrics_row(name, res, {
            "injected_nodes_accepted": len(fake_nodes),
            "edges_touching_injected": fake_edges,
            "injected_edge_support_mean": round(sum(e.support for e in inj) / len(inj), 4) if inj else None,
            "other_edge_support_mean": round(sum(e.support for e in others) / len(others), 4) if others else None,
            "injected_edges_below_verify_threshold": sum(1 for e in inj if e.support < thr),
        }))
    pd.DataFrame(rows).to_csv(out / "e2_multitool.csv", index=False)
    write_json(out / "e2_multitool_info.json", {**info, "learned_with_copy": rel_mt.to_dict(),
                                                 "learned_without_copy": rel_nocopy.to_dict()})
    summary["e2"] = rows

    # 3 — interoperability-aware order, MOVR, plan certificate -----------------------
    rows, certs = [], {}
    for method in ("tls_inventory", "cbom_inventory", "source_union", "exact_direct", "tfidf_cosine", "cigma"):
        g, rk, res = _evaluate(entities, relations, config=config, oracle=oracle, method=method)
        for order_name, order in (("primary", sorted(rk, key=lambda r: r.primary_rank)),
                                  ("interop_aware", ordering.interop_aware_order(rk, g))):
            outc = ordering.migration_outcomes([r.node_id for r in order], res.node_truth_map, oracle)
            cert = ordering.certify_plan(order, g)
            rows.append({"method": method, "order": order_name, **outc,
                         "plan_constraints_checked": cert["constraints_checked"],
                         "plan_valid_on_predicted_graph": cert["valid"]})
            if method == "cigma":
                certs[order_name] = cert
    pd.DataFrame(rows).to_csv(out / "e3_migration_order.csv", index=False)
    write_json(out / "e3_plan_certificates_cigma.json", certs)
    summary["e3"] = rows

    # 4 — two quantum-risk clocks -----------------------------------------------------
    g, rk, res = _evaluate(entities, relations, config=config, oracle=oracle, method="cigma")
    xrows, xsum = exposure.dual_clock_exposure(rk, g)
    pd.DataFrame([r.__dict__ if hasattr(r, "__dict__") else {s: getattr(r, s) for s in r.__slots__} for r in xrows]
                 ).to_csv(out / "e4_dual_clock.csv", index=False)
    write_json(out / "e4_dual_clock_summary.json", xsum)
    summary["e4"] = xsum

    # 5 — Merkle commitment and per-decision receipts ----------------------------------
    leaves = commitment.graph_leaves(g, rk)
    tree, ordered = commitment.build_tree(leaves)
    receipts = [commitment.decision_receipt(tree, ordered, r.node_id) for r in sorted(rk, key=lambda r: r.primary_rank)[:5]]
    all_ok = all(commitment.verify_inclusion(it["payload"], it["proof"], tree.root) for rc in receipts for it in rc["items"])
    tampered = dict(receipts[0]["items"][0]["payload"])
    tampered["primary_rank"] = tampered.get("primary_rank", 0) + 1 if tampered.get("kind") == "decision" else 0
    tampered["support"] = 0.0
    tamper_detected = not commitment.verify_inclusion(tampered, receipts[0]["items"][0]["proof"], tree.root)
    write_json(out / "e5_commitment.json", {
        "root": tree.root, "leaves": len(ordered), "tree_height": len(tree.levels) - 1,
        "receipts_top5": receipts, "all_receipts_verify": all_ok, "tamper_detected": tamper_detected,
        "mean_disclosed_fraction": sum(r["disclosed_leaves"] for r in receipts) / (len(receipts) * len(ordered)),
    })
    summary["e5"] = {"root": tree.root, "leaves": len(ordered), "all_receipts_verify": all_ok,
                     "tamper_detected": tamper_detected}

    # 6 — budgeted verification on the noisy multi-tool graph ----------------------------
    arows = []
    for gname in ("cigma_fixed_reliability", "cigma_learned_copy_aware_support"):
        g_noisy, _, res_noisy = graphs_mt[gname]
        cont = active.contested_scores(g_noisy, te, tr)
        for row in active.simulate(g_noisy, res_noisy.node_truth_map, truth_edge_set(toracle),
                                   budgets=[0, 2, 4, 6, 8, 10, 15, 20],
                                   policies=("random", "low_support", "impact_uncertainty", "contested"),
                                   contested=cont):
            arows.append({"graph": gname, **row})
    pd.DataFrame(arows).to_csv(out / "e6_active_verification.csv", index=False)
    summary["e6"] = arows

    write_json(out / "summary.json", summary)
    print(json.dumps({k: (v if k in ("e4", "e5") else "ok") for k, v in summary.items() if k != "notice"}, indent=1))


if __name__ == "__main__":
    main()
