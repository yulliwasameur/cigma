from __future__ import annotations

from dataclasses import replace

from cigma.pipeline import build_graph
from cigma.schema import RelationType, SourceFamily


def test_full_cigma_reconstructs_23_nodes_and_34_edges(cigma_graph):
    assert len(cigma_graph.nodes) == 23
    assert len(cigma_graph.edges) == 34


def test_source_union_keeps_46_nodes_and_34_observed_edges(observations, config):
    entities, relations = observations
    graph = build_graph(entities, relations, config=config, method="source_union")
    assert (len(graph.nodes), len(graph.edges)) == (46, 34)


def test_no_path_ablation_contains_only_29_direct_truth_edges(observations, config):
    entities, relations = observations
    graph = build_graph(entities, relations, config=config, method="cigma_no_paths")
    assert len(graph.edges) == 29
    assert all(not edge.derived for edge in graph.edges)


def test_no_quality_gate_retains_two_false_edges(observations, config):
    entities, relations = observations
    graph = build_graph(entities, relations, config=config, method="cigma_no_quality_gate")
    assert len(graph.nodes) == 25
    assert len(graph.edges) == 36


def test_every_node_and_edge_has_valid_public_provenance(cigma_graph, observations):
    entities, relations = observations
    entity_ids = {item.observation_id for item in entities}
    relation_ids = {item.observation_id for item in relations}
    assert all(node.observation_ids and set(node.observation_ids) <= entity_ids for node in cigma_graph.nodes.values())
    assert all(edge.evidence_ids and set(edge.evidence_ids) <= relation_ids for edge in cigma_graph.edges)


def test_derived_patient_algorithm_edge_unions_path_evidence(cigma_graph):
    service = next(node.node_id for node in cigma_graph.nodes.values() if "SVC-PATIENT-001" in node.identifiers.get("service_uid", []))
    algorithm = next(node.node_id for node in cigma_graph.nodes.values() if "RSA-2048" in node.identifiers.get("algorithm_id", []))
    edge = next(item for item in cigma_graph.edges if item.subject == service and item.object == algorithm and item.predicate == RelationType.USES)
    assert edge.derived
    assert len(edge.evidence_ids) >= 2
    assert set(edge.rules) == {"HOSTS_o_PRESENTS_o_USES", "USES_o_USES"}


def test_invalid_relation_signature_is_rejected(observations, config):
    entities, relations = observations
    valid = relations[0]
    invalid = replace(valid, observation_id="invalid-signature", predicate=RelationType.HOSTS)
    graph = build_graph(entities, [*relations, invalid], config=config, method="cigma")
    assert "invalid-signature" in graph.rejected_relation_ids


def test_tls_inventory_never_uses_non_tls_observations(observations, config):
    entities, relations = observations
    graph = build_graph(entities, relations, config=config, method="tls_inventory")
    entity_by_id = {item.observation_id: item for item in entities}
    assert all(entity_by_id[obs_id].source == SourceFamily.TLS for node in graph.nodes.values() for obs_id in node.observation_ids)
