# Reproducibility protocol

## Supported interpreter

- Python: `>=3.11`
- CI matrix: Python 3.11 and 3.12
- exact dependencies: `requirements.txt` and `requirements-dev.txt`

## Full reproduction

From the repository root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
PYTHONDONTWRITEBYTECODE=1 make verify
```

Expected release-0.1.0 milestones:

```text
61 tests pass
10 complete methods
6 leave-one-source-out conditions
384 paired robustness method runs
128 deletion scenarios
24 planned contrasts
prediction seal round trip passes
```

## Determinism

The generator uses fixed content and stable serialization. The campaign stores seed values and applies the same perturbed public observations to every paired method. Bootstrap and randomization routines have configured seeds. All JSON output is sorted and indented; JSONL output is canonicalized.

Run the full verification twice and compare:

```bash
make verify
python scripts/hash_manifest.py . > /tmp/cigma-first.json
make verify
python scripts/hash_manifest.py . > /tmp/cigma-second.json
diff -u /tmp/cigma-first.json /tmp/cigma-second.json
```

Exclude interpreter caches and environment directories from scientific file comparisons.

## Public/oracle isolation

`data/cigma_lab/public/` contains only entity and relation observations. `data/cigma_lab/oracle/` contains truth nodes, truth edges, mappings, priorities, and critical targets. The prediction phase has no oracle argument.

For a real replication, place the oracle under separate custody and record its tree digest before phase 2.

## Result manifests

The campaign manifest binds the configuration and input tree. The two-phase seal binds public data, configuration, source implementation, methods, and prediction files. `scripts/hash_manifest.py` provides a repository-wide file inventory for release packaging.

## Statistical unit

For missing-observation robustness, one deletion mask/seed is the paired experimental unit. Edge or node rows are not treated as independent samples. Confidence intervals and paired tests therefore resample or randomize at the scenario level.
