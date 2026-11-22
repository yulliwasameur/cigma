"""Deterministic complete-fixture, ablation, source-dropout, and perturbation campaign."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from .config import config_digest, load_config
from .evaluation import evaluate_method, load_oracle
from .io import load_observations, sha256_tree, write_json
from .pipeline import METHODS, MethodSpec, build_graph
from .schema import EntityObservation, RelationObservation, SourceFamily
from .scoring import rank_assets
from .stats import (
    holm_correction,
    paired_bootstrap_ci,
    paired_sign_randomization_pvalue,
    percentile_bootstrap_ci,
    wins_ties_losses,
)


COMPLETE_METHODS = (
    "tls_inventory",
    "cbom_inventory",
    "source_union",
    "exact_direct",
    "tfidf_cosine",
    "cigma",
    "cigma_no_aliases",
    "cigma_no_paths",
    "cigma_no_quality_gate",
    "cigma_uniform_reliability",
)


def _flat_metrics(result: Any) -> dict[str, Any]:
    return {"method": result.method, **dict(result.metrics)}


def _drop_observations(
    entities: Sequence[EntityObservation],
    relations: Sequence[RelationObservation],
    *,
    probability: float,
    seed: int,
) -> tuple[list[EntityObservation], list[RelationObservation], dict[str, float]]:
    if probability == 0.0:
        return list(entities), list(relations), {
            "realized_entity_deletion": 0.0,
            "realized_relation_deletion": 0.0,
        }
    rng = np.random.default_rng(seed)
    keep_entity = {
        item.observation_id: bool(rng.random() >= probability) for item in entities
    }
    kept_entities = [item for item in entities if keep_entity[item.observation_id]]
    kept_relations: list[RelationObservation] = []
    for item in relations:
        endpoints_survive = keep_entity[item.subject_observation_id] and keep_entity[item.object_observation_id]
        if endpoints_survive and bool(rng.random() >= probability):
            kept_relations.append(item)
    return kept_entities, kept_relations, {
        "realized_entity_deletion": 1.0 - len(kept_entities) / len(entities),
        "realized_relation_deletion": 1.0 - len(kept_relations) / len(relations),
    }


def _evaluate(
    entities: Sequence[EntityObservation],
    relations: Sequence[RelationObservation],
    *,
    config: Mapping[str, Any],
    oracle: Any,
    method: str | MethodSpec,
) -> tuple[Any, Any, dict[str, Any]]:
    graph = build_graph(entities, relations, config=config, method=method)
    rankings = rank_assets(graph, config=config)
    result = evaluate_method(
        graph,
        rankings,
        oracle,
        entity_observations=entities,
        relation_observations=relations,
        ndcg_cutoffs=config["evaluation"]["ndcg_cutoffs"],
        ece_bins=int(config["evaluation"]["ece_bins"]),
    )
    return graph, rankings, result


def run_campaign(
    *,
    data_root: str | Path,
    config_path: str | Path,
    output_root: str | Path,
) -> dict[str, Any]:
    data = Path(data_root)
    output = Path(output_root)
    metrics_dir = output / "metrics"
    graph_dir = output / "graphs"
    ranking_dir = output / "rankings"
    for directory in (metrics_dir, graph_dir, ranking_dir):
        directory.mkdir(parents=True, exist_ok=True)

    config = load_config(config_path)
    entities, relations = load_observations(
        data / "public" / "entities.jsonl",
        data / "public" / "relations.jsonl",
    )
    oracle = load_oracle(data / "oracle")

    complete_rows: list[dict[str, Any]] = []
    for method in COMPLETE_METHODS:
        graph, rankings, metrics = _evaluate(
            entities,
            relations,
            config=config,
            oracle=oracle,
            method=method,
        )
        write_json(graph_dir / f"{method}.json", graph.to_dict())
        pd.DataFrame([entry.to_dict() for entry in rankings]).to_csv(
            ranking_dir / f"{method}.csv", index=False
        )
        complete_rows.append(_flat_metrics(metrics))
    method_metrics = pd.DataFrame(complete_rows).sort_values("method")
    method_metrics.to_csv(metrics_dir / "method_metrics.csv", index=False)

    leave_rows: list[dict[str, Any]] = []
    present = {item.source for item in entities}
    for source in [item for item in SourceFamily if item in present]:   # only families present in the data
        base = METHODS["cigma"]
        spec = replace(
            base,
            name=f"cigma_without_{source.value}",
            sources=frozenset(item for item in SourceFamily if item != source),
        )
        _, _, metrics = _evaluate(
            entities,
            relations,
            config=config,
            oracle=oracle,
            method=spec,
        )
        row = _flat_metrics(metrics)
        row["omitted_source"] = source.value
        leave_rows.append(row)
    pd.DataFrame(leave_rows).sort_values("omitted_source").to_csv(
        metrics_dir / "leave_one_source_out.csv", index=False
    )

    robustness_rows: list[dict[str, Any]] = []
    probabilities = [float(value) for value in config["robustness"]["deletion_probabilities"]]
    seed_count = int(config["robustness"]["seeds"])
    robustness_methods = list(config["robustness"]["methods"])
    for probability in probabilities:
        for seed_index in range(seed_count):
            mask_seed = int(config["evaluation"]["statistics_seed"]) + int(probability * 10000) + seed_index
            perturbed_entities, perturbed_relations, realized = _drop_observations(
                entities,
                relations,
                probability=probability,
                seed=mask_seed,
            )
            for method in robustness_methods:
                _, _, metrics = _evaluate(
                    perturbed_entities,
                    perturbed_relations,
                    config=config,
                    oracle=oracle,
                    method=method,
                )
                row = _flat_metrics(metrics)
                row.update(
                    {
                        "nominal_deletion": probability,
                        "seed_index": seed_index,
                        "mask_seed": mask_seed,
                        **realized,
                    }
                )
                robustness_rows.append(row)
    robustness = pd.DataFrame(robustness_rows).sort_values(
        ["nominal_deletion", "seed_index", "method"]
    )
    robustness.to_csv(metrics_dir / "robustness_runs.csv", index=False)

    aggregate_rows: list[dict[str, Any]] = []
    aggregate_metrics = ["asset_f1", "pairwise_f1", "b3_f1", "edge_f1", "ndcg_at_5", "ndcg_at_10"]
    bootstrap_seed = int(config["evaluation"]["statistics_seed"])
    resamples = int(config["evaluation"]["bootstrap_resamples"])
    for (probability, method), group in robustness.groupby(["nominal_deletion", "method"], sort=True):
        for metric in aggregate_metrics:
            values = group.sort_values("seed_index")[metric].astype(float).tolist()
            lower, upper = percentile_bootstrap_ci(
                values,
                resamples=resamples,
                seed=bootstrap_seed + int(probability * 10000) + len(metric) + len(method),
            )
            aggregate_rows.append(
                {
                    "nominal_deletion": probability,
                    "method": method,
                    "metric": metric,
                    "mean": float(np.mean(values)),
                    "median": float(np.median(values)),
                    "ci95_lower": lower,
                    "ci95_upper": upper,
                    "n": len(values),
                }
            )
    pd.DataFrame(aggregate_rows).to_csv(
        metrics_dir / "robustness_aggregate.csv", index=False
    )

    contrast_rows: list[dict[str, Any]] = []
    contrast_metrics = list(config["robustness"]["contrast_metrics"])
    baselines = [method for method in robustness_methods if method != "cigma"]
    for probability in probabilities:
        level = robustness[robustness["nominal_deletion"] == probability]
        cigma = level[level["method"] == "cigma"].sort_values("seed_index")
        for baseline in baselines:
            comparison = level[level["method"] == baseline].sort_values("seed_index")
            if cigma["seed_index"].tolist() != comparison["seed_index"].tolist():
                raise AssertionError("paired perturbation masks are misaligned")
            for metric in contrast_metrics:
                left = cigma[metric].astype(float).to_numpy()
                right = comparison[metric].astype(float).to_numpy()
                differences = left - right
                lower, upper = paired_bootstrap_ci(
                    left,
                    right,
                    resamples=resamples,
                    seed=bootstrap_seed + int(probability * 10000) + len(metric) + len(baseline),
                )
                pvalue = paired_sign_randomization_pvalue(
                    differences,
                    draws=int(config["evaluation"]["randomization_draws"]),
                    seed=bootstrap_seed + int(probability * 10000) + len(metric) * 31,
                )
                wins, ties, losses = wins_ties_losses(differences)
                contrast_rows.append(
                    {
                        "nominal_deletion": probability,
                        "baseline": baseline,
                        "metric": metric,
                        "mean_difference": float(np.mean(differences)),
                        "median_difference": float(np.median(differences)),
                        "ci95_lower": lower,
                        "ci95_upper": upper,
                        "raw_p": pvalue,
                        "wins": wins,
                        "ties": ties,
                        "losses": losses,
                        "n": len(differences),
                    }
                )
    adjusted = holm_correction([row["raw_p"] for row in contrast_rows])
    for row, value in zip(contrast_rows, adjusted):
        row["holm_p"] = value
    pd.DataFrame(contrast_rows).to_csv(metrics_dir / "statistics.csv", index=False)

    cigma_row = method_metrics[method_metrics["method"] == "cigma"].iloc[0].to_dict()
    source_union_row = method_metrics[method_metrics["method"] == "source_union"].iloc[0].to_dict()
    summary = {
        "schema": "cigma-clean-room-campaign-v1",
        "complete_methods": list(COMPLETE_METHODS),
        "robustness_method_runs": len(robustness_rows),
        "robustness_scenarios": len(probabilities) * seed_count,
        "planned_contrasts": len(contrast_rows),
        "config_digest": config_digest(config),
        "data_tree_sha256": sha256_tree(data),
        "output_metrics_tree_sha256": sha256_tree(metrics_dir),
        "clean_room_metrics": {
            "cigma_asset_f1": float(cigma_row["asset_f1"]),
            "cigma_pairwise_f1": float(cigma_row["pairwise_f1"]),
            "cigma_b3_f1": float(cigma_row["b3_f1"]),
            "cigma_edge_f1": float(cigma_row["edge_f1"]),
            "cigma_ndcg_at_10": float(cigma_row["ndcg_at_10"]),
            "source_union_asset_f1": float(source_union_row["asset_f1"]),
            "source_union_edge_f1": float(source_union_row["edge_f1"]),
        },
        "clean_room_notice": (
            "These outputs were generated by the 2026 clean-room reference implementation; "
            "they are not the lost artifact's historical results."
        ),
    }
    write_json(output / "summary.json", summary)
    macro_lines = [
        "% Generated by the clean-room CIGMA campaign. Do not edit by hand.",
        f"\\newcommand{{\\CIGMARobustnessRuns}}{{{summary['robustness_method_runs']}}}",
        f"\\newcommand{{\\CIGMARobustnessScenarios}}{{{summary['robustness_scenarios']}}}",
        f"\\newcommand{{\\CIGMAPlannedContrasts}}{{{summary['planned_contrasts']}}}",
        f"\\newcommand{{\\CIGMACleanAssetFOne}}{{{summary['clean_room_metrics']['cigma_asset_f1']:.4f}}}",
        f"\\newcommand{{\\CIGMACleanEdgeFOne}}{{{summary['clean_room_metrics']['cigma_edge_f1']:.4f}}}",
        f"\\newcommand{{\\CIGMACleanNDCGTen}}{{{summary['clean_room_metrics']['cigma_ndcg_at_10']:.4f}}}",
    ]
    (output / "paper_macros.tex").write_text("\n".join(macro_lines) + "\n", encoding="utf-8")
    write_json(
        output / "manifest.json",
        {
            **summary,
            "graph_tree_sha256": sha256_tree(graph_dir),
            "ranking_tree_sha256": sha256_tree(ranking_dir),
        },
    )
    return summary


if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(description="Run the clean-room CIGMA evaluation campaign")
    parser.add_argument("--data", default="data/cigma_lab")
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--output", default="results/default")
    args = parser.parse_args()
    print(run_campaign(data_root=args.data, config_path=args.config, output_root=args.output))
