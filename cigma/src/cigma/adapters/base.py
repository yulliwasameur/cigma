"""Source-adapter primitives.

Adapters intentionally terminate at the public observation schema. They do not
perform cross-source entity resolution, ontology inference, or oracle access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Mapping

from ..normalize import normalize_attributes, normalize_identifiers
from ..schema import (
    EntityObservation,
    EntityType,
    RelationObservation,
    RelationType,
    SourceFamily,
    evidence_digest,
)


@dataclass(slots=True)
class AdapterOutput:
    entities: dict[str, EntityObservation] = field(default_factory=dict)
    relations: dict[str, RelationObservation] = field(default_factory=dict)

    def add_entity(self, observation: EntityObservation) -> EntityObservation:
        existing = self.entities.get(observation.observation_id)
        if existing is not None:
            compatible = (
                existing.source == observation.source
                and existing.local_key == observation.local_key
                and existing.entity_type == observation.entity_type
                and dict(existing.identifiers) == dict(observation.identifiers)
            )
            if not compatible:
                raise ValueError(f"conflicting entity observation: {observation.observation_id}")
            return existing
        self.entities[observation.observation_id] = observation
        return observation

    def add_relation(self, observation: RelationObservation) -> RelationObservation:
        existing = self.relations.get(observation.observation_id)
        if existing is not None and existing != observation:
            raise ValueError(f"conflicting relation observation: {observation.observation_id}")
        self.relations[observation.observation_id] = observation
        return observation

    def extend(self, other: "AdapterOutput") -> None:
        for item in other.entities.values():
            self.add_entity(item)
        for item in other.relations.values():
            self.add_relation(item)

    def ordered_entities(self) -> list[EntityObservation]:
        return [self.entities[key] for key in sorted(self.entities)]

    def ordered_relations(self) -> list[RelationObservation]:
        return [self.relations[key] for key in sorted(self.relations)]


class ObservationFactory:
    def __init__(self, source: SourceFamily, collected_at: str) -> None:
        self.source = source
        self.collected_at = collected_at

    def _id(self, kind: str, local_key: str) -> str:
        material = f"{self.source.value}|{kind}|{local_key}".encode("utf-8")
        return f"{kind[:3]}-{self.source.value}-{sha256(material).hexdigest()[:16]}"

    @staticmethod
    def _excerpt(record: Mapping[str, Any]) -> str:
        return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    def entity(
        self,
        *,
        local_key: str,
        entity_type: EntityType,
        identifiers: Mapping[str, Any],
        attributes: Mapping[str, Any] | None = None,
        quality: float = 1.0,
        locator: str,
        evidence_record: Mapping[str, Any] | None = None,
    ) -> EntityObservation:
        normalized_identifiers = normalize_identifiers(identifiers)
        normalized_attributes = normalize_attributes(attributes or {})
        record = evidence_record or {
            "local_key": local_key,
            "entity_type": entity_type.value,
            "identifiers": normalized_identifiers,
            "attributes": normalized_attributes,
        }
        excerpt = self._excerpt(record)
        item = EntityObservation(
            observation_id=self._id("entity", local_key),
            source=self.source,
            local_key=local_key,
            entity_type=entity_type,
            identifiers=normalized_identifiers,
            attributes=normalized_attributes,
            quality=float(quality),
            collected_at=self.collected_at,
            locator=locator,
            evidence_excerpt=excerpt,
            evidence_sha256=evidence_digest(excerpt),
        )
        item.validate()
        return item

    def relation(
        self,
        *,
        local_key: str,
        subject: EntityObservation,
        predicate: RelationType,
        object_: EntityObservation,
        quality: float = 1.0,
        locator: str,
        evidence_record: Mapping[str, Any] | None = None,
    ) -> RelationObservation:
        record = evidence_record or {
            "subject_local_key": subject.local_key,
            "predicate": predicate.value,
            "object_local_key": object_.local_key,
        }
        excerpt = self._excerpt(record)
        item = RelationObservation(
            observation_id=self._id("relation", local_key),
            source=self.source,
            subject_observation_id=subject.observation_id,
            predicate=predicate,
            object_observation_id=object_.observation_id,
            quality=float(quality),
            collected_at=self.collected_at,
            locator=locator,
            evidence_excerpt=excerpt,
            evidence_sha256=evidence_digest(excerpt),
        )
        item.validate()
        return item
