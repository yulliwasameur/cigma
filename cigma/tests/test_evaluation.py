from __future__ import annotations

import pytest

from cigma.evaluation import evaluate_method
from cigma.pipeline import build_graph
from cigma.scoring import rank_assets


def _metrics(method, observations, config, oracle):
    entities, relations = observations
    graph = build_graph(entities, relations, config=config, method=method)
    result = evaluate_method(
        graph, rank_assets(graph, config=config), oracle,
        entity_observations=entities, relation_observations=relations,
        ndcg_cutoffs=[5, 10], ece_bins=5,
    )
    return result


def test_source_union_asset_f1_matches_count_audit(observations, config, oracle):
    assert _metrics("source_union", observations, config, oracle).metrics["asset_f1"] == pytest.approx(2 / 3)


def test_source_union_edge_f1_matches_29_tp_5fp_5fn(observations, config, oracle):
    result = _metrics("source_union", observations, config, oracle)
    assert result.edge_counts == {"tp": 29, "fp": 5, "fn": 5, "fp_duplicate": 3, "fp_unmappable": 1, "fp_oracle_absent": 1}
    assert result.metrics["edge_f1"] == pytest.approx(29 / 34)


def test_full_cigma_has_four_perfect_reconstruction_f1s(observations, config, oracle):
    metrics = _metrics("cigma", observations, config, oracle).metrics
    assert [metrics[key] for key in ("asset_f1", "pairwise_f1", "b3_f1", "edge_f1")] == [1.0, 1.0, 1.0, 1.0]


def test_no_path_edge_f1_is_29_of_34_recall(observations, config, oracle):
    assert _metrics("cigma_no_paths", observations, config, oracle).metrics["edge_f1"] == pytest.approx(58 / 63)


def test_no_gate_metrics_match_two_distractors_and_two_false_edges(observations, config, oracle):
    metrics = _metrics("cigma_no_quality_gate", observations, config, oracle).metrics
    assert metrics["asset_f1"] == pytest.approx(46 / 48)
    assert metrics["edge_f1"] == pytest.approx(68 / 70)
    assert metrics["edge_fp_rate"] == pytest.approx(2 / 36)


def test_edge_false_positive_classes_are_disjoint(observations, config, oracle):
    result = _metrics("source_union", observations, config, oracle)
    counts = result.edge_counts
    assert counts["fp"] == counts["fp_duplicate"] + counts["fp_unmappable"] + counts["fp_oracle_absent"]
