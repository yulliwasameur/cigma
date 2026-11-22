from cigma.adapters import (
    adapt_cbom_records,
    adapt_cicd_records,
    adapt_cmdb_records,
    adapt_ot_records,
    adapt_pki_records,
    adapt_tls_records,
)
from cigma.schema import RelationType


TIME = "2026-08-19T00:00:00+00:00"


def test_tls_adapter_emits_endpoint_certificate_algorithm_and_relations():
    output = adapt_tls_records([
        {
            "endpoint_local_key": "ep",
            "endpoint_uri": "tls://example:443",
            "certificate_local_key": "cert",
            "certificate_fingerprint": "FPR",
            "algorithm_local_key": "alg",
            "algorithm_id": "RSA-2048",
        }
    ], collected_at=TIME)
    assert len(output.entities) == 3
    assert {item.predicate for item in output.relations.values()} == {RelationType.PRESENTS, RelationType.USES}


def test_pki_adapter_deduplicates_shared_root_and_algorithm_observations():
    base = {
        "issuer_local_key": "root",
        "issuer_fingerprint": "ROOT",
        "algorithm_local_key": "rsa",
        "algorithm_id": "RSA-2048",
    }
    output = adapt_pki_records([
        {**base, "certificate_local_key": "a", "certificate_fingerprint": "A"},
        {**base, "certificate_local_key": "b", "certificate_fingerprint": "B"},
    ], collected_at=TIME)
    assert len(output.entities) == 4
    assert len(output.relations) == 4


def test_cbom_adapter_emits_service_dependency():
    output = adapt_cbom_records([], dependency_records=[
        {
            "subject_service_local_key": "a",
            "subject_service_name": "a",
            "object_service_local_key": "b",
            "object_service_name": "b",
        }
    ], collected_at=TIME)
    assert len(output.entities) == 2
    assert next(iter(output.relations.values())).predicate == RelationType.DEPENDS_ON


def test_cicd_adapter_reuses_one_pipeline_for_multiple_deployments():
    output = adapt_cicd_records([
        {"pipeline_local_key": "p", "pipeline_uid": "P", "service_local_key": "a", "service_name": "a"},
        {"pipeline_local_key": "p", "pipeline_uid": "P", "service_local_key": "b", "service_name": "b"},
    ], collected_at=TIME)
    assert len(output.entities) == 3
    assert len(output.relations) == 2


def test_cmdb_adapter_preserves_low_quality_extra_relation():
    services = [
        {"service_local_key": "a", "service_name": "a", "endpoint_local_key": "ep-a", "endpoint_uri": "tls://a"},
        {"service_local_key": "b", "service_name": "b"},
    ]
    output = adapt_cmdb_records(services, extra_relations=[
        {"subject_local_key": "b", "predicate": "HOSTS", "object_local_key": "ep-a", "relation_local_key": "false", "relation_quality": 0.2}
    ], collected_at=TIME)
    assert any(item.quality == 0.2 for item in output.relations.values())


def test_ot_adapter_emits_distractor_entity_and_relation():
    output = adapt_ot_records([
        {
            "service_local_key": "svc", "service_name": "ot", "endpoint_local_key": "ep", "endpoint_uri": "tls://ot",
            "device_local_key": "dev", "device_serial": "D1", "distractor_device_local_key": "shadow", "distractor_device_serial": "D2"
        }
    ], collected_at=TIME)
    assert len(output.entities) == 4
    assert len(output.relations) == 3
    assert sum(item.quality < 0.4 for item in output.entities.values()) == 1
