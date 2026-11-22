"""Hybrid and post-quantum key establishment observed on real endpoints.

A TLS endpoint can *negotiate* a classical group in one session while being
*capable* of a hybrid group such as X25519MLKEM768 (Delgado, ePrint 2605.02978).
CIGMA records both: the negotiated group as a USES edge to an algorithm entity, and
the advertised capability as an endpoint attribute. The quantum-vulnerability policy
treats hybrid key establishment as protected for confidentiality (HNDL), while the
certificate signature keeps its own classical value (authenticity is unchanged until
the certificate itself is migrated).
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from ..adapters.base import AdapterOutput, ObservationFactory
from ..schema import EntityType, RelationType, SourceFamily

HYBRID_GROUPS = {"X25519MLKEM768", "SECP256R1MLKEM768", "X25519KYBER768DRAFT00"}
PQ_ONLY_GROUPS = {"MLKEM768", "MLKEM1024"}
CLASSICAL_GROUPS = {"X25519", "SECP256R1", "SECP384R1", "FFDHE2048"}

POLICY_VALUES = {
    # confidentiality of the key exchange (HNDL); 0 = not quantum-vulnerable
    "X25519MLKEM768": 0.0,
    "SECP256R1MLKEM768": 0.0,
    "MLKEM768": 0.0,
    "MLKEM1024": 0.0,
    "X25519": 1.0,
    "SECP256R1": 1.0,
    "SECP384R1": 1.0,
    "FFDHE2048": 1.0,
    # signatures
    "ML-DSA-65": 0.0,
    "ML-DSA-44": 0.0,
}


def classify_group(group: str) -> str:
    g = group.upper()
    if g in HYBRID_GROUPS:
        return "hybrid"
    if g in PQ_ONLY_GROUPS:
        return "post_quantum"
    if g in CLASSICAL_GROUPS:
        return "classical"
    return "unknown"


def extend_policy(config: Mapping[str, Any]) -> dict[str, Any]:
    import copy

    cfg = copy.deepcopy(dict(config))
    values = dict(cfg["algorithm_policy"]["values"])
    for k, v in POLICY_VALUES.items():
        values.setdefault(k, v)
    cfg["algorithm_policy"] = {**cfg["algorithm_policy"], "values": values}
    return cfg


def adapt_tls_kex_records(records: Iterable[Mapping[str, Any]], *, collected_at: str) -> AdapterOutput:
    """TLS records with the negotiated group and the advertised groups (e.g. from sslyze).

    Expected keys: endpoint_local_key, endpoint_uri, negotiated_group,
    supported_groups (list), locator, quality.
    """

    output = AdapterOutput()
    factory = ObservationFactory(SourceFamily.TLS, collected_at)
    for index, record0 in enumerate(records):
        record = dict(record0)
        base = str(record.get("locator", f"tls/kex.json#/{index}"))
        q = float(record.get("quality", 0.98))
        supported = [str(g).upper() for g in record.get("supported_groups", [])]
        negotiated = str(record["negotiated_group"]).upper()
        capability = "hybrid" if any(classify_group(g) in ("hybrid", "post_quantum") for g in supported) else "classical"
        output.add_entity(factory.entity(
            local_key=str(record["endpoint_local_key"]), entity_type=EntityType.ENDPOINT,
            identifiers={"endpoint_uri": record["endpoint_uri"]},
            attributes={"negotiated_group": negotiated, "kex_capability": capability,
                        "supported_groups": ",".join(sorted(supported))},
            quality=q, locator=f"{base}/endpoint", evidence_record=record))
        output.add_entity(factory.entity(
            local_key=f"kex_{negotiated.lower()}", entity_type=EntityType.ALGORITHM,
            identifiers={"algorithm_id": negotiated},
            attributes={"family": "kem" if classify_group(negotiated) != "classical" else "key_exchange",
                        "pq_status": classify_group(negotiated)},
            quality=q, locator=f"{base}/negotiated_group", evidence_record=record))
        # Endpoint -> algorithm is not an ontology signature: the negotiated group is linked
        # through the hosting service (service USES algorithm) once the service is resolved.
    return output
