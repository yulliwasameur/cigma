"""Deterministic CIGMA-Lab fixture generator.

This is a clean-room fixture reconstructed from the published specification. It
is not byte-identical to the lost 2026 artifact. Public observations and the
oracle are written to separate directories.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .adapters import (
    AdapterOutput,
    adapt_cbom_records,
    adapt_cicd_records,
    adapt_cmdb_records,
    adapt_ot_records,
    adapt_pki_records,
    adapt_tls_records,
)
from .config import canonical_json
from .io import sha256_tree, write_json, write_jsonl
from .schema import EntityType, RelationType, SourceFamily, validate_observations


FIXTURE_ID = "cigma-lab-clean-room-v1"
COLLECTED_AT = "2026-08-19T12:00:00+00:00"


def _edge_id(subject: str, predicate: RelationType, object_: str) -> str:
    return f"edge::{subject}::{predicate.value}::{object_}"


def truth_nodes() -> list[dict[str, Any]]:
    nodes = [
        ("svc_edge", EntityType.SERVICE, 2),
        ("svc_patient", EntityType.SERVICE, 3),
        ("svc_auth", EntityType.SERVICE, 3),
        ("svc_db", EntityType.SERVICE, 3),
        ("svc_ot", EntityType.SERVICE, 2),
        ("ep_edge", EntityType.ENDPOINT, 2),
        ("ep_patient", EntityType.ENDPOINT, 3),
        ("ep_db", EntityType.ENDPOINT, 3),
        ("ep_ot", EntityType.ENDPOINT, 2),
        ("cert_edge", EntityType.CERTIFICATE, 2),
        ("cert_patient", EntityType.CERTIFICATE, 3),
        ("cert_db", EntityType.CERTIFICATE, 3),
        ("cert_ot", EntityType.CERTIFICATE, 2),
        ("cert_root", EntityType.CERTIFICATE, 1),
        ("alg_rsa", EntityType.ALGORITHM, 0),
        ("alg_ecdsa", EntityType.ALGORITHM, 0),
        ("alg_aes", EntityType.ALGORITHM, 0),
        ("comp_patient", EntityType.SOFTWARE_COMPONENT, 3),
        ("comp_auth", EntityType.SOFTWARE_COMPONENT, 2),
        ("pipe_core", EntityType.PIPELINE, 1),
        ("data_patient", EntityType.DATA_CLASS, 0),
        ("data_auth", EntityType.DATA_CLASS, 0),
        ("dev_plc", EntityType.DEVICE, 2),
    ]
    return [
        {
            "truth_id": truth_id,
            "entity_type": entity_type.value,
            "priority": priority,
            "critical_target": priority >= 2
            and entity_type
            in {
                EntityType.SERVICE,
                EntityType.ENDPOINT,
                EntityType.CERTIFICATE,
                EntityType.SOFTWARE_COMPONENT,
                EntityType.DEVICE,
            },
        }
        for truth_id, entity_type, priority in nodes
    ]


def truth_edges() -> tuple[list[dict[str, Any]], set[tuple[str, RelationType, str]]]:
    direct: list[tuple[str, RelationType, str]] = [
        ("svc_edge", RelationType.HOSTS, "ep_edge"),
        ("svc_patient", RelationType.HOSTS, "ep_patient"),
        ("svc_db", RelationType.HOSTS, "ep_db"),
        ("svc_ot", RelationType.HOSTS, "ep_ot"),
        ("ep_edge", RelationType.PRESENTS, "cert_edge"),
        ("ep_patient", RelationType.PRESENTS, "cert_patient"),
        ("ep_db", RelationType.PRESENTS, "cert_db"),
        ("ep_ot", RelationType.PRESENTS, "cert_ot"),
        ("cert_edge", RelationType.USES, "alg_rsa"),
        ("cert_patient", RelationType.USES, "alg_rsa"),
        ("cert_db", RelationType.USES, "alg_rsa"),
        ("cert_ot", RelationType.USES, "alg_ecdsa"),
        ("cert_edge", RelationType.ISSUED_BY, "cert_root"),
        ("cert_patient", RelationType.ISSUED_BY, "cert_root"),
        ("cert_db", RelationType.ISSUED_BY, "cert_root"),
        ("cert_ot", RelationType.ISSUED_BY, "cert_root"),
        ("svc_patient", RelationType.USES, "comp_patient"),
        ("svc_auth", RelationType.USES, "comp_auth"),
        ("comp_patient", RelationType.USES, "alg_rsa"),
        ("comp_auth", RelationType.USES, "alg_ecdsa"),
        ("pipe_core", RelationType.DEPLOYS, "svc_patient"),
        ("pipe_core", RelationType.DEPLOYS, "svc_auth"),
        ("svc_patient", RelationType.PROCESSES, "data_patient"),
        ("svc_auth", RelationType.PROCESSES, "data_auth"),
        ("svc_edge", RelationType.DEPENDS_ON, "svc_patient"),
        ("svc_patient", RelationType.DEPENDS_ON, "svc_auth"),
        ("svc_patient", RelationType.DEPENDS_ON, "svc_db"),
        ("svc_auth", RelationType.DEPENDS_ON, "svc_db"),
        ("svc_ot", RelationType.DEPENDS_ON, "dev_plc"),
    ]
    derived: list[tuple[str, RelationType, str]] = [
        ("svc_edge", RelationType.USES, "alg_rsa"),
        ("svc_patient", RelationType.USES, "alg_rsa"),
        ("svc_db", RelationType.USES, "alg_rsa"),
        ("svc_ot", RelationType.USES, "alg_ecdsa"),
        ("svc_auth", RelationType.USES, "alg_ecdsa"),
    ]
    rows = [
        {
            "edge_id": _edge_id(subject, predicate, object_),
            "subject": subject,
            "predicate": predicate.value,
            "object": object_,
            "derived": triple in set(derived),
        }
        for triple in direct + derived
        for subject, predicate, object_ in [triple]
    ]
    return rows, set(direct)


def _build_public_observations() -> AdapterOutput:
    combined = AdapterOutput()

    tls_records = [
        {
            "endpoint_local_key": "tls_ep_edge",
            "endpoint_uri": "tls://edge.local:443",
            "hostname": "edge.local",
            "certificate_local_key": "tls_cert_edge",
            "certificate_fingerprint": "FPR-EDGE-RSA-001",
            "algorithm_local_key": "tls_alg_rsa",
            "algorithm_id": "RSA-2048",
            "key_bits": 2048,
            "emit_algorithm_relation": True,
            "locator": "sslyze/edge.json#/certificate_deployments/0",
        },
        {
            "endpoint_local_key": "tls_ep_patient",
            "endpoint_uri": "tls://patient.local:8443",
            "hostname": "patient.local",
            "certificate_local_key": "tls_cert_patient",
            "certificate_fingerprint": "FPR-PATIENT-RSA-002",
            "algorithm_local_key": "tls_alg_rsa",
            "algorithm_id": "RSA-2048",
            "key_bits": 2048,
            "emit_algorithm_relation": True,
            "locator": "sslyze/patient.json#/certificate_deployments/0",
        },
        {
            "endpoint_local_key": "tls_ep_db",
            "endpoint_uri": "tls://db.internal:5432",
            "hostname": "db.internal",
            "certificate_local_key": "tls_cert_db",
            "certificate_fingerprint": "FPR-DB-RSA-003",
            "algorithm_local_key": "unused_tls_db_algorithm",
            "algorithm_id": "RSA-2048",
            "emit_algorithm_entity": False,
            "emit_algorithm_relation": False,
            "locator": "sslyze/db.json#/certificate_deployments/0",
        },
        {
            "endpoint_local_key": "tls_ep_ot",
            "endpoint_uri": "tls://ot-gateway.local:8883",
            "hostname": "ot-gateway.local",
            "certificate_local_key": "tls_cert_ot",
            "certificate_fingerprint": "FPR-OT-ECDSA-004",
            "algorithm_local_key": "unused_tls_ot_algorithm",
            "algorithm_id": "ECDSA-P256",
            "emit_algorithm_entity": False,
            "emit_algorithm_relation": False,
            "locator": "sslyze/ot.json#/certificate_deployments/0",
        },
    ]
    combined.extend(adapt_tls_records(tls_records, collected_at=COLLECTED_AT))

    pki_records = [
        {
            "certificate_local_key": "pki_cert_edge",
            "certificate_fingerprint": "FPR-EDGE-RSA-001",
            "subject": "CN=edge.local",
            "issuer_local_key": "pki_cert_root",
            "issuer_fingerprint": "FPR-CIGMA-ROOT-000",
            "algorithm_local_key": "pki_alg_rsa",
            "algorithm_id": "RSA-2048",
            "key_bits": 2048,
            "locator": "pki/export.json#/certificates/edge",
        },
        {
            "certificate_local_key": "pki_cert_patient",
            "certificate_fingerprint": "FPR-PATIENT-RSA-002",
            "subject": "CN=patient.local",
            "issuer_local_key": "pki_cert_root",
            "issuer_fingerprint": "FPR-CIGMA-ROOT-000",
            "algorithm_local_key": "pki_alg_rsa",
            "algorithm_id": "RSA-2048",
            "key_bits": 2048,
            "locator": "pki/export.json#/certificates/patient",
        },
        {
            "certificate_local_key": "pki_cert_db",
            "certificate_fingerprint": "FPR-DB-RSA-003",
            "subject": "CN=db.internal",
            "issuer_local_key": "pki_cert_root",
            "issuer_fingerprint": "FPR-CIGMA-ROOT-000",
            "algorithm_local_key": "pki_alg_rsa",
            "algorithm_id": "RSA-2048",
            "key_bits": 2048,
            "locator": "pki/export.json#/certificates/db",
        },
        {
            "certificate_local_key": "pki_cert_ot",
            "certificate_fingerprint": "FPR-OT-ECDSA-004",
            "subject": "CN=ot-gateway.local",
            "issuer_local_key": "pki_cert_root",
            "issuer_fingerprint": "FPR-CIGMA-ROOT-000",
            "algorithm_local_key": "pki_alg_ecdsa",
            "algorithm_id": "ECDSA-P256",
            "key_bits": 256,
            "locator": "pki/export.json#/certificates/ot",
        },
    ]
    pki_extras = [
        {
            "certificate_local_key": "pki_cert_edge_inventory",
            "certificate_fingerprint": "FPR-EDGE-RSA-001",
            "subject": "CN=edge.local",
            "quality": 0.93,
            "locator": "pki/inventory.csv#row=2",
        },
        {
            "certificate_local_key": "pki_cert_root_inventory",
            "certificate_fingerprint": "FPR-CIGMA-ROOT-000",
            "subject": "CN=CIGMA Root",
            "quality": 0.95,
            "locator": "pki/inventory.csv#row=1",
        },
    ]
    combined.extend(
        adapt_pki_records(
            pki_records,
            collected_at=COLLECTED_AT,
            extra_certificates=pki_extras,
        )
    )

    cbom_component_records = [
        {
            "service_local_key": "code_svc_patient",
            "service_name": "patient-api",
            "repository_path": "services/patient-api",
            "component_local_key": "code_comp_patient",
            "purl": "pkg:pypi/cryptography@42.0.0",
            "component_name": "cryptography",
            "version": "42.0.0",
            "algorithm_local_key": "code_alg_rsa",
            "algorithm_id": "RSA-2048",
            "language": "python",
            "locator": "cbom/patient.cdx.json#/components/12",
        },
        {
            "service_local_key": "code_svc_auth",
            "service_name": "auth-service",
            "repository_path": "services/auth",
            "component_local_key": "code_comp_auth",
            "purl": "pkg:maven/org.bouncycastle/bcprov-jdk18on@1.78",
            "component_name": "bcprov-jdk18on",
            "version": "1.78",
            "algorithm_local_key": "code_alg_ecdsa",
            "algorithm_id": "ECDSA-P256",
            "language": "java",
            "locator": "cbom/auth.cdx.json#/components/4",
        },
    ]
    cbom_dependencies = [
        {
            "subject_service_local_key": "code_svc_edge",
            "subject_service_name": "edge-gateway",
            "subject_repository_path": "services/edge",
            "object_service_local_key": "code_svc_patient",
            "object_service_name": "patient-api",
            "object_repository_path": "services/patient-api",
            "relation_local_key": "code_edge_dep_patient_primary",
            "locator": "code/service-map.yaml#/edge/dependencies/0",
        },
        {
            "subject_service_local_key": "code_svc_patient",
            "subject_service_name": "patient-api",
            "subject_repository_path": "services/patient-api",
            "object_service_local_key": "code_svc_auth",
            "object_service_name": "auth-service",
            "object_repository_path": "services/auth",
            "relation_local_key": "code_patient_dep_auth",
            "locator": "code/service-map.yaml#/patient/dependencies/0",
        },
        {
            "subject_service_local_key": "code_svc_edge",
            "subject_service_name": "edge-gateway",
            "subject_repository_path": "services/edge",
            "object_service_local_key": "lock_svc_patient",
            "object_service_name": "patient-api",
            "object_repository_path": "deploy/patient",
            "relation_local_key": "code_edge_dep_patient_duplicate",
            "locator": "code/deployment-lock.yaml#/edge/dependencies/0",
        },
    ]
    combined.extend(
        adapt_cbom_records(
            cbom_component_records,
            dependency_records=cbom_dependencies,
            standalone_algorithms=[
                {
                    "algorithm_local_key": "code_alg_aes",
                    "algorithm_id": "AES-256-GCM",
                    "algorithm_family": "symmetric",
                    "locator": "cbom/common.cdx.json#/crypto/aes",
                }
            ],
            standalone_components=[
                {
                    "component_local_key": "code_comp_shadow",
                    "purl": "pkg:pypi/crypto-shadow@0.0.1",
                    "component_name": "crypto-shadow",
                    "version": "0.0.1",
                    "quality": 0.2,
                    "locator": "cbom/untrusted.json#/components/0",
                }
            ],
            collected_at=COLLECTED_AT,
        )
    )

    combined.extend(
        adapt_cicd_records(
            [
                {
                    "pipeline_local_key": "ci_pipe_core",
                    "pipeline_uid": "PIPE-CIGMA-CORE",
                    "service_local_key": "ci_svc_patient",
                    "service_uid": "SVC-PATIENT-001",
                    "service_name": "patient-api",
                    "deployment_name": "patient-api-v1",
                    "image": "ghcr.io/cigma/patient:1.0",
                    "locator": "cicd/workflow.json#/jobs/deploy-patient",
                },
                {
                    "pipeline_local_key": "ci_pipe_core",
                    "pipeline_uid": "PIPE-CIGMA-CORE",
                    "service_local_key": "ci_svc_auth",
                    "service_uid": "SVC-AUTH-001",
                    "service_name": "auth-service",
                    "deployment_name": "auth-service-v1",
                    "image": "ghcr.io/cigma/auth:1.0",
                    "locator": "cicd/workflow.json#/jobs/deploy-auth",
                },
            ],
            extra_pipelines=[
                {
                    "pipeline_local_key": "ci_pipe_core_metadata",
                    "pipeline_uid": "PIPE-CIGMA-CORE",
                    "platform": "github-actions",
                    "quality": 0.86,
                    "locator": "cicd/pipeline-catalog.csv#row=1",
                }
            ],
            collected_at=COLLECTED_AT,
        )
    )

    cmdb_services = [
        {
            "service_local_key": "cmdb_svc_edge",
            "service_uid": "SVC-EDGE-001",
            "service_name": "edge-gateway",
            "endpoint_local_key": "cmdb_ep_edge",
            "endpoint_uri": "tls://edge.local:443",
            "hostname": "edge.local",
            "criticality": 0.80,
            "exposure": 1.0,
            "migration_time_years": 1.5,
            "data_lifetime_years": 2.0,
            "agility": 0.75,
            "locator": "cmdb/services.csv#row=1",
        },
        {
            "service_local_key": "cmdb_svc_patient",
            "service_uid": "SVC-PATIENT-001",
            "service_name": "patient-api",
            "endpoint_local_key": "cmdb_ep_patient",
            "endpoint_uri": "tls://patient.local:8443",
            "hostname": "patient.local",
            "data_local_key": "cmdb_data_patient",
            "data_uid": "DATA-PATIENT-001",
            "data_name": "patient-records",
            "retention_years": 12.0,
            "criticality": 0.98,
            "exposure": 0.20,
            "migration_time_years": 2.0,
            "data_lifetime_years": 12.0,
            "agility": 0.45,
            "locator": "cmdb/services.csv#row=2",
        },
        {
            "service_local_key": "cmdb_svc_auth",
            "service_uid": "SVC-AUTH-001",
            "service_name": "auth-service",
            "data_local_key": "cmdb_data_auth",
            "data_uid": "DATA-AUTH-001",
            "data_name": "authentication-secrets",
            "retention_years": 8.5,
            "criticality": 0.90,
            "exposure": 0.60,
            "migration_time_years": 1.0,
            "data_lifetime_years": 8.5,
            "agility": 0.60,
            "locator": "cmdb/services.csv#row=3",
        },
        {
            "service_local_key": "cmdb_svc_db",
            "service_uid": "SVC-DB-001",
            "service_name": "patient-database",
            "endpoint_local_key": "cmdb_ep_db",
            "endpoint_uri": "tls://db.internal:5432",
            "hostname": "db.internal",
            "criticality": 0.98,
            "exposure": 0.20,
            "migration_time_years": 2.0,
            "data_lifetime_years": 12.0,
            "agility": 0.35,
            "locator": "cmdb/services.csv#row=4",
        },
        {
            "service_local_key": "cmdb_svc_ot",
            "service_uid": "SVC-OT-001",
            "service_name": "ot-gateway",
            "criticality": 0.92,
            "exposure": 0.30,
            "migration_time_years": 3.0,
            "data_lifetime_years": 5.0,
            "agility": 0.20,
            "locator": "cmdb/services.csv#row=5",
        },
    ]
    cmdb_dependencies = [
        {
            "subject_service_local_key": "cmdb_svc_patient",
            "object_service_local_key": "cmdb_svc_db",
            "locator": "cmdb/dependencies.csv#row=1",
        },
        {
            "subject_service_local_key": "cmdb_svc_auth",
            "object_service_local_key": "cmdb_svc_db",
            "locator": "cmdb/dependencies.csv#row=2",
        },
    ]
    combined.extend(
        adapt_cmdb_records(
            cmdb_services,
            dependencies=cmdb_dependencies,
            extra_relations=[
                {
                    "subject_local_key": "cmdb_svc_patient",
                    "predicate": RelationType.HOSTS.value,
                    "object_local_key": "cmdb_ep_edge",
                    "relation_local_key": "cmdb_false_patient_hosts_edge",
                    "relation_quality": 0.2,
                    "locator": "cmdb/unverified-links.csv#row=1",
                }
            ],
            collected_at=COLLECTED_AT,
        )
    )

    combined.extend(
        adapt_ot_records(
            [
                {
                    "service_local_key": "ot_svc_gateway",
                    "service_uid": "SVC-OT-001",
                    "service_name": "ot-gateway",
                    "endpoint_local_key": "ot_ep_gateway",
                    "endpoint_uri": "tls://ot-gateway.local:8883",
                    "device_local_key": "ot_device_plc",
                    "device_serial": "PLC-CIGMA-0001",
                    "device_model": "PLC-X1",
                    "firmware_constraint": "annual-window",
                    "distractor_device_local_key": "ot_device_shadow",
                    "distractor_device_serial": "PLC-SHADOW-9999",
                    "distractor_quality": 0.2,
                    "locator": "ot/inventory.json#/gateway",
                }
            ],
            collected_at=COLLECTED_AT,
        )
    )

    return combined


def _entity_truth_mapping(output: AdapterOutput) -> dict[str, str | None]:
    by_source_local_key: dict[tuple[SourceFamily, str], str | None] = {
        # TLS
        (SourceFamily.TLS, "tls_ep_edge"): "ep_edge",
        (SourceFamily.TLS, "tls_ep_patient"): "ep_patient",
        (SourceFamily.TLS, "tls_ep_db"): "ep_db",
        (SourceFamily.TLS, "tls_ep_ot"): "ep_ot",
        (SourceFamily.TLS, "tls_cert_edge"): "cert_edge",
        (SourceFamily.TLS, "tls_cert_patient"): "cert_patient",
        (SourceFamily.TLS, "tls_cert_db"): "cert_db",
        (SourceFamily.TLS, "tls_cert_ot"): "cert_ot",
        (SourceFamily.TLS, "tls_alg_rsa"): "alg_rsa",
        # PKI
        (SourceFamily.PKI, "pki_cert_edge"): "cert_edge",
        (SourceFamily.PKI, "pki_cert_patient"): "cert_patient",
        (SourceFamily.PKI, "pki_cert_db"): "cert_db",
        (SourceFamily.PKI, "pki_cert_ot"): "cert_ot",
        (SourceFamily.PKI, "pki_cert_root"): "cert_root",
        (SourceFamily.PKI, "pki_alg_rsa"): "alg_rsa",
        (SourceFamily.PKI, "pki_alg_ecdsa"): "alg_ecdsa",
        (SourceFamily.PKI, "pki_cert_edge_inventory"): "cert_edge",
        (SourceFamily.PKI, "pki_cert_root_inventory"): "cert_root",
        # CBOM
        (SourceFamily.CBOM, "code_svc_patient"): "svc_patient",
        (SourceFamily.CBOM, "lock_svc_patient"): "svc_patient",
        (SourceFamily.CBOM, "code_svc_auth"): "svc_auth",
        (SourceFamily.CBOM, "code_svc_edge"): "svc_edge",
        (SourceFamily.CBOM, "code_comp_patient"): "comp_patient",
        (SourceFamily.CBOM, "code_comp_auth"): "comp_auth",
        (SourceFamily.CBOM, "code_alg_rsa"): "alg_rsa",
        (SourceFamily.CBOM, "code_alg_ecdsa"): "alg_ecdsa",
        (SourceFamily.CBOM, "code_alg_aes"): "alg_aes",
        (SourceFamily.CBOM, "code_comp_shadow"): None,
        # CI/CD
        (SourceFamily.CICD, "ci_pipe_core"): "pipe_core",
        (SourceFamily.CICD, "ci_pipe_core_metadata"): "pipe_core",
        (SourceFamily.CICD, "ci_svc_patient"): "svc_patient",
        (SourceFamily.CICD, "ci_svc_auth"): "svc_auth",
        # CMDB
        (SourceFamily.CMDB, "cmdb_svc_edge"): "svc_edge",
        (SourceFamily.CMDB, "cmdb_svc_patient"): "svc_patient",
        (SourceFamily.CMDB, "cmdb_svc_auth"): "svc_auth",
        (SourceFamily.CMDB, "cmdb_svc_db"): "svc_db",
        (SourceFamily.CMDB, "cmdb_svc_ot"): "svc_ot",
        (SourceFamily.CMDB, "cmdb_ep_edge"): "ep_edge",
        (SourceFamily.CMDB, "cmdb_ep_patient"): "ep_patient",
        (SourceFamily.CMDB, "cmdb_ep_db"): "ep_db",
        (SourceFamily.CMDB, "cmdb_data_patient"): "data_patient",
        (SourceFamily.CMDB, "cmdb_data_auth"): "data_auth",
        # OT
        (SourceFamily.OT, "ot_svc_gateway"): "svc_ot",
        (SourceFamily.OT, "ot_ep_gateway"): "ep_ot",
        (SourceFamily.OT, "ot_device_plc"): "dev_plc",
        (SourceFamily.OT, "ot_device_shadow"): None,
    }
    mapping: dict[str, str | None] = {}
    for obs in output.ordered_entities():
        key = (obs.source, obs.local_key)
        if key not in by_source_local_key:
            raise AssertionError(f"missing fixture truth mapping: {key}")
        mapping[obs.observation_id] = by_source_local_key[key]
    return mapping


def generate_cigma_lab(output_dir: str | Path) -> dict[str, Any]:
    root = Path(output_dir)
    public_dir = root / "public"
    oracle_dir = root / "oracle"
    public_dir.mkdir(parents=True, exist_ok=True)
    oracle_dir.mkdir(parents=True, exist_ok=True)

    output = _build_public_observations()
    entities = output.ordered_entities()
    relations = output.ordered_relations()
    validate_observations(entities, relations)

    nodes = truth_nodes()
    edge_rows, direct_truth = truth_edges()
    entity_map = _entity_truth_mapping(output)
    truth_edge_by_triple = {
        (row["subject"], RelationType(row["predicate"]), row["object"]): row["edge_id"]
        for row in edge_rows
    }
    relation_map: dict[str, str | None] = {}
    for relation in relations:
        subject_truth = entity_map[relation.subject_observation_id]
        object_truth = entity_map[relation.object_observation_id]
        triple = (
            subject_truth,
            relation.predicate,
            object_truth,
        )
        if subject_truth is None or object_truth is None or triple not in direct_truth:
            relation_map[relation.observation_id] = None
        else:
            relation_map[relation.observation_id] = truth_edge_by_triple[triple]

    write_jsonl(public_dir / "entities.jsonl", (item.to_dict() for item in entities))
    write_jsonl(public_dir / "relations.jsonl", (item.to_dict() for item in relations))
    write_jsonl(oracle_dir / "nodes.jsonl", nodes)
    write_jsonl(oracle_dir / "edges.jsonl", edge_rows)
    write_json(oracle_dir / "observation_to_truth.json", entity_map)
    write_json(oracle_dir / "relation_to_truth.json", relation_map)
    priorities = {node["truth_id"]: node["priority"] for node in nodes}
    critical_targets = [node["truth_id"] for node in nodes if node["critical_target"]]
    write_json(oracle_dir / "priorities.json", priorities)
    write_json(oracle_dir / "critical_targets.json", critical_targets)

    entity_counts = Counter(item.source.value for item in entities)
    relation_counts = Counter(item.source.value for item in relations)
    true_relation_observations = sum(value is not None for value in relation_map.values())
    direct_truth_observed = len({value for value in relation_map.values() if value is not None})
    summary = {
        "fixture_id": FIXTURE_ID,
        "entity_observations": len(entities),
        "relation_observations": len(relations),
        "truth_entities": len(nodes),
        "truth_edges": len(edge_rows),
        "mapped_entity_observations": sum(value is not None for value in entity_map.values()),
        "distractor_entity_observations": sum(value is None for value in entity_map.values()),
        "true_relation_observations": true_relation_observations,
        "false_relation_observations": len(relations) - true_relation_observations,
        "unique_observed_direct_truth_edges": direct_truth_observed,
        "derived_truth_edges": sum(bool(row["derived"]) for row in edge_rows),
        "critical_targets": len(critical_targets),
        "entity_counts_by_source": dict(sorted(entity_counts.items())),
        "relation_counts_by_source": dict(sorted(relation_counts.items())),
    }
    write_json(root / "fixture_statistics.json", summary)
    write_json(
        root / "manifest.json",
        {
            "fixture_id": FIXTURE_ID,
            "public_tree_sha256": sha256_tree(public_dir),
            "oracle_tree_sha256": sha256_tree(oracle_dir),
            "statistics": summary,
        },
    )

    expected_entity_counts = {"tls": 9, "pki": 9, "cbom": 10, "cicd": 4, "cmdb": 10, "ot": 4}
    expected_relation_counts = {"tls": 6, "pki": 8, "cbom": 7, "cicd": 2, "cmdb": 8, "ot": 3}
    assert summary["entity_observations"] == 46
    assert summary["relation_observations"] == 34
    assert summary["truth_entities"] == 23
    assert summary["truth_edges"] == 34
    assert summary["mapped_entity_observations"] == 44
    assert summary["distractor_entity_observations"] == 2
    assert summary["true_relation_observations"] == 32
    assert summary["false_relation_observations"] == 2
    assert summary["unique_observed_direct_truth_edges"] == 29
    assert summary["derived_truth_edges"] == 5
    assert summary["critical_targets"] == 16
    assert summary["entity_counts_by_source"] == expected_entity_counts
    assert summary["relation_counts_by_source"] == expected_relation_counts
    return summary


if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(description="Generate the clean-room CIGMA-Lab fixture")
    parser.add_argument("output", nargs="?", default="data/cigma_lab")
    args = parser.parse_args()
    stats = generate_cigma_lab(args.output)
    print(canonical_json(stats))
