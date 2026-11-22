"""Command-line interface for generation, construction, evaluation, and sealing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .benchmark import generate_cigma_lab
from .config import load_config
from .evaluation import evaluate_method, load_oracle
from .experiment import run_campaign
from .external_validation import evaluate_sealed_predictions, seal_public_predictions
from .io import load_observations, sha256_tree, write_json
from .pipeline import METHODS, build_graph
from .scoring import rank_assets


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cigma", description="CIGMA reference implementation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="generate CIGMA-Lab public and oracle trees")
    generate.add_argument("--output", default="data/cigma_lab")

    run = subparsers.add_parser("run", help="construct graphs from public observations only")
    run.add_argument("--config", default="configs/default.yaml")
    run.add_argument("--public", default="data/cigma_lab/public")
    run.add_argument("--output", default="results/run")
    run.add_argument("--methods", nargs="+", default=["cigma"])

    evaluate = subparsers.add_parser("evaluate", help="evaluate methods with an evaluator-only oracle")
    evaluate.add_argument("--config", default="configs/default.yaml")
    evaluate.add_argument("--public", default="data/cigma_lab/public")
    evaluate.add_argument("--oracle", default="data/cigma_lab/oracle")
    evaluate.add_argument("--output", default="results/evaluation")
    evaluate.add_argument("--methods", nargs="+", default=["cigma"])

    campaign = subparsers.add_parser("campaign", help="run the complete clean-room campaign")
    campaign.add_argument("--config", default="configs/default.yaml")
    campaign.add_argument("--output", default="results/default")
    campaign.add_argument("--data-output", default="data/cigma_lab")

    seal = subparsers.add_parser("seal", help="phase 1: seal public-only predictions")
    seal.add_argument("--config", default="configs/default.yaml")
    seal.add_argument("--public", required=True)
    seal.add_argument("--output", required=True)
    seal.add_argument("--methods", nargs="+", default=["source_union", "exact_direct", "tfidf_cosine", "cigma"])

    evaluate_seal = subparsers.add_parser("evaluate-seal", help="phase 2: verify seal then load oracle")
    evaluate_seal.add_argument("--config", default="configs/default.yaml")
    evaluate_seal.add_argument("--seal-dir", required=True)
    evaluate_seal.add_argument("--public", required=True)
    evaluate_seal.add_argument("--oracle", required=True)
    evaluate_seal.add_argument("--oracle-sha256", required=True)
    evaluate_seal.add_argument("--output", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "generate":
        result = generate_cigma_lab(args.output)
    elif args.command == "run":
        result = _run_public(args.config, args.public, args.output, args.methods)
    elif args.command == "evaluate":
        result = _evaluate(args.config, args.public, args.oracle, args.output, args.methods)
    elif args.command == "campaign":
        generate_cigma_lab(args.data_output)
        result = run_campaign(
            data_root=args.data_output,
            config_path=args.config,
            output_root=args.output,
        )
    elif args.command == "seal":
        result = seal_public_predictions(
            public_dir=args.public,
            config_path=args.config,
            output_dir=args.output,
            methods=args.methods,
        )
    elif args.command == "evaluate-seal":
        result = evaluate_sealed_predictions(
            seal_dir=args.seal_dir,
            public_dir=args.public,
            oracle_dir=args.oracle,
            expected_oracle_tree_sha256=args.oracle_sha256,
            config_path=args.config,
            output_dir=args.output,
        )
    else:  # pragma: no cover
        raise AssertionError(args.command)
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


def _run_public(
    config_path: str,
    public_dir: str,
    output_dir: str,
    methods: Sequence[str],
) -> dict[str, object]:
    config = load_config(config_path)
    public = Path(public_dir)
    output = Path(output_dir)
    entities, relations = load_observations(
        public / "entities.jsonl", public / "relations.jsonl"
    )
    result: dict[str, object] = {"methods": {}}
    for method in methods:
        if method not in METHODS:
            raise ValueError(f"unknown method: {method}")
        graph = build_graph(entities, relations, config=config, method=method)
        rankings = rank_assets(graph, config=config)
        write_json(output / "graphs" / f"{method}.json", graph.to_dict())
        write_json(output / "rankings" / f"{method}.json", [row.to_dict() for row in rankings])
        result["methods"][method] = {
            "nodes": len(graph.nodes),
            "edges": len(graph.edges),
            "verify": sum(row.verify for row in rankings),
        }
    return result


def _evaluate(
    config_path: str,
    public_dir: str,
    oracle_dir: str,
    output_dir: str,
    methods: Sequence[str],
) -> dict[str, object]:
    config = load_config(config_path)
    public = Path(public_dir)
    output = Path(output_dir)
    entities, relations = load_observations(
        public / "entities.jsonl", public / "relations.jsonl"
    )
    oracle = load_oracle(oracle_dir)
    result: dict[str, object] = {"methods": {}}
    for method in methods:
        graph = build_graph(entities, relations, config=config, method=method)
        rankings = rank_assets(graph, config=config)
        evaluation = evaluate_method(
            graph,
            rankings,
            oracle,
            entity_observations=entities,
            relation_observations=relations,
            ndcg_cutoffs=config["evaluation"]["ndcg_cutoffs"],
            ece_bins=int(config["evaluation"]["ece_bins"]),
        )
        write_json(output / f"{method}.json", evaluation.to_dict())
        result["methods"][method] = evaluation.metrics
    return result


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
