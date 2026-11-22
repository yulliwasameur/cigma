"""Poisoning campaign: a malicious source injects k false relations.

The attacker controls one tool inside a source family. It re-reports real entities
(so that it looks consistent with the other sources) and adds k relations that
are type-valid but false. This is the knowledge-graph poisoning setting of ROAR
(Xi et al., USENIX Security 2023) transposed to cryptographic inventories.

Returned oracle maps every re-reported entity to the truth of its original and every
injected relation to ``None``. No oracle is used to build the poisoned observations
beyond choosing pairs that are *not* true edges (the attacker's goal is to add lies).
"""

from __future__ import annotations

import copy
import json
import random
from typing import Any, Mapping, Sequence

from ..ontology import is_valid_signature
from ..schema import EntityObservation, RelationObservation, RelationType, SourceFamily, evidence_digest

ATTACK_PREDICATES = (RelationType.DEPENDS_ON, RelationType.USES, RelationType.PRESENTS, RelationType.ISSUED_BY)


def _clone(obs: EntityObservation, tool: str) -> EntityObservation:
    raw = obs.to_dict()
    raw["observation_id"] = f"{obs.observation_id}~{tool}"
    raw["locator"] = f"tool={tool};{obs.locator}"
    raw["source"] = obs.source.value
    return EntityObservation.from_dict(raw)


def poison(
    entities: Sequence[EntityObservation],
    relations: Sequence[RelationObservation],
    oracle: Mapping[str, Any],
    *,
    k: int,
    seed: int,
    tool: str = "mal",
    quality_range: tuple[float, float] = (0.6, 0.95),
) -> tuple[list[EntityObservation], list[RelationObservation], dict[str, Any], list[str]]:
    rng = random.Random(seed)
    obs_truth = dict(oracle["observation_to_truth"])
    truth_edges = {(str(e["subject"]), str(e["predicate"]), str(e["object"])) for e in oracle["edges"]}
    real = [o for o in entities if obs_truth.get(o.observation_id) is not None]
    real.sort(key=lambda o: o.observation_id)
    out_e = list(entities)
    out_r = list(relations)
    new_oracle = copy.deepcopy(dict(oracle))
    clones: dict[str, EntityObservation] = {}
    injected: list[str] = []
    attempts = 0
    while len(injected) < k and attempts < 5000:
        attempts += 1
        a, b = rng.sample(real, 2)
        pred = rng.choice(ATTACK_PREDICATES)
        if not is_valid_signature(pred, a.entity_type, b.entity_type):
            continue
        ta, tb = obs_truth[a.observation_id], obs_truth[b.observation_id]
        if ta == tb or (ta, pred.value, tb) in truth_edges:
            continue
        for o in (a, b):
            if o.observation_id not in clones:
                c = _clone(o, tool)
                clones[o.observation_id] = c
                out_e.append(c)
                new_oracle["observation_to_truth"][c.observation_id] = obs_truth[o.observation_id]
        key = f"{len(injected)}"
        excerpt = json.dumps({"tool": tool, "claim": key, "s": a.local_key, "p": pred.value, "o": b.local_key},
                             sort_keys=True, separators=(",", ":"))
        rel = RelationObservation(
            observation_id=f"rel-{a.source.value}-poison-{seed}-{key}~{tool}",
            source=a.source,
            subject_observation_id=clones[a.observation_id].observation_id,
            predicate=pred,
            object_observation_id=clones[b.observation_id].observation_id,
            quality=round(rng.uniform(*quality_range), 3),
            collected_at="2026-08-19T12:00:00+00:00",
            locator=f"tool={tool};poison/{key}",
            evidence_excerpt=excerpt,
            evidence_sha256=evidence_digest(excerpt),
        )
        out_r.append(rel)
        new_oracle["relation_to_truth"][rel.observation_id] = None
        injected.append(rel.observation_id)
    return out_e, out_r, new_oracle, injected
