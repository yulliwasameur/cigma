"""Tests for the ICISSP 2027 extensions (cigma.ext)."""

from pathlib import Path

import pytest

from cigma.config import load_config
from cigma.evaluation import load_oracle
from cigma.experiment import _evaluate
from cigma.io import load_observations
from cigma.pipeline import build_graph
from cigma.ext import active, commitment, consensus, exposure, hybrid, multitool, ordering, reliability

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "cigma_lab"


@pytest.fixture(scope="module")
def setup():
    if not (DATA / "public" / "entities.jsonl").exists():
        pytest.skip("fixture not generated (run make verify first)")
    cfg = load_config(ROOT / "configs" / "default.yaml")
    e, r = load_observations(DATA / "public" / "entities.jsonl", DATA / "public" / "relations.jsonl")
    o = load_oracle(DATA / "oracle")
    return cfg, e, r, o


def test_learned_reliabilities_in_unit_interval_and_converge(setup):
    cfg, e, r, _ = setup
    res = reliability.learn_reliabilities(e, r, config=cfg)
    assert res.converged
    assert all(0.0 < v <= 1.0 for v in res.reliabilities.values())


def test_copy_detection_flags_the_copying_tools_only(setup):
    cfg, e, r, o = setup
    te, tr, _, _ = multitool.build_tool_views(e, r, o)
    res = reliability.learn_reliabilities(te, tr, config=cfg)
    assert [p[:2] for p in res.dependent_pairs] == [("cbom:tool_b", "cbom:tool_c")]
    assert res.reliabilities["cbom:tool_a"] > res.reliabilities["cbom:tool_b"]
    no_copy = reliability.learn_reliabilities(te, tr, config=cfg, copy_threshold=1.01)
    assert no_copy.reliabilities["cbom:tool_b"] > no_copy.reliabilities["cbom:tool_a"]


def test_tool_views_keep_ids_unique_and_oracle_consistent(setup):
    _, e, r, o = setup
    te, tr, to, info = multitool.build_tool_views(e, r, o)
    assert len({x.observation_id for x in te}) == len(te)
    assert all(x.observation_id in to["observation_to_truth"] for x in te)
    assert all(to["observation_to_truth"][i] is None for i in info["injected"]["entities"])


def test_interop_aware_order_removes_breaks_on_cigma(setup):
    cfg, e, r, o = setup
    g, rk, res = _evaluate(e, r, config=cfg, oracle=o, method="cigma")
    order = ordering.interop_aware_order(rk, g)
    assert ordering.certify_plan(order, g)["valid"]
    out = ordering.migration_outcomes([x.node_id for x in order], res.node_truth_map, o)
    assert out["movr"] == 0.0
    assert sorted(x.node_id for x in order) == sorted(x.node_id for x in rk)


def test_merkle_receipts_verify_and_detect_tampering(setup):
    cfg, e, r, o = setup
    g, rk, _ = _evaluate(e, r, config=cfg, oracle=o, method="cigma")
    tree, ordered = commitment.build_tree(commitment.graph_leaves(g, rk))
    for i, payload in enumerate(ordered):
        assert commitment.verify_inclusion(payload, commitment.inclusion_proof(tree, i), tree.root)
    bad = dict(ordered[0])
    bad["kind"] = "tampered"
    assert not commitment.verify_inclusion(bad, commitment.inclusion_proof(tree, 0), tree.root)


def test_dual_clock_marks_trust_anchor_as_authenticity_dominant(setup):
    cfg, e, r, o = setup
    g, rk, _ = _evaluate(e, r, config=cfg, oracle=o, method="cigma")
    rows, summary = exposure.dual_clock_exposure(rk, g, {"draws": 50})
    anchors = [x for x in rows if x.anchor_reach > 0]
    assert anchors and all(x.dominant_clock == "TNFL" for x in anchors)
    assert summary["assets"] == len(rk)


def test_consensus_requires_k_models_and_never_mutates(setup):
    cfg, e, r, o = setup
    g = build_graph(e, r, config=cfg, method="cigma")
    edge = next(x for x in g.edges if not x.derived)
    good = {"candidates": [{
        "claim_id": "c1", "subject": edge.subject, "predicate": edge.predicate.value, "object": edge.object,
        "method": "direct", "rule_id": None, "evidence_ids": [edge.evidence_ids[0]], "rationale": "x"}]}
    before = len(g.edges)
    one = consensus.consensus({"m1": [good], "m2": [{"candidates": []}]}, graph=g, relation_observations=r, k=2)
    two = consensus.consensus({"m1": [good], "m2": [good]}, graph=g, relation_observations=r, k=2)
    assert one["kept_triples"] == [] and len(two["kept_triples"]) == 1
    assert len(g.edges) == before and two["graph_mutated"] is False


def test_hybrid_group_classification_and_policy(setup):
    cfg, *_ = setup
    assert hybrid.classify_group("X25519MLKEM768") == "hybrid"
    assert hybrid.classify_group("x25519") == "classical"
    assert hybrid.extend_policy(cfg)["algorithm_policy"]["values"]["X25519MLKEM768"] == 0.0
    out = hybrid.adapt_tls_kex_records([{
        "endpoint_local_key": "ep1", "endpoint_uri": "https://shop.cigma.local:443",
        "negotiated_group": "X25519MLKEM768", "supported_groups": ["X25519MLKEM768", "X25519"]}],
        collected_at="2026-11-21T00:00:00+00:00")
    assert any(x.attributes.get("kex_capability") == "hybrid" for x in out.entities.values())


