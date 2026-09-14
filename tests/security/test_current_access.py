from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from edw_api.access.policy import AccessDenied, ROLE_OPERATIONS, RESOURCE_BOUND_OPERATIONS, authorize
from edw_api.access.routes import MemberPolicy

NOW = datetime(2026, 9, 11, tzinfo=timezone.utc)


@pytest.mark.parametrize("states,state", [(["future"], "future"), (["draft", "future"], "draft"), (["draft"], "future")])
def test_unknown_approval_vocabulary_cannot_grant_access(facts, resource, states, state):
    facts["approval_states"] = states
    resource["approval_state"] = state
    with pytest.raises(AccessDenied):
        authorize(facts, "resource:read", resource, now=NOW)


@pytest.fixture
def facts():
    return {"actor_id": "actor-a", "identity_active": True, "membership_active": True,
            "roles": ["author"], "workspace_id": "workspace-a", "tenant_id": "tenant-a",
            "project_id": "project-a", "customer_id": "customer-a", "product_id": "product-a",
            "department": "engineering", "project_scope": ["project-a"],
            "customer_scope": ["customer-a"], "product_scope": ["product-a"],
            "department_scope": ["engineering"], "owner_scope": "self",
            "approval_states": ["draft"], "classification": 1, "clearance": 2,
            "valid_from": NOW-timedelta(days=1), "valid_until": NOW+timedelta(days=1),
            "policy_epoch": 3, "workspace_epoch": 5}


@pytest.fixture
def resource(facts):
    return {key: facts[key] for key in ("workspace_id", "project_id", "customer_id", "product_id",
                                      "department", "classification", "valid_from", "valid_until")} | {
        "id": "resource-a", "owner_id": "actor-a", "approval_state": "draft", "policy_epoch": 7}


@pytest.mark.parametrize("role", ROLE_OPERATIONS)
def test_each_role_only_grants_its_declared_operation(facts, resource, role):
    facts["roles"] = [role]
    for other, operations in ROLE_OPERATIONS.items():
        for operation in operations:
            if other == role:
                result = authorize(facts, operation, resource, now=NOW)
                assert result.policy_epoch == (5, 3, 7)
                assert result.actor_id == "actor-a"
            else:
                with pytest.raises(AccessDenied):
                    authorize(facts, operation, resource, now=NOW)


@pytest.mark.parametrize("role", ROLE_OPERATIONS)
@pytest.mark.parametrize("field,value", [
    ("workspace_id", "foreign"), ("project_id", "foreign"), ("customer_id", "foreign"),
    ("product_id", "foreign"), ("department", "foreign"), ("owner_id", "foreign"),
    ("approval_state", "approved"), ("classification", 3), ("valid_until", NOW),
    ("valid_from", NOW+timedelta(seconds=1)), ("policy_epoch", 0),
])
def test_abac_and_clearance_apply_to_every_role_including_admin(facts, resource, role, field, value):
    facts["roles"] = [role]
    operation = next(iter(ROLE_OPERATIONS[role]))
    resource[field] = value
    with pytest.raises(AccessDenied):
        authorize(facts, operation, resource, now=NOW)


@pytest.mark.parametrize("field,value", [
    ("identity_active", False), ("membership_active", False), ("roles", []),
    ("roles", ["unrecognized"]), ("valid_from", NOW+timedelta(seconds=1)),
    ("valid_until", NOW), ("clearance", -1), ("clearance", True), ("policy_epoch", 0),
    ("workspace_epoch", "5"), ("project_scope", []), ("valid_from", "bad-date"),
])
def test_current_policy_revocation_fails_despite_old_context(facts, resource, field, value):
    old = authorize(facts, "resource:read", resource, now=NOW)
    facts[field] = value
    with pytest.raises(AccessDenied):
        authorize(facts, old.operation, resource, now=NOW)


def test_worker_delegation_is_narrow_and_current(facts, resource):
    delegation = {"id": "delegation-a", "actor_id": "actor-a", "workspace_id": "workspace-a",
                  "resource_id": "resource-a", "operation": "resource:read", "purpose": "stage",
                  "service_id": "eid-worker", "active": True, "issued_epoch": 5,
                  "expires_at": NOW+timedelta(minutes=1)}
    context = authorize(facts, "resource:read", resource, now=NOW, service_id="eid-worker",
                        purpose="stage", delegation=delegation)
    assert context.delegation_scope == "delegation-a"
    for key, value in {"actor_id": "another", "workspace_id": "another", "resource_id": None,
                       "operation": "document:approve", "purpose": "another", "active": False,
                       "service_id": "other", "expires_at": NOW, "issued_epoch": 4}.items():
        changed = deepcopy(delegation)
        changed[key] = value
        with pytest.raises(AccessDenied):
            authorize(facts, "resource:read", resource, now=NOW, service_id="eid-worker",
                      purpose="stage", delegation=changed)
    facts["membership_active"] = False
    with pytest.raises(AccessDenied):
        authorize(facts, "resource:read", resource, now=NOW, service_id="eid-worker",
                  purpose="stage", delegation=delegation)
    facts["membership_active"] = True
    facts["workspace_epoch"] += 2
    with pytest.raises(AccessDenied):
        authorize(facts, "resource:read", resource, now=NOW, service_id="eid-worker",
                  purpose="stage", delegation=delegation)


