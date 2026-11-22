# Optional bounded-model adapter

The principal CIGMA graph is deterministic and model-free. The optional model
adapter is a candidate generator only.

## Request contents

The bounded request contains:

- existing canonical node IDs and entity types;
- public relation observations, locators, and excerpts;
- the closed relation signatures;
- the two allow-listed path rules.

It excludes:

- the evaluator oracle and observation-to-truth maps;
- graph rankings and impact scores;
- source credentials and tools;
- permission to create nodes or extend the ontology.

## Deterministic validation

A candidate is rejected if it has a malformed batch shape, duplicate claim ID,
unknown node or evidence ID, invalid type signature, duplicate evidence ID,
evidence absent from the quality-gated graph, an unsupported direct triple,
unrelated direct evidence, or an incomplete/undeclared path.

The module exposes an injected transport interface rather than loading an API
key. This allows a caller to archive the exact request/response externally while
keeping the core package credential-free.
