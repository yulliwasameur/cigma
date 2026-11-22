#!/usr/bin/env python3
"""Host-dependent scaling probe for the clean-room CIGMA implementation.

This probe deliberately lives outside the deterministic accuracy manifest. It
replicates the public fixture with disjoint identifiers, executes full CIGMA,
and reports wall-clock time plus Python allocation peaks. Results are suitable
for implementation diagnostics only, not production-throughput claims.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import replace
import json
from pathlib import Path
from statistics import median
from time import perf_counter
import tracemalloc

from cigma.config import load_config
from cigma.io import load_observations
from cigma.pipeline import build_graph
from cigma.schema import EntityObservation, RelationObservation, evidence_digest
from cigma.scoring import rank_assets


def _replicated_identifier(key: str, value: str, replica: int) -> str:
    """Keep algorithm vocabulary global; namespace deployment-specific IDs."""
    if key == "algorithm_id":
        return value
    return f"{value}::replica-{replica:05d}"


def replicate_observations(
    entities: list[EntityObservation],
    relations: list[RelationObservation],
    factor: int,
) -> tuple[list[EntityObservation], list[RelationObservation]]:
    if factor < 1:
        raise ValueError("factor must be >= 1")
    replicated_entities: list[EntityObservation] = []
    replicated_relations: list[RelationObservation] = []
    for replica in range(factor):
        id_map: dict[str, str] = {}
        suffix = f"::replica-{replica:05d}"
        for observation in entities:
            observation_id = f"{observation.observation_id}{suffix}"
            id_map[observation.observation_id] = observation_id
            excerpt = f"{observation.evidence_excerpt}\nCIGMA scaling replica={replica}"
            replicated_entities.append(
                replace(
                    observation,
                    observation_id=observation_id,
                    local_key=f"{observation.local_key}{suffix}",
                    identifiers={
                        key: _replicated_identifier(key, value, replica)
                        for key, value in observation.identifiers.items()
                    },
                    locator=f"{observation.locator}/scaling-replica/{replica}",
                    evidence_excerpt=excerpt,
                    evidence_sha256=evidence_digest(excerpt),
                )
            )
        for observation in relations:
            excerpt = f"{observation.evidence_excerpt}\nCIGMA scaling replica={replica}"
            replicated_relations.append(
                replace(
                    observation,
                    observation_id=f"{observation.observation_id}{suffix}",
                    subject_observation_id=id_map[observation.subject_observation_id],
                    object_observation_id=id_map[observation.object_observation_id],
                    locator=f"{observation.locator}/scaling-replica/{replica}",
                    evidence_excerpt=excerpt,
                    evidence_sha256=evidence_digest(excerpt),
                )
            )
    return replicated_entities, replicated_relations


def run_probe(
    *,
    public_dir: Path,
    config_path: Path,
    output_dir: Path,
    factors: list[int],
    repetitions: int,
    warmup: bool,
) -> dict[str, object]:
    entities, relations = load_observations(
        public_dir / "entities.jsonl", public_dir / "relations.jsonl"
    )
    config = load_config(config_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, float | int]] = []

    for factor in factors:
        scaled_entities, scaled_relations = replicate_observations(entities, relations, factor)
        if warmup:
            graph = build_graph(scaled_entities, scaled_relations, config=config, method="cigma")
            rank_assets(graph, config=config)
        for repetition in range(repetitions):
            tracemalloc.start()
            graph_start = perf_counter()
            graph = build_graph(scaled_entities, scaled_relations, config=config, method="cigma")
            graph_seconds = perf_counter() - graph_start
            ranking_start = perf_counter()
            ranking = rank_assets(graph, config=config)
            ranking_seconds = perf_counter() - ranking_start
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            rows.append(
                {
                    "factor": factor,
                    "repetition": repetition,
                    "entity_observations": len(scaled_entities),
                    "relation_observations": len(scaled_relations),
                    "nodes": len(graph.nodes),
                    "edges": len(graph.edges),
                    "ranked_assets": len(ranking),
                    "graph_seconds": graph_seconds,
                    "ranking_seconds": ranking_seconds,
                    "peak_mib": peak / (1024 * 1024),
                }
            )

    fields = list(rows[0]) if rows else []
    with (output_dir / "runs.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    summary_rows: list[dict[str, float | int]] = []
    for factor in factors:
        group = [row for row in rows if row["factor"] == factor]
        summary_rows.append(
            {
                "factor": factor,
                "repetition": -1,
                "entity_observations": int(group[0]["entity_observations"]),
                "relation_observations": int(group[0]["relation_observations"]),
                "nodes": int(group[0]["nodes"]),
                "edges": int(group[0]["edges"]),
                "ranked_assets": int(group[0]["ranked_assets"]),
                "graph_seconds": median(float(row["graph_seconds"]) for row in group),
                "ranking_seconds": median(float(row["ranking_seconds"]) for row in group),
                "peak_mib": median(float(row["peak_mib"]) for row in group),
            }
        )
    with (output_dir / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(summary_rows)

    metadata = {
        "schema": "cigma-clean-room-scaling-v1",
        "host_dependent": True,
        "factors": factors,
        "repetitions": repetitions,
        "warmup": warmup,
        "accuracy_manifest_included": False,
        "notice": "Diagnostic only; not production throughput or cross-system evidence.",
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", type=Path, default=Path("data/cigma_lab/public"))
    parser.add_argument("--config", type=Path, default=Path("configs/default.yaml"))
    parser.add_argument("--output", type=Path, default=Path("results/scaling"))
    parser.add_argument("--factors", nargs="+", type=int, default=[1, 3, 10])
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--no-warmup", action="store_true")
    args = parser.parse_args()
    metadata = run_probe(
        public_dir=args.public,
        config_path=args.config,
        output_dir=args.output,
        factors=args.factors,
        repetitions=args.repetitions,
        warmup=not args.no_warmup,
    )
    print(json.dumps(metadata, sort_keys=True))


if __name__ == "__main__":
    main()
