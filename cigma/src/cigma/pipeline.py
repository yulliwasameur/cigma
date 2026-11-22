"""Deterministic CIGMA graph construction."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence

from .config import config_digest
from .ontology import PATH_RULES, is_valid_signature
from .resolution import lookup_reliability, resolve_entities
from .schema import (
    Edge,
    EntityObservation,
    GraphSnapshot,
    RelationObservation,
    RelationType,
    SourceFamily,
    validate_observations,
)


@dataclass(frozen=True, slots=True)
class MethodSpec:
    name: str
    sources: frozenset[SourceFamily]
    resolution_strategy: str
    use_aliases: bool
    compose_paths: bool
    apply_quality_gate: bool
    uniform_reliability: bool = False


_ALL_SOURCES = frozenset(SourceFamily)

METHODS: dict[str, MethodSpec] = {
    "tls_inventory": MethodSpec(
        "tls_inventory", frozenset({SourceFamily.TLS}), "strong", False, False, True
    ),
    "cbom_inventory": MethodSpec(
        "cbom_inventory", frozenset({SourceFamily.CBOM}), "strong", False, False, True
    ),
    "source_union": MethodSpec(
        "source_union", _ALL_SOURCES, "source_union", False, False, False
    ),
    "exact_direct": MethodSpec(
        "exact_direct", _ALL_SOURCES, "strong", False, False, True
    ),
    "tfidf_cosine": MethodSpec(
        "tfidf_cosine", _ALL_SOURCES, "tfidf", False, False, True
    ),
    # equal-access comparators (reviewer request): same quality gate and same path rules as CIGMA
    "exact_direct_paths": MethodSpec("exact_direct_paths", _ALL_SOURCES, "strong", False, True, True),
    "tfidf_cosine_paths": MethodSpec("tfidf_cosine_paths", _ALL_SOURCES, "tfidf", False, True, True),
    "fellegi_sunter": MethodSpec("fellegi_sunter", _ALL_SOURCES, "fellegi_sunter", False, False, True),
    "fellegi_sunter_paths": MethodSpec("fellegi_sunter_paths", _ALL_SOURCES, "fellegi_sunter", False, True, True),
    "rules_any_id_paths": MethodSpec("rules_any_id_paths", _ALL_SOURCES, "rules_any_id", False, True, True),
    "cigma": MethodSpec("cigma", _ALL_SOURCES, "cigma", True, True, True),
    "cigma_guard": MethodSpec("cigma_guard", _ALL_SOURCES, "cigma_guard", True, True, True),
    "cigma_no_aliases": MethodSpec(
        "cigma_no_aliases", _ALL_SOURCES, "cigma", False, True, True
    ),
    "cigma_no_paths": MethodSpec(
        "cigma_no_paths", _ALL_SOURCES, "cigma", True, False, True
    ),
    "cigma_no_quality_gate": MethodSpec(
        "cigma_no_quality_gate", _ALL_SOURCES, "cigma", True, True, False
    ),
    "cigma_uniform_reliability": MethodSpec(
        "cigma_uniform_reliability", _ALL_SOURCES, "cigma", True, True, True, True
    ),
}


def _noisy_or(values: Sequence[float]) -> float:
    remaining = 1.0
    for value in values:
        remaining *= 1.0 - min(1.0, max(0.0, float(value)))
    return min(1.0, max(0.0, 1.0 - remaining))


def _relation_support(
    relation: RelationObservation,
    subject_support: float,
    object_support: float,
    config: Mapping[str, Any],
    *,
    uniform_reliability: bool,
) -> float:
    reliability = (
        1.0
        if uniform_reliability
        else lookup_reliability(relation, config["source_reliabilities"])
    )
    value = float(relation.quality) * reliability * math.sqrt(subject_support * object_support)
    return min(1.0, max(0.0, value))


def _merge_edge(edge_map: dict[tuple[str, RelationType, str], Edge], candidate: Edge) -> None:
    current = edge_map.get(candidate.triple)
    if current is None:
        edge_map[candidate.triple] = candidate
        return
    current.evidence_ids = sorted(set(current.evidence_ids) | set(candidate.evidence_ids))
    current.support = _noisy_or([current.support, candidate.support])
    current.derived = current.derived and candidate.derived
    current.rules = sorted(set(current.rules) | set(candidate.rules))


def _compose_paths(
    nodes: Mapping[str, Any],
    direct_edges: Sequence[Edge],
    path_penalty: float,
) -> list[Edge]:
    by_predicate: dict[RelationType, list[Edge]] = defaultdict(list)
    for edge in direct_edges:
        by_predicate[edge.predicate].append(edge)
    for edges in by_predicate.values():
        edges.sort(key=lambda edge: (edge.subject, edge.object, tuple(edge.evidence_ids)))

    derived: list[Edge] = []
    for rule in PATH_RULES:
        if len(rule.predicates) == 3:
            first, second, third = rule.predicates
            for e1 in by_predicate[first]:
                if nodes[e1.subject].entity_type != rule.node_types[0]:
                    continue
                if nodes[e1.object].entity_type != rule.node_types[1]:
                    continue
                for e2 in by_predicate[second]:
                    if e2.subject != e1.object:
                        continue
                    if nodes[e2.object].entity_type != rule.node_types[2]:
                        continue
                    for e3 in by_predicate[third]:
                        if e3.subject != e2.object:
                            continue
                        if nodes[e3.object].entity_type != rule.node_types[3]:
                            continue
                        evidence = sorted(
                            set(e1.evidence_ids) | set(e2.evidence_ids) | set(e3.evidence_ids)
                        )
                        derived.append(
                            Edge(
                                subject=e1.subject,
                                predicate=rule.output_predicate,
                                object=e3.object,
                                evidence_ids=evidence,
                                support=min(e1.support, e2.support, e3.support)
                                * (path_penalty ** 2),
                                derived=True,
                                rules=[rule.rule_id],
                            )
                        )
        elif len(rule.predicates) == 2:
            first, second = rule.predicates
            for e1 in by_predicate[first]:
                if nodes[e1.subject].entity_type != rule.node_types[0]:
                    continue
                if nodes[e1.object].entity_type != rule.node_types[1]:
                    continue
                for e2 in by_predicate[second]:
                    if e2.subject != e1.object:
                        continue
                    if nodes[e2.object].entity_type != rule.node_types[2]:
                        continue
                    evidence = sorted(set(e1.evidence_ids) | set(e2.evidence_ids))
                    derived.append(
                        Edge(
                            subject=e1.subject,
                            predicate=rule.output_predicate,
                            object=e2.object,
                            evidence_ids=evidence,
                            support=min(e1.support, e2.support) * path_penalty,
                            derived=True,
                            rules=[rule.rule_id],
                        )
                    )
        else:  # pragma: no cover - closed rules are fixed above
            raise AssertionError(f"unsupported path length: {rule.rule_id}")
    return derived


def build_graph(
    entity_observations: Sequence[EntityObservation],
    relation_observations: Sequence[RelationObservation],
    *,
    config: Mapping[str, Any],
    method: str | MethodSpec = "cigma",
) -> GraphSnapshot:
    """Build an evidence-bearing graph from public observations only."""

    validate_observations(entity_observations, relation_observations)
    spec = METHODS[method] if isinstance(method, str) else method
    resolution = resolve_entities(
        entity_observations,
        strategy=spec.resolution_strategy,
        config=config,
        allowed_sources=set(spec.sources),
        apply_quality_gate=spec.apply_quality_gate,
        use_aliases=spec.use_aliases,
        uniform_reliability=spec.uniform_reliability,
    )
    relation_by_id = {obs.observation_id: obs for obs in relation_observations}
    gate = float(config["quality_gates"]["relation"])
    grouped: dict[tuple[str, RelationType, str], list[RelationObservation]] = defaultdict(list)
    quarantined_relations: list[str] = []
    rejected_relations: list[str] = []

    for relation in sorted(relation_observations, key=lambda item: item.observation_id):
        if relation.source not in spec.sources:
            continue
        if spec.apply_quality_gate and relation.quality < gate:
            quarantined_relations.append(relation.observation_id)
            continue
        subject_node = resolution.observation_to_node.get(relation.subject_observation_id)
        object_node = resolution.observation_to_node.get(relation.object_observation_id)
        if subject_node is None or object_node is None:
            quarantined_relations.append(relation.observation_id)
            continue
        subject_type = resolution.nodes[subject_node].entity_type
        object_type = resolution.nodes[object_node].entity_type
        if not is_valid_signature(relation.predicate, subject_type, object_type):
            rejected_relations.append(relation.observation_id)
            continue
        grouped[(subject_node, relation.predicate, object_node)].append(relation)

    edge_map: dict[tuple[str, RelationType, str], Edge] = {}
    for triple, observations in sorted(
        grouped.items(), key=lambda item: (item[0][0], item[0][1].value, item[0][2])
    ):
        subject, predicate, object_ = triple
        supports = [
            _relation_support(
                observation,
                resolution.nodes[subject].support,
                resolution.nodes[object_].support,
                config,
                uniform_reliability=spec.uniform_reliability,
            )
            for observation in observations
        ]
        edge_map[triple] = Edge(
            subject=subject,
            predicate=predicate,
            object=object_,
            evidence_ids=sorted(observation.observation_id for observation in observations),
            support=_noisy_or(supports),
            derived=False,
            rules=[],
        )

    direct_edges = list(edge_map.values())
    if spec.compose_paths:
        for derived in _compose_paths(
            resolution.nodes,
            direct_edges,
            float(config["path_penalty"]),
        ):
            _merge_edge(edge_map, derived)

    valid_entity_ids = {obs.observation_id for obs in entity_observations}
    valid_relation_ids = set(relation_by_id)
    for node in resolution.nodes.values():
        if not node.observation_ids or not set(node.observation_ids) <= valid_entity_ids:
            raise AssertionError(f"node lacks valid provenance: {node.node_id}")
    for edge in edge_map.values():
        if not edge.evidence_ids or not set(edge.evidence_ids) <= valid_relation_ids:
            raise AssertionError(f"edge lacks valid provenance: {edge.triple}")

    return GraphSnapshot(
        method=spec.name,
        nodes=resolution.nodes,
        edges=sorted(
            edge_map.values(),
            key=lambda edge: (edge.subject, edge.predicate.value, edge.object),
        ),
        observation_to_node=resolution.observation_to_node,
        quarantined_entity_ids=resolution.quarantined_observation_ids,
        quarantined_relation_ids=sorted(quarantined_relations),
        rejected_relation_ids=sorted(rejected_relations),
        config_digest=config_digest(config),
    )
