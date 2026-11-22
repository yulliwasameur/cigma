"""Evaluator-only graph, entity-resolution, ranking, and calibration metrics."""

from __future__ import annotations

import itertools
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from scipy.stats import kendalltau, spearmanr

from .io import read_json, read_jsonl
from .schema import EntityObservation, GraphSnapshot, RelationObservation
from .scoring import RankingEntry


@dataclass(slots=True)
class EvaluationResult:
    method: str
    metrics: dict[str, float | int]
    asset_counts: dict[str, int]
    edge_counts: dict[str, int]
    node_truth_map: dict[str, str | None]
    ranking_rows: list[dict[str, Any]]
    edge_rows: list[dict[str, Any]]
    calibration_rows: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_oracle(oracle_dir: str | Path) -> dict[str, Any]:
    root = Path(oracle_dir)
    return {
        "nodes": list(read_jsonl(root / "nodes.jsonl")),
        "edges": list(read_jsonl(root / "edges.jsonl")),
        "observation_to_truth": read_json(root / "observation_to_truth.json"),
        "relation_to_truth": read_json(root / "relation_to_truth.json"),
        "priorities": read_json(root / "priorities.json"),
        "critical_targets": read_json(root / "critical_targets.json"),
    }


def evaluate_method(
    graph: GraphSnapshot,
    rankings: Sequence[RankingEntry],
    oracle: Mapping[str, Any],
    *,
    entity_observations: Iterable[EntityObservation] | None = None,
    relation_observations: Iterable[RelationObservation] | None = None,
    ndcg_cutoffs: Sequence[int] = (5, 10),
    ece_bins: int = 5,
) -> EvaluationResult:
    observation_to_truth: dict[str, str | None] = dict(oracle["observation_to_truth"])
    truth_nodes = {str(node["truth_id"]): dict(node) for node in oracle["nodes"]}
    truth_edge_by_triple = {
        (str(edge["subject"]), str(edge["predicate"]), str(edge["object"])): str(edge["edge_id"])
        for edge in oracle["edges"]
    }

    node_truth_map, asset_counts = _asset_counts(graph, observation_to_truth, truth_nodes)
    asset_precision, asset_recall, asset_f1 = _prf(
        asset_counts["tp"], asset_counts["fp"], asset_counts["fn"]
    )
    pair_precision, pair_recall, pair_f1 = _pairwise_er(graph, observation_to_truth)
    b3_precision, b3_recall, b3_f1 = _b3(graph, observation_to_truth)
    edge_counts, edge_rows, discovered_truth_edges = _edge_counts(
        graph, node_truth_map, truth_edge_by_triple
    )
    edge_precision, edge_recall, edge_f1 = _prf(
        edge_counts["tp"], edge_counts["fp"], edge_counts["fn"]
    )
    edge_fp_rate = edge_counts["fp"] / max(1, edge_counts["tp"] + edge_counts["fp"])

    valid_entity_ids = {
        observation.observation_id for observation in (entity_observations or [])
    }
    valid_relation_ids = {
        observation.observation_id for observation in (relation_observations or [])
    }
    unsupported = 0
    assertion_count = len(graph.nodes) + len(graph.edges)
    if entity_observations is not None:
        unsupported += sum(
            not node.observation_ids or bool(set(node.observation_ids) - valid_entity_ids)
            for node in graph.nodes.values()
        )
    if relation_observations is not None:
        unsupported += sum(
            not edge.evidence_ids or bool(set(edge.evidence_ids) - valid_relation_ids)
            for edge in graph.edges
        )
    evidence_unsupported_rate = unsupported / max(1, assertion_count)

    discovered_truth_nodes = {
        truth_id for truth_id in node_truth_map.values() if truth_id is not None
    }
    critical_targets = {str(value) for value in oracle.get("critical_targets", [])}
    critical_misses = len(critical_targets - discovered_truth_nodes)

    ranking_metrics, ranking_rows = _ranking_metrics(
        rankings,
        node_truth_map,
        priorities={str(k): int(v) for k, v in dict(oracle["priorities"]).items()},
        truth_nodes=truth_nodes,
        cutoffs=tuple(int(value) for value in ndcg_cutoffs),
    )
    calibration_rows = [
        {
            "kind": "edge",
            "assertion": row["predicted_edge_key"],
            "score": float(row["support"]),
            "label": int(row["classification"] == "true_positive"),
        }
        for row in edge_rows
    ]
    brier, ece = calibration_metrics(calibration_rows, bins=ece_bins)

    metrics: dict[str, float | int] = {
        "asset_precision": asset_precision,
        "asset_recall": asset_recall,
        "asset_f1": asset_f1,
        "pairwise_precision": pair_precision,
        "pairwise_recall": pair_recall,
        "pairwise_f1": pair_f1,
        "b3_precision": b3_precision,
        "b3_recall": b3_recall,
        "b3_f1": b3_f1,
        "edge_precision": edge_precision,
        "edge_recall": edge_recall,
        "edge_f1": edge_f1,
        "typed_edge_precision": edge_precision,
        "typed_edge_recall": edge_recall,
        "typed_edge_f1": edge_f1,
        "edge_fp_rate": edge_fp_rate,
        "evidence_unsupported_rate": evidence_unsupported_rate,
        "critical_misses": critical_misses,
        "verify_count": sum(bool(row.verify) for row in rankings),
        "edge_brier": brier,
        "edge_ece": ece,
        "predicted_nodes": len(graph.nodes),
        "predicted_edges": len(graph.edges),
        "discovered_truth_nodes": len(discovered_truth_nodes),
        "discovered_truth_edges": len(discovered_truth_edges),
    }
    metrics.update(ranking_metrics)
    return EvaluationResult(
        method=graph.method,
        metrics=metrics,
        asset_counts=asset_counts,
        edge_counts=edge_counts,
        node_truth_map=node_truth_map,
        ranking_rows=ranking_rows,
        edge_rows=edge_rows,
        calibration_rows=calibration_rows,
    )


