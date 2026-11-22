"""Deterministic normalization for identifiers and attributes."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any


_WHITESPACE = re.compile(r"\s+")


def normalize_scalar(value: Any) -> Any:
    if isinstance(value, str):
        return _WHITESPACE.sub(" ", value.strip())
    return value


def normalize_identifier(key: str, value: str) -> str:
    normalized = normalize_scalar(value)
    if not isinstance(normalized, str):
        normalized = str(normalized)
    key_lower = key.lower()
    if key_lower in {
        "certificate_fingerprint",
        "spki_fingerprint",
        "algorithm_id",
        "service_uid",
        "device_serial",
        "pipeline_uid",
        "data_uid",
    }:
        return normalized.upper()
    if key_lower in {"hostname", "service_name", "deployment_name"}:
        return normalized.lower()
    if key_lower == "endpoint_uri":
        return normalized.lower().rstrip("/")
    if key_lower == "purl":
        return normalized.lower()
    if key_lower == "repository_path":
        return normalized.replace("\\", "/").strip("/").lower()
    return normalized


def normalize_identifiers(identifiers: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(key): normalize_identifier(str(key), str(value))
        for key, value in sorted(identifiers.items())
        if value is not None and str(value).strip()
    }


def normalize_attributes(attributes: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in sorted(attributes.items()):
        if isinstance(value, Mapping):
            result[str(key)] = normalize_attributes(value)
        elif isinstance(value, list):
            result[str(key)] = [normalize_scalar(item) for item in value]
        else:
            result[str(key)] = normalize_scalar(value)
    return result
