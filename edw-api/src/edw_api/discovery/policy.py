"""恢复政策复用当前授权；测试环境名称本身不授予权限。"""
from ..access.policy import AccessDenied, authorize


def authorize_restore(facts, resource, record, policy, *, environment, database_identity):
    context = authorize(facts, "resource:read", resource)
    try:
        now = facts["evaluated_at"]
        if (policy is None or policy["active"] is not True
                or str(policy["workspace_id"]) != str(resource["workspace_id"])
                or record["kind"] != "document" or resource["kind"] != "document"
                or policy["kind"] != "document" or policy["action"] != "restore_visibility"
                or policy["required_operation"] != "document:edit"
                or policy["owner_only"] is not True
                or str(resource["owner_id"]) != str(facts["actor_id"])
                or policy["environment_class"] != environment
                or not isinstance(policy["version"], str) or not 1 <= len(policy["version"]) <= 128
                or policy["valid_from"] > now
                or (policy["valid_until"] is not None and now >= policy["valid_until"])):
            raise AccessDenied()
        if environment == "isolated_development":
            if (database_identity != {"database_name": "eid_local_dev",
                                      "marker": "eid-local-dev-v1"}
                    or not policy["fixture_owner"] or not policy["fixture_version"]
                    or record["fixture_owner"] != policy["fixture_owner"]
                    or record["fixture_version"] != policy["fixture_version"]):
                raise AccessDenied()
        elif environment == "production":
            if any(row[key] is not None for row in (policy, record)
                   for key in ("fixture_owner", "fixture_version")):
                raise AccessDenied()
        else:
            raise AccessDenied()
        authorize(facts, policy["required_operation"], resource)
        return context
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise AccessDenied() from exc
