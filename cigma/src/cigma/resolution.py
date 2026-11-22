"""Stable, oracle-free entity resolution and attribute fusion."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
import math
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .normalize import normalize_identifier
from .schema import EntityObservation, EntityType, Node, SourceFamily


class UnionFind:
    def __init__(self, items: Iterable[str]) -> None:
        self.parent = {item: item for item in items}
        self.rank = {item: 0 for item in items}

    def find(self, item: str) -> str:
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, left: str, right: str) -> str:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left == root_right:
            return root_left
        rank_left = self.rank[root_left]
        rank_right = self.rank[root_right]
        if rank_left < rank_right or (rank_left == rank_right and root_left > root_right):
            root_left, root_right = root_right, root_left
            rank_left, rank_right = rank_right, rank_left
        self.parent[root_right] = root_left
        if rank_left == rank_right:
            self.rank[root_left] += 1
        return root_left

    def groups(self) -> list[list[str]]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for item in sorted(self.parent):
            grouped[self.find(item)].append(item)
        return [grouped[root] for root in sorted(grouped)]


@dataclass(slots=True)
class ResolutionResult:
    nodes: dict[str, Node]
    observation_to_node: dict[str, str]
    quarantined_observation_ids: list[str]
    merge_log: list[dict[str, Any]]


DEFAULT_STRONG_KEYS = (
    "certificate_fingerprint",
    "spki_fingerprint",
    "purl",
    "service_uid",
    "device_serial",
    "algorithm_id",
    "endpoint_uri",
    "pipeline_uid",
    "data_uid",
)

DEFAULT_ALIAS_KEYS = (
    "service_name",
    "hostname",
    "repository_path",
    "deployment_name",
)


def reliability_key(obs: Any) -> str:
    """Reliability key of an observation: ``source`` or ``source:tool``.

    A locator that starts with ``tool=<name>;`` marks which concrete tool produced
    the observation (for example several CBOM generators in one source family).
    """

    locator = str(getattr(obs, "locator", ""))
    if locator.startswith("tool="):
        tool = locator[5:].split(";", 1)[0]
        if tool:
            return f"{obs.source.value}:{tool}"
    return obs.source.value


def lookup_reliability(obs: Any, reliabilities: Mapping[str, float]) -> float:
    key = reliability_key(obs)
    if key in reliabilities:
        return float(reliabilities[key])
    return float(reliabilities.get(obs.source.value, 1.0))


def _source_weight(obs: EntityObservation, reliabilities: Mapping[str, float]) -> float:
    return float(obs.quality) * lookup_reliability(obs, reliabilities)


def _strong_values(
    member_ids: Sequence[str],
    by_id: Mapping[str, EntityObservation],
    strong_keys: Sequence[str],
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for member_id in member_ids:
        obs = by_id[member_id]
        for key in strong_keys:
            value = obs.identifiers.get(key)
            if value:
                result[key].add(normalize_identifier(key, value))
    return dict(result)


def _clusters_conflict(
    left: Sequence[str],
    right: Sequence[str],
    by_id: Mapping[str, EntityObservation],
    strong_keys: Sequence[str],
) -> bool:
    left_values = _strong_values(left, by_id, strong_keys)
    right_values = _strong_values(right, by_id, strong_keys)
    for key in strong_keys:
        if key in left_values and key in right_values:
            if left_values[key].isdisjoint(right_values[key]):
                return True
    return False


def _cluster_text(member_ids: Sequence[str], by_id: Mapping[str, EntityObservation]) -> str:
    tokens: list[str] = []
    for member_id in member_ids:
        obs = by_id[member_id]
        tokens.append(obs.local_key)
        for key, value in sorted(obs.identifiers.items()):
            tokens.append(f"{key}:{value}")
        for key in ("name", "subject", "model"):
            value = obs.attributes.get(key)
            if value is not None:
                tokens.append(f"{key}:{value}")
    return " | ".join(tokens)


def _merge_by_key(
    uf: UnionFind,
    by_id: Mapping[str, EntityObservation],
    keys: Sequence[str],
    *,
    rule: str,
    merge_log: list[dict[str, Any]],
    check_conflicts: bool,
    strong_keys: Sequence[str],
    ambiguity_guard: bool = False,
) -> None:
    buckets: dict[tuple[EntityType, str, str], list[str]] = defaultdict(list)
    for obs_id, obs in by_id.items():
        for key in keys:
            value = obs.identifiers.get(key)
            if value:
                buckets[(obs.entity_type, key, normalize_identifier(key, value))].append(obs_id)

    for (entity_type, key, value), obs_ids in sorted(buckets.items(), key=lambda item: str(item[0])):
        ordered = sorted(obs_ids)
        if len(ordered) < 2:
            continue
        if ambiguity_guard:
            # an alias value shared by clusters with conflicting strong identifiers is ambiguous:
            # do not merge any record on it (the records stay separate and go to VERIFY)
            groups = {uf.find(item): [m for m in by_id if uf.find(m) == uf.find(item)] for item in ordered}
            reps = list(groups.values())
            if any(_clusters_conflict(reps[i], reps[j], by_id, strong_keys)
                   for i in range(len(reps)) for j in range(i + 1, len(reps))):
                merge_log.append({"rule": rule, "entity_type": entity_type.value, "key": key, "value": value,
                                  "left": ordered, "right": [], "decision": "blocked_ambiguous_alias"})
                continue
        anchor = ordered[0]
        for candidate in ordered[1:]:
            left_group = [item for item in by_id if uf.find(item) == uf.find(anchor)]
            right_group = [item for item in by_id if uf.find(item) == uf.find(candidate)]
            if check_conflicts and _clusters_conflict(left_group, right_group, by_id, strong_keys):
                merge_log.append(
                    {
                        "rule": rule,
                        "entity_type": entity_type.value,
                        "key": key,
                        "value": value,
                        "left": sorted(left_group),
                        "right": sorted(right_group),
                        "decision": "blocked_strong_identifier_conflict",
                    }
                )
                continue
            before_left = uf.find(anchor)
            before_right = uf.find(candidate)
            if before_left != before_right:
                uf.union(anchor, candidate)
                merge_log.append(
                    {
                        "rule": rule,
                        "entity_type": entity_type.value,
                        "key": key,
                        "value": value,
                        "left": anchor,
                        "right": candidate,
                        "decision": "merged",
                    }
                )


def _merge_by_tfidf(
    uf: UnionFind,
    by_id: Mapping[str, EntityObservation],
    *,
    threshold: float,
    merge_log: list[dict[str, Any]],
    strong_keys: Sequence[str],
) -> None:
    initial_groups = uf.groups()
    for entity_type in EntityType:
        groups = [group for group in initial_groups if by_id[group[0]].entity_type == entity_type]
        if len(groups) < 2:
            continue
        texts = [_cluster_text(group, by_id) for group in groups]
        vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), lowercase=True)
        matrix = vectorizer.fit_transform(texts)
        similarities = cosine_similarity(matrix)
        candidates: list[tuple[float, int, int]] = []
        for left in range(len(groups)):
            for right in range(left + 1, len(groups)):
                score = float(similarities[left, right])
                if score >= threshold:
                    candidates.append((score, left, right))
        candidates.sort(key=lambda item: (-item[0], groups[item[1]][0], groups[item[2]][0]))
        for score, left_index, right_index in candidates:
            left_anchor = groups[left_index][0]
            right_anchor = groups[right_index][0]
            if uf.find(left_anchor) == uf.find(right_anchor):
                continue
            current_left = [item for item in by_id if uf.find(item) == uf.find(left_anchor)]
            current_right = [item for item in by_id if uf.find(item) == uf.find(right_anchor)]
            if _clusters_conflict(current_left, current_right, by_id, strong_keys):
                merge_log.append(
                    {
                        "rule": "tfidf_cosine",
                        "entity_type": entity_type.value,
                        "score": score,
                        "left": sorted(current_left),
                        "right": sorted(current_right),
                        "decision": "blocked_strong_identifier_conflict",
                    }
                )
                continue
            uf.union(left_anchor, right_anchor)
            merge_log.append(
                {
                    "rule": "tfidf_cosine",
                    "entity_type": entity_type.value,
                    "score": score,
                    "left": sorted(current_left),
                    "right": sorted(current_right),
                    "decision": "merged",
                }
            )



def _fs_fields(obs: EntityObservation) -> dict[str, str]:
    """Comparison fields for probabilistic linkage: every identifier plus three name-like attributes."""
    fields = {f"id:{k}": str(v).strip().lower() for k, v in obs.identifiers.items() if v}
    for key in ("name", "subject", "model"):
        value = obs.attributes.get(key)
        if value is not None:
            fields[f"attr:{key}"] = str(value).strip().lower()
    return fields


def _merge_by_fellegi_sunter(
    uf: UnionFind,
    by_id: Mapping[str, EntityObservation],
    *,
    threshold: float,
    merge_log: list[dict[str, Any]],
    strong_keys: Sequence[str],
    iterations: int = 50,
) -> None:
    """Unsupervised Fellegi-Sunter record linkage (EM on agreement patterns, as in Splink).

    Each pair of current clusters of the same type gets one agreement level per field
    (agree / disagree / missing). EM estimates m (agreement among matches) and u (among
    non-matches) per field; pairs whose posterior match probability reaches `threshold`
    are merged, highest first, unless a strong identifier conflicts.
    """
    initial_groups = uf.groups()
    for entity_type in EntityType:
        groups = [g for g in initial_groups if by_id[g[0]].entity_type == entity_type]
        if len(groups) < 2:
            continue
        gfields = []
        for g in groups:
            merged: dict[str, set[str]] = {}
            for member in g:
                for k, v in _fs_fields(by_id[member]).items():
                    merged.setdefault(k, set()).add(v)
            gfields.append(merged)
        keys = sorted({k for f in gfields for k in f})
        pairs, vectors = [], []
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                vec = []
                for k in keys:
                    a, b = gfields[i].get(k), gfields[j].get(k)
                    vec.append(-1 if not a or not b else (1 if a & b else 0))
                pairs.append((i, j)); vectors.append(vec)
        if not pairs:
            continue
        # u (agreement among non-matches) from all pairs, as Splink estimates it by random sampling;
        # EM then estimates only m and the match prior lambda.
        u = {}
        for idx, k in enumerate(keys):
            obs_k = [vec[idx] for vec in vectors if vec[idx] != -1]
            u[k] = min(0.5, max(0.001, (sum(1 for g in obs_k if g == 1) + 0.5) / (len(obs_k) + 1.0)))
        m = {k: 0.9 for k in keys}; lam = 0.05
        post = [0.0] * len(pairs)
        for _ in range(iterations):
            for n, vec in enumerate(vectors):
                pm, pu = lam, 1.0 - lam
                for k, g in zip(keys, vec):
                    if g == -1:
                        continue
                    pm *= m[k] if g == 1 else 1.0 - m[k]
                    pu *= u[k] if g == 1 else 1.0 - u[k]
                post[n] = pm / (pm + pu) if pm + pu > 0 else 0.0
            lam = min(0.5, max(0.001, sum(post) / len(post)))
            for idx, k in enumerate(keys):
                num = den = 0.0
                for n, vec in enumerate(vectors):
                    if vec[idx] == -1:
                        continue
                    den += post[n]
                    if vec[idx] == 1:
                        num += post[n]
                m[k] = min(0.999, max(0.001, (num + 0.5) / (den + 1.0)))
        order = sorted(range(len(pairs)), key=lambda n: (-post[n], groups[pairs[n][0]][0], groups[pairs[n][1]][0]))
        for n in order:
            if post[n] < threshold:
                break
            la, ra = groups[pairs[n][0]][0], groups[pairs[n][1]][0]
            if uf.find(la) == uf.find(ra):
                continue
            cur_l = [x for x in by_id if uf.find(x) == uf.find(la)]
            cur_r = [x for x in by_id if uf.find(x) == uf.find(ra)]
            decision = "merged"
            if _clusters_conflict(cur_l, cur_r, by_id, strong_keys):
                decision = "blocked_strong_identifier_conflict"
            else:
                uf.union(la, ra)
            merge_log.append({"rule": "fellegi_sunter", "entity_type": entity_type.value,
                              "posterior": round(post[n], 4), "left": sorted(cur_l), "right": sorted(cur_r),
                              "decision": decision})


def _fuse_attributes(
    observations: Sequence[EntityObservation],
    reliabilities: Mapping[str, float],
) -> dict[str, Any]:
    keys = sorted({key for obs in observations for key in obs.attributes})
    fused: dict[str, Any] = {}
    for key in keys:
        values: list[tuple[Any, float]] = []
        for obs in observations:
            value = obs.attributes.get(key)
            if value is not None:
                values.append((value, _source_weight(obs, reliabilities)))
        if not values:
            continue
        if all(isinstance(value, bool) for value, _ in values):
            true_weight = sum(weight for value, weight in values if value)
            false_weight = sum(weight for value, weight in values if not value)
            fused[key] = true_weight >= false_weight
        elif all(isinstance(value, (int, float)) and not isinstance(value, bool) for value, _ in values):
            total_weight = sum(weight for _, weight in values)
            fused[key] = (
                sum(float(value) * weight for value, weight in values) / total_weight
                if total_weight > 0
                else float(np.mean([float(value) for value, _ in values]))
            )
        else:
            support: dict[str, float] = defaultdict(float)
            original: dict[str, Any] = {}
            for value, weight in values:
                key_value = repr(value)
                support[key_value] += weight
                original[key_value] = value
            winner = sorted(support, key=lambda item: (-support[item], item))[0]
            fused[key] = original[winner]
    return fused


def _node_support(observations: Sequence[EntityObservation], reliabilities: Mapping[str, float]) -> float:
    remaining = 1.0
    for obs in observations:
        remaining *= 1.0 - min(1.0, max(0.0, _source_weight(obs, reliabilities)))
    return min(1.0, max(0.0, 1.0 - remaining))


def _canonical_anchor(
    observations: Sequence[EntityObservation],
    strong_keys: Sequence[str],
    alias_keys: Sequence[str],
) -> tuple[str, str]:
    for key in strong_keys:
        values = sorted({obs.identifiers[key] for obs in observations if obs.identifiers.get(key)})
        if values:
            return key, values[0]
    for key in alias_keys:
        values = sorted({obs.identifiers[key] for obs in observations if obs.identifiers.get(key)})
        if values:
            return key, values[0]
    return "observation_id", sorted(obs.observation_id for obs in observations)[0]


def resolve_entities(
    observations: Sequence[EntityObservation],
    *,
    strategy: str,
    config: Mapping[str, Any],
    allowed_sources: set[SourceFamily] | None = None,
    apply_quality_gate: bool = True,
    use_aliases: bool = False,
    uniform_reliability: bool = False,
) -> ResolutionResult:
    """Resolve public observations without reading any evaluator-only data."""

    gate = float(config["quality_gates"]["entity"])
    retained: list[EntityObservation] = []
    quarantined: list[str] = []
    for obs in sorted(observations, key=lambda item: item.observation_id):
        if allowed_sources is not None and obs.source not in allowed_sources:
            continue
        if apply_quality_gate and obs.quality < gate:
            quarantined.append(obs.observation_id)
            continue
        retained.append(obs)

    by_id = {obs.observation_id: obs for obs in retained}
    uf = UnionFind(by_id)
    merge_log: list[dict[str, Any]] = []
    strong_keys = tuple(config["identity"].get("strong_keys", DEFAULT_STRONG_KEYS))
    alias_keys = tuple(config["identity"].get("alias_keys", DEFAULT_ALIAS_KEYS))

    if strategy == "source_union":
        pass
    elif strategy in {"strong", "cigma", "cigma_guard", "tfidf", "fellegi_sunter", "rules_any_id"}:
        _merge_by_key(
            uf,
            by_id,
            strong_keys,
            rule="strong_identifier",
            merge_log=merge_log,
            check_conflicts=False,
            strong_keys=strong_keys,
        )
        if strategy in {"cigma", "cigma_guard"} and use_aliases:
            _merge_by_key(
                uf,
                by_id,
                alias_keys,
                rule="compatible_alias",
                merge_log=merge_log,
                check_conflicts=True,
                strong_keys=strong_keys,
                ambiguity_guard=strategy == "cigma_guard",
            )
        if strategy == "rules_any_id":
            # classic deterministic linkage rule: any shared identifier value links two records
            _merge_by_key(
                uf,
                by_id,
                alias_keys,
                rule="rule_shared_identifier",
                merge_log=merge_log,
                check_conflicts=False,
                strong_keys=strong_keys,
            )
        if strategy == "fellegi_sunter":
            _merge_by_fellegi_sunter(
                uf,
                by_id,
                threshold=float(config["identity"].get("fellegi_sunter_threshold", 0.9)),
                merge_log=merge_log,
                strong_keys=strong_keys,
            )
        if strategy == "tfidf":
            _merge_by_tfidf(
                uf,
                by_id,
                threshold=float(config["identity"]["tfidf_threshold"]),
                merge_log=merge_log,
                strong_keys=strong_keys,
            )
    else:
        raise ValueError(f"unknown resolution strategy: {strategy}")

    reliabilities = {
        str(key): 1.0 if uniform_reliability else float(value)
        for key, value in config["source_reliabilities"].items()
    }
    nodes: dict[str, Node] = {}
    observation_to_node: dict[str, str] = {}
    used_node_ids: set[str] = set()

    for member_ids in uf.groups():
        cluster_obs = [by_id[member_id] for member_id in member_ids]
        entity_type = cluster_obs[0].entity_type
        if any(obs.entity_type != entity_type for obs in cluster_obs):
            raise AssertionError("union-find cluster contains mixed entity types")
        key, value = _canonical_anchor(cluster_obs, strong_keys, alias_keys)
        material = f"{entity_type.value}|{key}|{value}".encode("utf-8")
        node_id = f"{entity_type.value}:{sha256(material).hexdigest()[:16]}"
        if node_id in used_node_ids:
            disambiguator = sha256("|".join(member_ids).encode("utf-8")).hexdigest()[:8]
            node_id = f"{node_id}:{disambiguator}"
        used_node_ids.add(node_id)

        identifiers: dict[str, list[str]] = {}
        for identifier_key in sorted({key for obs in cluster_obs for key in obs.identifiers}):
            identifiers[identifier_key] = sorted(
                {obs.identifiers[identifier_key] for obs in cluster_obs if obs.identifiers.get(identifier_key)}
            )
        node_merge_log = [
            entry
            for entry in merge_log
            if any(member_id in str(entry) for member_id in member_ids)
        ]
        node = Node(
            node_id=node_id,
            entity_type=entity_type,
            identifiers=identifiers,
            attributes=_fuse_attributes(cluster_obs, reliabilities),
            observation_ids=sorted(member_ids),
            support=_node_support(cluster_obs, reliabilities),
            merge_log=node_merge_log,
        )
        nodes[node_id] = node
        for member_id in member_ids:
            observation_to_node[member_id] = node_id

    return ResolutionResult(
        nodes=nodes,
        observation_to_node=observation_to_node,
        quarantined_observation_ids=sorted(quarantined),
        merge_log=merge_log,
    )
