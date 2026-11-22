# Datasheet for CIGMA-Bench (after Gebru et al., "Datasheets for Datasets")

**Motivation.** No public benchmark scores cryptographic inventories against an independent oracle,
nor migration orders by breakage and exposure. CIGMA-Bench fills that gap.

**Composition.** L0: synthetic but realistic observations (TLS scans, PKI, CBOM, CI/CD, CMDB, OT) of a
small hospital-like system; every observation has a locator and a SHA-256 of its evidence excerpt.
L1: observations collected from Google's public Online Boutique demo deployed by the authors.
No personal data. No real organization's infrastructure.

**Collection.** L0 is generated deterministically (`benchmark.py`, fixed seeds). L1 is collected by
the scripts in `l1-deployed/collect/` after 15 minutes of synthetic traffic.

**Labelling.** L0 oracle is written with the generator, in a separate directory never read by the
prediction phase. L1 oracle: two independent annotators blind to predictions, one arbiter, Cohen's
kappa reported per entity and relation type.

**Uses.** Evaluating inventory fusion, entity resolution, dependency reconstruction, migration
planning, and LLM-assisted candidate generation under a fail-closed validator.
**Not for:** claims about any real organization's posture, or production throughput.

**Distribution.** Code MIT; data and results CC BY 4.0; third-party components under their own
licences (Online Boutique and Istio: Apache-2.0).

**Maintenance.** Maintained by the authors; issues and pull requests on GitHub; versioned on Zenodo.

**Known limits.** L0 is small (23 entities). The original 2026 implementation and its 30 model
responses were lost; all numbers come from the clean-room v0.1.0 reimplementation and its extensions.
