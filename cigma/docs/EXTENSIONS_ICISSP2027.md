# Extensions for the ICISSP 2027 final version (21/11/2026)

All numbers below come from `make extensions` on the controlled fixture (CIGMA-Lab).
They are new clean-room results. The core pipeline is unchanged: the main campaign
still produces the same metrics digest (`6581404b2b70…`).

Regenerate: `PYTHONPATH=src python scripts/run_extensions.py` → `results/extensions/`.

## E1 — Source reliabilities learned without ground truth (`ext/reliability.py`)

- Truth-discovery loop (leave-one-out, Beta prior, unconfirmed items count 0.5).
- Base fixture: reconstruction unchanged (all F1 = 1.0). The VERIFY queue grows from 15 to 18,
  because learned values (≈ 0.57–0.67) are more cautious than the hand-set ones (0.86–0.98).
- **What this shows**: the hand-set values are not needed to reconstruct the graph. They
  only change what is sent to human verification.

## E2 — Several CBOM tools that disagree (`ext/multitool.py`)

Setup: tool A is complete and correct. Tool B misses 40 % of the items and adds false ones:
a fake component and fake USES and DEPENDS-ON edges. Tool C copies tool B.

| Method | Typed-edge F1 | Edge FP rate | Injected edge support / other edges |
|---|---|---|---|
| Tool A alone | 1.000 | 0.000 | – |
| Tool B (or C) alone | 0.866 | 0.121 | 0.658 / 0.830 |
| Union of the 3 tools | 0.744 | 0.341 | 0.573 / 0.710 |
| Majority vote, then CIGMA | 0.866 | 0.121 | 0.929 / 0.866 |
| CIGMA, fixed reliabilities | **0.944** | 0.105 | 0.929 / 0.862 |
| CIGMA, learned, no copy detection | 0.944 | 0.105 | 0.922 / 0.584 |
| CIGMA, learned + copy-aware support | 0.944 | 0.105 | **0.541 / 0.548** |

- CIGMA beats the majority vote (0.944 against 0.866): the vote throws away true items
  that only tool A reports.
- The vote accepts the false items, because the copying tool gives them a second vote.
- **Copy detection**: without it, the two copying tools look *more* reliable than the
  correct tool (0.867 against 0.792). With it, the order is right (A 0.756 > B = C 0.691).
- **Copy-aware support** (dependent sources count as one witness): the false edges no
  longer look stronger than the true ones (0.541 against 0.548, instead of 0.929 against 0.862).
- **Limit, said plainly**: no unsupervised setting removes the false items. Telling a
  complete tool apart from a pair of tools that copy each other's mistakes needs a human
  check. This leads to E6.

## E3 — Interoperability-aware migration order (`ext/ordering.py`)

MOVR is Eq. 3 of the paper. A break is a dependency v → u where u is migrated before v.

| Method | Order | MOVR | Break-steps | Exposure AUC |
|---|---|---|---|---|
| CIGMA | primary (urgency) | 0.04 | 4 | 0.408 |
| CIGMA | **interoperability-aware** | **0.00** | **0** | 0.439 |
| ExactDirect / TF-IDF | primary | 0.04 | 4 | 0.410 |
| ExactDirect / TF-IDF | interoperability-aware | 0.03 | 3 | 0.425 |
| SourceUnion | interoperability-aware | 0.08 | 8 | 0.440 |

- On CIGMA's graph, the dependency-respecting order removes every break. The cost is
  +0.031 of exposure area: urgent assets wait a little.
- The same reordering on the baselines' graphs does not remove all breaks, because their
  graphs miss dependencies. This is a *migration-level* benefit of better reconstruction,
  the outcome the reviewers asked for.
- Each plan comes with a machine-checkable certificate (SHA-256 over the order and every
  DEPENDS-ON constraint checked; `e3_plan_certificates_cigma.json`).

## E4 — Two quantum-risk clocks (`ext/exposure.py`)

- HNDL (confidentiality: data lifetime + migration time) and TNFL (authenticity:
  remaining trust of a signing key + migration time, weighted by how many certificates
  the key anchors). The median quantum arrival is drawn in [8, 25] years (400 draws).
