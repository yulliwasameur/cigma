"""CI/CD deployment adapter."""
from __future__ import annotations
from typing import Any, Iterable, Mapping
from .base import AdapterOutput, ObservationFactory
from ..schema import EntityType, RelationType, SourceFamily


def adapt_cicd_records(records: Iterable[Mapping[str,Any]], *, extra_pipelines: Iterable[Mapping[str,Any]]=(), collected_at: str) -> AdapterOutput:
    output=AdapterOutput(); factory=ObservationFactory(SourceFamily.CICD,collected_at)
    def pipeline(rec: Mapping[str,Any], key: str):
        return output.add_entity(factory.entity(local_key=key,entity_type=EntityType.PIPELINE,identifiers={"pipeline_uid":rec["pipeline_uid"]},
            attributes={"platform":rec.get("platform","github-actions")},quality=float(rec.get("quality",0.91)),
            locator=str(rec.get("locator","cicd/deployments.json")),evidence_record=dict(rec)))
    def service(rec: Mapping[str,Any], key: str):
        ids={"service_name":rec["service_name"]}
        if rec.get("service_uid"): ids["service_uid"]=rec["service_uid"]
        if rec.get("deployment_name"): ids["deployment_name"]=rec["deployment_name"]
        return output.add_entity(factory.entity(local_key=key,entity_type=EntityType.SERVICE,identifiers=ids,attributes={"image":rec.get("image")},
            quality=float(rec.get("quality",0.91)),locator=str(rec.get("locator","cicd/deployments.json")),evidence_record=dict(rec)))
    for index, rec0 in enumerate(records):
        r=dict(rec0); r.setdefault("locator",f"cicd/deployments.json#/{index}")
        pipe=pipeline(r,str(r["pipeline_local_key"])); svc=service(r,str(r["service_local_key"]))
        output.add_relation(factory.relation(local_key=str(r.get("relation_local_key",f"{pipe.local_key}:DEPLOYS:{svc.local_key}")),subject=pipe,
            predicate=RelationType.DEPLOYS,object_=svc,quality=float(r.get("relation_quality",r.get("quality",0.91))),locator=f"{r['locator']}/deployment",evidence_record=r))
    for index, rec0 in enumerate(extra_pipelines):
        r=dict(rec0); r.setdefault("locator",f"cicd/extra_pipelines.json#/{index}"); pipeline(r,str(r["pipeline_local_key"]))
    return output
