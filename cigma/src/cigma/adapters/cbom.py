"""Code/CBOM adapter."""
from __future__ import annotations
from typing import Any, Iterable, Mapping
from .base import AdapterOutput, ObservationFactory
from ..schema import EntityType, RelationType, SourceFamily


def adapt_cbom_records(component_records: Iterable[Mapping[str,Any]], *, dependency_records: Iterable[Mapping[str,Any]]=(),
                       standalone_algorithms: Iterable[Mapping[str,Any]]=(), standalone_components: Iterable[Mapping[str,Any]]=(),
                       collected_at: str) -> AdapterOutput:
    output=AdapterOutput(); factory=ObservationFactory(SourceFamily.CBOM,collected_at)
    def service(rec: Mapping[str,Any], local_key_field: str="service_local_key"):
        ids={"service_name":rec["service_name"]}
        if rec.get("service_uid"): ids["service_uid"]=rec["service_uid"]
        if rec.get("repository_path"): ids["repository_path"]=rec["repository_path"]
        return output.add_entity(factory.entity(local_key=str(rec[local_key_field]),entity_type=EntityType.SERVICE,identifiers=ids,
            attributes={"language":rec.get("language")},quality=float(rec.get("quality",0.88)),locator=str(rec.get("locator","cbom/records.json")),evidence_record=dict(rec)))
    def component(rec: Mapping[str,Any]):
        return output.add_entity(factory.entity(local_key=str(rec["component_local_key"]),entity_type=EntityType.SOFTWARE_COMPONENT,
            identifiers={"purl":rec["purl"]},attributes={"name":rec.get("component_name"),"version":rec.get("version")},
            quality=float(rec.get("quality",0.88)),locator=str(rec.get("locator","cbom/records.json")),evidence_record=dict(rec)))
    def algorithm(rec: Mapping[str,Any]):
        return output.add_entity(factory.entity(local_key=str(rec["algorithm_local_key"]),entity_type=EntityType.ALGORITHM,
            identifiers={"algorithm_id":rec["algorithm_id"]},attributes={"family":rec.get("algorithm_family")},
            quality=float(rec.get("quality",0.88)),locator=str(rec.get("locator","cbom/records.json")),evidence_record=dict(rec)))
    for index, rec0 in enumerate(component_records):
        r=dict(rec0); r.setdefault("locator",f"cbom/components.json#/{index}")
        svc=service(r); comp=component(r); alg=algorithm(r); q=float(r.get("relation_quality",r.get("quality",0.88)))
        output.add_relation(factory.relation(local_key=str(r.get("service_component_relation_key",f"{svc.local_key}:USES:{comp.local_key}")),
            subject=svc,predicate=RelationType.USES,object_=comp,quality=q,locator=f"{r['locator']}/service_component",evidence_record=r))
        if bool(r.get("emit_component_algorithm_relation",True)):
            output.add_relation(factory.relation(local_key=str(r.get("component_algorithm_relation_key",f"{comp.local_key}:USES:{alg.local_key}")),
                subject=comp,predicate=RelationType.USES,object_=alg,quality=q,locator=f"{r['locator']}/component_algorithm",evidence_record=r))
    for index, rec0 in enumerate(dependency_records):
        r=dict(rec0); r.setdefault("locator",f"cbom/dependencies.json#/{index}")
        subject=service({**r,"service_local_key":r["subject_service_local_key"],"service_name":r["subject_service_name"],
            "service_uid":r.get("subject_service_uid"),"repository_path":r.get("subject_repository_path")})
        object_=service({**r,"service_local_key":r["object_service_local_key"],"service_name":r["object_service_name"],
            "service_uid":r.get("object_service_uid"),"repository_path":r.get("object_repository_path")})
        output.add_relation(factory.relation(local_key=str(r.get("relation_local_key",f"{subject.local_key}:DEPENDS-ON:{object_.local_key}")),
            subject=subject,predicate=RelationType.DEPENDS_ON,object_=object_,quality=float(r.get("relation_quality",r.get("quality",0.88))),
            locator=f"{r['locator']}/dependency",evidence_record=r))
    for index, rec0 in enumerate(standalone_algorithms):
        r=dict(rec0); r.setdefault("locator",f"cbom/algorithms.json#/{index}"); algorithm(r)
    for index, rec0 in enumerate(standalone_components):
        r=dict(rec0); r.setdefault("locator",f"cbom/standalone_components.json#/{index}"); component(r)
    return output
