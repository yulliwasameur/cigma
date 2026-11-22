"""Executable compliance queries over the evidence graph (decision 37).

Each rule returns findings that carry their evidence ids, so a compliance answer is
itself proof-carrying. Rules encode published deadlines (checked 22/11/2026):

- NIST IR 8547 (final, 27 Oct 2026): every quantum-vulnerable public-key algorithm is
  deprecated after 2030 and disallowed after 2035; under EO 14412, federal high-value
  assets need PQC key establishment by 31 Dec 2030 and PQC signatures by 31 Dec 2031.
- EU Coordinated Implementation Roadmap (NIS Cooperation Group, June 2025): start by
  end 2026; high-risk use cases transitioned by end 2030; medium/low risk by 2035 as far
  as feasible.
- ANSSI (2022 position, 2023 follow-up, FAQ): hybridization wherever post-quantum
  protection is needed; products without PQC should no longer be bought from 2030.

These are encodings for research, not legal advice; thresholds (what counts as
"high-risk") are configurable and reported with the results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..schema import EntityType, GraphSnapshot, RelationType
from ..scoring import RankingEntry

RULES = {
    "NIST-IR-8547": "Quantum-vulnerable public-key algorithm: deprecated after 2030, disallowed after 2035.",
    "NIST-HVA-KEX-2030": "High-value asset: post-quantum key establishment required by 2030-12-31.",
    "NIST-HVA-SIG-2031": "High-value asset: post-quantum signatures required by 2031-12-31.",
    "EU-HIGH-RISK-2030": "High-risk use case still quantum-vulnerable: transition due by end 2030.",
    "ANSSI-HYBRID": "Post-quantum mechanism without hybridization.",
    "ANSSI-CONFIDENTIALITY-2030": "Data needing confidentiality beyond 2030 protected only classically.",
}


@dataclass(slots=True)
class Finding:
    rule: str
    node_id: str
    deadline: str
    detail: str
    evidence_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"rule": self.rule, "node_id": self.node_id, "deadline": self.deadline,
                "detail": self.detail, "evidence_ids": self.evidence_ids}


def run_compliance(
    graph: GraphSnapshot,
    rankings: Sequence[RankingEntry],
    *,
    current_year: int = 2026,
    high_value_criticality: float = 0.8,
    high_risk_tier: int = 3,
) -> list[Finding]:
    findings: list[Finding] = []
    algo_edges: dict[str, list[Any]] = {}
    for e in graph.edges:
        if e.predicate == RelationType.USES and graph.nodes[e.object].entity_type == EntityType.ALGORITHM:
            algo_edges.setdefault(e.subject, []).append(e)
    for r in rankings:
        q = r.impact.get("Q")
        # evidence: algorithm edges of the asset, of its services, and of the components
        # those services use (two hops), plus the asset's own observations
        sources = [r.node_id, *r.service_contexts]
        comps = [e.object for s in r.service_contexts for e in graph.edges
                 if e.subject == s and e.predicate == RelationType.USES
                 and graph.nodes[e.object].entity_type == EntityType.SOFTWARE_COMPONENT]
        hop_edges = [e for n in [*sources, *comps] for e in algo_edges.get(n, [])]
        hop_edges += [e for e in graph.edges if e.predicate == RelationType.ISSUED_BY and e.subject == r.node_id]
        evid = sorted({i for e in hop_edges for i in e.evidence_ids} | set(graph.nodes[r.node_id].observation_ids))
        if q is not None and q >= 1.0:
            findings.append(Finding("NIST-IR-8547", r.node_id, "2030-12-31 / 2035-12-31", RULES["NIST-IR-8547"], evid))
            crit = r.impact.get("C")
            if crit is not None and crit >= high_value_criticality:
                rule = "NIST-HVA-SIG-2031" if r.entity_type == EntityType.CERTIFICATE else "NIST-HVA-KEX-2030"
                findings.append(Finding(rule, r.node_id, "2031-12-31" if rule.endswith("2031") else "2030-12-31",
                                        RULES[rule], evid))
            if r.upper_tier >= high_risk_tier:
                findings.append(Finding("EU-HIGH-RISK-2030", r.node_id, "2030-12-31", RULES["EU-HIGH-RISK-2030"], evid))
            for s in r.service_contexts:
                life = graph.nodes[s].attributes.get("data_lifetime_years") if s in graph.nodes else None
                processed = [graph.nodes[e.object].attributes.get("retention_years")
                             for e in graph.edges if e.subject == s and e.predicate == RelationType.PROCESSES]
                horizon = max([v for v in [life, *processed] if isinstance(v, (int, float))], default=None)
                if horizon is not None and current_year + horizon > 2030:
                    findings.append(Finding("ANSSI-CONFIDENTIALITY-2030", r.node_id, "now",
                                            f"{RULES['ANSSI-CONFIDENTIALITY-2030']} (needed until {current_year + horizon:.0f})", evid))
                    break
    for nid, node in graph.nodes.items():
        if node.entity_type == EntityType.ALGORITHM and node.attributes.get("pq_status") == "post_quantum":
            findings.append(Finding("ANSSI-HYBRID", nid, "now", RULES["ANSSI-HYBRID"], sorted(node.observation_ids)))
    return findings


def summary(findings: Sequence[Finding]) -> dict[str, Any]:
    out: dict[str, int] = {}
    for f in findings:
        out[f.rule] = out.get(f.rule, 0) + 1
    return {"findings_by_rule": out, "assets_with_findings": len({f.node_id for f in findings}),
            "all_findings_carry_evidence": all(bool(f.evidence_ids) for f in findings if f.rule != "ANSSI-HYBRID")}
