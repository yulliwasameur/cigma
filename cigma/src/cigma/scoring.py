"""Impact, evidence, tier, Pareto, and VERIFY scoring."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.stats import rankdata

from .schema import EntityType, GraphSnapshot, RelationType


FACTOR_ORDER = ("Q", "H", "C", "B", "X")


@dataclass(slots=True)
class RankingEntry:
    node_id: str
    entity_type: EntityType
    service_contexts: list[str]
    impact: dict[str, float | None]
    lower_impact: dict[str, float]
    upper_impact: dict[str, float]
    lower_tier: int
    upper_tier: int
    pareto_front: int
    evidence_confidence: float
    migration_feasibility: float | None
    verify: bool
    primary_rank: int = 0
    weighted_score: float = 0.0
    weighted_rank: int = 0
    mean_factor_rank: float = 0.0
    mean_factor_order_rank: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "entity_type": self.entity_type.value,
            "service_contexts": self.service_contexts,
            "impact": self.impact,
            "lower_impact": self.lower_impact,
            "upper_impact": self.upper_impact,
            "lower_tier": self.lower_tier,
            "upper_tier": self.upper_tier,
            "pareto_front": self.pareto_front,
            "evidence_confidence": self.evidence_confidence,
            "migration_feasibility": self.migration_feasibility,
            "verify": self.verify,
            "primary_rank": self.primary_rank,
            "weighted_score": self.weighted_score,
            "weighted_rank": self.weighted_rank,
            "mean_factor_rank": self.mean_factor_rank,
            "mean_factor_order_rank": self.mean_factor_order_rank,
        }


def _tier(vector: Mapping[str, float]) -> int:
    q, h, c, x, b = (vector[name] for name in ("Q", "H", "C", "X", "B"))
    if q >= 0.8 and (h >= 0.8 or c >= 0.9):
        return 3
    if q >= 0.8 and (h >= 0.5 or c >= 0.7 or x >= 0.5 or b >= 0.5):
        return 2
    if q >= 0.5 or (q >= 0.2 and c >= 0.8):
        return 1
    return 0


def _edge_adjacency(graph: GraphSnapshot):
    outgoing: dict[tuple[str, RelationType], list[Any]] = defaultdict(list)
    incoming: dict[tuple[str, RelationType], list[Any]] = defaultdict(list)
    for edge in graph.edges:
        outgoing[(edge.subject, edge.predicate)].append(edge)
        incoming[(edge.object, edge.predicate)].append(edge)
    return outgoing, incoming


def _service_contexts(
    graph: GraphSnapshot,
    node_id: str,
    outgoing: Mapping[tuple[str, RelationType], Sequence[Any]],
    incoming: Mapping[tuple[str, RelationType], Sequence[Any]],
) -> set[str]:
    node = graph.nodes[node_id]
    contexts: set[str] = set()
    if node.entity_type == EntityType.SERVICE:
        contexts.add(node_id)
    elif node.entity_type == EntityType.ENDPOINT:
        contexts.update(edge.subject for edge in incoming.get((node_id, RelationType.HOSTS), []))
    elif node.entity_type == EntityType.CERTIFICATE:
        endpoints = [edge.subject for edge in incoming.get((node_id, RelationType.PRESENTS), [])]
        for endpoint in endpoints:
            contexts.update(edge.subject for edge in incoming.get((endpoint, RelationType.HOSTS), []))
        # Root/intermediate certificates inherit contexts from issued leaf certificates.
        for issued_edge in incoming.get((node_id, RelationType.ISSUED_BY), []):
            leaf = issued_edge.subject
            leaf_endpoints = [
                edge.subject for edge in incoming.get((leaf, RelationType.PRESENTS), [])
            ]
            for endpoint in leaf_endpoints:
                contexts.update(
                    edge.subject for edge in incoming.get((endpoint, RelationType.HOSTS), [])
                )
    elif node.entity_type == EntityType.SOFTWARE_COMPONENT:
        contexts.update(edge.subject for edge in incoming.get((node_id, RelationType.USES), []))
    elif node.entity_type == EntityType.PIPELINE:
        contexts.update(edge.object for edge in outgoing.get((node_id, RelationType.DEPLOYS), []))
    elif node.entity_type == EntityType.DEVICE:
        contexts.update(edge.subject for edge in incoming.get((node_id, RelationType.DEPENDS_ON), []))
    return {context for context in contexts if graph.nodes[context].entity_type == EntityType.SERVICE}


def _service_dependents(
    graph: GraphSnapshot,
    incoming: Mapping[tuple[str, RelationType], Sequence[Any]],
    service_id: str,
) -> set[str]:
    seen: set[str] = set()
    queue: deque[str] = deque([service_id])
    while queue:
        current = queue.popleft()
        for edge in incoming.get((current, RelationType.DEPENDS_ON), []):
            dependent = edge.subject
            if graph.nodes[dependent].entity_type != EntityType.SERVICE:
                continue
            if dependent not in seen and dependent != service_id:
                seen.add(dependent)
                queue.append(dependent)
    return seen


def _max_known(values: Sequence[Any]) -> float | None:
    known = [float(value) for value in values if value is not None]
    return max(known) if known else None


def _min_known(values: Sequence[Any]) -> float | None:
    known = [float(value) for value in values if value is not None]
    return min(known) if known else None


def _algorithm_context(
    graph: GraphSnapshot,
    service_contexts: set[str],
    outgoing: Mapping[tuple[str, RelationType], Sequence[Any]],
    algorithm_policy: Mapping[str, float],
) -> tuple[float | None, list[float]]:
    q_values: list[float] = []
    supports: list[float] = []
    for service_id in sorted(service_contexts):
        for edge in outgoing.get((service_id, RelationType.USES), []):
            target = graph.nodes[edge.object]
            if target.entity_type != EntityType.ALGORITHM:
                continue
            ids = target.identifiers.get("algorithm_id", [])
            known = [float(algorithm_policy[value]) for value in ids if value in algorithm_policy]
            if known:
                q_values.append(max(known))
                supports.append(float(edge.support))
    return (max(q_values) if q_values else None), supports


def _pareto_fronts(entries: list[RankingEntry]) -> None:
    grouped: dict[tuple[int, int], list[RankingEntry]] = defaultdict(list)
    for entry in entries:
        grouped[(entry.upper_tier, entry.lower_tier)].append(entry)

    for group in grouped.values():
        remaining = set(entry.node_id for entry in group)
        by_id = {entry.node_id: entry for entry in group}
        front = 1
        while remaining:
            nondominated: list[str] = []
            for candidate_id in sorted(remaining):
                candidate = by_id[candidate_id]
                dominated = False
                candidate_vector = [candidate.upper_impact[key] for key in FACTOR_ORDER]
                for other_id in remaining:
                    if other_id == candidate_id:
                        continue
                    other = by_id[other_id]
                    other_vector = [other.upper_impact[key] for key in FACTOR_ORDER]
                    if all(a >= b for a, b in zip(other_vector, candidate_vector)) and any(
                        a > b for a, b in zip(other_vector, candidate_vector)
                    ):
                        dominated = True
                        break
                if not dominated:
                    nondominated.append(candidate_id)
            for node_id in nondominated:
                by_id[node_id].pareto_front = front
                remaining.remove(node_id)
            front += 1


def rank_assets(graph: GraphSnapshot, *, config: Mapping[str, Any]) -> list[RankingEntry]:
    ranked_types = {EntityType(value) for value in config["ranking"]["ranked_types"]}
    outgoing, incoming = _edge_adjacency(graph)
    service_ids = [
        node_id for node_id, node in graph.nodes.items() if node.entity_type == EntityType.SERVICE
    ]
    service_count = len(service_ids)
    algorithm_policy = {
        str(key): float(value) for key, value in config["algorithm_policy"]["values"].items()
    }
    horizon = float(config["policy_horizon_years"])
    entries: list[RankingEntry] = []

    for node_id in sorted(graph.nodes):
        node = graph.nodes[node_id]
        if node.entity_type not in ranked_types:
            continue
        contexts = _service_contexts(graph, node_id, outgoing, incoming)
        q_value, algorithm_supports = _algorithm_context(
            graph, contexts, outgoing, algorithm_policy
        )
        criticality = _max_known(
            [graph.nodes[service].attributes.get("criticality") for service in contexts]
        )
        exposure = _max_known(
            [graph.nodes[service].attributes.get("exposure") for service in contexts]
        )
        migration_time = _max_known(
            [graph.nodes[service].attributes.get("migration_time_years") for service in contexts]
        )
        data_lifetimes: list[Any] = [
            graph.nodes[service].attributes.get("data_lifetime_years") for service in contexts
        ]
        for service in contexts:
            for edge in outgoing.get((service, RelationType.PROCESSES), []):
                data_lifetimes.append(graph.nodes[edge.object].attributes.get("retention_years"))
        data_lifetime = _max_known(data_lifetimes)
        agility = _min_known(
            [graph.nodes[service].attributes.get("agility") for service in contexts]
        )
        blast = 0.0
        if contexts and service_count > 1:
            blast = max(
                len(_service_dependents(graph, incoming, service)) / max(1, service_count - 1)
                for service in contexts
            )

        h_known = q_value is not None and data_lifetime is not None and migration_time is not None
        h_value = None
        if q_value is not None:
            diagnostic_lifetime = 0.0 if data_lifetime is None else data_lifetime
            diagnostic_migration = 1.0 if migration_time is None else migration_time
            h_value = q_value * min(1.0, (diagnostic_lifetime + diagnostic_migration) / horizon)

        impact: dict[str, float | None] = {
            "Q": q_value,
            "H": h_value,
            "C": criticality,
            "X": exposure,
            "B": blast,
        }
        known_flags = {
            "Q": q_value is not None,
            "H": h_known,
            "C": criticality is not None,
            "X": exposure is not None,
            "B": True,
        }
        lower = {
            key: float(impact[key]) if known_flags[key] and impact[key] is not None else 0.0
            for key in impact
        }
        upper = {
            key: float(impact[key]) if known_flags[key] and impact[key] is not None else 1.0
            for key in impact
        }
        lower_tier = _tier(lower)
        upper_tier = _tier(upper)
        algorithm_confidence = min(algorithm_supports) if algorithm_supports else 0.5 * node.support
        evidence_confidence = min(float(node.support), float(algorithm_confidence))
        verify = upper_tier >= int(config["ranking"]["verify_upper_tier_minimum"]) and (
            lower_tier != upper_tier
            or evidence_confidence < float(config["verification_threshold"])
        )
        weights = config["ranking"]["weighted_baseline"]
        weighted_score = sum(float(weights[key]) * upper[key] for key in weights)
        entries.append(
            RankingEntry(
                node_id=node_id,
                entity_type=node.entity_type,
                service_contexts=sorted(contexts),
                impact=impact,
                lower_impact=lower,
                upper_impact=upper,
                lower_tier=lower_tier,
                upper_tier=upper_tier,
                pareto_front=0,
                evidence_confidence=evidence_confidence,
                migration_feasibility=agility,
                verify=verify,
                weighted_score=weighted_score,
            )
        )

    _pareto_fronts(entries)
    entries.sort(
        key=lambda entry: (
            -entry.upper_tier,
            -entry.lower_tier,
            entry.pareto_front,
            -entry.upper_impact["Q"],
            -entry.upper_impact["H"],
            -entry.upper_impact["C"],
            -entry.upper_impact["B"],
            -entry.upper_impact["X"],
            entry.node_id,
        )
    )
    for index, entry in enumerate(entries, start=1):
        entry.primary_rank = index

    weighted = sorted(entries, key=lambda entry: (-entry.weighted_score, entry.node_id))
    for index, entry in enumerate(weighted, start=1):
        entry.weighted_rank = index

    if entries:
        factor_ranks = []
        for factor in FACTOR_ORDER:
            values = np.array([-entry.upper_impact[factor] for entry in entries], dtype=float)
            factor_ranks.append(rankdata(values, method="average"))
        means = np.mean(np.vstack(factor_ranks), axis=0)
        for entry, mean_rank in zip(entries, means):
            entry.mean_factor_rank = float(mean_rank)
        mean_order = sorted(entries, key=lambda entry: (entry.mean_factor_rank, entry.node_id))
        for index, entry in enumerate(mean_order, start=1):
            entry.mean_factor_order_rank = index
    return entries
