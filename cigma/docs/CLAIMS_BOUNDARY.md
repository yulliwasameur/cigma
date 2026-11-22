# Claims boundary

## Supported by this repository

The current clean-room release supports claims that:

- a deterministic implementation exists for the declared observation contract and closed ontology;
- the generated public fixture and oracle are stored in separate directories;
- the fixture shape is 46 entity observations, 34 relation observations, 23 oracle entities, and 34 oracle edges;
- six source families are represented with the declared per-source counts;
- ten complete-fixture methods and six leave-one-source-out runs execute;
- 384 paired robustness method runs and 24 planned statistical contrasts execute;
- every accepted node and edge has evidence identifiers known to the input;
- the optional-model validator is fail-closed and cannot mutate the graph;
- the two-phase external protocol checks source/configuration/code/prediction bindings before oracle loading;
- current tests and result manifests can be regenerated from a clean extraction.

## Not supported without additional evidence

Do not use this repository to claim:

- byte-for-byte recovery of the lost 2026 artifact;
- reproduction of the historical 59-test codebase or its exact module bytes;
- reproduction of the historical 30 live model responses or their model-service variability;
- organizational, enterprise, or cross-institutional accuracy;
- expert agreement with the prioritization policy;
- analyst-effort reduction, usability, or production throughput;
- production vendor connector coverage;
- prompt-injection immunity or a general hallucination rate;
- automatic choice or execution of a PQC migration;
- superiority of the primary order over all weighted policies;
- a public DOI, public code release, or external independent replication.

## Historical values versus clean-room values

Historical manuscript values can be used to explain the design target, but must not be relabelled as outputs of this repository. Every table generated from this code should carry the repository version, configuration digest, fixture digest, and result-manifest hash.

If a manuscript value and a current output disagree, the correct options are:

1. update the manuscript to the current result;
2. state that the manuscript used a lost historical implementation;
3. rerun a newly frozen protocol and report the new value.

Hard-coding the old value into the implementation or fixture is prohibited.