def _asset_counts(
    graph: GraphSnapshot,
    observation_to_truth: Mapping[str, str | None],
    truth_nodes: Mapping[str, Any],
) -> tuple[dict[str, str | None], dict[str, int]]:
    node_truth_map: dict[str, str | None] = {}
    discovered: set[str] = set()
    tp = fp_unmapped = fp_duplicate = fp_mixed = 0
    for node_id in sorted(graph.nodes):
        truths = {
            observation_to_truth.get(observation_id)
            for observation_id in graph.nodes[node_id].observation_ids
        }
        truths.discard(None)
        if len(truths) == 1:
            truth_id = str(next(iter(truths)))
            node_truth_map[node_id] = truth_id
            if truth_id in discovered:
                fp_duplicate += 1
            else:
                discovered.add(truth_id)
                tp += 1
        elif len(truths) == 0:
            node_truth_map[node_id] = None
            fp_unmapped += 1
        else:
            node_truth_map[node_id] = None
            fp_mixed += 1
    fn = len(set(truth_nodes) - discovered)
    return node_truth_map, {
        "tp": tp,
        "fp": fp_unmapped + fp_duplicate + fp_mixed,
        "fn": fn,
        "fp_unmapped": fp_unmapped,
        "fp_duplicate": fp_duplicate,
        "fp_mixed": fp_mixed,
    }


def _pairwise_er(
    graph: GraphSnapshot,
    observation_to_truth: Mapping[str, str | None],
) -> tuple[float, float, float]:
    retained_true_ids = sorted(
        observation_id
        for observation_id, truth_id in observation_to_truth.items()
        if truth_id is not None and observation_id in graph.observation_to_node
    )
    predicted_clusters: dict[str, list[str]] = defaultdict(list)
    truth_clusters: dict[str, list[str]] = defaultdict(list)
    for observation_id in retained_true_ids:
        predicted_clusters[graph.observation_to_node[observation_id]].append(observation_id)
        truth_clusters[str(observation_to_truth[observation_id])].append(observation_id)
    predicted_pairs = {
        pair
        for members in predicted_clusters.values()
        for pair in itertools.combinations(sorted(members), 2)
    }
    truth_pairs = {
        pair
        for members in truth_clusters.values()
        for pair in itertools.combinations(sorted(members), 2)
    }
    return _prf(
        len(predicted_pairs & truth_pairs),
        len(predicted_pairs - truth_pairs),
        len(truth_pairs - predicted_pairs),
    )


