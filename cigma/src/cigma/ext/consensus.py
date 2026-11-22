"""k-of-n agreement across several language models, behind the deterministic validator.

Each model proposes candidate claims (same frozen prompt and schema). A claim is
kept only if (1) the fail-closed validator accepts it for the model that proposed it
and (2) at least ``k`` distinct models proposed the same triple. Neither step can
mutate the principal graph. The curve "false triples accepted vs useful triples
recovered" as k grows is the quantity reported in the paper.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence

from ..openai_adapter import validate_candidate_batch
from ..schema import GraphSnapshot, RelationObservation


def consensus(
    batches: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    graph: GraphSnapshot,
    relation_observations: Sequence[RelationObservation],
    k: int,
) -> dict[str, Any]:
    """``batches``: model name -> list of raw batches (one per call)."""

    proposers: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    validated: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    rejected_reasons: dict[str, int] = defaultdict(int)
    for model, calls in batches.items():
        for raw in calls:
            try:
                audit = validate_candidate_batch(raw, graph=graph, relation_observations=relation_observations)
            except ValueError:
                rejected_reasons["malformed_batch"] += 1
                continue
            assert audit.graph_mutated is False
            for claim in audit.accepted:
                t = (claim.subject, claim.predicate.value, claim.object)
                proposers[t].add(model)
                validated[t].add(model)
            for item in audit.rejected:
                rejected_reasons[item["reason"].split(":")[0]] += 1
                cand = item.get("candidate") or {}
                if {"subject", "predicate", "object"} <= set(cand):
                    proposers[(cand["subject"], str(cand["predicate"]), cand["object"])].add(model)
    kept = sorted(t for t, models in validated.items() if len(models) >= k)
    return {
        "k": k,
        "models": sorted(batches),
        "kept_triples": [list(t) for t in kept],
        "proposed_triples": len(proposers),
        "validated_triples": len(validated),
        "rejected_reasons": dict(sorted(rejected_reasons.items())),
        "graph_mutated": False,
    }


def score_against_truth(
    kept_triples: Sequence[Sequence[str]],
    node_truth_map: Mapping[str, str | None],
    truth_edges: set[tuple[str, str, str]],
) -> dict[str, float]:
    tp = fp = 0
    for s, p, o in kept_triples:
        ts, to = node_truth_map.get(s), node_truth_map.get(o)
        if ts is not None and to is not None and (ts, p, to) in truth_edges:
            tp += 1
        else:
            fp += 1
    return {"accepted_true": tp, "accepted_false": fp,
            "precision": tp / (tp + fp) if tp + fp else 1.0,
            "recall_of_truth_edges": tp / len(truth_edges) if truth_edges else 0.0}
