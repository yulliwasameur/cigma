# CIGMA-Bench — a benchmark for evidence-grounded cryptographic inventory and post-quantum migration

## The task (one sentence)
From public observations only, build a typed cryptographic dependency graph whose every node and
edge cites its evidence, and a migration order; you are scored against a hidden, independently
annotated oracle.

## Levels
| Level | What | Status |
|---|---|---|
| L0 controlled | CIGMA-Lab: 46 entity / 34 relation observations, 23 entities, 34 typed edges, 6 source families | released |
| L0+ adversarial | Same, with disagreeing tool views, poisoning (k = 0…16), signed observations | released (generators) |
| L1 deployed | Online Boutique (11 microservices) on Kubernetes + Istio mTLS + 2-level PKI, 6 source families, 2 annotators + arbiter | collection scripts released; oracle after annotation |
| L2 scale | Replicated / generated enterprises up to 10,000 assets | generator released |

## How to submit
1. Produce `submission.json` (schema `cigma-bench-submission-v1`, see `cigma/src/cigma/ext/benchmark_api.py`).
   `python scripts/cigma_eval.py --make-baseline cigma --out submission.json` writes a valid example.
2. Score locally on L0: `python scripts/cigma_eval.py --submission submission.json --data data/cigma_lab`.
3. For hidden levels (L1), seal first (`seal/seal.py`), send the submission and the seal digest;
   the evaluator verifies the seal before opening the oracle (protocol model-checked, `formal/`).

## Metrics (all reported)
Pairwise F1 and B³ (entity resolution), typed-edge F1, edge false-positive rate, unsupported
nodes/edges (must be 0 for a valid entry), NDCG@10, MOVR (Eq. 3 of the paper), exposure AUC.

## Standard exports
CycloneDX 1.6 (CBOM view) and W3C PROV-O JSON-LD: `ext/benchmark_api.to_cyclonedx`, `to_prov_jsonld`.

## Leaderboard (L0, reference methods)
| Method | Pairwise F1 | B³ F1 | Typed-edge F1 | Edge FP | MOVR | Exposure AUC |
|---|---|---|---|---|---|---|
| SourceUnion | 0.000 | 0.687 | 0.853 | 0.147 | 0.070 | 0.390 |
| ExactDirect | 0.826 | 0.942 | 0.906 | 0.033 | 0.040 | 0.410 |
| CIGMA (primary order) | 1.000 | 1.000 | 1.000 | 0.000 | 0.040 | 0.408 |

## Where it lives
GitHub (code, issues, contributions) · Zenodo (versioned DOI, all data and results) ·
Hugging Face Datasets (data + dataset card) · Docker image (one-command reproduction).
Publication waits for the camera-ready version (no preprint during ICISSP review).

## Versioning and maintenance
Semantic versions; `CHANGELOG.md`; new tools or source families are added through pull requests
with a fixture and an oracle extension; monthly CI re-runs every level.