def test_active_policies_return_permutations(setup):
    cfg, e, r, o = setup
    te, tr, _, _ = multitool.build_tool_views(e, r, o)
    g = build_graph(te, tr, config=cfg, method="cigma")
    cont = active.contested_scores(g, te, tr)
    for policy in ("random", "low_support", "impact_uncertainty", "contested"):
        order = active.verification_order(g, policy, contested=cont)
        assert sorted(order) == list(range(len(g.edges)))


def test_poisoning_injects_k_false_relations(setup):
    cfg, e, r, o = setup
    from cigma.ext import poisoning
    pe, pr, po, inj = poisoning.poison(e, r, o, k=5, seed=1)
    assert len(inj) == 5 and all(po["relation_to_truth"][i] is None for i in inj)
    assert len({x.observation_id for x in pe}) == len(pe)


def test_conformal_pvalues_and_bh():
    from cigma.ext import conformal
    p = conformal.conformal_pvalues([0.99, 0.1], [0.2, 0.3, 0.4])
    assert p[0] == 0.25 and p[1] == 1.0
    assert conformal.benjamini_hochberg([0.001, 0.9], 0.1) == [True, False]
    fdp, power = conformal.fdp_and_power([True, True, False], [True, False, True])
    assert fdp == 0.5 and power == 0.5


def test_blended_order_endpoints(setup):
    cfg, e, r, o = setup
    g, rk, _ = _evaluate(e, r, config=cfg, oracle=o, method="cigma")
    assert [x.node_id for x in ordering.blended_order(rk, g, 0.0)] == [x.node_id for x in sorted(rk, key=lambda r: r.primary_rank)]
    assert ordering.certify_plan(ordering.blended_order(rk, g, 1.0), g)["valid"]


def test_ml_dsa_dsse_rejects_untrusted_and_revoked(setup):
    pytest.importorskip("dilithium_py")
    cfg, e, r, o = setup
    from cigma.ext import attestation
    k_ok, k_bad = attestation.generate_key("tls"), attestation.generate_key("mal")
    ring = attestation.Keyring()
    ring.add(k_ok)
    good = attestation.sign_observation(e[0], k_ok, kind="entity")
    bad = attestation.sign_observation(e[1], k_bad, kind="entity")
    assert attestation.verify_envelope(good, ring)[0]
    assert attestation.verify_envelope(bad, ring)[1] == "untrusted_key"
    tampered = dict(good)
    tampered["payloadType"] = attestation.PAYLOAD_TYPE_RELATION
    assert attestation.verify_envelope(tampered, ring)[1] == "bad_signature"
    ring.revoke(k_ok.keyid)
    assert attestation.verify_envelope(good, ring)[1] == "revoked_key"


def test_planning_greedy_and_solver_plans_are_certified():
    pytest.importorskip("ortools")
    from cigma.ext import planning
    pr = planning.random_enterprise(30, seed=3)
    g = planning.greedy_plan(pr)
    assert planning.check_plan(pr, g)["valid"]
    opt = planning.solve_optimal(pr, time_limit_s=5, workers=2)
    assert planning.check_plan(pr, opt["plan"])["valid"]
    assert opt["objective"] <= planning.objective(pr, g) + 1e-6
    bad = dict(opt["plan"])
    a, b = pr.effective_precedences()[0]
    bad[a], bad[b] = max(bad[a], bad[b]) + 1, min(bad[a], bad[b])
    assert not planning.check_plan(pr, bad)["valid"]


def test_compliance_findings_carry_evidence(setup):
    cfg, e, r, o = setup
    from cigma.ext import compliance
    g, rk, _ = _evaluate(e, r, config=cfg, oracle=o, method="cigma")
    f = compliance.run_compliance(g, rk)
    assert f and compliance.summary(f)["all_findings_carry_evidence"]


def test_benchmark_evaluator_reproduces_campaign(setup, tmp_path):
    cfg, e, r, o = setup
    import json
    from cigma.ext import benchmark_api
    g, rk, res = _evaluate(e, r, config=cfg, oracle=o, method="exact_direct")
    sub = tmp_path / "s.json"
    sub.write_text(json.dumps({"method": "exact_direct", "graph": g.to_dict(),
                               "order": [x.node_id for x in sorted(rk, key=lambda x: x.primary_rank)],
                               "rankings": [x.to_dict() for x in rk]}))
    out = benchmark_api.evaluate_submission(sub, DATA)
    assert abs(out["typed_edge_f1"] - res.metrics["typed_edge_f1"]) < 1e-9
    assert out["unsupported_edges"] == 0
    assert benchmark_api.to_cyclonedx(g)["specVersion"] == "1.6"


def test_version_log_consistency_and_forgery():
    from cigma.ext import commitment
    log = commitment.VersionLog.empty()
    roots = []
    for i in range(5):
        log.append(f"{i:064x}", {"version": i})
        roots.append(log.root())
    for m in range(1, 6):
        assert commitment.verify_consistency(m, 5, roots[m - 1], roots[4], log.prove(m))
    forged = commitment.VersionLog(entries=[b"forged"] + log.entries[1:])
    assert not commitment.verify_consistency(1, 5, roots[0], forged.root(), forged.prove(1))
