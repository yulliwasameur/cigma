"""Operational-technology inventory adapter."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .base import AdapterOutput, ObservationFactory
from ..schema import EntityType, RelationType, SourceFamily


def adapt_ot_records(
    records: Iterable[Mapping[str, Any]],
    *,
    collected_at: str,
) -> AdapterOutput:
    """Convert OT gateway/device records to CIGMA observations.

    The optional ``distractor_device_*`` fields intentionally model a
    low-quality, false inventory link used by CIGMA-Lab's quality-gate test.
    """

    output = AdapterOutput()
    factory = ObservationFactory(SourceFamily.OT, collected_at)

    for index, raw in enumerate(records):
        record = dict(raw)
        base = str(record.get("locator", f"ot/inventory.json#/{index}"))
        quality = float(record.get("quality", 0.86))
        relation_quality = float(record.get("relation_quality", quality))

        service_ids: dict[str, Any] = {"service_name": record["service_name"]}
        if record.get("service_uid"):
            service_ids["service_uid"] = record["service_uid"]
        service = output.add_entity(
            factory.entity(
                local_key=str(record["service_local_key"]),
                entity_type=EntityType.SERVICE,
                identifiers=service_ids,
                attributes={
                    "criticality": record.get("criticality"),
                    "migration_time_years": record.get("migration_time_years"),
                    "agility": record.get("agility"),
                },
                quality=quality,
                locator=f"{base}/service",
                evidence_record=record,
            )
        )

        endpoint_ids: dict[str, Any] = {}
        if record.get("endpoint_uri"):
            endpoint_ids["endpoint_uri"] = record["endpoint_uri"]
        if record.get("hostname"):
            endpoint_ids["hostname"] = record["hostname"]
        endpoint = output.add_entity(
            factory.entity(
                local_key=str(record["endpoint_local_key"]),
                entity_type=EntityType.ENDPOINT,
                identifiers=endpoint_ids,
                attributes={"protocol": record.get("protocol", "MQTT/TLS")},
                quality=quality,
                locator=f"{base}/endpoint",
                evidence_record=record,
            )
        )

        device = output.add_entity(
            factory.entity(
                local_key=str(record["device_local_key"]),
                entity_type=EntityType.DEVICE,
                identifiers={"device_serial": record["device_serial"]},
                attributes={
                    "model": record.get("device_model"),
                    "firmware_constraint": record.get("firmware_constraint"),
                },
                quality=quality,
                locator=f"{base}/device",
                evidence_record=record,
            )
        )

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
                quality=relation_quality,
                locator=f"{base}/hosts",
                evidence_record=record,
            )
        )
        output.add_relation(
            factory.relation(
                local_key=str(
                    record.get(
                        "device_relation_key",
                        f"{service.local_key}:DEPENDS-ON:{device.local_key}",
                    )
                ),
                subject=service,
                predicate=RelationType.DEPENDS_ON,
                object_=device,
                quality=relation_quality,
                locator=f"{base}/device-dependency",
                evidence_record=record,
            )
        )

        if record.get("distractor_device_local_key"):
            distractor = output.add_entity(
                factory.entity(
                    local_key=str(record["distractor_device_local_key"]),
                    entity_type=EntityType.DEVICE,
                    identifiers={
                        "device_serial": record.get(
                            "distractor_device_serial", "UNKNOWN-DISTRACTOR"
                        )
                    },
                    attributes={"unverified": True},
                    quality=float(record.get("distractor_quality", 0.2)),
                    locator=f"{base}/unverified-device",
                    evidence_record=record,
                )
            )
            output.add_relation(
                factory.relation(
                    local_key=str(
                        record.get(
                            "distractor_relation_key",
                            f"{service.local_key}:DEPENDS-ON:{distractor.local_key}",
                        )
                    ),
                    subject=service,
                    predicate=RelationType.DEPENDS_ON,
                    object_=distractor,
                    quality=float(record.get("distractor_quality", 0.2)),
                    locator=f"{base}/unverified-device-dependency",
                    evidence_record=record,
                )
            )

    return output
