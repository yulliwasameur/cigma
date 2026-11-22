"""Configuration loading and canonical hashing."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

import yaml


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "default.yaml"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    with target.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError("configuration root must be a mapping")
    validate_config(raw)
    return deepcopy(raw)


def validate_config(config: Mapping[str, Any]) -> None:
    required = {
        "quality_gates",
        "source_reliabilities",
        "identity",
        "path_penalty",
        "verification_threshold",
        "policy_horizon_years",
        "algorithm_policy",
        "ranking",
        "evaluation",
        "robustness",
    }
    missing = required - set(config)
    if missing:
        raise ValueError(f"missing configuration sections: {sorted(missing)}")

    for gate_name in ("entity", "relation"):
        value = float(config["quality_gates"][gate_name])
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"quality gate {gate_name} must lie in [0, 1]")

    for source, reliability in config["source_reliabilities"].items():
        if not 0.0 <= float(reliability) <= 1.0:
            raise ValueError(f"source reliability {source} must lie in [0, 1]")

    if not 0.0 < float(config["path_penalty"]) <= 1.0:
        raise ValueError("path_penalty must lie in (0, 1]")
    if not 0.0 <= float(config["verification_threshold"]) <= 1.0:
        raise ValueError("verification_threshold must lie in [0, 1]")
    if float(config["policy_horizon_years"]) <= 0:
        raise ValueError("policy_horizon_years must be positive")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def config_digest(config: Mapping[str, Any]) -> str:
    return sha256(canonical_json(config).encode("utf-8")).hexdigest()
