#!/usr/bin/env python3
"""Second batch of ICISSP 2027 experiments (A* plan): poisoning, conformal FDR, Pareto front.

PYTHONPATH=src python scripts/run_extensions_v2.py --output results/extensions
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import numpy as np
import pandas as pd

from cigma.config import load_config
from cigma.evaluation import evaluate_method, load_oracle
from cigma.experiment import _evaluate
from cigma.io import load_observations, write_json
from cigma.pipeline import build_graph
from cigma.scoring import rank_assets
from cigma.ext import conformal, ordering, poisoning, reliability


def truth_edges(oracle):
    return {(str(e["subject"]), str(e["predicate"]), str(e["object"])) for e in oracle["edges"]}


def build(e, r, cfg, oracle, learned: bool):
    if learned:
        res_rel = reliability.learn_reliabilities(e, r, config=cfg)
        cfg = reliability.config_with_learned_reliabilities(cfg, res_rel)
        g = reliability.dependence_aware_support(build_graph(e, r, config=cfg, method="cigma"), r, config=cfg, result=res_rel)
    else:
        g = build_graph(e, r, config=cfg, method="cigma")
    rk = rank_assets(g, config=cfg)
    res = evaluate_method(g, rk, oracle, entity_observations=e, relation_observations=r,
                          ndcg_cutoffs=cfg["evaluation"]["ndcg_cutoffs"], ece_bins=int(cfg["evaluation"]["ece_bins"]))
    return g, rk, res, cfg


def bootstrap_ci(values, seed=0, n=2000):
    rng = np.random.default_rng(seed)
    arr = np.asarray(values, dtype=float)
    if len(arr) == 0:
        return (float("nan"), float("nan"))
    means = [rng.choice(arr, size=len(arr), replace=True).mean() for _ in range(n)]
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/cigma_lab")
    ap.add_argument("--config", default="configs/default.yaml")
    ap.add_argument("--output", default="results/extensions")
    ap.add_argument("--seeds", type=int, default=20)
    a = ap.parse_args()
    out = Path(a.output)
    out.mkdir(parents=True, exist_ok=True)
    cfg0 = load_config(a.config)
    E, R = load_observations(Path(a.data) / "public" / "entities.jsonl", Path(a.data) / "public" / "relations.jsonl")
    O = load_oracle(Path(a.data) / "oracle")
    summary = {}

    # E7 — poisoning campaign ---------------------------------------------------------
    rows = []
    for k in (0, 2, 4, 8, 16):
        for seed in range(a.seeds):
            e, r, o, inj = poisoning.poison(E, R, O, k=k, seed=1000 + seed)
            inj_set = set(inj)
            for name, learned in (("cigma_fixed", False), ("cigma_learned_copy_aware", True)):
                g, rk, res, cfg = build(e, r, cfg0, o, learned)
                thr = float(cfg0["verification_threshold"])
                poisoned_edges = [x for x in g.edges if set(x.evidence_ids) & inj_set]
                rows.append({"k": k, "seed": seed, "method": name,
                             "typed_edge_f1": res.metrics["typed_edge_f1"],
                             "edge_fp_rate": res.metrics["edge_fp_rate"],
                             "poisoned_edges_accepted": len(poisoned_edges),
                             "poisoned_edges_flagged_for_review": sum(1 for x in poisoned_edges if x.support < thr),
                             "true_edges_flagged_for_review": sum(
                                 1 for x in g.edges
                                 if x not in poisoned_edges and x.support < thr
                                 and res.node_truth_map.get(x.subject) is not None
                                 and (res.node_truth_map.get(x.subject), x.predicate.value, res.node_truth_map.get(x.object)) in truth_edges(o)),
                             "kendall_tau_b": res.metrics["kendall_tau_b"]})
            g, rk, res = _evaluate(e, r, config=cfg0, oracle=o, method="source_union")
            rows.append({"k": k, "seed": seed, "method": "source_union",
                         "typed_edge_f1": res.metrics["typed_edge_f1"], "edge_fp_rate": res.metrics["edge_fp_rate"],
                         "poisoned_edges_accepted": sum(1 for x in g.edges if set(x.evidence_ids) & inj_set),
                         "poisoned_edges_flagged_for_review": None, "true_edges_flagged_for_review": None, "kendall_tau_b": res.metrics["kendall_tau_b"]})
    df = pd.DataFrame(rows)
    df.to_csv(out / "e7_poisoning_runs.csv", index=False)
    agg = df.groupby(["method", "k"]).agg(typed_edge_f1=("typed_edge_f1", "mean"),
                                          edge_fp_rate=("edge_fp_rate", "mean"),
                                          poisoned_accepted=("poisoned_edges_accepted", "mean"),
                                          poisoned_flagged=("poisoned_edges_flagged_for_review", "mean"),
                                          true_flagged=("true_edges_flagged_for_review", "mean")).reset_index()
    agg.to_csv(out / "e7_poisoning_summary.csv", index=False)
    summary["e7"] = agg.round(4).to_dict(orient="records")

    # E8 — conformal FDR on accepted edges (split: train scorer / calibrate / test) ---------
    from sklearn.linear_model import LogisticRegression

    def scenario(seed):
        k = (4, 8, 16)[seed % 3]
        e, r, o, _ = poisoning.poison(E, R, O, k=k, seed=seed)
        rr = reliability.learn_reliabilities(e, r, config=cfg0)
        c2 = reliability.config_with_learned_reliabilities(cfg0, rr)
        gl = reliability.dependence_aware_support(build_graph(e, r, config=c2, method="cigma"), r, config=c2, result=rr)
        gf = build_graph(e, r, config=cfg0, method="cigma")
        res = evaluate_method(gl, rank_assets(gl, config=c2), o, entity_observations=e, relation_observations=r)
        feats = conformal.edge_features(gf, gl, r)
        labels = conformal.edge_labels(gl, res.node_truth_map, truth_edges(o))
        X = [feats[x.triple] for x in gl.edges]
        y = [int(t) for _, t in labels]
        fixed_support = [row[0] for row in X]
        return X, y, fixed_support

    n = 3 * a.seeds
    train = [scenario(s) for s in range(3000, 3000 + n)]
    Xtr = [x for X, _, _ in train for x in X]
    ytr = [v for _, y, _ in train for v in y]
    scorer = LogisticRegression(max_iter=2000).fit(Xtr, ytr)
    calib_learned, calib_fixed = [], []
    for s in range(5000, 5000 + n):
        X, y, fs = scenario(s)
        sc = scorer.predict_proba(X)[:, 1]
        calib_learned += [float(v) for v, t in zip(sc, y) if not t]
        calib_fixed += [v for v, t in zip(fs, y) if not t]
    crow = []
    for s in range(9000, 9000 + n):
        X, y, fs = scenario(s)
        sc = [float(v) for v in scorer.predict_proba(X)[:, 1]]
        truth = [bool(t) for t in y]
        for alpha in (0.05, 0.10, 0.20):
            for score_name, scores, cal in (("learned_score", sc, calib_learned), ("fixed_support", fs, calib_fixed)):
                acc = conformal.select(scores, cal, alpha)
                fdp, power = conformal.fdp_and_power(acc, truth)
                crow.append({"seed": s, "rule": f"conformal_{score_name}_alpha_{alpha}", "fdp": fdp, "power": power})
        for name, thr in (("accept_all", -1.0), ("threshold_0.85", 0.85), ("threshold_0.50", 0.50)):
            acc = [v >= thr for v in fs]
            fdp, power = conformal.fdp_and_power(acc, truth)
            crow.append({"seed": s, "rule": name, "fdp": fdp, "power": power})
    cdf = pd.DataFrame(crow)
    cdf.to_csv(out / "e8_conformal_runs.csv", index=False)
    csum = []
    for rule, grp in cdf.groupby("rule"):
        lo, hi = bootstrap_ci(grp["fdp"].tolist())
        csum.append({"rule": rule, "fdr_mean": grp["fdp"].mean(), "fdr_ci95_low": lo, "fdr_ci95_high": hi,
                     "power_mean": grp["power"].mean(), "test_scenarios": len(grp)})
    pd.DataFrame(csum).to_csv(out / "e8_conformal_summary.csv", index=False)
    summary["e8"] = {"train_edges": len(Xtr), "calibration_false_edges": len(calib_learned),
                     "rows": pd.DataFrame(csum).round(4).to_dict(orient="records")}

    # E9 — Pareto front urgency vs breakage --------------------------------------------
    g, rk, res = _evaluate(E, R, config=cfg0, oracle=O, method="cigma")
    prow = []
    for lam in [i / 10 for i in range(11)]:
        order = ordering.blended_order(rk, g, lam)
        outc = ordering.migration_outcomes([x.node_id for x in order], res.node_truth_map, O)
        prow.append({"lambda": lam, **outc, "plan_valid": ordering.certify_plan(order, g)["valid"]})
    pd.DataFrame(prow).to_csv(out / "e9_pareto_front.csv", index=False)
    summary["e9"] = prow

    # E10 — signed observations (ML-DSA-65, DSSE) against poisoning -------------------
    from cigma.ext import attestation
    from cigma.resolution import reliability_key
    e, r, o, inj = poisoning.poison(E, R, O, k=8, seed=4242)
    inj_set = set(inj)
    honest_keys = sorted({reliability_key(x) for x in list(E) + list(R)})
    keys = {k: attestation.generate_key(k) for k in honest_keys}
    ring = attestation.Keyring()
    for k in keys.values():
        ring.add(k)
    rows10 = []
    # (a) outsider: attacker signs with its own key, not in the keyring
    keys_a = dict(keys)
    keys_a["cbom:mal"] = keys_a["tls:mal"] = keys_a["pki:mal"] = keys_a["cmdb:mal"] = attestation.generate_key("mal")
    for k in [x for x in {reliability_key(y) for y in list(e) + list(r)} if x.endswith(":mal")]:
        keys_a[k] = keys_a["cbom:mal"]
    ee, re_, timing = attestation.sign_all(e, r, keys_a)
    ve, vr, info = attestation.load_verified(ee, re_, ring)
    g, rk, res = _evaluate(ve, vr, config=cfg0, oracle=o, method="cigma")
    rows10.append({"scenario": "outsider_untrusted_key", "poisoned_accepted": sum(1 for x in g.edges if set(x.evidence_ids) & inj_set),
                   "typed_edge_f1": res.metrics["typed_edge_f1"], **{f"reason_{k}": v for k, v in info["reasons"].items()}})
    # (b) insider: attacker holds the key of a trusted tool (cbom); then that key is revoked
    mal_rel_key = next(iter({reliability_key(y) for y in r if y.observation_id in inj_set}))
    fam = mal_rel_key.split(":")[0]
    keys_b = dict(keys)
    for k in {reliability_key(y) for y in list(e) + list(r)}:
        if k.endswith(":mal"):
            keys_b[k] = keys[fam]
    eb, rb, _ = attestation.sign_all(e, r, keys_b)
    vb, vrb, infob = attestation.load_verified(eb, rb, ring)
    g, rk, res = _evaluate(vb, vrb, config=cfg0, oracle=o, method="cigma")
    rows10.append({"scenario": "insider_stolen_trusted_key", "poisoned_accepted": sum(1 for x in g.edges if set(x.evidence_ids) & inj_set),
                   "typed_edge_f1": res.metrics["typed_edge_f1"], **{f"reason_{k}": v for k, v in infob["reasons"].items()}})
    ring.revoke(keys[fam].keyid)
    vc, vrc, infoc = attestation.load_verified(eb, rb, ring)
    g, rk, res = _evaluate(vc, vrc, config=cfg0, oracle=o, method="cigma")
    rows10.append({"scenario": f"insider_after_revoking_{fam}_key", "poisoned_accepted": sum(1 for x in g.edges if set(x.evidence_ids) & inj_set),
                   "typed_edge_f1": res.metrics["typed_edge_f1"], **{f"reason_{k}": v for k, v in infoc["reasons"].items()}})
    pd.DataFrame(rows10).to_csv(out / "e10_signed_observations.csv", index=False)
    summary["e10"] = {"rows": rows10, "timing": timing, "verify_seconds": info["verify_seconds_total"],
                      "scheme": "ML-DSA-65 (FIPS 204), dilithium-py reference implementation",
                      "public_key_bytes": len(next(iter(keys.values())).public_key)}

    write_json(out / "summary_v2.json", summary)
    print(json.dumps({"e7": summary["e7"][:4], "e8": summary["e8"], "e9": prow}, indent=1, default=float)[:6000])


if __name__ == "__main__":
    main()
