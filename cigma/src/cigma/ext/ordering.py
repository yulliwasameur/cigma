"""Interoperability-aware migration order, MOVR, exposure, and plan certificates.

Why: ranking quality (NDCG) says "urgent things first"; operators also need
"nothing breaks on the way". When a server stops accepting classical key exchange
before its clients can speak the new protocol, the dependency breaks. Following the
dependency graph so that clients become hybrid-capable before their servers switch
removes most of these breaks (Sharma et al., 2026, report 88.6 % fewer failures on
simulated enterprises).

Definitions used here (paper, Eq. 3):
- a *migration unit* is a service or a device; every ranked asset belongs to the
  units in its service context;
- a unit is *migrated* as soon as one of its assets is migrated;
- for a dependency v -> u (v depends on u), I_t(e) = 0 when u is migrated and v is not;
- MOVR(pi) = (1 / (T |E_m|)) * sum_t sum_e 1[I_t(e) = 0];
- exposure AUC = normalized area under the remaining vulnerable priority curve.
"""

from __future__ import annotations

import hashlib
import heapq
import json
from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence

from ..schema import EntityType, GraphSnapshot, RelationType
from ..scoring import RankingEntry


# ---------------------------------------------------------------- predicted graph side

def _unit_dependencies(graph: GraphSnapshot) -> list[tuple[str, str]]:
    return sorted(
        (e.subject, e.object)
        for e in graph.edges
        if e.predicate == RelationType.DEPENDS_ON
    )


def interop_aware_order(entries: Sequence[RankingEntry], graph: GraphSnapshot) -> list[RankingEntry]:
    """Reorder assets so that clients are upgraded before the servers they depend on.

    Services are topologically sorted on DEPENDS-ON (client before server); ties and
    cycles are broken by the best primary rank of the service's assets. Each asset is
    placed at the latest position among its service contexts, then by primary rank.
    """

    best_rank: dict[str, int] = {}
    for entry in entries:
        for s in entry.service_contexts or []:
            best_rank[s] = min(best_rank.get(s, 10**9), entry.primary_rank)
        if entry.entity_type in (EntityType.SERVICE, EntityType.DEVICE):
            best_rank[entry.node_id] = min(best_rank.get(entry.node_id, 10**9), entry.primary_rank)
    deps = _unit_dependencies(graph)
    units = set(best_rank) | {u for edge in deps for u in edge}
    indeg: dict[str, int] = {u: 0 for u in units}
    succ: dict[str, list[str]] = defaultdict(list)
    for client, server in deps:  # client must come before server
        succ[client].append(server)
        indeg[server] += 1
    heap = [(best_rank.get(u, 10**9), u) for u in units if indeg[u] == 0]
    heapq.heapify(heap)
    position: dict[str, int] = {}
    remaining = dict(indeg)
    while len(position) < len(units):
        if not heap:  # cycle: release the best-ranked blocked unit
            blocked = sorted((best_rank.get(u, 10**9), u) for u in units if u not in position)
            heapq.heappush(heap, blocked[0])
            remaining[blocked[0][1]] = 0
        _, u = heapq.heappop(heap)
        if u in position:
            continue
        position[u] = len(position)
        for v in succ[u]:
            remaining[v] -= 1
            if remaining[v] == 0 and v not in position:
                heapq.heappush(heap, (best_rank.get(v, 10**9), v))

    def key(entry: RankingEntry) -> tuple[int, int, str]:
        ctx = list(entry.service_contexts or [])
        if entry.entity_type in (EntityType.SERVICE, EntityType.DEVICE):
            ctx.append(entry.node_id)
        pos = max((position[c] for c in ctx if c in position), default=0)
        return (pos, entry.primary_rank, entry.node_id)

    return sorted(entries, key=key)


def certify_plan(order: Sequence[RankingEntry], graph: GraphSnapshot) -> dict[str, Any]:
    """Machine-checkable certificate: every DEPENDS-ON constraint checked on the predicted graph."""

    first_step: dict[str, int] = {}
    for step, entry in enumerate(order):
        units = list(entry.service_contexts or [])
        if entry.entity_type in (EntityType.SERVICE, EntityType.DEVICE):
            units.append(entry.node_id)
        for u in units:
            first_step.setdefault(u, step)
    checked, violations = [], []
    for client, server in _unit_dependencies(graph):
        if client not in first_step or server not in first_step:
            continue
        ok = first_step[client] <= first_step[server]
        checked.append({"client": client, "server": server, "client_step": first_step[client],
                        "server_step": first_step[server], "satisfied": ok})
        if not ok:
            violations.append(checked[-1])
    body = {
        "graph_config_digest": graph.config_digest,
        "order": [e.node_id for e in order],
        "constraints": checked,
    }
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    return {"certificate_sha256": digest, "constraints_checked": len(checked),
            "violations": violations, "valid": not violations, **body}


# ---------------------------------------------------------------- evaluator side (oracle)

