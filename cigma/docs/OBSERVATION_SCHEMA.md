# CIGMA observation schema

CIGMA accepts evidence-preserving observations rather than vendor-specific files. A source adapter converts TLS, PKI, CBOM, CI/CD, CMDB, or OT records into two newline-delimited JSON streams.

## Entity observation

One JSON object per line in `entities.jsonl`:

```json
{
  "observation_id": "ent-tls-001",
  "source": "tls",
  "local_key": "endpoint-0",
  "entity_type": "endpoint",
  "identifiers": {"endpoint_uri": "tls://api.example:443"},
  "attributes": {"protocol": "TLS1.3"},
  "quality": 0.98,
  "collected_at": "2026-08-19T00:00:00+00:00",
  "locator": "sslyze/api.json#/endpoints/0",
  "evidence_excerpt": "api.example:443 negotiated TLS1.3",
  "evidence_sha256": "<lowercase SHA-256 of evidence_excerpt>"
}
```

| Field | Type | Constraint |
|---|---|---|
| `observation_id` | string | globally unique, non-empty |
| `source` | enum | `tls`, `pki`, `cbom`, `cicd`, `cmdb`, `ot` |
| `local_key` | string | non-empty source-local identifier |
| `entity_type` | enum | one of the eight entity types below |
| `identifiers` | object<string,string> | strong and/or alias identifiers |
| `attributes` | object | typed source-reported attributes; unknowns may be absent |
| `quality` | number | closed interval `[0,1]` |
| `collected_at` | ISO-8601 string | timezone recommended |
| `locator` | string | replayable location within retained evidence |
| `evidence_excerpt` | string | retained source excerpt, treated as untrusted data |
| `evidence_sha256` | 64-char hex | exact SHA-256 of UTF-8 `evidence_excerpt` |

## Relation observation

One JSON object per line in `relations.jsonl`:

```json
{
  "observation_id": "rel-tls-001",
  "source": "tls",
  "subject_observation_id": "ent-tls-endpoint-001",
  "predicate": "PRESENTS",
  "object_observation_id": "ent-tls-cert-001",
  "quality": 0.98,
  "collected_at": "2026-08-19T00:00:00+00:00",
  "locator": "sslyze/api.json#/certificate_deployments/0",
  "evidence_excerpt": "endpoint api.example:443 presents fingerprint FPR-001",
  "evidence_sha256": "<lowercase SHA-256 of evidence_excerpt>"
}
```

Both endpoint observation IDs must occur in `entities.jsonl`. The predicate and endpoint types must satisfy the closed ontology after identity resolution.

## Closed entity ontology

1. `service`
2. `endpoint`
3. `certificate`
4. `algorithm`
5. `software_component`
6. `pipeline`
7. `data_class`
8. `device`

## Closed relation ontology

| Predicate | Allowed domain -> range |
|---|---|
| `HOSTS` | service -> endpoint |
| `PRESENTS` | endpoint -> certificate |
| `USES` | certificate -> algorithm; software_component -> algorithm; service -> software_component; service -> algorithm; device -> algorithm |
| `ISSUED-BY` | certificate -> certificate |
| `DEPENDS-ON` | service -> service; service -> device |
| `DEPLOYS` | pipeline -> service |
| `PROCESSES` | service -> data_class |
| `PROTECTS` | algorithm -> data_class; certificate -> data_class |

## Identity keys

Configured strong keys:

```text
certificate_fingerprint, spki_fingerprint, purl, service_uid,
device_serial, algorithm_id, endpoint_uri, pipeline_uid, data_uid
```

Configured alias keys:

```text
service_name, hostname, repository_path, deployment_name
```

Strong-key equality can merge same-type observations. Alias merging is permitted only for compatible types when no conflicting strong identifier is present. Canonical IDs hash the entity type and a deterministic anchor, so input order does not affect the identifier.

## Quality and provenance

The default entity and relation quality gates are both `0.40`. Records below the relevant gate are quarantined for full CIGMA, rather than silently deleted from the audit trail. Every accepted node retains its entity-observation IDs. Every accepted edge retains relation-observation IDs; a derived edge retains the union of the complete path evidence.

## Allow-listed composition

Only two path rules can introduce a derived edge:

```text
service HOSTS endpoint
endpoint PRESENTS certificate
certificate USES algorithm
=> service USES algorithm
```

and

```text
service USES software_component
software_component USES algorithm
=> service USES algorithm
```

Any other multi-hop inference is absent unless a future configuration and implementation version explicitly adds a rule.

## Minimal end-to-end example

Run:

```bash
PYTHONPATH=src python examples/minimal/generate.py
```

The example emits five entity observations and three direct relation observations. Two endpoint observations—one from TLS and one from CMDB—share `endpoint_uri=tls://demo.local:443` and resolve to one canonical endpoint. CIGMA then accepts:

```text
service HOSTS endpoint
endpoint PRESENTS certificate
certificate USES RSA-2048
```

and derives:

```text
service USES RSA-2048
```

The resulting edge records all three relation evidence IDs and the rule identifier `HOSTS_o_PRESENTS_o_USES`. The exact input and result files are committed under `examples/minimal/`.

## Feeding a new real system

1. Retain the original vendor export or an authorized redacted copy.
2. Implement or configure an adapter that emits the exact JSONL contract above.
3. Make locators stable and meaningful within the retained export.
4. Compute `evidence_sha256` from the exact retained excerpt; do not hash a different object.
5. Avoid placing oracle IDs, gold labels, or migration priorities in public observations.
6. Run public prediction and seal the output before any evaluator opens the oracle.
7. Build the oracle independently and store it outside the public tree.
