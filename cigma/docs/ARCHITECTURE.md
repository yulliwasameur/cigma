# Architecture

## Trust boundary

The principal pipeline is deterministic. Source adapters and source records may be wrong, stale, duplicated, contradictory, or malicious. The configuration, ontology, validator, evidence store, and evaluator custody controls are trusted components for the purposes of this implementation.

The optional model is untrusted and candidate-only. It has no mutation path to the principal graph.

## Modules

| Module | Responsibility |
|---|---|
| `schema.py` | serializable observations, nodes, edges, graph snapshot, validation |
| `ontology.py` | eight entity types, eight typed predicates, two path rules |
| `adapters/` | source-family conversion to the public observation contract |
| `normalize.py` | deterministic value normalization |
| `resolution.py` | quality gates, strong/alias/TF-IDF resolution, canonical IDs, fusion, support |
| `pipeline.py` | method registry, direct typed claims, path composition, graph invariants |
| `scoring.py` | Q/H/C/X/B, bounds, tiers, Pareto fronts, comparators, VERIFY |
| `evaluation.py` | evaluator-only reconstruction, ranking, calibration, and FP metrics |
| `stats.py` | seeded bootstrap, paired randomization, Holm correction |
| `experiment.py` | complete fixture, source ablations, paired robustness campaign |
| `openai_adapter.py` | bounded candidate schema and deterministic fail-closed validation |
| `external_validation.py` | public-only prediction seal and delayed oracle evaluation |
| `benchmark.py` | deterministic clean-room CIGMA-Lab generator and separate truth tree |
| `cli.py` | command-line entry points |

## Pipeline phases

### 1. Ingestion and validation

Entity and relation observations are parsed independently. IDs must be unique, relation endpoints must exist, timestamps must parse, quality must lie in `[0,1]`, and the SHA-256 digest must match the retained excerpt.

### 2. Quality gate

Full CIGMA quarantines observations below configured entity or relation thresholds. Ablation methods can disable this gate. Quarantined observations remain visible in graph metadata.

### 3. Identity resolution

A union-find structure merges same-type observations in a stable order. Strong identifier equality is applied first. Alias merging is allowed only when the clusters have no conflicting strong key. The TF-IDF comparator uses character n-gram similarity over public identifier values and a frozen threshold; it never reads the oracle.

Canonical IDs are deterministic hashes of the entity type and selected stable anchor.

### 4. Attribute fusion and node support

Numeric attributes use reliability- and quality-weighted means. Boolean attributes use weighted majority. Categorical attributes use the value with the highest total weighted support and a deterministic tie-break.

For observation `i`, support term `p_i = quality_i * source_reliability_i`. Cluster support is noisy-OR:

```text
c_v = 1 - product_i(1 - p_i)
```

### 5. Direct typed claims

Relation observations surviving the gate map their public endpoints to canonical nodes. The ontology checks the domain and range. Same canonical triples combine their evidence and support. Rejected and quarantined IDs remain separate.

### 6. Path composition

Only the two declared rules in `ontology.py` can derive an edge. Derived support is the minimum edge support on the path multiplied by `path_penalty^(path_length-1)`. Provenance is the sorted union of path evidence IDs.

### 7. Migration factors and ordering

For ranked asset types, CIGMA derives:

- `Q`: configured quantum-vulnerability policy value;
- `H`: HNDL urgency from `Q`, data lifetime, migration time, and policy horizon;
- `C`: criticality;
- `X`: exposure;
- `B`: normalized transitive dependent-service blast radius.

Unknown values generate lower and upper vectors by substituting 0 and 1. The primary order is:

1. descending upper tier;
2. descending lower tier;
3. Pareto front within an equal `(upper_tier, lower_tier)` stratum;
4. deterministic lexicographic upper-vector order and canonical ID.

Evidence confidence and migration feasibility are exported separately. Confidence cannot reduce urgency. An item enters `VERIFY` when it can be high impact and its tier is uncertain or its evidence support is below threshold.

### 8. Evaluation

The evaluator is the only module that receives truth. It compares predicted clusters and typed triples with evaluator-only mappings. It also reports duplicate, unmappable, and oracle-absent edge false positives separately from unsupported provenance.

### 9. Two-phase external validation

Phase 1 receives public observations and configuration only, writes predictions, and seals:

- public tree digest;
- configuration digest;
- source-only implementation digest;
- method list;
- prediction file digests.

Phase 2 verifies every binding and every prediction before opening the oracle directory. Interpreter caches are deliberately excluded from the implementation digest because they are not source code and can be created by ordinary imports.
