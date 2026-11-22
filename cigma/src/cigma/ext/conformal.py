"""Guaranteed false-discovery rate on accepted edges (conformal selection).

Question answered: "of the edges CIGMA accepts, what fraction can be false?" We give
a finite-sample guarantee instead of a hand-set threshold.

Method (conformal p-values for outlier/novelty testing, Bates et al., Ann. Statist.
2023; FDR control by Benjamini-Hochberg as in conformal link prediction, Du et al.,
JCGS 2025):

- null hypothesis for an edge j: "edge j is false";
- calibration set: supports of edges *known to be false* (verified by an analyst, or
  from labelled scenarios); n0 of them;
- conformal p-value: p_j = (1 + #{i in calibration : s_i >= s_j}) / (n0 + 1);
- Benjamini-Hochberg at level alpha on {p_j} selects the edges to accept.

If calibration nulls and test nulls are exchangeable, the expected fraction of false
edges among accepted ones is at most alpha (conformal p-values are PRDS, so BH holds).
The exchangeability assumption is the honest limit: calibration must come from the
same kind of noise as deployment (e.g. the analyst's verification queue on that system).
"""

from __future__ import annotations

from bisect import bisect_left
from typing import Mapping, Sequence

from ..schema import GraphSnapshot


def edge_labels(
    graph: GraphSnapshot, node_truth_map: Mapping[str, str | None], truth_edges: set[tuple[str, str, str]]
) -> list[tuple[float, bool]]:
    out = []
    for e in graph.edges:
        s, o = node_truth_map.get(e.subject), node_truth_map.get(e.object)
        out.append((float(e.support), s is not None and o is not None and (s, e.predicate.value, o) in truth_edges))
    return out


def conformal_pvalues(test_scores: Sequence[float], null_calibration: Sequence[float]) -> list[float]:
    cal = sorted(null_calibration)
    n0 = len(cal)
    out = []
    for s in test_scores:
        greater_equal = n0 - bisect_left(cal, s)
        out.append((1 + greater_equal) / (n0 + 1))
    return out


def benjamini_hochberg(pvalues: Sequence[float], alpha: float) -> list[bool]:
    m = len(pvalues)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvalues[i])
    k_star = 0
    for rank, i in enumerate(order, start=1):
        if pvalues[i] <= alpha * rank / m:
            k_star = rank
    accepted = set(order[:k_star])
    return [i in accepted for i in range(m)]


def select(test_scores: Sequence[float], null_calibration: Sequence[float], alpha: float) -> list[bool]:
    return benjamini_hochberg(conformal_pvalues(test_scores, null_calibration), alpha)


def fdp_and_power(accepted: Sequence[bool], is_true: Sequence[bool]) -> tuple[float, float]:
    acc = sum(accepted)
    false_acc = sum(1 for a, t in zip(accepted, is_true) if a and not t)
    true_total = sum(is_true)
    true_acc = sum(1 for a, t in zip(accepted, is_true) if a and t)
    return (false_acc / acc if acc else 0.0), (true_acc / true_total if true_total else 0.0)


# ------------------------------------------------------------------ learned edge score

PREDICATES = ("HOSTS", "PRESENTS", "USES", "ISSUED-BY", "DEPENDS-ON", "DEPLOYS", "PROCESSES", "PROTECTS")


def edge_features(graph_fixed: GraphSnapshot, graph_learned: GraphSnapshot, relations) -> dict:
    """Oracle-free features per edge of ``graph_learned`` (keyed by triple).

    Uses supports under fixed and learned reliabilities, the number of independent
    tools/families behind the edge, whether it is derived, and the predicate. Tool
    *identity* is never a feature (a deployment does not know which tool lies).
    """

    from ..resolution import reliability_key

    rel = {r.observation_id: r for r in relations}
    fixed = {e.triple: e.support for e in graph_fixed.edges}
    out = {}
    for e in graph_learned.edges:
        keys = {reliability_key(rel[i]) for i in e.evidence_ids if i in rel}
        row = [fixed.get(e.triple, 0.0), float(e.support), float(len(keys)),
               float(len({k.split(":")[0] for k in keys})), float(e.derived)]
        row += [1.0 if e.predicate.value == p else 0.0 for p in PREDICATES]
        out[e.triple] = row
    return out
