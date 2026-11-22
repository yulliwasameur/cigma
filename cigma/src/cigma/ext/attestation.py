"""Signed observations: DSSE envelopes with post-quantum ML-DSA signatures.

Each tool signs every observation it emits, as in-toto attestations do for software
supply chains. The envelope follows DSSE (Dead Simple Signing Envelope): the
signature covers PAE(type, body) = "DSSEv1 <len(type)> <type> <len(body)> <body>",
so the payload type cannot be swapped. Keys are ML-DSA-65 (FIPS 204): the migration
tool itself is post-quantum.

What this buys, and what it does not:
- an observation from a tool that is not in the trusted keyring is rejected at load
  time (injection by an outsider fails);
- every accepted observation is attributable to one key, so a compromised tool can be
  revoked and all of its observations removed in one step;
- a *trusted* tool that lies still passes: that case is handled by learned
  reliabilities, copy detection, conformal selection and human verification.

Implementation note: ``dilithium-py`` is a pure-Python reference implementation of
FIPS 204, fine for research measurements, not constant-time, not for production.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from ..resolution import reliability_key

PAYLOAD_TYPE_ENTITY = "application/vnd.cigma.entity-observation+json"
PAYLOAD_TYPE_RELATION = "application/vnd.cigma.relation-observation+json"


def _pae(payload_type: str, body: bytes) -> bytes:
    t = payload_type.encode()
    return b"DSSEv1 " + str(len(t)).encode() + b" " + t + b" " + str(len(body)).encode() + b" " + body


def _scheme():
    from dilithium_py.ml_dsa import ML_DSA_65

    return ML_DSA_65


@dataclass(slots=True)
class ToolKey:
    tool: str
    public_key: bytes
    secret_key: bytes | None = None

    @property
    def keyid(self) -> str:
        return hashlib.sha256(self.public_key).hexdigest()[:16]


def generate_key(tool: str) -> ToolKey:
    pk, sk = _scheme().keygen()
    return ToolKey(tool=tool, public_key=pk, secret_key=sk)


@dataclass(slots=True)
class Keyring:
    trusted: dict[str, ToolKey] = field(default_factory=dict)   # keyid -> key
    revoked: set[str] = field(default_factory=set)

    def add(self, key: ToolKey) -> None:
        self.trusted[key.keyid] = ToolKey(key.tool, key.public_key)

    def revoke(self, keyid: str) -> None:
        self.revoked.add(keyid)


def sign_observation(obs: Any, key: ToolKey, *, kind: str) -> dict[str, Any]:
    payload_type = PAYLOAD_TYPE_ENTITY if kind == "entity" else PAYLOAD_TYPE_RELATION
    body = json.dumps(obs.to_dict(), sort_keys=True, separators=(",", ":")).encode()
    sig = _scheme().sign(key.secret_key, _pae(payload_type, body))
    return {
        "payloadType": payload_type,
        "payload": base64.b64encode(body).decode(),
        "signatures": [{"keyid": key.keyid, "sig": base64.b64encode(sig).decode()}],
    }


def verify_envelope(env: Mapping[str, Any], keyring: Keyring) -> tuple[bool, str, str | None]:
    sigs = env.get("signatures") or []
    if not sigs:
        return False, "unsigned", None
    body = base64.b64decode(env["payload"])
    for s in sigs:
        kid = s.get("keyid")
        if kid in keyring.revoked:
            return False, "revoked_key", kid
        key = keyring.trusted.get(kid)
        if key is None:
            continue
        if _scheme().verify(key.public_key, _pae(env["payloadType"], body), base64.b64decode(s["sig"])):
            return True, "ok", kid
        return False, "bad_signature", kid
    return False, "untrusted_key", sigs[0].get("keyid")


def sign_all(
    entities: Sequence[Any], relations: Sequence[Any], keys: Mapping[str, ToolKey],
    *, default_key: ToolKey | None = None,
) -> tuple[list[dict], list[dict], dict[str, float]]:
    """Sign each observation with the key of its reliability key (``source`` or ``source:tool``)."""

    t0 = time.perf_counter()
    ent_env, rel_env = [], []
    for o in entities:
        k = keys.get(reliability_key(o)) or default_key
        ent_env.append(sign_observation(o, k, kind="entity") if k else {"payloadType": PAYLOAD_TYPE_ENTITY,
                       "payload": base64.b64encode(json.dumps(o.to_dict(), sort_keys=True).encode()).decode(), "signatures": []})
    for o in relations:
        k = keys.get(reliability_key(o)) or default_key
        rel_env.append(sign_observation(o, k, kind="relation") if k else {"payloadType": PAYLOAD_TYPE_RELATION,
                       "payload": base64.b64encode(json.dumps(o.to_dict(), sort_keys=True).encode()).decode(), "signatures": []})
    dt = time.perf_counter() - t0
    n = len(entities) + len(relations)
    return ent_env, rel_env, {"sign_seconds_total": dt, "sign_ms_per_observation": 1000 * dt / max(1, n)}


def load_verified(
    ent_env: Iterable[Mapping[str, Any]], rel_env: Iterable[Mapping[str, Any]], keyring: Keyring,
) -> tuple[list[Any], list[Any], dict[str, Any]]:
    """Return only verified observations; relations whose endpoints were rejected are dropped too."""

    from ..schema import EntityObservation, RelationObservation

    t0 = time.perf_counter()
    reasons: dict[str, int] = {}
    by_key: dict[str, int] = {}
    ents = []
    for env in ent_env:
        ok, why, kid = verify_envelope(env, keyring)
        reasons[why] = reasons.get(why, 0) + 1
        if ok:
            ents.append(EntityObservation.from_dict(json.loads(base64.b64decode(env["payload"]))))
            by_key[kid] = by_key.get(kid, 0) + 1
    ids = {e.observation_id for e in ents}
    rels = []
    for env in rel_env:
        ok, why, kid = verify_envelope(env, keyring)
        reasons[why] = reasons.get(why, 0) + 1
        if ok:
            r = RelationObservation.from_dict(json.loads(base64.b64decode(env["payload"])))
            if r.subject_observation_id in ids and r.object_observation_id in ids:
                rels.append(r)
                by_key[kid] = by_key.get(kid, 0) + 1
            else:
                reasons["dangling_after_rejection"] = reasons.get("dangling_after_rejection", 0) + 1
    dt = time.perf_counter() - t0
    return ents, rels, {"reasons": reasons, "accepted_by_keyid": by_key,
                        "verify_seconds_total": dt}
