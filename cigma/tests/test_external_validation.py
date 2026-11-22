from __future__ import annotations

import json

import pytest

from cigma.external_validation import evaluate_sealed_predictions, seal_public_predictions
from cigma.io import sha256_tree


def test_two_phase_seal_round_trip(fixture_root, project_root, tmp_path):
    seal = tmp_path / "seal"
    evaluation = tmp_path / "evaluation"
    seal_public_predictions(
        public_dir=fixture_root / "public",
        config_path=project_root / "configs" / "default.yaml",
        output_dir=seal,
        methods=("cigma",),
    )
    summary = evaluate_sealed_predictions(
        seal_dir=seal,
        public_dir=fixture_root / "public",
        oracle_dir=fixture_root / "oracle",
        expected_oracle_tree_sha256=sha256_tree(fixture_root / "oracle"),
        config_path=project_root / "configs" / "default.yaml",
        output_dir=evaluation,
    )
    assert summary["methods"]["cigma"]["metrics"]["edge_f1"] == 1.0


def test_prediction_tampering_fails_closed_before_oracle_loading(fixture_root, project_root, tmp_path, monkeypatch):
    seal = tmp_path / "seal"
    seal_public_predictions(
        public_dir=fixture_root / "public",
        config_path=project_root / "configs" / "default.yaml",
        output_dir=seal,
        methods=("cigma",),
    )
    graph_path = seal / "cigma.graph.json"
    graph_path.write_text(graph_path.read_text() + " ")
    import cigma.external_validation as module
    called = {"oracle": False}
    def forbidden(*args, **kwargs):
        called["oracle"] = True
        raise AssertionError("oracle must not be loaded")
    monkeypatch.setattr(module, "load_oracle", forbidden)
    with pytest.raises(ValueError, match="prediction graph seal mismatch"):
        evaluate_sealed_predictions(
            seal_dir=seal,
            public_dir=fixture_root / "public",
            oracle_dir=fixture_root / "oracle",
            expected_oracle_tree_sha256=sha256_tree(fixture_root / "oracle"),
            config_path=project_root / "configs" / "default.yaml",
            output_dir=tmp_path / "evaluation",
        )
    assert called["oracle"] is False


def test_prediction_seal_ignores_interpreter_cache_files(fixture_root, project_root, tmp_path):
    """Interpreter caches are not part of the sealed implementation contract."""
    seal = tmp_path / "seal"
    cache = project_root / "src" / "cigma" / "__pycache__" / "seal-noise.pyc"
    seal_public_predictions(
        public_dir=fixture_root / "public",
        config_path=project_root / "configs" / "default.yaml",
        output_dir=seal,
        methods=("cigma",),
    )
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(b"interpreter cache noise")
    try:
        summary = evaluate_sealed_predictions(
            seal_dir=seal,
            public_dir=fixture_root / "public",
            oracle_dir=fixture_root / "oracle",
            expected_oracle_tree_sha256=sha256_tree(fixture_root / "oracle"),
            config_path=project_root / "configs" / "default.yaml",
            output_dir=tmp_path / "evaluation",
        )
        assert summary["methods"]["cigma"]["metrics"]["edge_f1"] == 1.0
    finally:
        cache.unlink(missing_ok=True)
