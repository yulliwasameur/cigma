"""CMDB/service-catalog adapter."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .base import AdapterOutput, ObservationFactory
from ..schema import EntityObservation, EntityType, RelationType, SourceFamily


def adapt_cmdb_records(
    service_records: Iterable[Mapping[str, Any]],
    *,
    dependencies: Iterable[Mapping[str, Any]] = (),
    extra_relations: Iterable[Mapping[str, Any]] = (),
    collected_at: str,
) -> AdapterOutput:
    """Convert service-catalog/CMDB rows into public CIGMA observations.

    A service row can optionally expose one endpoint and one processed data
    class. Dependencies and deliberately low-quality extra relations are passed
    separately so that the adapter remains useful for real source exports.
    """

    output = AdapterOutput()
    factory = ObservationFactory(SourceFamily.CMDB, collected_at)
    entities_by_local_key: dict[str, EntityObservation] = {}

    def add_service(record: Mapping[str, Any]) -> EntityObservation:
        local_key = str(record["service_local_key"])
        identifiers: dict[str, Any] = {"service_name": record["service_name"]}
        if record.get("service_uid"):
            identifiers["service_uid"] = record["service_uid"]
        if record.get("deployment_name"):
            identifiers["deployment_name"] = record["deployment_name"]
        attributes = {
            "criticality": record.get("criticality"),
            "exposure": record.get("exposure"),
            "migration_time_years": record.get("migration_time_years"),
            "data_lifetime_years": record.get("data_lifetime_years"),
            "agility": record.get("agility"),
            "owner": record.get("owner"),
        }
        item = output.add_entity(
            factory.entity(
                local_key=local_key,
                entity_type=EntityType.SERVICE,
                identifiers=identifiers,
                attributes=attributes,
                quality=float(record.get("quality", 0.94)),
                locator=str(record.get("locator", "cmdb/services.json")),
                evidence_record=dict(record),
            )
        )
        entities_by_local_key[local_key] = item
        return item

    def add_endpoint(record: Mapping[str, Any]) -> EntityObservation:
        local_key = str(record["endpoint_local_key"])
        identifiers: dict[str, Any] = {}
        if record.get("endpoint_uri"):
            identifiers["endpoint_uri"] = record["endpoint_uri"]
        if record.get("hostname"):
            identifiers["hostname"] = record["hostname"]
        item = output.add_entity(
            factory.entity(
                local_key=local_key,
                entity_type=EntityType.ENDPOINT,
                identifiers=identifiers,
                attributes={"exposure": record.get("exposure")},
                quality=float(record.get("quality", 0.94)),
                locator=f"{record.get('locator', 'cmdb/services.json')}/endpoint",
                evidence_record=dict(record),
            )
        )
        entities_by_local_key[local_key] = item
        return item

    def add_data(record: Mapping[str, Any]) -> EntityObservation:
        local_key = str(record["data_local_key"])
        identifiers: dict[str, Any] = {"data_name": record["data_name"]}
        if record.get("data_uid"):
            identifiers["data_uid"] = record["data_uid"]
        item = output.add_entity(
            factory.entity(
                local_key=local_key,
                entity_type=EntityType.DATA_CLASS,
                identifiers=identifiers,
                attributes={"retention_years": record.get("retention_years")},
                quality=float(record.get("quality", 0.94)),
                locator=f"{record.get('locator', 'cmdb/services.json')}/data",
                evidence_record=dict(record),
            )
        )
        entities_by_local_key[local_key] = item
        return item

    for index, raw in enumerate(service_records):
        record = dict(raw)
        record.setdefault("locator", f"cmdb/services.json#/{index}")
        service = add_service(record)
        q = float(record.get("relation_quality", record.get("quality", 0.94)))

        if record.get("endpoint_local_key"):
            endpoint = add_endpoint(record)
            output.add_relation(
                factory.relation(
                    local_key=str(
                        record.get(
                            "hosts_relation_key",
                            f"{service.local_key}:HOSTS:{endpoint.local_key}",
                        )
                    ),
                    subject=service,
                    predicate=RelationType.HOSTS,
                    object_=endpoint,
                    quality=q,
                    locator=f"{record['locator']}/hosts",
                    evidence_record=record,
                )
            )

        if record.get("data_local_key"):
            data = add_data(record)
            output.add_relation(
                factory.relation(
                    local_key=str(
                        record.get(
                            "processes_relation_key",
                            f"{service.local_key}:PROCESSES:{data.local_key}",
                        )
                    ),
                    subject=service,
                    predicate=RelationType.PROCESSES,
                    object_=data,
                    quality=q,
                    locator=f"{record['locator']}/processes",
                    evidence_record=record,
                )
            )

    for index, raw in enumerate(dependencies):
        record = dict(raw)
        record.setdefault("locator", f"cmdb/dependencies.json#/{index}")
        subject_key = str(record["subject_service_local_key"])
        object_key = str(record["object_service_local_key"])
        if subject_key not in entities_by_local_key or object_key not in entities_by_local_key:
            raise ValueError(
                f"CMDB dependency references unknown service: {subject_key!r} -> {object_key!r}"
            )
        subject = entities_by_local_key[subject_key]
        object_ = entities_by_local_key[object_key]
        output.add_relation(
            factory.relation(
                local_key=str(
                    record.get(
                        "relation_local_key",
                        f"{subject.local_key}:DEPENDS-ON:{object_.local_key}",
                    )
                ),
                subject=subject,
                predicate=RelationType.DEPENDS_ON,
                object_=object_,
                quality=float(record.get("relation_quality", record.get("quality", 0.94))),
                locator=str(record["locator"]),
                evidence_record=record,
            )
        )

    for index, raw in enumerate(extra_relations):
        record = dict(raw)
        record.setdefault("locator", f"cmdb/extra-relations.json#/{index}")
        subject_key = str(record["subject_local_key"])
        object_key = str(record["object_local_key"])
        if subject_key not in entities_by_local_key or object_key not in entities_by_local_key:
            raise ValueError(
                f"CMDB extra relation references unknown entity: {subject_key!r} -> {object_key!r}"
            )
        predicate = RelationType(str(record["predicate"]))
        subject = entities_by_local_key[subject_key]
        object_ = entities_by_local_key[object_key]
        output.add_relation(
            factory.relation(
                local_key=str(
                    record.get(
                        "relation_local_key",
                        f"{subject.local_key}:{predicate.value}:{object_.local_key}",
                    )
                ),
                subject=subject,
                predicate=predicate,
                object_=object_,
                quality=float(record.get("relation_quality", record.get("quality", 0.94))),
                locator=str(record["locator"]),
                evidence_record=record,
            )
        )

    return output