- On the fixture, the root certificate is the only TNFL-dominant asset, and it is ranked first.
  The order is stable across all draws (Kendall τ = 1.0) and identical to the primary order.
- **Reading**: the second clock does not reorder this small fixture, consistent with Shaw
  (2026), who finds reordering in one of four systems. It must be tested on the real system
  (L1), where the issuing CA and the leaf certificates have very different lifetimes.

## E5 — Merkle commitment and per-decision receipts (`ext/commitment.py`)

- 76 leaves (configuration, nodes, edges, decisions), tree height 7, one 32-byte root.
- A receipt for one decision discloses 4 to 6 leaves (6.6 % of the graph on average) with
  their inclusion proofs. All receipts verify; a modified leaf is rejected.
- **Why it matters**: an auditor or a regulator can check one migration decision and its
  evidence without receiving the map of the organization's weak spots.

## E6 — Budgeted human verification (`ext/active.py`)

False edges found among 4, on the noisy multi-tool graph:

| Policy | 6 checks | 10 checks | 15 checks |
|---|---|---|---|
| Random | 1 | 1 | 1 |
| Lowest support first | 0 | 0 | 0 |
| Uncertainty × reach, copy-aware support | 1 | 2 | **4** |
| Intra-family disagreement, copy-aware support | 1 | 2 | 3 |

- With copy-aware support, the "uncertainty × reach" policy finds every false edge in
  15 checks. Random checking finds only one.
- "Lowest support first" fails: the false items are well supported by their two copies.

## Not run here

- **k-of-n consensus across language models (`ext/consensus.py`)**: tested (unit tests),
  but its numbers require the real outputs of the 6 open models on LUMI (`rq3-lumi/`).
  No simulated model output is reported.
- **Hybrid key exchange (`ext/hybrid.py`)**: adapter and policy are ready and tested.
  Measurement requires the L1 gateway with X25519MLKEM768 enabled.

---

# Second batch (A* plan, 22/11/2026)

Regenerate: `PYTHONPATH=src python scripts/run_extensions_v2.py` (20 seeds per setting).

## E7 — Poisoning campaign (`ext/poisoning.py`)

A malicious tool re-reports real entities and injects k type-valid false relations.
Mean over 20 seeds:

| k | Union: edge F1 | CIGMA: edge F1 | Poisoned edges flagged, fixed reliabilities | Poisoned edges flagged, learned + copy-aware | True edges flagged (fixed / learned) |
|---|---|---|---|---|---|
| 0 | 0.853 | 1.000 | – | – | 18 / 34 |
| 4 | 0.806 | 0.937 | 3.90 of 4.85 (80 %) | 4.75 of 4.85 (98 %) | 17 / 33 |
| 16 | 0.694 | 0.809 | 11.70 of 17.20 (68 %) | 15.95 of 17.20 (93 %) | 15 / 31 |

- CIGMA degrades more slowly than the union (0.809 against 0.694 at k = 16).
- Learned, copy-aware reliabilities send 93 % of the poisoned edges to human review at
  k = 16 (68 % with fixed values), at the price of about twice as many true edges in the queue.

## E8 — Guaranteed false-discovery rate on accepted edges (`ext/conformal.py`)

Split design: a scorer is trained on 60 poisoned scenarios, calibrated on the false edges
of 60 other scenarios, and tested on 60 more. Edges are accepted by Benjamini-Hochberg
on conformal p-values.

| Rule | Observed FDR (95 % CI) | Power (true edges kept) |
|---|---|---|
| Accept all (CIGMA default) | 0.219 (0.195–0.243) | 1.000 |
| Fixed threshold 0.85 | 0.102 (0.083–0.121) | 0.520 |
| Conformal, α = 0.05 | **0.016** (0.009–0.025) | 0.412 |
| Conformal, α = 0.10 | **0.021** (0.014–0.029) | 0.499 |
| Conformal, α = 0.20 | **0.042** (0.031–0.053) | 0.665 |

