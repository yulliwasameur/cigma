"""Two-phase public-prediction sealing and evaluator-only oracle access."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

from .config import config_digest, load_config
from .evaluation import evaluate_method, load_oracle
from .io import load_observations, read_json, sha256_file, sha256_tree, write_json
from .pipeline import METHODS, build_graph
from .schema import Edge, EntityType, GraphSnapshot, Node, RelationType
from .scoring import RankingEntry, rank_assets


def _implementation_root() -> Path:
    return Path(__file__).resolve().parent


def _implementation_tree_sha256() -> str:
    """Hash executable package sources, excluding interpreter caches.

    A prediction seal must survive ordinary imports. Hashing ``__pycache__`` would
    bind the seal to interpreter-generated files whose presence and metadata are
    not part of the implementation contract. Only version-controlled Python
    source files below the package root are included, with their relative paths.
    """
    root = _implementation_root()
    digest = sha256()
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def _graph_from_dict(raw: Mapping[str, Any]) -> GraphSnapshot:
    nodes = {
        item["node_id"]: Node(
            node_id=str(item["node_id"]),
            entity_type=EntityType(str(item["entity_type"])),
            identifiers={str(key): list(value) for key, value in item["identifiers"].items()},
            attributes=dict(item["attributes"]),
            observation_ids=list(item["observation_ids"]),
            support=float(item["support"]),
            merge_log=list(item.get("merge_log", [])),
        )
        for item in raw["nodes"]
    }
    edges = [
        Edge(
            subject=str(item["subject"]),
            predicate=RelationType(str(item["predicate"])),
            object=str(item["object"]),
            evidence_ids=list(item["evidence_ids"]),
            support=float(item["support"]),
            derived=bool(item.get("derived", False)),
            rules=list(item.get("rules", [])),
        )
        for item in raw["edges"]
    ]
    return GraphSnapshot(
        method=str(raw["method"]),
        nodes=nodes,
        edges=edges,
        observation_to_node={str(key): str(value) for key, value in raw["observation_to_node"].items()},
        quarantined_entity_ids=list(raw.get("quarantined_entity_ids", [])),
        quarantined_relation_ids=list(raw.get("quarantined_relation_ids", [])),
        rejected_relation_ids=list(raw.get("rejected_relation_ids", [])),
        config_digest=str(raw["config_digest"]),
    )


def _ranking_from_dict(raw: Mapping[str, Any]) -> RankingEntry:
    return RankingEntry(
        node_id=str(raw["node_id"]),
        entity_type=EntityType(str(raw["entity_type"])),
        service_contexts=list(raw["service_contexts"]),
        impact=dict(raw["impact"]),
        lower_impact={str(key): float(value) for key, value in raw["lower_impact"].items()},
        upper_impact={str(key): float(value) for key, value in raw["upper_impact"].items()},
        lower_tier=int(raw["lower_tier"]),
        upper_tier=int(raw["upper_tier"]),
        pareto_front=int(raw["pareto_front"]),
        evidence_confidence=float(raw["evidence_confidence"]),
        migration_feasibility=(
            None if raw.get("migration_feasibility") is None else float(raw["migration_feasibility"])
        ),
        verify=bool(raw["verify"]),
        primary_rank=int(raw.get("primary_rank", 0)),
        weighted_score=float(raw.get("weighted_score", 0.0)),
        weighted_rank=int(raw.get("weighted_rank", 0)),
        mean_factor_rank=float(raw.get("mean_factor_rank", 0.0)),
        mean_factor_order_rank=int(raw.get("mean_factor_order_rank", 0)),
    )


def seal_public_predictions(
    *,
    public_dir: str | Path,
    config_path: str | Path,
    output_dir: str | Path,
    methods: Sequence[str] = ("source_union", "exact_direct", "tfidf_cosine", "cigma"),
) -> dict[str, Any]:
    """Phase 1: build and seal predictions without an oracle parameter."""
    public = Path(public_dir)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    config = load_config(config_path)
    entities, relations = load_observations(
        public / "entities.jsonl", public / "relations.jsonl"
    )
    prediction_files: dict[str, dict[str, str]] = {}
    for method in methods:
        if method not in METHODS:
            raise ValueError(f"unknown method: {method}")
        graph = build_graph(entities, relations, config=config, method=method)
        rankings = rank_assets(graph, config=config)
        graph_path = output / f"{method}.graph.json"
        ranking_path = output / f"{method}.ranking.json"
        write_json(graph_path, graph.to_dict())
        write_json(ranking_path, [entry.to_dict() for entry in rankings])
        prediction_files[method] = {
            "graph": graph_path.name,
            "graph_sha256": sha256_file(graph_path),
            "ranking": ranking_path.name,
            "ranking_sha256": sha256_file(ranking_path),
        }
    manifest = {
        "schema": "cigma-prediction-seal-v1",
        "public_tree_sha256": sha256_tree(public),
        "config_sha256": sha256_file(config_path),
        "config_digest": config_digest(config),
        "implementation_tree_sha256": _implementation_tree_sha256(),
        "methods": list(methods),
        "prediction_files": prediction_files,
    }
    write_json(output / "manifest.json", manifest)
    manifest["manifest_sha256"] = sha256_file(output / "manifest.json")
    write_json(output / "seal.json", manifest)
    return manifest


def evaluate_sealed_predictions(
    *,
    seal_dir: str | Path,
    public_dir: str | Path,
    oracle_dir: str | Path,
    expected_oracle_tree_sha256: str,
    config_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Phase 2: fail closed on seal drift before loading evaluator-only truth."""
    seal_root = Path(seal_dir)
    public = Path(public_dir)
    oracle_root = Path(oracle_dir)
    output = Path(output_dir)
    manifest = read_json(seal_root / "manifest.json")
    if manifest["public_tree_sha256"] != sha256_tree(public):
        raise ValueError("public dataset binding mismatch")
    if manifest["config_sha256"] != sha256_file(config_path):
        raise ValueError("configuration binding mismatch")
    if manifest["implementation_tree_sha256"] != _implementation_tree_sha256():
        raise ValueError("implementation binding mismatch")
    for method, files in manifest["prediction_files"].items():
        if sha256_file(seal_root / files["graph"]) != files["graph_sha256"]:
            raise ValueError(f"prediction graph seal mismatch: {method}")
        if sha256_file(seal_root / files["ranking"]) != files["ranking_sha256"]:
            raise ValueError(f"prediction ranking seal mismatch: {method}")

    # The oracle is opened only after public/configuration/code/prediction checks.
    actual_oracle_digest = sha256_tree(oracle_root)
    if actual_oracle_digest != expected_oracle_tree_sha256:
        raise ValueError("oracle custody digest mismatch")
    oracle = load_oracle(oracle_root)
    entities, relations = load_observations(
        public / "entities.jsonl", public / "relations.jsonl"
    )
    config = load_config(config_path)
    results: dict[str, Any] = {}
    output.mkdir(parents=True, exist_ok=True)
    for method, files in manifest["prediction_files"].items():
        graph = _graph_from_dict(read_json(seal_root / files["graph"]))
        rankings = [_ranking_from_dict(item) for item in read_json(seal_root / files["ranking"])]
        evaluation = evaluate_method(
            graph,
            rankings,
            oracle,
            entity_observations=entities,
            relation_observations=relations,
            ndcg_cutoffs=config["evaluation"]["ndcg_cutoffs"],
            ece_bins=int(config["evaluation"]["ece_bins"]),
        )
        results[method] = evaluation.to_dict()
    summary = {
        "schema": "cigma-sealed-evaluation-v1",
        "public_tree_sha256": manifest["public_tree_sha256"],
        "oracle_tree_sha256": actual_oracle_digest,
        "methods": results,
    }
    write_json(output / "summary.json", summary)
    return summary
