# Security policy

This repository is private research software. It processes evidence that may identify services, endpoints, certificates, software dependencies, pipelines, business data classes, and operational technology.

## Do not commit

- private keys, API keys, passwords, tokens, `.env` files;
- unredacted confidential infrastructure exports;
- personal data not required by the scientific protocol;
- external-model raw inputs unless disclosure is authorized;
- evaluator truth in a branch or package intended for blind phase-1 prediction.

## Operational controls

- use read-only source connectors;
- retain minimum evidence excerpts and stable locators;
- encrypt stored evidence and restrict repository access;
- separate public observations from oracle custody;
- inspect candidate-model output as untrusted data;
- do not allow the optional model to call tools or mutate the graph;
- validate every evidence digest and ontology signature;
- rotate any credential accidentally exposed and purge it from Git history.

## Reporting

Report a suspected vulnerability privately to the repository owner. Include the affected version, reproducible steps, impact, and a proposed fix when available. Do not place sensitive evidence in a public issue.
