from __future__ import annotations

from dataclasses import replace

from cigma.pipeline import build_graph
from cigma.resolution import resolve_entities
from cigma.schema import EntityObservation


def test_source_union_preserves_one_node_per_retained_observation(observations, config):
    entities, _ = observations
    result = resolve_entities(entities, strategy="source_union", config=config, apply_quality_gate=False)
    assert len(result.nodes) == 46


def test_strong_fingerprint_merges_tls_and_pki_certificate(observations, config):
    entities, _ = observations
    result = resolve_entities(entities, strategy="strong", config=config)
    matching = [node for node in result.nodes.values() if "FPR-EDGE-RSA-001" in node.identifiers.get("certificate_fingerprint", [])]
    assert len(matching) == 1
    assert len(matching[0].observation_ids) == 3


def test_alias_enabled_resolution_recovers_23_truth_clusters(observations, config):
    entities, _ = observations
    result = resolve_entities(entities, strategy="cigma", config=config, use_aliases=True)
    assert len(result.nodes) == 23


def test_alias_disabled_resolution_leaves_service_duplicates(observations, config):
    entities, _ = observations
    result = resolve_entities(entities, strategy="cigma", config=config, use_aliases=False)
    assert len(result.nodes) == 27


def test_quality_gate_quarantines_two_distractor_entities(observations, config):
    entities, _ = observations
    result = resolve_entities(entities, strategy="cigma", config=config, use_aliases=True)
    assert len(result.quarantined_observation_ids) == 2


def test_node_support_is_bounded(observations, config):
    entities, _ = observations
    result = resolve_entities(entities, strategy="cigma", config=config, use_aliases=True)
    assert all(0.0 <= node.support <= 1.0 for node in result.nodes.values())


def test_numeric_attribute_fusion_uses_quality_reliability_weights(observations, config):
    entities, _ = observations
    patient = [item for item in entities if item.local_key == "cmdb_svc_patient"][0]
    altered = replace(patient, observation_id="manual-extra", quality=0.5, attributes={**patient.attributes, "criticality": 0.5})
    result = resolve_entities([*entities, altered], strategy="cigma", config=config, use_aliases=True)
    node = result.nodes[result.observation_to_node[patient.observation_id]]
    assert 0.5 < node.attributes["criticality"] < 0.98


def test_canonical_ids_are_invariant_to_input_order(observations, config):
    entities, _ = observations
    left = resolve_entities(entities, strategy="cigma", config=config, use_aliases=True)
    right = resolve_entities(list(reversed(entities)), strategy="cigma", config=config, use_aliases=True)
    assert left.observation_to_node == right.observation_to_node
