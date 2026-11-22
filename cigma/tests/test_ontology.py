from cigma.ontology import PATH_RULES, RELATION_SIGNATURES, is_valid_signature
from cigma.schema import EntityType, RelationType


def test_closed_ontology_has_eight_entity_and_relation_types():
    assert len(EntityType) == 8
    assert len(RelationType) == 8


def test_hosts_signature_is_valid():
    assert is_valid_signature(RelationType.HOSTS, EntityType.SERVICE, EntityType.ENDPOINT)


def test_hosts_rejects_service_to_certificate():
    assert not is_valid_signature(RelationType.HOSTS, EntityType.SERVICE, EntityType.CERTIFICATE)


def test_allow_list_contains_exactly_the_two_published_paths():
    assert [rule.rule_id for rule in PATH_RULES] == ["HOSTS_o_PRESENTS_o_USES", "USES_o_USES"]


def test_uses_relation_supports_all_declared_domains():
    signatures = RELATION_SIGNATURES[RelationType.USES]
    assert (EntityType.CERTIFICATE, EntityType.ALGORITHM) in signatures
    assert (EntityType.SOFTWARE_COMPONENT, EntityType.ALGORITHM) in signatures
    assert (EntityType.SERVICE, EntityType.SOFTWARE_COMPONENT) in signatures
    assert (EntityType.SERVICE, EntityType.ALGORITHM) in signatures
    assert (EntityType.DEVICE, EntityType.ALGORITHM) in signatures
