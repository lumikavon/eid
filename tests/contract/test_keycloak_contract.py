from edw_api.keycloak_contract import (
    MONITOR_EFFECTIVE_REALM_MANAGEMENT_ROLES,
    MONITOR_REALM_MANAGEMENT_ROLES,
)


def test_monitor_role_contract_separates_assigned_roots_from_effective_roles():
    assert MONITOR_REALM_MANAGEMENT_ROLES == frozenset({"view-clients", "view-realm"})
    assert MONITOR_EFFECTIVE_REALM_MANAGEMENT_ROLES == frozenset(
        {"query-clients", "view-clients", "view-realm"}
    )
