"""Source reliabilities learned without ground truth.

Idea: a source is reliable when *other* sources tend to confirm what it says.
We alternate two steps (an EM-style truth-discovery loop):

1. the belief that an item is true is a noisy-OR over the sources that claim it;
2. the reliability of a source is the average belief of its items, computed
   *leave-one-out* (its own vote is removed) and smoothed by a Beta prior.

Items are canonical entities (after strong-key resolution, which never reads the
oracle) and typed triples. Two sources whose claim sets overlap far more than
chance are treated as one witness when they confirm each other (copy detection),
so that two generators built on the same library cannot vote twice.
"""

from __future__ import annotations

import copy
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..pipeline import build_graph
from ..resolution import reliability_key
from ..schema import EntityObservation, RelationObservation


@dataclass(slots=True)
class ReliabilityResult:
    reliabilities: dict[str, float]
    iterations: int
    converged: bool
    dependent_pairs: list[tuple[str, str, float]] = field(default_factory=list)
    item_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reliabilities": self.reliabilities,
            "iterations": self.iterations,
            "converged": self.converged,
            "dependent_pairs": [list(item) for item in self.dependent_pairs],
            "item_counts": self.item_counts,
        }


def _claims(
    entities: Sequence[EntityObservation],
    relations: Sequence[RelationObservation],
    config: Mapping[str, Any],
) -> dict[str, dict[str, float]]:
    """item -> {source_key: max quality}.

    Items come from CIGMA's own identity resolution run with *uniform* reliabilities
    (strong keys, then conflict-free aliases), so the learned values cannot feed back
    into the clustering that defines them. No oracle is read.
    """

    graph = build_graph(entities, relations, config=config, method="cigma_uniform_reliability")
    by_id = {obs.observation_id: obs for obs in entities}
    claims: dict[str, dict[str, float]] = defaultdict(dict)
    for node_id, node in graph.nodes.items():
        for obs_id in node.observation_ids:
            obs = by_id[obs_id]
            key = reliability_key(obs)
            claims[f"N:{node_id}"][key] = max(claims[f"N:{node_id}"].get(key, 0.0), float(obs.quality))
    for rel in relations:
        s = graph.observation_to_node.get(rel.subject_observation_id)
        o = graph.observation_to_node.get(rel.object_observation_id)
        if s is None or o is None:
            continue
        item = f"E:{s}|{rel.predicate.value}|{o}"
        key = reliability_key(rel)
        claims[item][key] = max(claims[item].get(key, 0.0), float(rel.quality))
    return claims


def _dependent_pairs(
    claims: Mapping[str, Mapping[str, float]], threshold: float, min_items: int
) -> list[tuple[str, str, float]]:
    """Copy detection: two sources are dependent when (i) their claim sets overlap
    almost fully (Jaccard >= threshold) and (ii) they share items that *no other
    source* reports. Sharing rare claims is the classic evidence of copying
    (Dong et al.; DepenBaye, IEEE TCSS 2026); a mere subset relation is not."""

    items_by_source: dict[str, set[str]] = defaultdict(set)
    for item, sources in claims.items():
        for source in sources:
            items_by_source[source].add(item)
    keys = sorted(items_by_source)
    pairs = []
    for i, a in enumerate(keys):
        for b in keys[i + 1 :]:
            A, B = items_by_source[a], items_by_source[b]
            if min(len(A), len(B)) < min_items:
                continue
            jaccard = len(A & B) / len(A | B)
            exclusive = sum(1 for item in A & B if set(claims[item]) == {a, b})
            if jaccard >= threshold and exclusive >= 1:
                pairs.append((a, b, round(jaccard, 4)))
    return pairs


def learn_reliabilities(
    entities: Sequence[EntityObservation],
    relations: Sequence[RelationObservation],
    *,
    config: Mapping[str, Any],
    prior: float = 0.8,
    unconfirmed_belief: float = 0.5,
    prior_strength: float = 2.0,
    max_iterations: int = 100,
    tolerance: float = 1e-6,
    copy_threshold: float = 0.9,
    copy_min_items: int = 4,
    floor: float = 0.05,
) -> ReliabilityResult:
    claims = _claims(entities, relations, config)
    dependent = _dependent_pairs(claims, copy_threshold, copy_min_items)
    partners: dict[str, set[str]] = defaultdict(set)
    for a, b, _ in dependent:
        partners[a].add(b)
        partners[b].add(a)
    sources = sorted({s for item in claims.values() for s in item})
    r = {s: prior for s in sources}
    converged = False
    iteration = 0
    for iteration in range(1, max_iterations + 1):
        sums: dict[str, float] = defaultdict(float)
        counts: dict[str, int] = defaultdict(int)
        for item, supporters in claims.items():
            for s in supporters:
                excluded = {s} | partners[s]
                remaining = 1.0
                for other, quality in supporters.items():
                    if other in excluded:
                        continue
                    remaining *= 1.0 - quality * r[other]
                loo_belief = 1.0 - remaining if len(supporters.keys() - excluded) else unconfirmed_belief
                sums[s] += loo_belief
                counts[s] += 1
        new_r = {
            s: max(floor, (sums[s] + prior_strength * prior) / (counts[s] + prior_strength))
            for s in sources
        }
        delta = max(abs(new_r[s] - r[s]) for s in sources) if sources else 0.0
        r = new_r
        if delta < tolerance:
            converged = True
            break
    counts_out: dict[str, int] = defaultdict(int)
    for supporters in claims.values():
        for s in supporters:
            counts_out[s] += 1
    return ReliabilityResult(
        reliabilities={s: round(v, 6) for s, v in sorted(r.items())},
        iterations=iteration,
        converged=converged,
        dependent_pairs=dependent,
        item_counts=dict(sorted(counts_out.items())),
    )


def config_with_learned_reliabilities(
    config: Mapping[str, Any], result: ReliabilityResult
) -> dict[str, Any]:
    updated = copy.deepcopy(dict(config))
    merged = dict(updated["source_reliabilities"])
    merged.update(result.reliabilities)
    updated["source_reliabilities"] = merged
    return updated


def dependence_aware_support(
    graph: Any,
    relations: Sequence[RelationObservation],
    *,
    config: Mapping[str, Any],
    result: ReliabilityResult,
) -> Any:
    """Recompute edge support so that dependent sources count as one witness.

    Within a group of mutually dependent sources the strongest observation is kept
    (max); independent groups are then combined by noisy-OR as in the core pipeline.
    Returns a copy of the graph; the core graph is never modified.
    """

    from ..pipeline import _relation_support  # same per-observation formula as the core

    groups: dict[str, str] = {}
    for a, b, _ in result.dependent_pairs:
        ga, gb = groups.get(a, a), groups.get(b, b)
        root = min(ga, gb)
        for k, v in list(groups.items()):
            if v in (ga, gb):
                groups[k] = root
        groups[a] = groups[b] = root
    rel_by_id = {r.observation_id: r for r in relations}
    g = copy.deepcopy(graph)
    for edge in g.edges:
        if edge.derived:
            continue
        best: dict[str, float] = {}
        for oid in edge.evidence_ids:
            r = rel_by_id[oid]
            key = reliability_key(r)
            grp = groups.get(key, key)
            s = _relation_support(r, g.nodes[edge.subject].support, g.nodes[edge.object].support,
                                  config, uniform_reliability=False)
            best[grp] = max(best.get(grp, 0.0), s)
        remaining = 1.0
        for v in best.values():
            remaining *= 1.0 - v
        edge.support = min(1.0, max(0.0, 1.0 - remaining))
    return g
