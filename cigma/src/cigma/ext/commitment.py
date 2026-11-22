"""Merkle commitment of a CIGMA graph, with per-decision inclusion proofs.

Problem: a migration decision ("move service X first") is audited months later, by
someone who should not see the whole inventory (it is a map of the organization's
weak spots). Idea, borrowed from Certificate Transparency and transparency logs for
supply chains (Sigstore; VeriSBOM, ASE 2026; TrustBOM 2026):

- every node, edge and ranking decision becomes a leaf ``H(0x00 || canonical JSON)``;
- leaves are sorted and hashed into a Merkle tree (``H(0x01 || left || right)``);
- the 32-byte root is published (e.g. in the prediction seal or a transparency log);
- an auditor receives one decision, its evidence leaves and their inclusion proofs,
  and checks them against the root without seeing anything else.

Domain separation (0x00 leaves / 0x01 inner nodes) prevents second-preimage tricks.
Leaf payloads carry evidence *digests*, never raw excerpts, so a proof reveals only
what the auditor is meant to see.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..schema import GraphSnapshot
from ..scoring import RankingEntry


def _h(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def leaf_hash(payload: Mapping[str, Any]) -> bytes:
    return _h(b"\x00" + json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())


def _inner(left: bytes, right: bytes) -> bytes:
    return _h(b"\x01" + left + right)


def graph_leaves(
    graph: GraphSnapshot,
    rankings: Sequence[RankingEntry] = (),
    evidence_digests: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    digests = dict(evidence_digests or {})
    leaves: list[dict[str, Any]] = [{"kind": "config", "config_digest": graph.config_digest, "method": graph.method}]
    for node_id in sorted(graph.nodes):
        n = graph.nodes[node_id]
        leaves.append({
            "kind": "node", "node_id": node_id, "entity_type": n.entity_type.value,
            "support": round(float(n.support), 6),
            "evidence": sorted(digests.get(i, i) for i in n.observation_ids),
        })
    for e in graph.edges:
        leaves.append({
            "kind": "edge", "subject": e.subject, "predicate": e.predicate.value, "object": e.object,
            "derived": e.derived, "rules": list(e.rules), "support": round(float(e.support), 6),
            "evidence": sorted(digests.get(i, i) for i in e.evidence_ids),
        })
    for r in rankings:
        leaves.append({
            "kind": "decision", "node_id": r.node_id, "primary_rank": r.primary_rank,
            "upper_tier": r.upper_tier, "lower_tier": r.lower_tier, "verify": r.verify,
            "evidence_confidence": round(float(r.evidence_confidence), 6),
        })
    return leaves


@dataclass(slots=True)
class MerkleTree:
    leaves: list[bytes]
    levels: list[list[bytes]]

    @property
    def root(self) -> str:
        return self.levels[-1][0].hex()


def build_tree(payloads: Sequence[Mapping[str, Any]]) -> tuple[MerkleTree, list[Mapping[str, Any]]]:
    hashed = sorted(((leaf_hash(p), p) for p in payloads), key=lambda item: item[0])
    leaves = [h for h, _ in hashed]
    ordered = [p for _, p in hashed]
    if not leaves:
        leaves = [_h(b"\x00")]
    levels = [leaves]
    while len(levels[-1]) > 1:
        cur = levels[-1]
        nxt = []
        for i in range(0, len(cur), 2):
            right = cur[i + 1] if i + 1 < len(cur) else cur[i]  # duplicate the last odd node
            nxt.append(_inner(cur[i], right))
        levels.append(nxt)
    return MerkleTree(leaves=leaves, levels=levels), ordered


def inclusion_proof(tree: MerkleTree, index: int) -> list[dict[str, str]]:
    proof = []
    for level in tree.levels[:-1]:
        sibling = index ^ 1
        if sibling >= len(level):
            sibling = index
        proof.append({"side": "right" if sibling > index or sibling == index else "left",
                      "hash": level[sibling].hex()})
        index //= 2
    return proof


def verify_inclusion(payload: Mapping[str, Any], proof: Sequence[Mapping[str, str]], root_hex: str) -> bool:
    node = leaf_hash(payload)
    for step in proof:
        sib = bytes.fromhex(step["hash"])
        node = _inner(node, sib) if step["side"] == "right" else _inner(sib, node)
    return node.hex() == root_hex


def decision_receipt(
    tree: MerkleTree, ordered: Sequence[Mapping[str, Any]], node_id: str
) -> dict[str, Any]:
    """Proof bundle for one ranking decision plus every edge touching that node."""

    items = []
    for i, p in enumerate(ordered):
        if (p.get("kind") == "decision" and p.get("node_id") == node_id) or (
            p.get("kind") == "edge" and node_id in (p.get("subject"), p.get("object"))
        ) or (p.get("kind") == "node" and p.get("node_id") == node_id):
            items.append({"payload": dict(p), "proof": inclusion_proof(tree, i)})
    return {"root": tree.root, "node_id": node_id, "items": items,
            "disclosed_leaves": len(items), "total_leaves": len(ordered)}


# ------------------------------------------------------------------ append-only version log (RFC 6962)

def _mth(leaves: Sequence[bytes]) -> bytes:
    """Merkle tree hash of RFC 6962 (Certificate Transparency) over leaf *data*."""

    n = len(leaves)
    if n == 0:
        return _h(b"")
    if n == 1:
        return _h(b"\x00" + leaves[0])
    k = 1 << ((n - 1).bit_length() - 1)
    return _inner(_mth(leaves[:k]), _mth(leaves[k:]))


def consistency_proof(leaves: Sequence[bytes], m: int) -> list[bytes]:
    """PROOF(m, D[n]) from RFC 6962, section 2.1.2: the first m entries are a prefix of the n entries."""

    def subproof(m: int, d: Sequence[bytes], b: bool) -> list[bytes]:
        n = len(d)
        if m == n:
            return [] if b else [_mth(d)]
        k = 1 << ((n - 1).bit_length() - 1)
        if m <= k:
            return subproof(m, d[:k], b) + [_mth(d[k:])]
        return subproof(m - k, d[k:], False) + [_mth(d[:k])]

    return subproof(m, list(leaves), True)


def verify_consistency(m: int, n: int, old_root: bytes, new_root: bytes, proof: Sequence[bytes]) -> bool:
    """Verifier of RFC 9162 (CT v2), section 2.1.4.2."""

    if m == n:
        return old_root == new_root and not proof
    if m == 0:
        return False
    path = list(proof)
    if m & (m - 1) == 0:          # m is a power of two: old root is the first node
        path = [old_root] + path
    fn, sn = m - 1, n - 1
    while fn & 1:
        fn >>= 1
        sn >>= 1
    if not path:
        return False
    fr = sr = path[0]
    for c in path[1:]:
        if sn == 0:
            return False
        if fn & 1 or fn == sn:
            fr = _inner(c, fr)
            sr = _inner(c, sr)
            while fn and not fn & 1:
                fn >>= 1
                sn >>= 1
        else:
            sr = _inner(sr, c)
        fn >>= 1
        sn >>= 1
    return fr == old_root and sr == new_root and sn == 0


@dataclass(slots=True)
class VersionLog:
    """Append-only log of graph roots: every new inventory version is appended; auditors
    check that version n extends version m (no rewritten history) with a consistency proof."""

    entries: list[bytes]

    @classmethod
    def empty(cls) -> "VersionLog":
        return cls(entries=[])

    def append(self, graph_root_hex: str, meta: Mapping[str, Any]) -> int:
        self.entries.append(json.dumps({"root": graph_root_hex, **meta}, sort_keys=True).encode())
        return len(self.entries)

    def root(self, size: int | None = None) -> bytes:
        return _mth(self.entries[: len(self.entries) if size is None else size])

    def prove(self, m: int) -> list[bytes]:
        return consistency_proof(self.entries, m)


def leakage_of_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """What a receipt reveals, formally: the disclosed leaves (their full payload), and for
    each undisclosed leaf only a 32-byte hash on the proof path, plus the total leaf count
    implied by the tree height. Hashes are of salted-free canonical JSON, so a low-entropy
    leaf could be guessed by brute force; this function counts such sibling leaves."""

    disclosed = receipt["items"]
    sibling_hashes = {step["hash"] for it in disclosed for step in it["proof"]}
    return {"disclosed_leaves": len(disclosed), "sibling_hashes_revealed": len(sibling_hashes),
            "total_leaves": receipt["total_leaves"],
            "fraction_of_payloads_revealed": len(disclosed) / max(1, receipt["total_leaves"])}
