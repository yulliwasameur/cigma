# Clean-room reconstruction notice

This repository is a **new reference implementation reconstructed in August 2026** from the published CIGMA specification and surviving audit documents. It is not the lost historical `CIGMA_artifact.zip`, is not byte-identical to that implementation, and does not recover missing historical raw model responses or their original manifests.

The lost artifact was previously audited as a 357-entry archive with SHA-256:

```text
da0133091b3b405727eeb415ed243dccce5c843ce871c42f0fae406a3edb5adf
```

That digest is retained solely as historical provenance. No file in this repository is presented as matching it.

## Rules for scientific use

1. Label this code as **CIGMA Reference Implementation — clean-room rebuild**.
2. Treat every result under `results/` as a new run unless a manifest explicitly says otherwise.
3. Do not cite the old 59-test count as a result of this repository; this release has its own test count and manifests.
4. Do not claim the historical 30-call optional-model cohort has been reproduced.
5. If current outputs differ from a manuscript, update the manuscript or explain the version difference; never hard-code historical values.
6. Keep public observations and evaluator-only truth separated in any external replication.
