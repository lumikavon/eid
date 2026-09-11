"""Exact local Keycloak contracts shared by bootstrap and runtime readiness."""

from collections.abc import Mapping, Sequence


REALM_NAME = "eid-local"
WEB_CLIENT_ID = "eid-web"
MONITOR_CLIENT_ID = "eid-readiness-monitor"
MONITOR_CLIENT_SECRET = "local-keycloak-readiness-monitor-only"
# These are the two root roles assigned to the service account. Keycloak expands
# view-clients to query-clients in access tokens because view-clients is composite.
MONITOR_REALM_MANAGEMENT_ROLES = frozenset({"view-clients", "view-realm"})
MONITOR_EFFECTIVE_REALM_MANAGEMENT_ROLES = frozenset(
    {*MONITOR_REALM_MANAGEMENT_ROLES, "query-clients"}
)
WEB_REDIRECT_URIS = ["http://localhost:18080/auth/callback"]
WEB_ORIGINS = ["http://localhost:18080"]
WEB_LOGOUT_REDIRECT_URI = "http://localhost:18080/"


def web_client_contract_matches(client: object) -> bool:
    if not isinstance(client, Mapping):
        return False
    attributes = client.get("attributes")
    return (
        client.get("clientId") == WEB_CLIENT_ID
        and client.get("enabled") is True
        and client.get("publicClient") is True
        and client.get("standardFlowEnabled") is True
        and client.get("implicitFlowEnabled") is False
        and client.get("directAccessGrantsEnabled") is False
        and client.get("redirectUris") == WEB_REDIRECT_URIS
        and client.get("webOrigins") == WEB_ORIGINS
        and isinstance(attributes, Mapping)
        and attributes.get("pkce.code.challenge.method") == "S256"
        and attributes.get("post.logout.redirect.uris") == WEB_LOGOUT_REDIRECT_URI
    )


def audience_mapper_contract_matches(mappers: object) -> bool:
    if not isinstance(mappers, Sequence) or isinstance(mappers, (str, bytes)):
        return False
    audience_mappers = [
        mapper
        for mapper in mappers
        if isinstance(mapper, Mapping)
        and mapper.get("protocolMapper") == "oidc-audience-mapper"
    ]
    if len(audience_mappers) != 1:
        return False
    mapper = audience_mappers[0]
    config = mapper.get("config")
    return (
        mapper.get("name") == "audience-eid-web"
        and mapper.get("protocol") == "openid-connect"
        and mapper.get("consentRequired") is False
        and isinstance(config, Mapping)
        and config.get("included.client.audience") == WEB_CLIENT_ID
        and config.get("access.token.claim") == "true"
    )


def realm_contract_matches(realm: object) -> bool:
    return (
        isinstance(realm, Mapping)
        and realm.get("realm") == REALM_NAME
        and realm.get("registrationAllowed") is False
    )


def monitor_client_contract_matches(client: object) -> bool:
    return (
        isinstance(client, Mapping)
        and client.get("clientId") == MONITOR_CLIENT_ID
        and client.get("enabled") is True
        and client.get("publicClient") is False
        and client.get("serviceAccountsEnabled") is True
        and client.get("standardFlowEnabled") is False
        and client.get("implicitFlowEnabled") is False
        and client.get("directAccessGrantsEnabled") is False
    )


def monitor_roles_from_token(access_token: str) -> frozenset[str]:
    """Read role names only; Admin REST remains the authorization authority."""
    import jwt

    payload = jwt.decode(
        access_token,
        options={"verify_signature": False, "verify_aud": False},
        algorithms=["RS256"],
    )
    resource_access = payload.get("resource_access")
    if not isinstance(resource_access, Mapping):
        return frozenset()
    realm_management = resource_access.get("realm-management")
    if not isinstance(realm_management, Mapping):
        return frozenset()
    roles = realm_management.get("roles")
    if not isinstance(roles, list) or any(not isinstance(role, str) for role in roles):
        return frozenset()
    return frozenset(roles)
