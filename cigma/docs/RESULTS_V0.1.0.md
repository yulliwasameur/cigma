# Clean-room results — v0.1.0

These are **new outputs from the clean-room implementation**, not recovered historical results.

## Complete fixture

| Method | Asset F1 | Pairwise F1 | B3 F1 | Typed-edge F1 | Edge FP | Critical misses |
|---|---:|---:|---:|---:|---:|---:|
| TLSInventory | 0.5161 | 0.0526 | 0.1259 | 0.3000 | 0.0000 | 10 |
| CBOMInventory | 0.5000 | 0.0000 | 0.9412 | 0.2927 | 0.1429 | 11 |
| SourceUnion | 0.6667 | 0.0000 | 0.6866 | 0.8529 | 0.1471 | 0 |
| ExactDirect | 0.9200 | 0.8261 | 0.9419 | 0.9063 | 0.0606 | 0 |
| TFIDF-Cosine | 0.9200 | 0.8261 | 0.9419 | 0.9063 | 0.0606 | 0 |
| CIGMA | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 | 0 |

Values should always be read from `results/default/metrics/method_metrics.csv`; this page is a human summary.

## Ablation interpretation

- removing aliases preserves truth-node recall but creates duplicate clusters and lowers entity-resolution quality;
- removing path composition preserves the entities but limits relation recall to directly observed triples;
- removing the quality gate admits the two low-quality distractors/false claims and creates false positives;
- uniform reliability leaves the full graph unchanged but changes support and therefore the VERIFY queue.

## Robustness

The campaign evaluates nominal entity-observation deletion probabilities `0`, `0.10`, `0.25`, and `0.50`, with 32 paired seeds and three methods per scenario. Relations survive only when both endpoints survive and the relation draw succeeds, so relation loss is steeper than the nominal entity loss.

At nominal 50% deletion, clean-room CIGMA has approximately:

- asset F1: `0.8257` mean;
- typed-edge F1: `0.2082` mean.

Exact confidence intervals and all paired comparisons are in:

- `results/default/metrics/robustness_aggregate.csv`;
- `results/default/metrics/statistics.csv`.

## Ranking caution

The v0.1.0 priority labels and configuration are author-defined. Current NDCG values differ from the lost implementation because this is a new fixture realization and new code. Ranking values are diagnostics for the clean-room scenario, not expert validation.