def test_unknown_operation_and_unbound_service_deny(facts):
    for operation, service in [("unknown", "eid-api"), ("workspace:read", "eid-worker"),
                               ("workspace:read", "system-admin")]:
        with pytest.raises(AccessDenied):
            authorize(facts, operation, service_id=service, now=NOW)


def test_resource_cannot_lower_workspace_classification(facts, resource):
    resource["classification"] = 0
    facts["classification"] = 3
    with pytest.raises(AccessDenied):
        authorize(facts, "resource:read", resource, now=NOW)


@pytest.mark.parametrize("service", ["eid-api", "eid-worker"])
@pytest.mark.parametrize("states", [[], ["approved"], ["draft"]])
def test_unbound_creation_requires_draft_scope(facts, service, states):
    facts["approval_states"] = states
    delegation = {"id": "delegation-a", "actor_id": "actor-a", "workspace_id": "workspace-a",
                  "resource_id": None, "operation": "document:create", "purpose": "stage",
                  "service_id": "eid-worker", "active": True, "issued_epoch": 5,
                  "expires_at": NOW+timedelta(minutes=1)}
    options = {"now": NOW, "service_id": service, "purpose": "stage",
               "delegation": delegation if service == "eid-worker" else None}
    if "draft" in states:
        assert authorize(facts, "document:create", **options).operation == "document:create"
    else:
        with pytest.raises(AccessDenied):
            authorize(facts, "document:create", **options)


@pytest.mark.parametrize("service", ["eid-api", "eid-worker"])
@pytest.mark.parametrize("workspace_level,resource_level", [(3, 0), (0, 3)])
def test_successful_context_retains_the_higher_classification(facts, resource, service,
                                                            workspace_level, resource_level):
    facts["classification"] = workspace_level
    facts["clearance"] = 3
    resource["classification"] = resource_level
    delegation = {"id": "delegation-a", "actor_id": "actor-a", "workspace_id": "workspace-a",
                  "resource_id": "resource-a", "operation": "resource:read", "purpose": "stage",
                  "service_id": "eid-worker", "active": True, "issued_epoch": 5,
                  "expires_at": NOW+timedelta(minutes=1)}
    context = authorize(facts, "resource:read", resource, now=NOW, service_id=service,
                        purpose="stage", delegation=delegation if service == "eid-worker" else None)
    assert context.classification == 3
    assert context.policy_epoch == (5, 3, 7)


def test_database_clock_is_authoritative_for_current_validity(facts):
    facts["valid_from"] = NOW
    facts["valid_until"] = NOW+timedelta(seconds=1)
    facts["evaluated_at"] = NOW
    assert authorize(facts, "workspace:read").actor_id == "actor-a"
    facts["evaluated_at"] = NOW+timedelta(seconds=1)
    with pytest.raises(AccessDenied):
        authorize(facts, "workspace:read")
    with pytest.raises(AccessDenied):
        authorize(None, "workspace:read")


def test_client_actor_and_scope_overrides_are_rejected():
    with pytest.raises(ValueError):
        MemberPolicy.model_validate({"actor_id": "admin", "scope": "*"})


@pytest.mark.parametrize("operation", sorted(RESOURCE_BOUND_OPERATIONS))
@pytest.mark.parametrize("service", ["eid-api", "eid-worker"])
def test_resource_operations_never_authorize_an_unbound_resource(facts, operation, service):
    facts["roles"] = list(ROLE_OPERATIONS)
    delegation = {"id": "d", "actor_id": "actor-a", "workspace_id": "workspace-a",
                  "resource_id": None, "operation": operation, "purpose": "stage",
                  "service_id": "eid-worker", "active": True,
                  "expires_at": NOW+timedelta(minutes=1)}
    with pytest.raises(AccessDenied):
        authorize(facts, operation, now=NOW, service_id=service,
                  purpose="stage", delegation=delegation if service=="eid-worker" else None)
