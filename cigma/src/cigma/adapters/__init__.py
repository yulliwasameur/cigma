"""Public source-family adapters."""

from .base import AdapterOutput, ObservationFactory
from .cbom import adapt_cbom_records
from .cicd import adapt_cicd_records
from .cmdb import adapt_cmdb_records
from .ot import adapt_ot_records
from .pki import adapt_pki_records
from .tls import adapt_tls_records

__all__ = [
    "AdapterOutput",
    "ObservationFactory",
    "adapt_cbom_records",
    "adapt_cicd_records",
    "adapt_cmdb_records",
    "adapt_ot_records",
    "adapt_pki_records",
    "adapt_tls_records",
]
