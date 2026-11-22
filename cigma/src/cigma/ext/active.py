"""Budgeted human verification: which uncertain edge should an analyst check first?

CIGMA already produces a VERIFY queue. Here the analyst has a budget of b checks.
Each check reveals whether one predicted edge is true (the oracle plays the analyst
in the controlled study). Policies:

- ``random``: uniform order (seeded);
- ``low_support``: lowest evidence support first;
- ``impact_uncertainty``: highest expected effect on the migration order, i.e.
  ``support * (1 - support)`` (Bernoulli variance) times the priority reach of the
  edge's endpoints (how many ranked assets depend on them). This follows provenance-
  guided verification in probabilistic databases (ActivePDB, VLDB 2022) and
  entropy-reduction on uncertain graphs (Arafat et al., DSAA 2024).

A verified-false edge is removed; a verified-true edge gets support 1.0.
Reported: typed-edge precision after b checks, and how many false edges remain.
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any, Mapping, Sequence

from ..schema import GraphSnapshot


def _reach(graph: GraphSnapshot) -> dict[str, int]:
    deg: dict[str, int] = defaultdict(int)
    for e in graph.edges:
        deg[e.subject] += 1
        deg[e.object] += 1
    return deg


def _tool_of(locator: str) -> str | None:
    return locator[5:].split(";", 1)[0] if locator.startswith("tool=") else None


def contested_scores(
    graph: GraphSnapshot,
    entity_observations: Sequence[Any],
    relation_observations: Sequence[Any],
) -> list[int]:
    """Intra-family disagreement per edge (0 = uncontested).

    A node is contested when only part of the tools of a multi-tool family report it.
    An edge is contested when one of its endpoints is contested, or when a tool that
    reports both endpoints does not report the edge. No oracle is read.
    """

    ent = {o.observation_id: o for o in entity_observations}
    rel = {o.observation_id: o for o in relation_observations}
    family_tools: dict[str, set[str]] = defaultdict(set)
    for o in entity_observations:
        t = _tool_of(str(o.locator))
        if t:
            family_tools[o.source.value].add(t)
    node_tools: dict[str, dict[str, set[str]]] = {}
    for nid, node in graph.nodes.items():
        per: dict[str, set[str]] = defaultdict(set)
        for oid in node.observation_ids:
            o = ent.get(oid)
            t = _tool_of(str(o.locator)) if o else None
            if t:
                per[o.source.value].add(t)
        node_tools[nid] = per
    contested_node = {
        nid: any(0 < len(per.get(f, set())) < len(ts) for f, ts in family_tools.items() if len(ts) >= 2)
        for nid, per in node_tools.items()
    }
    scores = []
    for e in graph.edges:
        claim: dict[str, set[str]] = defaultdict(set)
        for oid in e.evidence_ids:
            r = rel.get(oid)
            t = _tool_of(str(r.locator)) if r else None
            if t:
                claim[r.source.value].add(t)
        silent = 0
        for f, ts in family_tools.items():
            both = node_tools[e.subject].get(f, set()) & node_tools[e.object].get(f, set())
            if claim.get(f) and both - claim[f]:
                silent += 1
        scores.append(2 * int(contested_node[e.subject] or contested_node[e.object]) + int(silent > 0))
    return scores


def verification_order(
    graph: GraphSnapshot,
    policy: str,
    seed: int = 20261121,
    contested: Sequence[int] | None = None,
) -> list[int]:
    idx = list(range(len(graph.edges)))
    if policy == "random":
        random.Random(seed).shuffle(idx)
        return idx
    if policy == "low_support":
        return sorted(idx, key=lambda i: (graph.edges[i].support, i))
    if policy == "impact_uncertainty":
        reach = _reach(graph)

        def score(i: int) -> float:
            e = graph.edges[i]
            s = float(e.support)
            return s * (1 - s) * (1 + reach[e.subject] + reach[e.object]) + (0.25 if e.derived else 0.0)

        return sorted(idx, key=lambda i: (-score(i), i))
    if policy == "contested":
        if contested is None:
            raise ValueError("contested policy needs contested scores")
        return sorted(idx, key=lambda i: (-contested[i], graph.edges[i].support, i))
    raise ValueError(policy)


def simulate(
    graph: GraphSnapshot,
    node_truth_map: Mapping[str, str | None],
    truth_edges: set[tuple[str, str, str]],
    *,
    budgets: Sequence[int],
    policies: Sequence[str] = ("random", "low_support", "impact_uncertainty"),
    seed: int = 20261121,
    contested: Sequence[int] | None = None,
) -> list[dict[str, Any]]:
    def is_true(i: int) -> bool:
        e = graph.edges[i]
        s, o = node_truth_map.get(e.subject), node_truth_map.get(e.object)
        return s is not None and o is not None and (s, e.predicate.value, o) in truth_edges

    truth_flags = [is_true(i) for i in range(len(graph.edges))]
    total_false = sum(1 for f in truth_flags if not f)
    rows = []
    for policy in policies:
        order = verification_order(graph, policy, seed, contested)
        for b in budgets:
            checked = set(order[:b])
            remaining_false = sum(1 for i, f in enumerate(truth_flags) if not f and i not in checked)
            kept = [i for i in range(len(graph.edges)) if not (i in checked and not truth_flags[i])]
            tp = sum(1 for i in kept if truth_flags[i])
            rows.append({
                "policy": policy, "budget": b,
                "false_edges_found": total_false - remaining_false,
                "false_edges_remaining": remaining_false,
                "precision_after": tp / len(kept) if kept else 1.0,
            })
    return rows
