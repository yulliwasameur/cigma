from __future__ import annotations

from copy import deepcopy

from cigma.pipeline import build_graph
from cigma.scoring import rank_assets


def test_primary_ranking_is_deterministic(cigma_graph, config):
    left = [row.to_dict() for row in rank_assets(cigma_graph, config=config)]
    right = [row.to_dict() for row in rank_assets(cigma_graph, config=config)]
    assert left == right


def test_uniform_reliability_cannot_change_primary_urgency_order(observations, config):
    entities, relations = observations
    normal = rank_assets(build_graph(entities, relations, config=config, method="cigma"), config=config)
    uniform = rank_assets(build_graph(entities, relations, config=config, method="cigma_uniform_reliability"), config=config)
    assert [row.node_id for row in normal] == [row.node_id for row in uniform]


def test_agility_is_separate_from_primary_rank(cigma_graph, config):
    altered = deepcopy(cigma_graph)
    for node in altered.nodes.values():
        if "agility" in node.attributes:
            node.attributes["agility"] = 1.0 - float(node.attributes["agility"])
    normal = rank_assets(cigma_graph, config=config)
    changed = rank_assets(altered, config=config)
    assert [row.node_id for row in normal] == [row.node_id for row in changed]


def test_unknown_impact_factors_export_zero_one_bounds(observations, config):
    entities, relations = observations
    graph = build_graph(entities, relations, config=config, method="source_union")
    rows = rank_assets(graph, config=config)
    assert any(row.lower_impact["C"] == 0.0 and row.upper_impact["C"] == 1.0 for row in rows)


def test_high_impact_uncertain_item_enters_verify_queue(cigma_rankings):
    assert any(row.upper_tier >= 2 and row.verify for row in cigma_rankings)


def test_weighted_and_mean_factor_comparator_ranks_are_exported(cigma_rankings):
    assert sorted(row.weighted_rank for row in cigma_rankings) == list(range(1, len(cigma_rankings) + 1))
    assert sorted(row.mean_factor_order_rank for row in cigma_rankings) == list(range(1, len(cigma_rankings) + 1))
