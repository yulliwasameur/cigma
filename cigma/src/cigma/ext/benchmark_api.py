"""Public benchmark interface: the standard task, submissions, and standard exports.

THE TASK. From the public observations only (`public/entities.jsonl`,
`public/relations.jsonl`), produce (1) a typed cryptographic dependency graph whose
nodes and edges cite observation ids, and (2) a migration order. The hidden oracle
scores entity resolution (pairwise F1, B³), typed-edge F1, unsupported decisions,
MOVR, exposure AUC and NDCG.

A submission is one JSON file:
  {"method": str, "graph": <GraphSnapshot.to_dict()>, "order": [node_id, ...],
   "rankings": optional list of RankingEntry.to_dict()}
Any tool may produce it; CIGMA's own `GraphSnapshot.to_dict()` is already valid.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from ..evaluation import evaluate_method, load_oracle
from ..io import load_observations
from ..schema import Edge, EntityType, GraphSnapshot, Node, RelationType
from ..scoring import RankingEntry
from .ordering import migration_outcomes

SUBMISSION_SCHEMA_VERSION = "cigma-bench-submission-v1"


def graph_from_dict(raw: Mapping[str, Any]) -> GraphSnapshot:
    nodes = {
        n["node_id"]: Node(node_id=n["node_id"], entity_type=EntityType(n["entity_type"]),
                           identifiers=dict(n.get("identifiers", {})), attributes=dict(n.get("attributes", {})),
                           observation_ids=list(n["observation_ids"]), support=float(n.get("support", 1.0)),
                           merge_log=list(n.get("merge_log", [])))
        for n in raw["nodes"]
    }
    edges = [Edge(subject=e["subject"], predicate=RelationType(e["predicate"]), object=e["object"],
                  evidence_ids=list(e["evidence_ids"]), support=float(e.get("support", 1.0)),
                  derived=bool(e.get("derived", False)), rules=list(e.get("rules", [])))
             for e in raw["edges"]]
    obs_to_node = dict(raw.get("observation_to_node") or {oid: n.node_id for n in nodes.values() for oid in n.observation_ids})
    return GraphSnapshot(method=str(raw.get("method", "submission")), nodes=nodes, edges=edges,
                         observation_to_node=obs_to_node,
                         quarantined_entity_ids=list(raw.get("quarantined_entity_ids", [])),
                         quarantined_relation_ids=list(raw.get("quarantined_relation_ids", [])),
                         rejected_relation_ids=list(raw.get("rejected_relation_ids", [])),
                         config_digest=str(raw.get("config_digest", "external")))


def _rankings_from(order: list[str], graph: GraphSnapshot, raw_rankings: list[Mapping[str, Any]] | None) -> list[RankingEntry]:
    if raw_rankings:
        out = []
        for r in raw_rankings:
            out.append(RankingEntry(
                node_id=r["node_id"], entity_type=EntityType(r["entity_type"]),
                service_contexts=list(r.get("service_contexts", [])), impact=dict(r.get("impact", {})),
                lower_impact=dict(r.get("lower_impact", {})), upper_impact=dict(r.get("upper_impact", {})),
                lower_tier=int(r.get("lower_tier", 0)), upper_tier=int(r.get("upper_tier", 0)),
                pareto_front=int(r.get("pareto_front", 0)), evidence_confidence=float(r.get("evidence_confidence", 0)),
                migration_feasibility=r.get("migration_feasibility"), verify=bool(r.get("verify", False)),
                primary_rank=int(r.get("primary_rank", 0)), weighted_rank=int(r.get("weighted_rank", 0)),
                mean_factor_order_rank=int(r.get("mean_factor_order_rank", 0))))
        return out
    entries = []
    for i, nid in enumerate(order, start=1):
        if nid not in graph.nodes:
            continue
        entries.append(RankingEntry(node_id=nid, entity_type=graph.nodes[nid].entity_type, service_contexts=[],
                                    impact={}, lower_impact={k: 0.0 for k in "QHCBX"}, upper_impact={k: 0.0 for k in "QHCBX"},
                                    lower_tier=0, upper_tier=0, pareto_front=0, evidence_confidence=0.0,
                                    migration_feasibility=None, verify=False, primary_rank=i, weighted_rank=i,
                                    mean_factor_order_rank=i))
    return entries


def evaluate_submission(submission_path: str | Path, data_dir: str | Path) -> dict[str, Any]:
    sub = json.loads(Path(submission_path).read_text())
    data = Path(data_dir)
    ents, rels = load_observations(data / "public" / "entities.jsonl", data / "public" / "relations.jsonl")
    oracle = load_oracle(data / "oracle")
    graph = graph_from_dict(sub["graph"])
    valid_e = {o.observation_id for o in ents}
    valid_r = {r.observation_id for r in rels}
    unsupported_nodes = sum(1 for n in graph.nodes.values() if not set(n.observation_ids) <= valid_e or not n.observation_ids)
    unsupported_edges = sum(1 for e in graph.edges if not set(e.evidence_ids) <= valid_r or not e.evidence_ids)
    order = list(sub.get("order") or [])
    rankings = _rankings_from(order, graph, sub.get("rankings"))
    res = evaluate_method(graph, rankings, oracle, entity_observations=ents, relation_observations=rels)
    mig = migration_outcomes(order or [r.node_id for r in sorted(rankings, key=lambda r: r.primary_rank)],
                             res.node_truth_map, oracle)
    m = res.metrics
    return {"schema": SUBMISSION_SCHEMA_VERSION, "method": sub.get("method", "unknown"),
            "pairwise_f1": m["pairwise_f1"], "b3_f1": m["b3_f1"], "asset_f1": m["asset_f1"],
            "typed_edge_f1": m["typed_edge_f1"], "edge_fp_rate": m["edge_fp_rate"],
            "unsupported_nodes": unsupported_nodes, "unsupported_edges": unsupported_edges,
            "ndcg_at_10": m.get("ndcg_at_10"), **{k: mig[k] for k in ("movr", "exposure_auc")}}


# ------------------------------------------------------------------ standard exports

def to_cyclonedx(graph: GraphSnapshot) -> dict[str, Any]:
    """CycloneDX 1.6 BOM with cryptographic-asset components and dependencies (a CBOM view)."""

    comps, deps = [], {}
    for nid, n in sorted(graph.nodes.items()):
        c: dict[str, Any] = {"bom-ref": nid, "name": next(iter(sum(n.identifiers.values(), [])), nid)}
        if n.entity_type == EntityType.ALGORITHM:
            c.update(type="cryptographic-asset", cryptoProperties={"assetType": "algorithm",
                     "algorithmProperties": {"primitive": "unknown"}, "oid": None})
        elif n.entity_type == EntityType.CERTIFICATE:
            c.update(type="cryptographic-asset", cryptoProperties={"assetType": "certificate"})
        elif n.entity_type == EntityType.SOFTWARE_COMPONENT:
            c.update(type="library")
        else:
            c.update(type="application" if n.entity_type == EntityType.SERVICE else "data" if n.entity_type == EntityType.DATA_CLASS else "device")
        c["properties"] = [{"name": "cigma:entity_type", "value": n.entity_type.value},
                           {"name": "cigma:support", "value": f"{n.support:.4f}"},
                           {"name": "cigma:evidence", "value": ",".join(n.observation_ids)}]
        comps.append(c)
    for e in graph.edges:
        deps.setdefault(e.subject, set()).add(e.object)
    return {"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
            "metadata": {"tools": {"components": [{"type": "application", "name": "cigma"}]}},
            "components": comps,
            "dependencies": [{"ref": k, "dependsOn": sorted(v)} for k, v in sorted(deps.items())]}


def to_prov_jsonld(graph: GraphSnapshot) -> dict[str, Any]:
    """W3C PROV-O (JSON-LD): each node/edge is a prov:Entity derived from observation entities."""

    g: list[dict[str, Any]] = []
    for nid, n in sorted(graph.nodes.items()):
        g.append({"@id": f"cigma:{nid}", "@type": "prov:Entity",
                  "prov:wasDerivedFrom": [{"@id": f"obs:{o}"} for o in n.observation_ids]})
    for i, e in enumerate(graph.edges):
        g.append({"@id": f"cigma:edge/{i}", "@type": ["prov:Entity", f"cigma:{e.predicate.value}"],
                  "cigma:subject": {"@id": f"cigma:{e.subject}"}, "cigma:object": {"@id": f"cigma:{e.object}"},
                  "prov:wasDerivedFrom": [{"@id": f"obs:{o}"} for o in e.evidence_ids],
                  "prov:wasGeneratedBy": {"@id": "cigma:activity/derivation" if e.derived else "cigma:activity/direct"}})
    return {"@context": {"prov": "http://www.w3.org/ns/prov#", "cigma": "https://w3id.org/cigma#",
                         "obs": "https://w3id.org/cigma/observation/"}, "@graph": g}
