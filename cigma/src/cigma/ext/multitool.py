"""Several disagreeing generators inside one source family.

Empirical studies show that CBOM/SBOM generators disagree on the same code
(BF-CBOM, ICPC 2026; Muneza et al., SANER 2025). This module builds a controlled
version of that situation on the fixture so that fusion strategies can be compared
against the evaluator-only oracle:

- ``tool_a``: complete and correct (a copy of the family's observations);
- ``tool_b``: misses part of the items and adds plausible but false items;
- ``tool_c``: copies ``tool_b`` (same false items), i.e. a dependent witness.

A naive majority vote then accepts the false items (two votes), which is exactly
the failure that dependence-aware learned reliabilities should avoid.
Observation ids get a tool suffix and locators start with ``tool=<name>;`` so that
``reliability_key`` can tell the tools apart. The oracle maps every copy to the same
truth as its original and every injected item to ``None``.
"""

from __future__ import annotations

import copy
import json
import random
from collections import defaultdict
from typing import Any, Mapping, Sequence

from ..schema import (
    EntityObservation,
    EntityType,
    RelationObservation,
    RelationType,
    SourceFamily,
    evidence_digest,
)


def _clone_entity(obs: EntityObservation, tool: str, quality: float | None = None) -> EntityObservation:
    raw = obs.to_dict()
    raw["observation_id"] = f"{obs.observation_id}~{tool}"
    raw["locator"] = f"tool={tool};{obs.locator}"
    if quality is not None:
        raw["quality"] = quality
    return EntityObservation.from_dict(raw)


def _clone_relation(obs: RelationObservation, tool: str, quality: float | None = None) -> RelationObservation:
    raw = obs.to_dict()
    raw["observation_id"] = f"{obs.observation_id}~{tool}"
    raw["subject_observation_id"] = f"{obs.subject_observation_id}~{tool}"
    raw["object_observation_id"] = f"{obs.object_observation_id}~{tool}"
    raw["locator"] = f"tool={tool};{obs.locator}"
    if quality is not None:
        raw["quality"] = quality
    return RelationObservation.from_dict(raw)


def _fake_entity(
    tool: str, local_key: str, entity_type: EntityType, identifiers: dict[str, str], quality: float
) -> EntityObservation:
    record = {"tool": tool, "local_key": local_key, **identifiers}
    excerpt = json.dumps(record, sort_keys=True, separators=(",", ":"))
    return EntityObservation(
        observation_id=f"ent-cbom-fake-{local_key}~{tool}",
        source=SourceFamily.CBOM,
        local_key=local_key,
        entity_type=entity_type,
        identifiers=identifiers,
        attributes={},
        quality=quality,
        collected_at="2026-08-19T12:00:00+00:00",
        locator=f"tool={tool};cbom/fake/{local_key}",
        evidence_excerpt=excerpt,
        evidence_sha256=evidence_digest(excerpt),
    )


def _fake_relation(
    tool: str, key: str, subject_id: str, predicate: RelationType, object_id: str, quality: float
) -> RelationObservation:
    excerpt = json.dumps({"tool": tool, "claim": key}, sort_keys=True, separators=(",", ":"))
    return RelationObservation(
        observation_id=f"rel-cbom-fake-{key}~{tool}",
        source=SourceFamily.CBOM,
        subject_observation_id=subject_id,
        predicate=predicate,
        object_observation_id=object_id,
        quality=quality,
        collected_at="2026-08-19T12:00:00+00:00",
        locator=f"tool={tool};cbom/fake/{key}",
        evidence_excerpt=excerpt,
        evidence_sha256=evidence_digest(excerpt),
    )


