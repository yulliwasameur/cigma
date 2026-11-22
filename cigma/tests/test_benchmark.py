from __future__ import annotations

from collections import Counter
from pathlib import Path

from cigma.benchmark import generate_cigma_lab
from cigma.io import load_observations, read_json, read_jsonl, sha256_tree


def test_fixture_has_published_top_level_counts(fixture_root):
    stats = read_json(fixture_root / "fixture_statistics.json")
    assert (stats["entity_observations"], stats["relation_observations"]) == (46, 34)
    assert (stats["truth_entities"], stats["truth_edges"]) == (23, 34)


def test_fixture_generation_is_byte_deterministic(tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    generate_cigma_lab(left)
    generate_cigma_lab(right)
    assert sha256_tree(left) == sha256_tree(right)


def test_public_records_do_not_embed_truth_ids(fixture_root):
    public_text = "".join(path.read_text() for path in (fixture_root / "public").glob("*.jsonl"))
    assert "truth_id" not in public_text
    assert "oracle" not in public_text.lower()


def test_every_public_observation_has_locator_excerpt_and_digest(fixture_root):
    entities, relations = load_observations(
        fixture_root / "public" / "entities.jsonl", fixture_root / "public" / "relations.jsonl"
    )
    assert all(item.locator and item.evidence_excerpt and len(item.evidence_sha256) == 64 for item in entities + relations)


def test_fixture_entity_source_counts_match_contract(fixture_root):
    entities, _ = load_observations(fixture_root / "public" / "entities.jsonl", fixture_root / "public" / "relations.jsonl")
    assert Counter(item.source.value for item in entities) == {"tls": 9, "pki": 9, "cbom": 10, "cicd": 4, "cmdb": 10, "ot": 4}


def test_fixture_relation_source_counts_match_contract(fixture_root):
    _, relations = load_observations(fixture_root / "public" / "entities.jsonl", fixture_root / "public" / "relations.jsonl")
    assert Counter(item.source.value for item in relations) == {"tls": 6, "pki": 8, "cbom": 7, "cicd": 2, "cmdb": 8, "ot": 3}


def test_fixture_has_32_true_and_two_false_relation_observations(fixture_root):
    mapping = read_json(fixture_root / "oracle" / "relation_to_truth.json")
    assert sum(value is not None for value in mapping.values()) == 32
    assert sum(value is None for value in mapping.values()) == 2


def test_fixture_has_sixteen_critical_targets_and_34_unique_edges(fixture_root):
    critical = read_json(fixture_root / "oracle" / "critical_targets.json")
    edges = list(read_jsonl(fixture_root / "oracle" / "edges.jsonl"))
    assert len(critical) == 16
    assert len(edges) == len({row["edge_id"] for row in edges}) == 34


def test_scaling_replication_namespaces_deployment_identifiers(project_root):
    import importlib.util
    from cigma.io import load_observations

    script = project_root / "scripts" / "benchmark_scaling.py"
    spec = importlib.util.spec_from_file_location("cigma_scaling_probe", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    entities, relations = load_observations(
        project_root / "data" / "cigma_lab" / "public" / "entities.jsonl",
        project_root / "data" / "cigma_lab" / "public" / "relations.jsonl",
    )
    scaled_entities, scaled_relations = module.replicate_observations(entities, relations, 2)
    assert len(scaled_entities) == 2 * len(entities)
    assert len(scaled_relations) == 2 * len(relations)
    assert len({item.observation_id for item in scaled_entities}) == len(scaled_entities)
    algorithm_ids = {
        item.identifiers.get("algorithm_id")
        for item in scaled_entities
        if "algorithm_id" in item.identifiers
    }
    assert "RSA-2048" in algorithm_ids
