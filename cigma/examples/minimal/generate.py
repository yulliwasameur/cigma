"""Generate the minimal cross-source example without oracle data."""

from pathlib import Path

from cigma.adapters import AdapterOutput, adapt_cmdb_records, adapt_tls_records
from cigma.io import write_jsonl

ROOT = Path(__file__).resolve().parent
TIME = "2026-08-26T00:00:00+00:00"


def main() -> None:
    output = AdapterOutput()
    output.extend(
        adapt_cmdb_records(
            [
                {
                    "service_local_key": "cmdb_service",
                    "service_uid": "SVC-MINIMAL-001",
                    "service_name": "minimal-api",
                    "endpoint_local_key": "cmdb_endpoint",
                    "endpoint_uri": "tls://minimal.local:443",
                    "hostname": "minimal.local",
                    "criticality": 0.9,
                    "exposure": 1.0,
                    "migration_time_years": 1.0,
                    "data_lifetime_years": 5.0,
                    "agility": 0.6,
                    "locator": "cmdb/minimal.json#/service",
                }
            ],
            collected_at=TIME,
        )
    )
    output.extend(
        adapt_tls_records(
            [
                {
                    "endpoint_local_key": "tls_endpoint",
                    "endpoint_uri": "tls://minimal.local:443",
                    "hostname": "minimal.local",
                    "certificate_local_key": "tls_certificate",
                    "certificate_fingerprint": "FPR-MINIMAL-RSA-001",
                    "algorithm_local_key": "tls_algorithm",
                    "algorithm_id": "RSA-2048",
                    "key_bits": 2048,
                    "locator": "tls/minimal.json#/scan",
                }
            ],
            collected_at=TIME,
        )
    )
    public = ROOT / "public"
    write_jsonl(public / "entities.jsonl", (item.to_dict() for item in output.ordered_entities()))
    write_jsonl(public / "relations.jsonl", (item.to_dict() for item in output.ordered_relations()))


if __name__ == "__main__":
    main()
