from __future__ import annotations

from dataclasses import replace

import pytest

from cigma.adapters.base import ObservationFactory
from cigma.schema import (
    EntityType,
    RelationType,
    SourceFamily,
    evidence_digest,
    validate_observations,
)


def _items():
    factory = ObservationFactory(SourceFamily.TLS, "2026-08-19T00:00:00+00:00")
    left = factory.entity(
        local_key="endpoint",
        entity_type=EntityType.ENDPOINT,
        identifiers={"endpoint_uri": "tls://a:443"},
        locator="tls/a#/endpoint",
    )
    right = factory.entity(
        local_key="certificate",
        entity_type=EntityType.CERTIFICATE,
        identifiers={"certificate_fingerprint": "ABC"},
        locator="tls/a#/certificate",
    )
    relation = factory.relation(
        local_key="presents",
        subject=left,
        predicate=RelationType.PRESENTS,
        object_=right,
        locator="tls/a#/presents",
    )
    return left, right, relation


def test_evidence_digest_is_sha256():
    assert evidence_digest("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_entity_observation_round_trip():
    left, _, _ = _items()
    assert type(left).from_dict(left.to_dict()) == left


def test_relation_observation_round_trip():
    _, _, relation = _items()
    assert type(relation).from_dict(relation.to_dict()) == relation


def test_entity_quality_out_of_range_is_rejected():
    left, _, _ = _items()
    with pytest.raises(ValueError, match="quality"):
        replace(left, quality=1.1).validate()


def test_evidence_hash_mismatch_is_rejected():
    left, _, _ = _items()
    with pytest.raises(ValueError, match="digest mismatch"):
        replace(left, evidence_sha256="0" * 64).validate()


def test_duplicate_entity_observation_ids_are_rejected():
    left, _, _ = _items()
    with pytest.raises(ValueError, match="duplicate entity"):
        validate_observations([left, left], [])


def test_relation_with_unknown_endpoint_is_rejected():
    left, right, relation = _items()
    with pytest.raises(ValueError, match="unknown relation object"):
        validate_observations([left], [relation])