def _b3(
    graph: GraphSnapshot,
    observation_to_truth: Mapping[str, str | None],
) -> tuple[float, float, float]:
    predicted_members: dict[str, set[str]] = defaultdict(set)
    for observation_id, node_id in graph.observation_to_node.items():
        predicted_members[node_id].add(observation_id)
    truth_members: dict[str, set[str]] = defaultdict(set)
    for observation_id, truth_id in observation_to_truth.items():
        if truth_id is not None and observation_id in graph.observation_to_node:
            truth_members[str(truth_id)].add(observation_id)
    precisions: list[float] = []
    recalls: list[float] = []
    for observation_id, truth_id in observation_to_truth.items():
        if truth_id is None or observation_id not in graph.observation_to_node:
            continue
        predicted = predicted_members[graph.observation_to_node[observation_id]]
        truth_cluster = truth_members[str(truth_id)]
        overlap = len(predicted & truth_cluster)
        precisions.append(overlap / max(1, len(predicted)))
        recalls.append(overlap / max(1, len(truth_cluster)))
    precision = float(np.mean(precisions)) if precisions else 0.0
    recall = float(np.mean(recalls)) if recalls else 0.0
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def _edge_counts(
    graph: GraphSnapshot,
    node_truth_map: Mapping[str, str | None],
    truth_edge_by_triple: Mapping[tuple[str, str, str], str],
) -> tuple[dict[str, int], list[dict[str, Any]], set[tuple[str, str, str]]]:
    seen_truth: set[tuple[str, str, str]] = set()
    rows: list[dict[str, Any]] = []
    tp = fp_duplicate = fp_unmappable = fp_oracle_absent = 0
    for edge in sorted(
        graph.edges,
        key=lambda item: (item.subject, item.predicate.value, item.object, item.derived),
    ):
        subject_truth = node_truth_map.get(edge.subject)
        object_truth = node_truth_map.get(edge.object)
        triple = (
            subject_truth,
            edge.predicate.value,
            object_truth,
        ) if subject_truth is not None and object_truth is not None else None
        if triple is None:
            classification = "false_positive_unmappable"
            fp_unmappable += 1
            truth_edge_id = None
        elif triple not in truth_edge_by_triple:
            classification = "false_positive_oracle_absent"
            fp_oracle_absent += 1
            truth_edge_id = None
        elif triple in seen_truth:
            classification = "false_positive_duplicate"
            fp_duplicate += 1
            truth_edge_id = truth_edge_by_triple[triple]
        else:
            classification = "true_positive"
            tp += 1
            seen_truth.add(triple)
            truth_edge_id = truth_edge_by_triple[triple]
        rows.append(
            {
                "predicted_edge_key": f"{edge.subject}|{edge.predicate.value}|{edge.object}",
                "subject_truth_id": subject_truth,
                "predicate": edge.predicate.value,
                "object_truth_id": object_truth,
                "truth_edge_id": truth_edge_id,
                "classification": classification,
                "support": float(edge.support),
                "derived": bool(edge.derived),
                "rules": list(edge.rules),
                "evidence_ids": list(edge.evidence_ids),
            }
        )
    fp = fp_duplicate + fp_unmappable + fp_oracle_absent
    fn = len(set(truth_edge_by_triple) - seen_truth)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "fp_duplicate": fp_duplicate,
        "fp_unmappable": fp_unmappable,
        "fp_oracle_absent": fp_oracle_absent,
    }, rows, seen_truth


