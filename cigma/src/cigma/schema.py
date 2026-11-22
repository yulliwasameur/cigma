"""Core serialisable data structures for the clean-room CIGMA rebuild."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any, Iterable, Mapping


class SourceFamily(str, Enum):
    TLS = "tls"
    PKI = "pki"
    CBOM = "cbom"
    CICD = "cicd"
    CMDB = "cmdb"
    OT = "ot"
    TELEMETRY = "telemetry"


class EntityType(str, Enum):
    SERVICE = "service"
    ENDPOINT = "endpoint"
    CERTIFICATE = "certificate"
    ALGORITHM = "algorithm"
    SOFTWARE_COMPONENT = "software_component"
    PIPELINE = "pipeline"
    DATA_CLASS = "data_class"
    DEVICE = "device"


class RelationType(str, Enum):
    HOSTS = "HOSTS"
    PRESENTS = "PRESENTS"
    USES = "USES"
    ISSUED_BY = "ISSUED-BY"
    DEPENDS_ON = "DEPENDS-ON"
    DEPLOYS = "DEPLOYS"
    PROCESSES = "PROCESSES"
    PROTECTS = "PROTECTS"


def evidence_digest(excerpt: str) -> str:
    """Return the lowercase SHA-256 digest of an evidence excerpt."""

    return sha256(excerpt.encode("utf-8")).hexdigest()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True, slots=True)
class EntityObservation:
    observation_id: str
    source: SourceFamily
    local_key: str
    entity_type: EntityType
    identifiers: Mapping[str, str]
    attributes: Mapping[str, Any]
    quality: float
    collected_at: str
    locator: str
    evidence_excerpt: str
    evidence_sha256: str

    def validate(self) -> None:
        if not self.observation_id.strip():
            raise ValueError("entity observation_id must be non-empty")
        if not self.local_key.strip():
            raise ValueError("entity local_key must be non-empty")
        if not 0.0 <= float(self.quality) <= 1.0:
            raise ValueError("entity quality must lie in [0, 1]")
        if not self.locator.strip():
            raise ValueError("entity locator must be non-empty")
        if evidence_digest(self.evidence_excerpt) != self.evidence_sha256:
            raise ValueError(f"entity evidence digest mismatch: {self.observation_id}")
        datetime.fromisoformat(self.collected_at.replace("Z", "+00:00"))

    def to_dict(self) -> dict[str, Any]:
        raw = asdict(self)
        raw["source"] = self.source.value
        raw["entity_type"] = self.entity_type.value
        raw["identifiers"] = dict(self.identifiers)
        raw["attributes"] = dict(self.attributes)
        return raw

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "EntityObservation":
        item = cls(
            observation_id=str(raw["observation_id"]),
            source=SourceFamily(str(raw["source"])),
            local_key=str(raw["local_key"]),
            entity_type=EntityType(str(raw["entity_type"])),
            identifiers={str(k): str(v) for k, v in dict(raw.get("identifiers", {})).items()},
            attributes=dict(raw.get("attributes", {})),
            quality=float(raw["quality"]),
            collected_at=str(raw["collected_at"]),
            locator=str(raw["locator"]),
            evidence_excerpt=str(raw["evidence_excerpt"]),
            evidence_sha256=str(raw["evidence_sha256"]),
        )
        item.validate()
        return item


@dataclass(frozen=True, slots=True)
class RelationObservation:
    observation_id: str
    source: SourceFamily
    subject_observation_id: str
    predicate: RelationType
    object_observation_id: str
    quality: float
    collected_at: str
    locator: str
    evidence_excerpt: str
    evidence_sha256: str

    def validate(self) -> None:
        if not self.observation_id.strip():
            raise ValueError("relation observation_id must be non-empty")
        if not self.subject_observation_id.strip() or not self.object_observation_id.strip():
            raise ValueError("relation endpoints must be non-empty")
        if not 0.0 <= float(self.quality) <= 1.0:
            raise ValueError("relation quality must lie in [0, 1]")
        if not self.locator.strip():
            raise ValueError("relation locator must be non-empty")
        if evidence_digest(self.evidence_excerpt) != self.evidence_sha256:
            raise ValueError(f"relation evidence digest mismatch: {self.observation_id}")
        datetime.fromisoformat(self.collected_at.replace("Z", "+00:00"))

    def to_dict(self) -> dict[str, Any]:
        raw = asdict(self)
        raw["source"] = self.source.value
        raw["predicate"] = self.predicate.value
        return raw

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RelationObservation":
        item = cls(
            observation_id=str(raw["observation_id"]),
            source=SourceFamily(str(raw["source"])),
            subject_observation_id=str(raw["subject_observation_id"]),
            predicate=RelationType(str(raw["predicate"])),
            object_observation_id=str(raw["object_observation_id"]),
            quality=float(raw["quality"]),
            collected_at=str(raw["collected_at"]),
            locator=str(raw["locator"]),
            evidence_excerpt=str(raw["evidence_excerpt"]),
            evidence_sha256=str(raw["evidence_sha256"]),
        )
        item.validate()
        return item


@dataclass(slots=True)
class Node:
    node_id: str
    entity_type: EntityType
    identifiers: dict[str, list[str]]
    attributes: dict[str, Any]
    observation_ids: list[str]
    support: float
    merge_log: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "entity_type": self.entity_type.value,
            "identifiers": self.identifiers,
            "attributes": self.attributes,
            "observation_ids": self.observation_ids,
            "support": self.support,
            "merge_log": self.merge_log,
        }


@dataclass(slots=True)
class Edge:
    subject: str
    predicate: RelationType
    object: str
    evidence_ids: list[str]
    support: float
    derived: bool = False
    rules: list[str] = field(default_factory=list)

    @property
    def triple(self) -> tuple[str, RelationType, str]:
        return self.subject, self.predicate, self.object

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "predicate": self.predicate.value,
            "object": self.object,
            "evidence_ids": self.evidence_ids,
            "support": self.support,
            "derived": self.derived,
            "rules": self.rules,
        }


@dataclass(slots=True)
class GraphSnapshot:
    method: str
    nodes: dict[str, Node]
    edges: list[Edge]
    observation_to_node: dict[str, str]
    quarantined_entity_ids: list[str]
    quarantined_relation_ids: list[str]
    rejected_relation_ids: list[str]
    config_digest: str

    def edge_index(self) -> dict[tuple[str, RelationType, str], Edge]:
        return {edge.triple: edge for edge in self.edges}

    def direct_evidence_ids(self) -> set[str]:
        return {
            evidence_id
            for edge in self.edges
            if not edge.derived
            for evidence_id in edge.evidence_ids
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "nodes": [self.nodes[node_id].to_dict() for node_id in sorted(self.nodes)],
            "edges": [
                edge.to_dict()
                for edge in sorted(
                    self.edges,
                    key=lambda e: (e.subject, e.predicate.value, e.object, e.derived),
                )
            ],
            "observation_to_node": dict(sorted(self.observation_to_node.items())),
            "quarantined_entity_ids": sorted(self.quarantined_entity_ids),
            "quarantined_relation_ids": sorted(self.quarantined_relation_ids),
            "rejected_relation_ids": sorted(self.rejected_relation_ids),
            "config_digest": self.config_digest,
        }


def validate_observations(
    entity_observations: Iterable[EntityObservation],
    relation_observations: Iterable[RelationObservation],
) -> None:
    entity_ids: set[str] = set()
    for obs in entity_observations:
        obs.validate()
        if obs.observation_id in entity_ids:
            raise ValueError(f"duplicate entity observation ID: {obs.observation_id}")
        entity_ids.add(obs.observation_id)

    relation_ids: set[str] = set()
    for obs in relation_observations:
        obs.validate()
        if obs.observation_id in relation_ids:
            raise ValueError(f"duplicate relation observation ID: {obs.observation_id}")
        relation_ids.add(obs.observation_id)
        if obs.subject_observation_id not in entity_ids:
            raise ValueError(f"unknown relation subject: {obs.subject_observation_id}")
        if obs.object_observation_id not in entity_ids:
            raise ValueError(f"unknown relation object: {obs.object_observation_id}")
