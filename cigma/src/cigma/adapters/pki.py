"""PKI inventory adapter."""
from __future__ import annotations
from typing import Any, Iterable, Mapping
from .base import AdapterOutput, ObservationFactory
from ..schema import EntityType, RelationType, SourceFamily


def adapt_pki_records(records: Iterable[Mapping[str, Any]], *, collected_at: str, extra_certificates: Iterable[Mapping[str, Any]]=()) -> AdapterOutput:
    output=AdapterOutput(); factory=ObservationFactory(SourceFamily.PKI,collected_at)
    def cert_entity(rec: Mapping[str,Any], key: str, locator: str):
        return output.add_entity(factory.entity(local_key=key, entity_type=EntityType.CERTIFICATE,
            identifiers={"certificate_fingerprint":rec["certificate_fingerprint"]},
            attributes={"subject":rec.get("subject"),"key_bits":rec.get("key_bits"),"rotation_days":rec.get("rotation_days")},
            quality=float(rec.get("quality",0.97)), locator=locator, evidence_record=dict(rec)))
    for index, record0 in enumerate(records):
        r=dict(record0); base=str(r.get("locator",f"pki/certificates.json#/{index}"))
        cert=cert_entity(r,str(r["certificate_local_key"]),f"{base}/certificate")
        issuer=cert_entity({"certificate_fingerprint":r["issuer_fingerprint"],"subject":r.get("issuer_subject","CN=CIGMA Root"),
            "key_bits":r.get("issuer_key_bits",4096),"quality":r.get("quality",0.97)},str(r["issuer_local_key"]),f"{base}/issuer")
        alg=output.add_entity(factory.entity(local_key=str(r["algorithm_local_key"]), entity_type=EntityType.ALGORITHM,
            identifiers={"algorithm_id":r["algorithm_id"]}, attributes={"family":r.get("algorithm_family")},
            quality=float(r.get("quality",0.97)), locator=f"{base}/algorithm", evidence_record=r))
        rq=float(r.get("relation_quality",r.get("quality",0.97)))
        output.add_relation(factory.relation(local_key=f"{cert.local_key}:USES:{alg.local_key}",subject=cert,predicate=RelationType.USES,
            object_=alg,quality=rq,locator=f"{base}/algorithm_relation",evidence_record=r))
        output.add_relation(factory.relation(local_key=f"{cert.local_key}:ISSUED-BY:{issuer.local_key}",subject=cert,predicate=RelationType.ISSUED_BY,
            object_=issuer,quality=rq,locator=f"{base}/issuer_relation",evidence_record=r))
    for index, rec0 in enumerate(extra_certificates):
        rec=dict(rec0); cert_entity(rec,str(rec["certificate_local_key"]),str(rec.get("locator",f"pki/extras.json#/{index}")))
    return output