def build_tool_views(
    entities: Sequence[EntityObservation],
    relations: Sequence[RelationObservation],
    oracle: Mapping[str, Any],
    *,
    seed: int = 20261121,
    drop_fraction: float = 0.4,
    family: SourceFamily = SourceFamily.CBOM,
    noisy_quality: float = 0.86,
) -> tuple[list[EntityObservation], list[RelationObservation], dict[str, Any], dict[str, Any]]:
    rng = random.Random(seed)
    fam_e = [o for o in entities if o.source == family]
    fam_r = [o for o in relations if o.source == family]
    other_e = [o for o in entities if o.source != family]
    other_r = [o for o in relations if o.source != family]
    obs_truth = dict(oracle["observation_to_truth"])
    rel_truth = dict(oracle["relation_to_truth"])

    out_e: list[EntityObservation] = list(other_e)
    out_r: list[RelationObservation] = list(other_r)
    new_obs_truth = {k: v for k, v in obs_truth.items() if not any(o.observation_id == k for o in fam_e)}
    new_rel_truth = {k: v for k, v in rel_truth.items() if not any(o.observation_id == k for o in fam_r)}

    # tool_a: complete and correct
    for obs in fam_e:
        c = _clone_entity(obs, "tool_a")
        out_e.append(c)
        new_obs_truth[c.observation_id] = obs_truth.get(obs.observation_id)
    for rel in fam_r:
        c = _clone_relation(rel, "tool_a")
        out_r.append(c)
        new_rel_truth[c.observation_id] = rel_truth.get(rel.observation_id)

    # tool_b: partial + false items; tool_c copies tool_b
    kept = sorted(fam_e, key=lambda o: o.observation_id)
    rng.shuffle(kept)
    kept_ids = {o.observation_id for o in kept[int(round(drop_fraction * len(kept))) :]}
    services = sorted(
        (o for o in fam_e if o.entity_type == EntityType.SERVICE and o.observation_id in kept_ids),
        key=lambda o: o.observation_id,
    )
    algorithms = sorted(
        (o for o in fam_e if o.entity_type == EntityType.ALGORITHM and o.observation_id in kept_ids),
        key=lambda o: o.observation_id,
    )
    injected: dict[str, list[str]] = {"entities": [], "relations": []}
    for tool in ("tool_b", "tool_c"):
        for obs in fam_e:
            if obs.observation_id in kept_ids:
                c = _clone_entity(obs, tool, noisy_quality)
                out_e.append(c)
                new_obs_truth[c.observation_id] = obs_truth.get(obs.observation_id)
        for rel in fam_r:
            if rel.subject_observation_id in kept_ids and rel.object_observation_id in kept_ids:
                c = _clone_relation(rel, tool, noisy_quality)
                out_r.append(c)
                new_rel_truth[c.observation_id] = rel_truth.get(rel.observation_id)
        fake = _fake_entity(
            tool, "fake_comp", EntityType.SOFTWARE_COMPONENT,
            {"purl": "pkg:npm/legacy-crypto-shim@0.9.1"}, noisy_quality,
        )
        out_e.append(fake)
        new_obs_truth[fake.observation_id] = None
        injected["entities"].append(fake.observation_id)
        if services:
            r1 = _fake_relation(
                tool, "svc_uses_fake", f"{services[0].observation_id}~{tool}",
                RelationType.USES, fake.observation_id, noisy_quality,
            )
            out_r.append(r1)
            new_rel_truth[r1.observation_id] = None
            injected["relations"].append(r1.observation_id)
        if algorithms:
            r2 = _fake_relation(
                tool, "fake_uses_alg", fake.observation_id, RelationType.USES,
                f"{algorithms[0].observation_id}~{tool}", noisy_quality,
            )
            out_r.append(r2)
            new_rel_truth[r2.observation_id] = None
            injected["relations"].append(r2.observation_id)
        if len(services) >= 2:
            r3 = _fake_relation(
                tool, "fake_depends", f"{services[-1].observation_id}~{tool}",
                RelationType.DEPENDS_ON, f"{services[0].observation_id}~{tool}", noisy_quality,
            )
            out_r.append(r3)
            new_rel_truth[r3.observation_id] = None
            injected["relations"].append(r3.observation_id)

    new_oracle = copy.deepcopy(dict(oracle))
    new_oracle["observation_to_truth"] = new_obs_truth
    new_oracle["relation_to_truth"] = new_rel_truth
    info = {
        "tools": ["tool_a", "tool_b", "tool_c"],
        "kept_fraction_tool_b": 1 - drop_fraction,
        "injected": injected,
        "family": family.value,
    }
    return out_e, out_r, new_oracle, info


def _identity(obs: EntityObservation) -> tuple[str, tuple[tuple[str, str], ...]]:
    return obs.entity_type.value, tuple(sorted((k, str(v)) for k, v in obs.identifiers.items()))


def majority_vote_filter(
    entities: Sequence[EntityObservation],
    relations: Sequence[RelationObservation],
    *,
    min_votes: int = 2,
) -> tuple[list[EntityObservation], list[RelationObservation]]:
    """Keep a tool-tagged item only if at least ``min_votes`` tools report it."""

    def tool_of(obs: Any) -> str | None:
        loc = str(obs.locator)
        return loc[5:].split(";", 1)[0] if loc.startswith("tool=") else None

    by_id = {o.observation_id: o for o in entities}
    votes: dict[Any, set[str]] = defaultdict(set)
    for o in entities:
        t = tool_of(o)
        if t:
            votes[_identity(o)].add(t)
    keep_e = [o for o in entities if tool_of(o) is None or len(votes[_identity(o)]) >= min_votes]
    kept_ids = {o.observation_id for o in keep_e}
    rvotes: dict[Any, set[str]] = defaultdict(set)

    def rkey(r: RelationObservation) -> Any:
        return (_identity(by_id[r.subject_observation_id]), r.predicate.value, _identity(by_id[r.object_observation_id]))

    for r in relations:
        t = tool_of(r)
        if t and r.subject_observation_id in by_id and r.object_observation_id in by_id:
            rvotes[rkey(r)].add(t)
    keep_r = [
        r for r in relations
        if r.subject_observation_id in kept_ids and r.object_observation_id in kept_ids
        and (tool_of(r) is None or len(rvotes[rkey(r)]) >= min_votes)
    ]
    return keep_e, keep_r


def restrict_to_tool(
    entities: Sequence[EntityObservation], relations: Sequence[RelationObservation], tool: str
) -> tuple[list[EntityObservation], list[RelationObservation]]:
    def ok(obs: Any) -> bool:
        loc = str(obs.locator)
        return not loc.startswith("tool=") or loc.startswith(f"tool={tool};")

    e = [o for o in entities if ok(o)]
    ids = {o.observation_id for o in e}
    r = [x for x in relations if ok(x) and x.subject_observation_id in ids and x.object_observation_id in ids]
    return e, r