def _ranking_metrics(
    rankings: Sequence[RankingEntry],
    node_truth_map: Mapping[str, str | None],
    *,
    priorities: Mapping[str, int],
    truth_nodes: Mapping[str, Mapping[str, Any]],
    cutoffs: Sequence[int],
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    primary_relevance: list[float] = []
    weighted_rows = sorted(rankings, key=lambda row: row.weighted_rank)
    mean_rows = sorted(rankings, key=lambda row: row.mean_factor_order_rank)

    for row in sorted(rankings, key=lambda item: item.primary_rank):
        truth_id = node_truth_map.get(row.node_id)
        duplicate = truth_id in seen if truth_id is not None else False
        relevance = 0.0
        if truth_id is not None and not duplicate:
            seen.add(truth_id)
            relevance = float(priorities.get(truth_id, 0))
        primary_relevance.append(relevance)
        rows.append(
            {
                **row.to_dict(),
                "truth_id": truth_id,
                "duplicate_truth": duplicate,
                "relevance": relevance,
            }
        )

    ranked_type_values = {
        "service",
        "endpoint",
        "certificate",
        "software_component",
        "pipeline",
        "device",
    }
    ideal_relevance = sorted(
        (
            float(priorities.get(truth_id, 0))
            for truth_id, node in truth_nodes.items()
            if str(node["entity_type"]) in ranked_type_values
        ),
        reverse=True,
    )
    metrics: dict[str, float] = {}
    for cutoff in cutoffs:
        metrics[f"ndcg_at_{cutoff}"] = ndcg(primary_relevance, ideal_relevance, cutoff)
        metrics[f"weighted_ndcg_at_{cutoff}"] = _ordering_ndcg(
            weighted_rows, node_truth_map, priorities, ideal_relevance, cutoff
        )
        metrics[f"mean_factor_ndcg_at_{cutoff}"] = _ordering_ndcg(
            mean_rows, node_truth_map, priorities, ideal_relevance, cutoff
        )

    unique_primary: list[tuple[int, str, int]] = []
    seen.clear()
    for row in sorted(rankings, key=lambda item: item.primary_rank):
        truth_id = node_truth_map.get(row.node_id)
        if truth_id is None or truth_id in seen:
            continue
        seen.add(truth_id)
        unique_primary.append((row.primary_rank, truth_id, priorities.get(truth_id, 0)))
    if len(unique_primary) >= 2:
        ranks = [rank for rank, _, _ in unique_primary]
        desired = [-priority for _, _, priority in unique_primary]
        tau = kendalltau(ranks, desired, variant="b").statistic
        rho = spearmanr(ranks, desired).statistic
        metrics["kendall_tau_b"] = _finite_or_zero(tau)
        metrics["spearman_rho"] = _finite_or_zero(rho)
    else:
        metrics["kendall_tau_b"] = 0.0
        metrics["spearman_rho"] = 0.0

    urgent = {truth_id for truth_id, priority in priorities.items() if int(priority) >= 2}
    top_five = {truth_id for _, truth_id, _ in unique_primary[:5]}
    metrics["urgent_recall_at_5"] = len(urgent & top_five) / max(1, len(urgent))
    return metrics, rows


def _ordering_ndcg(
    rows: Sequence[RankingEntry],
    node_truth_map: Mapping[str, str | None],
    priorities: Mapping[str, int],
    ideal: Sequence[float],
    cutoff: int,
) -> float:
    seen: set[str] = set()
    values: list[float] = []
    for row in rows:
        truth_id = node_truth_map.get(row.node_id)
        if truth_id is None or truth_id in seen:
            values.append(0.0)
        else:
            seen.add(truth_id)
            values.append(float(priorities.get(truth_id, 0)))
    return ndcg(values, ideal, cutoff)


def ndcg(relevance: Sequence[float], ideal: Sequence[float], cutoff: int) -> float:
    def dcg(values: Sequence[float]) -> float:
        return sum(
            (2.0 ** float(value) - 1.0) / math.log2(index + 2.0)
            for index, value in enumerate(values)
        )

    denominator = dcg(ideal[:cutoff])
    return dcg(relevance[:cutoff]) / denominator if denominator else 0.0


def calibration_metrics(
    rows: Sequence[Mapping[str, Any]], *, bins: int = 5
) -> tuple[float, float]:
    if not rows:
        return 0.0, 0.0
    scores = np.asarray([float(row["score"]) for row in rows], dtype=float)
    labels = np.asarray([float(row["label"]) for row in rows], dtype=float)
    brier = float(np.mean((scores - labels) ** 2))
    boundaries = np.linspace(0.0, 1.0, bins + 1)
    ece = 0.0
    for index in range(bins):
        lower, upper = boundaries[index], boundaries[index + 1]
        mask = (scores >= lower) & (scores <= upper if index == bins - 1 else scores < upper)
        if not np.any(mask):
            continue
        ece += float(np.mean(mask)) * abs(
            float(np.mean(scores[mask])) - float(np.mean(labels[mask]))
        )
    return brier, ece


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def _finite_or_zero(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0
