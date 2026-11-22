from __future__ import annotations

from pathlib import Path

import pytest

from cigma.benchmark import generate_cigma_lab
from cigma.config import load_config
from cigma.evaluation import load_oracle
from cigma.io import load_observations
from cigma.pipeline import build_graph
from cigma.scoring import rank_assets


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def config():
    return load_config(PROJECT_ROOT / "configs" / "default.yaml")


@pytest.fixture(scope="session")
def fixture_root(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("cigma_lab")
    generate_cigma_lab(root)
    return root


@pytest.fixture(scope="session")
def observations(fixture_root):
    return load_observations(
        fixture_root / "public" / "entities.jsonl",
        fixture_root / "public" / "relations.jsonl",
    )


@pytest.fixture(scope="session")
def oracle(fixture_root):
    return load_oracle(fixture_root / "oracle")


@pytest.fixture(scope="session")
def cigma_graph(observations, config):
    entities, relations = observations
    return build_graph(entities, relations, config=config, method="cigma")


@pytest.fixture(scope="session")
def cigma_rankings(cigma_graph, config):
    return rank_assets(cigma_graph, config=config)
