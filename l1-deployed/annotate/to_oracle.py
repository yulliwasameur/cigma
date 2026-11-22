#!/usr/bin/env python3
"""Turn the adjudicated L1 annotation (out/oracle/*.csv) into the CIGMA oracle format.

Run ONLY after verify_seal.py has confirmed the sealed predictions. Inputs:
  out/oracle/entities.csv, edges.csv, migration_targets.csv   (adjudicated by C)
  out/observations/{entities,relations}.jsonl                  (public observations, never predictions)
Output: out/oracle_cigma/{nodes.jsonl, edges.jsonl, observation_to_truth.json,
        relation_to_truth.json, priorities.json, critical_targets.json}

Mapping rules (fixed before annotation):
  * an observation maps to a truth entity of the same type that shares at least one
    identifier (key and normalized value); strong keys win over aliases; ties -> unmapped;
  * a relation observation maps to the truth edge (subject, predicate, object) of its mapped
    endpoints, if that edge is in the oracle; otherwise it maps to nothing;
  * an oracle edge is marked derived when it follows from other oracle edges through one of
    CIGMA's two declared path rules (service-endpoint-certificate-algorithm, service-component-algorithm).
"""
import csv, json, pathlib, sys

base = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(base.parent / "cigma" / "src"))
from cigma.normalize import normalize_identifiers  # noqa: E402

STRONG = {"certificate_fingerprint", "spki_fingerprint", "purl", "service_uid", "device_serial",
          "algorithm_id", "endpoint_uri", "pipeline_uid", "data_uid"}


def ids_of(text: str) -> dict:
    out = {}
    for part in (text or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return normalize_identifiers(out)


def read_csv(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def main():
    o = base / "out" / "oracle"
    obs = base / "out" / "observations"
    ents = read_csv(o / "entities.csv")
    edges = read_csv(o / "edges.csv")
    targets = read_csv(o / "migration_targets.csv")
    truth = {e["entity_id"].strip(): {"type": e["type"].strip(), "ids": ids_of(e["identifiers"])} for e in ents}

    def match(obs_row):
        strong, alias = set(), set()
        for tid, t in truth.items():
            if t["type"] != obs_row["entity_type"]:
                continue
            for k, v in obs_row["identifiers"].items():
                if t["ids"].get(k) == v:
                    (strong if k in STRONG else alias).add(tid)
        cand = strong or alias
        return next(iter(cand)) if len(cand) == 1 else None

    O = [json.loads(l) for l in open(obs / "entities.jsonl")]
    R = [json.loads(l) for l in open(obs / "relations.jsonl")]
    o2t = {r["observation_id"]: match(r) for r in O}
    E = {(e["subject_id"].strip(), e["predicate"].strip().upper(), e["object_id"].strip()) for e in edges}

    def derived(s, p, ob):
        if p != "USES":
            return False
        ts, to = truth.get(s, {}).get("type"), truth.get(ob, {}).get("type")
        if ts == "service" and to == "algorithm":
            for (a, p1, ep) in E:
                if a == s and p1 == "HOSTS":
                    for (e2, p2, c) in E:
                        if e2 == ep and p2 == "PRESENTS" and (c, "USES", ob) in E:
                            return True
            for (a, p1, comp) in E:
                if a == s and p1 == "USES" and truth.get(comp, {}).get("type") == "software_component" and (comp, "USES", ob) in E:
                    return True
        return False

    out = base / "out" / "oracle_cigma"
    out.mkdir(parents=True, exist_ok=True)
    prio = {t["entity_id"].strip(): int(t["priority"]) for t in targets}
    with open(out / "nodes.jsonl", "w") as f:
        for tid, t in sorted(truth.items()):
            f.write(json.dumps({"truth_id": tid, "entity_type": t["type"], "critical_target": tid in prio,
                                "priority": prio.get(tid, 0)}) + "\n")
    edge_ids = {}
    with open(out / "edges.jsonl", "w") as f:
        for (s, p, ob) in sorted(E):
            eid = f"edge::{s}::{p}::{ob}"
            edge_ids[(s, p, ob)] = eid
            f.write(json.dumps({"edge_id": eid, "subject": s, "predicate": p, "object": ob, "derived": derived(s, p, ob)}) + "\n")
    r2t = {}
    for r in R:
        s, ob = o2t.get(r["subject_observation_id"]), o2t.get(r["object_observation_id"])
        r2t[r["observation_id"]] = edge_ids.get((s, r["predicate"], ob)) if s and ob else None
    json.dump(o2t, open(out / "observation_to_truth.json", "w"), indent=1, sort_keys=True)
    json.dump(r2t, open(out / "relation_to_truth.json", "w"), indent=1, sort_keys=True)
    json.dump({tid: prio.get(tid, 0) for tid in sorted(truth)}, open(out / "priorities.json", "w"), indent=1)
    json.dump(sorted(prio), open(out / "critical_targets.json", "w"), indent=1)
    print(json.dumps({"truth_nodes": len(truth), "truth_edges": len(E),
                      "mapped_observations": sum(v is not None for v in o2t.values()), "observations": len(o2t),
                      "mapped_relations": sum(v is not None for v in r2t.values()), "relations": len(r2t)}))


if __name__ == "__main__":
    main()