def truth_units(oracle: Mapping[str, Any]) -> dict[str, set[str]]:
    """truth node -> set of truth migration units (services / devices)."""

    nodes = {str(n["truth_id"]): str(n["entity_type"]) for n in oracle["nodes"]}
    out_edges: dict[tuple[str, str], list[str]] = defaultdict(list)
    in_edges: dict[tuple[str, str], list[str]] = defaultdict(list)
    for e in oracle["edges"]:
        out_edges[(str(e["subject"]), str(e["predicate"]))].append(str(e["object"]))
        in_edges[(str(e["object"]), str(e["predicate"]))].append(str(e["subject"]))
    units: dict[str, set[str]] = defaultdict(set)
    for nid, typ in nodes.items():
        if typ in ("service", "device"):
            units[nid].add(nid)
    for svc in [n for n, t in nodes.items() if t == "service"]:
        for ep in out_edges[(svc, "HOSTS")]:
            units[ep].add(svc)
            for cert in out_edges[(ep, "PRESENTS")]:
                units[cert].add(svc)
        for comp in out_edges[(svc, "USES")]:
            units[comp].add(svc)
        for pipe in in_edges[(svc, "DEPLOYS")]:
            units[pipe].add(svc)
    changed = True
    while changed:  # issuers inherit the units of the certificates they issued
        changed = False
        for e in oracle["edges"]:
            if str(e["predicate"]) == "ISSUED-BY":
                leaf, issuer = str(e["subject"]), str(e["object"])
                before = len(units[issuer])
                units[issuer] |= units[leaf]
                changed |= len(units[issuer]) != before
    return dict(units)


def truth_dependencies(oracle: Mapping[str, Any]) -> list[tuple[str, str]]:
    return sorted((str(e["subject"]), str(e["object"])) for e in oracle["edges"]
                  if str(e["predicate"]) == "DEPENDS-ON")


def migration_outcomes(
    predicted_order: Sequence[str],
    node_truth_map: Mapping[str, str | None],
    oracle: Mapping[str, Any],
) -> dict[str, float]:
    """MOVR, interoperability breaks and exposure AUC of a predicted order, on the oracle."""

    priorities = {str(k): int(v) for k, v in oracle["priorities"].items()}
    units = truth_units(oracle)
    deps = truth_dependencies(oracle)
    ranked_truth = [t for t, p in priorities.items() if t in units]
    seen: set[str] = set()
    order: list[str] = []
    for node in predicted_order:
        t = node_truth_map.get(node)
        if t is not None and t in units and t not in seen:
            seen.add(t)
            order.append(t)
    missing = sorted(set(ranked_truth) - seen)
    order += missing  # assets the method never found are migrated last
    migrated: set[str] = set()
    total = sum(priorities.get(t, 0) for t in order) or 1
    remaining = total
    movr_sum = breaks_sum = 0.0
    exposure_area = 0.0
    first_break_step = None
    for step, t in enumerate(order, start=1):
        migrated |= units.get(t, set())
        remaining -= priorities.get(t, 0)
        broken = sum(1 for client, server in deps if server in migrated and client not in migrated)
        if broken and first_break_step is None:
            first_break_step = step
        movr_sum += broken / max(1, len(deps))
        breaks_sum += broken
        exposure_area += remaining / total
    T = max(1, len(order))
    return {
        "movr": movr_sum / T,
        "interop_break_steps": breaks_sum,
        "exposure_auc": exposure_area / T,
        "missing_assets_appended": float(len(missing)),
        "first_break_step": float(first_break_step or 0),
    }


def blended_order(entries: Sequence[RankingEntry], graph: GraphSnapshot, lam: float) -> list[RankingEntry]:
    """Interpolate between urgency (lam = 0) and no-break order (lam = 1).

    Each asset gets a normalized position in both orders; the blended key is
    lam * interop_position + (1 - lam) * urgency_position. Sweeping lam traces the
    urgency/breakage trade-off that the operator chooses on (Pareto front).
    """

    urgency = sorted(entries, key=lambda r: r.primary_rank)
    interop = interop_aware_order(entries, graph)
    n = max(1, len(entries) - 1)
    pu = {r.node_id: i / n for i, r in enumerate(urgency)}
    pi = {r.node_id: i / n for i, r in enumerate(interop)}
    return sorted(entries, key=lambda r: (lam * pi[r.node_id] + (1 - lam) * pu[r.node_id], r.primary_rank))


def sharma2026_order(entries: Sequence[RankingEntry], graph: GraphSnapshot) -> list[RankingEntry]:
    """Reimplementation of Sharma et al. (ICAISET 2026) on our graph, for comparison.

    Their method: quantum risk = vulnerability x graph centrality; plan = reversed
    topological order over dependencies ("leaves first"), ties broken by risk.
    We use degree centrality on all predicted edges and the predicted DEPENDS-ON edges.
    """

    degree: dict[str, int] = defaultdict(int)
    for e in graph.edges:
        degree[e.subject] += 1
        degree[e.object] += 1
    max_deg = max(degree.values(), default=1)

    def risk(entry: RankingEntry) -> float:
        return float(entry.upper_impact.get("Q", 0.0)) * (1 + degree[entry.node_id] / max_deg)

    deps = _unit_dependencies(graph)
    depth: dict[str, int] = {}
    succ: dict[str, list[str]] = defaultdict(list)
    for client, server in deps:
        succ[client].append(server)

    def level(u: str, stack: frozenset[str] = frozenset()) -> int:
        if u in depth:
            return depth[u]
        if u in stack:
            return 0
        depth[u] = 1 + max((level(v, stack | {u}) for v in succ.get(u, [])), default=-1)
        return depth[u]

    def key(entry: RankingEntry):
        ctx = list(entry.service_contexts or []) + ([entry.node_id] if entry.entity_type in (EntityType.SERVICE, EntityType.DEVICE) else [])
        lv = max((level(c) for c in ctx), default=0)   # high level = far from the leaves (servers called by many)
        return (-lv, -risk(entry), entry.node_id)       # clients (high level in caller chains) first

    return sorted(entries, key=key)
