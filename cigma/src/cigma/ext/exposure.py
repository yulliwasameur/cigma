"""Two quantum-risk clocks: confidentiality (HNDL) and authenticity (TNFL).

- Harvest-now-decrypt-later (HNDL): traffic recorded today is decrypted once a
  cryptographically relevant quantum computer exists. Mosca's rule: loss if
  data lifetime x + migration time y > time to quantum arrival z.
- Trust-now-forge-later (TNFL): a classical signing key that is still trusted when
  z arrives can be used to forge. Loss if remaining trust lifetime + migration time
  > z, and the damage grows with the number of certificates and services that the
  key anchors (Grover et al., PKIA 2026; Campbell, Computers 2026: "migrate anchors first").

The arrival time z is uncertain. We draw the median arrival year of a lognormal
distribution from a range (expert surveys disagree), compute both expected losses
per asset in each draw, and report how stable the resulting order is. All
parameters live in ``DEFAULTS`` and are reported with the results; they are
assumptions, not measurements.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.stats import kendalltau, norm

from ..schema import EntityType, GraphSnapshot, RelationType
from ..scoring import RankingEntry

DEFAULTS = {
    "median_years_range": [8.0, 25.0],   # median time to quantum arrival, drawn uniformly
    "lognormal_sigma": 0.5,
    "draws": 400,
    "seed": 20261121,
    "leaf_trust_years_default": 1.0,     # leaf certificate without known rotation
    "anchor_trust_years_default": 20.0,  # issuing / root certificate
    "migration_years_default": 1.0,
}


def _p_arrival_before(t: float, median: float, sigma: float) -> float:
    if t <= 0:
        return 0.0
    return float(norm.cdf((math.log(t) - math.log(median)) / sigma))


@dataclass(slots=True)
class ExposureRow:
    node_id: str
    entity_type: str
    q: float
    hndl_horizon: float
    tnfl_horizon: float
    anchor_reach: int
    p_hndl_mean: float
    p_tnfl_mean: float
    risk_mean: float
    rank_mean: float
    rank_p05: float
    rank_p95: float
    dominant_clock: str


def _issued_closure(graph: GraphSnapshot) -> dict[str, set[str]]:
    issued: dict[str, set[str]] = defaultdict(set)
    for e in graph.edges:
        if e.predicate == RelationType.ISSUED_BY:
            issued[e.object].add(e.subject)
    closure: dict[str, set[str]] = {}

    def visit(n: str, stack: frozenset[str]) -> set[str]:
        if n in closure:
            return closure[n]
        out: set[str] = set()
        for child in issued.get(n, ()):
            if child in stack:
                continue
            out.add(child)
            out |= visit(child, stack | {child})
        closure[n] = out
        return out

    for n in list(issued):
        visit(n, frozenset({n}))
    return closure


def dual_clock_exposure(
    entries: Sequence[RankingEntry],
    graph: GraphSnapshot,
    params: Mapping[str, Any] | None = None,
) -> tuple[list[ExposureRow], dict[str, Any]]:
    p = {**DEFAULTS, **(params or {})}
    closure = _issued_closure(graph)
    rows_static = []
    for entry in entries:
        q = float(entry.upper_impact.get("Q", 0.0))
        services = [graph.nodes[s] for s in entry.service_contexts if s in graph.nodes]
        lifetimes = [s.attributes.get("data_lifetime_years") for s in services]
        for s in entry.service_contexts:
            for e in graph.edges:
                if e.subject == s and e.predicate == RelationType.PROCESSES:
                    lifetimes.append(graph.nodes[e.object].attributes.get("retention_years"))
        known_life = [float(v) for v in lifetimes if isinstance(v, (int, float))]
        migr = [s.attributes.get("migration_time_years") for s in services]
        known_migr = [float(v) for v in migr if isinstance(v, (int, float))]
        y = max(known_migr) if known_migr else float(p["migration_years_default"])
        x = max(known_life) if known_life else 0.0
        hndl_h = x + y
        reach = 0
        tnfl_h = 0.0
        if entry.entity_type == EntityType.CERTIFICATE:
            reach = len(closure.get(entry.node_id, set()))
            rot = graph.nodes[entry.node_id].attributes.get("rotation_days")
            if reach > 0:
                trust = float(p["anchor_trust_years_default"])
            elif isinstance(rot, (int, float)):
                trust = float(rot) / 365.0
            else:
                trust = float(p["leaf_trust_years_default"])
            tnfl_h = trust + y
        c = float(entry.upper_impact.get("C", 0.0))
        rows_static.append((entry, q, hndl_h, tnfl_h, reach, c))

    rng = np.random.default_rng(int(p["seed"]))
    lo, hi = p["median_years_range"]
    medians = rng.uniform(float(lo), float(hi), int(p["draws"]))
    sigma = float(p["lognormal_sigma"])
    n = len(rows_static)
    risks = np.zeros((len(medians), n))
    ph = np.zeros((len(medians), n))
    pt = np.zeros((len(medians), n))
    for d, med in enumerate(medians):
        for i, (entry, q, hh, th, reach, c) in enumerate(rows_static):
            a = q * _p_arrival_before(hh, med, sigma)
            b = q * _p_arrival_before(th, med, sigma) if th > 0 else 0.0
            ph[d, i], pt[d, i] = a, b
            # confidentiality weighted by criticality; authenticity by anchored reach
            risks[d, i] = max(a * (0.5 + 0.5 * c), b * min(1.0, (1 + reach) / 4.0))
    ranks = np.zeros_like(risks)
    for d in range(len(medians)):
        order = np.lexsort((np.arange(n), -risks[d]))
        ranks[d, order] = np.arange(1, n + 1)
    rows = []
    for i, (entry, q, hh, th, reach, c) in enumerate(rows_static):
        rows.append(ExposureRow(
            node_id=entry.node_id, entity_type=entry.entity_type.value, q=q,
            hndl_horizon=hh, tnfl_horizon=th, anchor_reach=reach,
            p_hndl_mean=float(ph[:, i].mean()), p_tnfl_mean=float(pt[:, i].mean()),
            risk_mean=float(risks[:, i].mean()), rank_mean=float(ranks[:, i].mean()),
            rank_p05=float(np.percentile(ranks[:, i], 5)), rank_p95=float(np.percentile(ranks[:, i], 95)),
            dominant_clock="TNFL" if pt[:, i].mean() * (1 + reach) > ph[:, i].mean() else "HNDL",
        ))
    rows.sort(key=lambda r: (r.rank_mean, r.node_id))
    # stability: how often does the order flip between draws?
    taus = []
    ref = ranks[0]
    for d in range(1, len(medians)):
        tau = kendalltau(ref, ranks[d]).statistic
        taus.append(0.0 if tau != tau else float(tau))
    primary = {e.node_id: e.primary_rank for e in entries}
    mean_rank_order = [r.node_id for r in rows]
    tau_vs_primary = kendalltau(
        [primary[nid] for nid in mean_rank_order], list(range(1, n + 1))
    ).statistic if n >= 2 else 1.0
    summary = {
        "params": p,
        "assets": n,
        "tnfl_dominant_assets": sum(1 for r in rows if r.dominant_clock == "TNFL"),
        "rank_stability_kendall_tau_mean": float(np.mean(taus)) if taus else 1.0,
        "kendall_tau_dual_clock_vs_primary": float(0.0 if tau_vs_primary != tau_vs_primary else tau_vs_primary),
    }
    return rows, summary
