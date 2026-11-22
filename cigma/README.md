# CIGMA Reference Implementation

**Clean-room reference implementation** of *CIGMA: Provenance-Preserving Cryptographic Dependency Reconstruction for Post-Quantum Network Migration*.

CIGMA turns heterogeneous TLS, PKI, CBOM, CI/CD, CMDB, and OT observations into a deterministic, typed dependency graph. Every accepted node and edge retains locator-backed evidence. The implementation includes stable identity resolution, quality-gate quarantine, attribute fusion, support scoring, two allow-listed path-composition rules, migration prioritization, comparator methods, ablations, robustness experiments, evaluator-only truth, and a bounded optional-model validator.

> [!IMPORTANT]
> This repository is **not** the lost historical 357-entry artifact. It is a new implementation reconstructed from the published specification and surviving audit documents. Do not describe its outputs as a byte-for-byte reproduction of the historical campaign. See [NOTICE.md](NOTICE.md) and [docs/CLAIMS_BOUNDARY.md](docs/CLAIMS_BOUNDARY.md).

## Current verified state

Release candidate: **0.1.0-clean-room**

```text
61/61 tests                         PASS
complete-fixture methods           10
leave-one-source-out runs           6
paired robustness method runs     384
robustness scenarios              128
planned statistical contrasts      24
two-phase prediction seal          PASS
```

The current clean-room fixture contains 46 entity observations and 34 relation observations from six source families, with evaluator-only truth containing 23 entities and 34 typed edges. These counts reproduce the declared benchmark shape; the records, hashes, results, and manifests are newly generated.

## Quick start

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
make verify
```

`make verify` performs all of the following:

1. regenerates the public CIGMA-Lab observations and separate oracle;
2. runs the complete test suite;
3. executes ten methods on the complete fixture;
4. executes six source ablations;
5. executes 384 paired dropout runs and 24 planned contrasts;
6. regenerates paper macros and robustness figures;
7. seals public-only predictions and verifies them before oracle loading.

## Common commands

```bash
make generate       # regenerate data/cigma_lab
make test           # regenerate fixture and run tests
make campaign       # regenerate the complete deterministic evaluation
make seal-demo      # demonstrate public prediction sealing and delayed oracle access
make verify         # full clean-room verification

cigma generate --output data/cigma_lab
cigma run --entities data/cigma_lab/public/entities.jsonl \
          --relations data/cigma_lab/public/relations.jsonl \
          --config configs/default.yaml --method cigma \
          --output results/one-run
```

## Input boundary for a new real system

Adapters must emit two JSONL streams:

- `entities.jsonl`: one `EntityObservation` per line;
- `relations.jsonl`: one `RelationObservation` per line.

The exact field-level contract, ontology, evidence rules, and a minimal end-to-end example are documented in [docs/OBSERVATION_SCHEMA.md](docs/OBSERVATION_SCHEMA.md). The runnable example is under [`examples/minimal/`](examples/minimal/).

## Architecture

```text
source exports
  -> source-family adapters
  -> normalized evidence observations
  -> quality gate / quarantine
  -> stable identity resolution
  -> direct typed claims
  -> allow-listed path composition
  -> evidence-preserving graph
  -> impact/support separation
  -> tier -> Pareto -> lexicographic order
  -> VERIFY queue and evaluator-only metrics
```

The closed ontology contains eight entity types and eight predicates. Only these path rules can derive a new edge:

- `HOSTS o PRESENTS o USES` -> `service USES algorithm`;
- `USES o USES` -> `service USES algorithm`.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Methods

The executable registry contains:

- `tls_inventory`
- `cbom_inventory`
- `source_union`
- `exact_direct`
- `tfidf_cosine`
- `cigma`
- `cigma_no_aliases`
- `cigma_no_paths`
- `cigma_no_quality_gate`
- `cigma_uniform_reliability`

The robustness campaign deliberately compares `source_union`, `exact_direct`, and `cigma` on the same deletion masks.

## Current clean-room results

On the newly generated complete fixture, full CIGMA obtains 1.0 asset, pairwise entity-resolution, B3, and typed-edge F1, with no edge false positive, no unsupported accepted assertion, and no critical-target miss. These values establish consistency with this finite fixture only. They are **not** an estimate of enterprise accuracy.

The full machine-readable outputs are in [`results/default/`](results/default/). A concise interpretation is in [docs/RESULTS_V0.1.0.md](docs/RESULTS_V0.1.0.md).

## Optional model boundary

`src/cigma/openai_adapter.py` contains a candidate-only contract and deterministic fail-closed validator. The core campaign makes no network call and requires no API key. A live transport must be explicitly injected by the caller. Candidate output cannot create nodes, extend the ontology, bypass the quality-gated graph, or mutate the principal graph.

No lost historical model responses are recreated or claimed by this repository.

## Reproducibility and integrity

- canonical JSON and JSONL serialization;
- order-stable canonical identifiers;
- SHA-256 evidence validation;
- separate public and evaluator-only directories;
- deterministic seeds and paired deletion masks;
- versioned configuration;
- result manifests and tree hashes;
- source-only implementation seal that excludes interpreter caches.

See [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md).

## Repository map

```text
configs/                 versioned thresholds and policies
data/cigma_lab/          newly generated public fixture and separate oracle
docs/                    contracts, architecture, claims, results, reproduction
examples/minimal/        smallest end-to-end new-system example
results/default/         current deterministic campaign outputs
scripts/                 paper macros, figures, hashes, full runner
src/cigma/               implementation
tests/                   61 unit and invariant tests
```

A complete file inventory is in [MANIFEST.md](MANIFEST.md).

## License and disclosure

This private research repository is currently all-rights-reserved; see [LICENSE](LICENSE). It is intended for author-controlled validation before any public artifact release. Security reports should follow [SECURITY.md](SECURITY.md).
