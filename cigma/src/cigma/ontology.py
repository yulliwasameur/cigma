"""Closed CIGMA entity/relation ontology and allow-listed path rules."""

from __future__ import annotations

from dataclasses import dataclass

from .schema import EntityType, RelationType


RELATION_SIGNATURES: dict[RelationType, frozenset[tuple[EntityType, EntityType]]] = {
    RelationType.HOSTS: frozenset({(EntityType.SERVICE, EntityType.ENDPOINT)}),
    RelationType.PRESENTS: frozenset({(EntityType.ENDPOINT, EntityType.CERTIFICATE)}),
    RelationType.USES: frozenset(
        {
            (EntityType.CERTIFICATE, EntityType.ALGORITHM),
            (EntityType.SOFTWARE_COMPONENT, EntityType.ALGORITHM),
            (EntityType.SERVICE, EntityType.SOFTWARE_COMPONENT),
            (EntityType.SERVICE, EntityType.ALGORITHM),
            (EntityType.DEVICE, EntityType.ALGORITHM),
        }
    ),
    RelationType.ISSUED_BY: frozenset({(EntityType.CERTIFICATE, EntityType.CERTIFICATE)}),
    RelationType.DEPENDS_ON: frozenset(
        {
            (EntityType.SERVICE, EntityType.SERVICE),
            (EntityType.SERVICE, EntityType.DEVICE),
        }
    ),
    RelationType.DEPLOYS: frozenset({(EntityType.PIPELINE, EntityType.SERVICE)}),
    RelationType.PROCESSES: frozenset({(EntityType.SERVICE, EntityType.DATA_CLASS)}),
    RelationType.PROTECTS: frozenset(
        {
            (EntityType.ALGORITHM, EntityType.DATA_CLASS),
            (EntityType.CERTIFICATE, EntityType.DATA_CLASS),
        }
    ),
}


@dataclass(frozen=True, slots=True)
class PathRule:
    rule_id: str
    predicates: tuple[RelationType, ...]
    node_types: tuple[EntityType, ...]
    output_predicate: RelationType


PATH_RULES: tuple[PathRule, ...] = (
    PathRule(
        rule_id="HOSTS_o_PRESENTS_o_USES",
        predicates=(RelationType.HOSTS, RelationType.PRESENTS, RelationType.USES),
        node_types=(
            EntityType.SERVICE,
            EntityType.ENDPOINT,
            EntityType.CERTIFICATE,
            EntityType.ALGORITHM,
        ),
        output_predicate=RelationType.USES,
    ),
    PathRule(
        rule_id="USES_o_USES",
        predicates=(RelationType.USES, RelationType.USES),
        node_types=(EntityType.SERVICE, EntityType.SOFTWARE_COMPONENT, EntityType.ALGORITHM),
        output_predicate=RelationType.USES,
    ),
)


def is_valid_signature(
    predicate: RelationType,
    subject_type: EntityType,
    object_type: EntityType,
) -> bool:
    return (subject_type, object_type) in RELATION_SIGNATURES[predicate]


def require_valid_signature(
    predicate: RelationType,
    subject_type: EntityType,
    object_type: EntityType,
) -> None:
    if not is_valid_signature(predicate, subject_type, object_type):
        raise ValueError(
            f"invalid relation signature: {subject_type.value} "
            f"{predicate.value} {object_type.value}"
        )
