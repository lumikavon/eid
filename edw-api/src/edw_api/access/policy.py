"""Framework-independent, deny-by-default decisions over current database facts."""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone


ROLE_OPERATIONS = {
    "author": {"document:create", "document:edit"},
    "expert": {"document:review"},
    "quality": {"quality:review"},
    "template_admin": {"template:publish"},
    "knowledge_admin": {"knowledge:manage"},
    "approver": {"document:approve"},
    "system_admin": {"membership:manage"},
}
COMMON_OPERATIONS = {"workspace:read", "resource:read", "inventory:read"}
APPROVAL_STATES = {"draft", "in_review", "approved", "rejected"}
OPERATIONS = COMMON_OPERATIONS | set().union(*ROLE_OPERATIONS.values())
RESOURCE_BOUND_OPERATIONS = OPERATIONS - {
    "workspace:read", "inventory:read", "document:create", "membership:manage"
}


class AccessDenied(Exception):
    """No protected identity or resource detail is included in the error."""


def _time(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise AccessDenied()
    return value


def _valid(row, now):
    start, end = _time(row.get("valid_from")), _time(row.get("valid_until"))
    return start is not None and start <= now and (end is None or now < end)


@dataclass(frozen=True)
class AuthContext:
    actor_id: str
    service_id: str
    tenant_id: str
    workspace_id: str
    policy_epoch: tuple[int, int, int]
    classification: int
    operation: str
    purpose: str
    delegation_scope: str | None
    request_id: str = ""
    trace_id: str = ""

    def payload(self):
        return asdict(self)


def authorize(facts, operation, resource=None, *, service_id="eid-api", purpose="interactive",
              delegation=None, now=None):
    try:
        if not isinstance(facts, dict):
            raise AccessDenied()
        now = now or _time(facts.get("evaluated_at")) or datetime.now(timezone.utc)
        if not facts or facts["identity_active"] is not True or facts["membership_active"] is not True:
            raise AccessDenied()
        roles = facts["roles"]
        if not roles or any(role not in ROLE_OPERATIONS for role in roles) or not _valid(facts, now):
            raise AccessDenied()
        if any(state not in APPROVAL_STATES for state in facts["approval_states"]):
            raise AccessDenied()
        allowed = COMMON_OPERATIONS | set().union(*(ROLE_OPERATIONS[role] for role in roles))
        if operation not in allowed:
            raise AccessDenied()
        if resource is None and operation in RESOURCE_BOUND_OPERATIONS:
            raise AccessDenied()
        if resource is None and operation == "document:create" and "draft" not in facts["approval_states"]:
            raise AccessDenied()
        target = resource if resource is not None else facts
        if str(target["workspace_id"]) != str(facts["workspace_id"]):
            raise AccessDenied()
        for dimension in ("project", "customer", "product", "department"):
            key = dimension if dimension == "department" else dimension + "_id"
            # A wildcard is an explicit stored grant, never a client-supplied default.
            scopes = facts[dimension + "_scope"]
            if target[key] not in scopes and "*" not in scopes:
                raise AccessDenied()
        if resource is not None:
            if not _valid(resource, now):
                raise AccessDenied()
            if facts["owner_scope"] != "any" and str(resource["owner_id"]) != str(facts["actor_id"]):
                raise AccessDenied()
            if (resource["approval_state"] not in APPROVAL_STATES
                    or resource["approval_state"] not in facts["approval_states"]):
                raise AccessDenied()
        level, clearance = target["classification"], facts["clearance"]
        if type(level) is not int or type(clearance) is not int or not 0 <= level <= clearance <= 3:
            raise AccessDenied()
        workspace_level = facts["classification"]
        if type(workspace_level) is not int or not 0 <= workspace_level <= clearance:
            raise AccessDenied()
        level = max(level, workspace_level)
        epochs = (facts["workspace_epoch"], facts["policy_epoch"],
                  resource["policy_epoch"] if resource is not None else facts["workspace_epoch"])
        if any(type(epoch) is not int or epoch < 1 for epoch in epochs):
            raise AccessDenied()
        if service_id != "eid-api":
            if service_id != "eid-worker" or not delegation:
                raise AccessDenied()
            expected_resource = str(resource["id"]) if resource is not None else None
            actual_resource = str(delegation["resource_id"]) if delegation["resource_id"] else None
            if (delegation["service_id"] != service_id or delegation["active"] is not True
                    or type(delegation["issued_epoch"]) is not int
                    or delegation["issued_epoch"] != facts["workspace_epoch"]
                    or str(delegation["actor_id"]) != str(facts["actor_id"])
                    or str(delegation["workspace_id"]) != str(facts["workspace_id"])
                    or actual_resource != expected_resource or delegation["operation"] != operation
                    or delegation["purpose"] != purpose or _time(delegation["expires_at"]) <= now):
                raise AccessDenied()
        return AuthContext(str(facts["actor_id"]), service_id, str(facts["tenant_id"]),
                           str(facts["workspace_id"]), epochs, level, operation, purpose,
                           str(delegation["id"]) if delegation else None)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise AccessDenied() from exc
