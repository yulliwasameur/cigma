"""TLS scan adapter."""

from __future__ import annotations
from typing import Any, Iterable, Mapping
from .base import AdapterOutput, ObservationFactory
from ..schema import EntityType, RelationType, SourceFamily


def adapt_tls_records(records: Iterable[Mapping[str, Any]], *, collected_at: str) -> AdapterOutput:
    output = AdapterOutput(); factory = ObservationFactory(SourceFamily.TLS, collected_at)
    for index, record0 in enumerate(records):
        record = dict(record0); base = str(record.get("locator", f"tls/records.json#/{index}")); q=float(record.get("quality",0.98))
        ep = output.add_entity(factory.entity(local_key=str(record["endpoint_local_key"]), entity_type=EntityType.ENDPOINT,
            identifiers={"endpoint_uri":record["endpoint_uri"], **({"hostname":record["hostname"]} if record.get("hostname") else {})},
            attributes={"protocol":record.get("protocol","TLS1.3"),"exposure":record.get("exposure")}, quality=q, locator=f"{base}/endpoint", evidence_record=record))
        cert = output.add_entity(factory.entity(local_key=str(record["certificate_local_key"]), entity_type=EntityType.CERTIFICATE,
            identifiers={"certificate_fingerprint":record["certificate_fingerprint"]}, attributes={"key_bits":record.get("key_bits")},
            quality=q, locator=f"{base}/certificate", evidence_record=record))
        alg = None
        if bool(record.get("emit_algorithm_entity", True)):
            alg = output.add_entity(factory.entity(local_key=str(record["algorithm_local_key"]), entity_type=EntityType.ALGORITHM,
                identifiers={"algorithm_id":record["algorithm_id"]}, attributes={"family":record.get("algorithm_family")},
                quality=q, locator=f"{base}/algorithm", evidence_record=record))
        output.add_relation(factory.relation(local_key=f"{ep.local_key}:PRESENTS:{cert.local_key}", subject=ep,
            predicate=RelationType.PRESENTS, object_=cert, quality=float(record.get("relation_quality",q)),
            locator=f"{base}/presented_certificate", evidence_record=record))
        if bool(record.get("emit_algorithm_relation", True)):
            if alg is None: raise ValueError("TLS algorithm relation requested without algorithm entity")
            output.add_relation(factory.relation(local_key=f"{cert.local_key}:USES:{alg.local_key}", subject=cert,
                predicate=RelationType.USES, object_=alg, quality=float(record.get("relation_quality",q)),
                locator=f"{base}/public_key_algorithm", evidence_record=record))
    return output
