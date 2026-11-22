from __future__ import annotations

from cigma.openai_adapter import bounded_input, validate_candidate_batch
from cigma.schema import RelationType


def test_bounded_input_excludes_oracle_scores_and_structured_attributes(cigma_graph, observations):
    _, relations = observations
    payload = bounded_input(cigma_graph, relations)
    text = str(payload).lower()
    assert "oracle" not in text
    assert "ranking" not in text
    assert "support" not in text
    assert all(set(node) == {"node_id", "entity_type"} for node in payload["nodes"])


def test_exact_direct_candidate_is_accepted(cigma_graph, observations):
    _, relations = observations
    edge = next(item for item in cigma_graph.edges if not item.derived)
    batch = {"candidates": [{
        "claim_id": "c1", "subject": edge.subject, "predicate": edge.predicate.value,
        "object": edge.object, "method": "direct", "evidence_ids": edge.evidence_ids, "rule_id": None,
    }]}
    audit = validate_candidate_batch(batch, graph=cigma_graph, relation_observations=relations)
    assert len(audit.accepted) == 1 and not audit.rejected and audit.graph_mutated is False


def test_low_quality_quarantined_evidence_cannot_bypass_gate(cigma_graph, observations):
    _, relations = observations
    low = next(item for item in relations if item.quality < 0.4)
    batch = {"candidates": [{
        "claim_id": "c2", "subject": next(iter(cigma_graph.nodes)), "predicate": RelationType.DEPENDS_ON.value,
        "object": next(iter(cigma_graph.nodes)), "method": "direct", "evidence_ids": [low.observation_id], "rule_id": None,
    }]}
    audit = validate_candidate_batch(batch, graph=cigma_graph, relation_observations=relations)
    assert audit.rejected[0]["reason"] in {"evidence_absent_from_quality_gated_graph", "invalid_ontology_signature"}