- The guarantee holds in every setting (observed FDR well below α), whereas the fixed
  threshold gives no guarantee and here sits right at 10 %.
- At α = 0.20 the conformal rule keeps more true edges (66.5 %) than the 0.85 threshold
  (52 %) with less than half its false-edge rate.
- Limit: the guarantee assumes the calibration false edges look like deployment ones
  (exchangeability). In deployment, calibration comes from the analyst's verification queue.
- Supports computed with learned reliabilities separate true and false edges poorly
  (AUC 0.56, against 0.78 with fixed values): the learned scorer combines both.

## E9 — Urgency / breakage Pareto front (`ext/ordering.py`, `blended_order`)

| λ (0 = urgency, 1 = no-break) | 0.0 | 0.4 | 0.7 | 0.8 | 1.0 |
|---|---|---|---|---|---|
| MOVR | 0.04 | 0.03 | 0.01 | **0.00** | 0.00 |
| Exposure AUC | 0.408 | 0.421 | 0.437 | 0.440 | 0.439 |

From λ = 0.8, the plan is breakage-free and certified; the operator pays +0.032 of exposure
for it. The curve is not monotone in between (λ = 0.6 has 6 break-steps), which is why the
certificate, not the weight, decides validity.

## E10 — Signed observations, ML-DSA-65 in DSSE envelopes (`ext/attestation.py`)

Poisoning with k = 8, three attacker models:

| Scenario | Poisoned edges accepted | Typed-edge F1 |
|---|---|---|
| Outsider (own key, not trusted) | **0** (21 envelopes rejected) | 1.000 |
| Insider (stolen key of a trusted tool) | 11 | 0.872 |
| Same, after revoking that key | **0** (38 envelopes rejected) | 0.867 |

- Signatures stop outsiders completely and make insiders attributable: one revocation
  removes every poisoned edge, at the cost of the honest observations signed with that
  key until they are re-signed.
- Cost (pure-Python reference implementation): 52.7 ms to sign and about 7 ms to verify
  per observation; public key 1,952 bytes, signature 3,309 bytes. A C implementation (liboqs)
  is orders of magnitude faster; these numbers are an upper bound.

## Third batch (E11–E16, compliance, ZK)

Command: `make extensions-v3` (full run ≈ 25 min on 2 cores; `--quick` ≈ 3 min).
Outputs: `results/extensions/e11_*`, `e14_*`, `e15_*`, `e16_*`, `summary_v3.json`.

| Exp. | Question | Result (L0 / synthetic) |
|---|---|---|
| E11 | Is the certified CP-SAT plan better than the greedy plan? | L0: optimum proven, certificate `592fea8e…`. Synthetic: greedy excess 22.5 % (50 units, gap 1.5 %), 5.7 % (500), 0.4 % (5,000). All plans pass `check_plan`. |
| E13 | How do the orders compare? | MOVR / exposure: primary 0.04 / 0.408; interop-aware 0.00 / 0.439; Sharma 2026 0.07 / 0.451; CP-SAT 0.00 / 0.425. |
| E14 | Is the HNDL/TNFL ranking robust to its parameters? | Sobol, 1,792 evaluations: Kendall τ = 1 everywhere; anchors always ranked first. |
| E15 | Does the fail-closed validator resist injected candidates? | 0 / 1,779 adversarial candidates accepted; 300 / 300 valid ones accepted. |
| E16 | Is the version log append-only? | RFC 6962 consistency proofs verify (2 hashes); rewritten history detected. |
| Compliance | Which rules are violated, with which evidence? | NIST IR 8547: 18, HVA-SIG-2031: 5, HVA-KEX-2030: 13, EU high-risk 2030: 15, ANSSI confidentiality 2030: 15. Every finding carries evidence (2-hop). |
| ZK | Can we prove "policy holds" without revealing the inventory? | Groth16 circuit `zk/policy.circom` (32 assets). Single-party local setup: research use only. |

Scaling (`results/scaling/`): 1.8 s / 28 s / 165 s graph build at ×10 / ×43 / ×100 (2,003 nodes); near-quadratic because of pairwise alias comparison.
