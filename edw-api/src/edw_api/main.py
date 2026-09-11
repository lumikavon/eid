import logging
import re
import secrets
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, wait

import boto3
import httpx
import jwt
import psycopg
import redis
from botocore.config import Config
from botocore.exceptions import ClientError
from celery import Celery
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from kombu import Connection as BrokerConnection
from starlette.exceptions import HTTPException as StarletteHTTPException

from .auth import OidcVerifier, bearer_token
from .config import get_settings
from .db import CURRENT_ACCOUNT_SQL, current_account
from .errors import ApiError
from .keycloak_contract import (
    MONITOR_EFFECTIVE_REALM_MANAGEMENT_ROLES,
    WEB_CLIENT_ID,
    audience_mapper_contract_matches,
    monitor_roles_from_token,
    realm_contract_matches,
    web_client_contract_matches,
)

settings = get_settings()
verifier = OidcVerifier(settings)
app = FastAPI(title="EID API", version="0.1.0")
logger = logging.getLogger(__name__)

TRACEPARENT_RE = re.compile(r"00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})")
EXPECTED_OIDC_AUDIENCE = WEB_CLIENT_ID
READINESS_DEADLINE_SECONDS = 6.0
KEYCLOAK_PROBE_DEADLINE_SECONDS = 4.5
KEYCLOAK_HTTP_TIMEOUT_SECONDS = 0.75
READINESS_PROBE_NAMES = ("postgres", "redis", "rabbitmq", "s3", "keycloak", "worker")
_READINESS_EXECUTOR = ThreadPoolExecutor(max_workers=len(READINESS_PROBE_NAMES))
_READINESS_CAPACITY = threading.BoundedSemaphore(len(READINESS_PROBE_NAMES) * 2)


def _trace_context(incoming: str | None) -> tuple[str, str]:
    match = TRACEPARENT_RE.fullmatch(incoming or "")
    if match and match.group(1) != "0" * 32 and match.group(2) != "0" * 16:
        return incoming or "", match.group(1)
    trace_id = uuid.uuid4().hex
    return f"00-{trace_id}-{secrets.token_hex(8)}-01", trace_id


@app.middleware("http")
async def request_context(request: Request, call_next):
    incoming = request.headers.get("X-Request-ID", "")
    request_id = incoming if re.fullmatch(r"[A-Za-z0-9._-]{1,128}", incoming) else str(uuid.uuid4())
    request.state.request_id = request_id
    traceparent, trace_id = _trace_context(request.headers.get("traceparent"))
    request.state.trace_id = trace_id
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(
            "unexpected_request_failure error_type=%s request_id=%s trace_id=%s",
            type(exc).__name__,
            request_id,
            trace_id,
        )
        response = _error_response(
            status_code=500,
            code="INTERNAL_SERVER_ERROR",
            message="服务暂时无法处理该请求",
            request_id=request_id,
            trace_id=trace_id,
        )
    response.headers["X-Request-ID"] = request_id
    response.headers["traceparent"] = traceparent
    return response


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    request_id: str,
    trace_id: str,
    details: dict | None = None,
    retryable: bool = False,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "request_id": request_id,
                "trace_id": trace_id,
                "retryable": retryable,
            }
        },
    )


@app.exception_handler(ApiError)
async def api_error(request: Request, exc: ApiError):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    trace_id = getattr(request.state, "trace_id", uuid.uuid4().hex)
    return _error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
        request_id=request_id,
        trace_id=trace_id,
        retryable=exc.retryable,
    )


@app.exception_handler(StarletteHTTPException)
async def framework_http_error(request: Request, exc: StarletteHTTPException):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    trace_id = getattr(request.state, "trace_id", uuid.uuid4().hex)
    code, message = {
        404: ("ROUTE_NOT_FOUND", "请求的接口不存在"),
        405: ("METHOD_NOT_ALLOWED", "该接口不支持此请求方法"),
    }.get(exc.status_code, ("HTTP_ERROR", "请求无法处理"))
    return _error_response(
        status_code=exc.status_code,
        code=code,
        message=message,
        request_id=request_id,
        trace_id=trace_id,
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error(request: Request, _exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    trace_id = getattr(request.state, "trace_id", uuid.uuid4().hex)
    return _error_response(
        status_code=422,
        code="REQUEST_VALIDATION_ERROR",
        message="请求参数格式无效",
        request_id=request_id,
        trace_id=trace_id,
    )


@app.get("/health/live")
def live():
    return {"status": "live"}


def _postgres_status() -> str:
    try:
        with psycopg.connect(
            settings.database_url,
            connect_timeout=2,
            options="-c statement_timeout=2000",
        ) as conn:
            database_name, database_user, marker = conn.execute(
                "SELECT current_database(), current_user, "
                "shobj_description(oid, 'pg_database') "
                "FROM pg_database WHERE datname=current_database()"
            ).fetchone()
            if (
                database_name != "eid_local_dev"
                or database_user != "eid_api"
                or marker != settings.environment_marker
            ):
                return "marker_schema_or_privilege_mismatch"
            revision_rows = conn.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchall()
            required_access = conn.execute(
                """
                WITH required(name) AS (
                    VALUES ('identity_account'), ('workspace_membership'), ('workspace')
                ), resolved AS (
                    SELECT to_regclass(format('%I.%I', current_schema(), name)) AS table_oid
                    FROM required
                )
                SELECT bool_and(
                    table_oid IS NOT NULL
                    AND CASE WHEN table_oid IS NULL THEN FALSE
                             ELSE has_table_privilege(current_user, table_oid, 'SELECT') END
                )
                FROM resolved
                """
            ).fetchone()[0]
            if (
                revision_rows != [(settings.required_schema_revision,)]
                or required_access is not True
            ):
                return "marker_schema_or_privilege_mismatch"
            conn.execute(f"EXPLAIN {CURRENT_ACCOUNT_SQL}", ("__readiness_probe__",))
            return "ready"
    except (
        psycopg.errors.UndefinedColumn,
        psycopg.errors.UndefinedTable,
        psycopg.errors.InsufficientPrivilege,
    ):
        return "marker_schema_or_privilege_mismatch"
    except Exception:
        return "unavailable"


def _redis_status() -> str:
    client = None
    try:
        client = redis.from_url(
            settings.redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        return "ready" if client.ping() else "unavailable"
    except Exception:
        return "unavailable"
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


def _rabbitmq_status() -> str:
    try:
        with BrokerConnection(settings.rabbitmq_url, connect_timeout=2) as broker:
            broker.connect()
        return "ready"
    except Exception:
        return "unavailable"


def _s3_status() -> str:
    s3 = None
    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            config=Config(connect_timeout=2, read_timeout=2, retries={"max_attempts": 0}),
        )
        s3.head_bucket(Bucket=settings.s3_bucket)
        return "ready"
    except ClientError as exc:
        error = exc.response.get("Error") or {}
        metadata = exc.response.get("ResponseMetadata") or {}
        if error.get("Code") in {"NoSuchBucket", "404"} or metadata.get("HTTPStatusCode") == 404:
            return "bucket_missing"
        return "unavailable"
    except Exception:
        return "unavailable"
    finally:
        if s3 is not None:
            try:
                s3.close()
            except Exception:
                pass


def _keycloak_timeout(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError
    return min(KEYCLOAK_HTTP_TIMEOUT_SECONDS, remaining)


def _keycloak_client_contract_status(deadline: float) -> str:
    if settings.keycloak_admin_url.rstrip("/") != "http://keycloak:8080":
        return "admin_url_mismatch"
    if settings.keycloak_monitor_client_id != "eid-readiness-monitor":
        return "monitor_client_mismatch"

    with httpx.Client(base_url=settings.keycloak_admin_url.rstrip("/")) as client:
        token_response = client.post(
            "/realms/eid-local/protocol/openid-connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.keycloak_monitor_client_id,
                "client_secret": settings.keycloak_monitor_client_secret,
            },
            timeout=_keycloak_timeout(deadline),
        )
        if token_response.status_code != 200:
            return "monitor_token_unavailable"
        token_payload = token_response.json()
        access_token = token_payload.get("access_token") if isinstance(token_payload, dict) else None
        if not isinstance(access_token, str) or not access_token:
            return "monitor_token_unavailable"
        try:
            if monitor_roles_from_token(access_token) != MONITOR_EFFECTIVE_REALM_MANAGEMENT_ROLES:
                return "monitor_role_mismatch"
        except (jwt.PyJWTError, TypeError, ValueError):
            return "monitor_token_unavailable"

        headers = {"Authorization": f"Bearer {access_token}"}
        realm_response = client.get(
            "/admin/realms/eid-local",
            headers=headers,
            timeout=_keycloak_timeout(deadline),
        )
        if realm_response.status_code == 403:
            return "monitor_permission_denied"
        if realm_response.status_code != 200:
            return "unavailable"
        if not realm_contract_matches(realm_response.json()):
            return "realm_configuration_mismatch"

        clients_response = client.get(
            "/admin/realms/eid-local/clients",
            params={"clientId": WEB_CLIENT_ID},
            headers=headers,
            timeout=_keycloak_timeout(deadline),
        )
        if clients_response.status_code == 403:
            return "monitor_permission_denied"
        if clients_response.status_code != 200:
            return "unavailable"
        clients = clients_response.json()
        if not isinstance(clients, list) or len(clients) != 1:
            return "client_configuration_mismatch"
        web_client = clients[0]
        if not web_client_contract_matches(web_client):
            return "client_configuration_mismatch"
        client_id = web_client.get("id")
        if not isinstance(client_id, str) or not client_id:
            return "client_configuration_mismatch"

        mappers_response = client.get(
            f"/admin/realms/eid-local/clients/{client_id}/protocol-mappers/models",
            headers=headers,
            timeout=_keycloak_timeout(deadline),
        )
        if mappers_response.status_code == 403:
            return "monitor_permission_denied"
        if mappers_response.status_code != 200:
            return "unavailable"
        if not audience_mapper_contract_matches(mappers_response.json()):
            return "audience_mapper_mismatch"
    return "ready"


def _keycloak_status() -> str:
    deadline = time.monotonic() + KEYCLOAK_PROBE_DEADLINE_SECONDS
    public_issuer = settings.oidc_issuer.rstrip("/")
    internal_issuer = settings.oidc_internal_issuer.rstrip("/")
    expected_public_jwks_url = f"{public_issuer}/protocol/openid-connect/certs"
    expected_internal_jwks_url = f"{internal_issuer}/protocol/openid-connect/certs"

    if settings.oidc_audience != EXPECTED_OIDC_AUDIENCE:
        return "audience_mismatch"
    if settings.oidc_jwks_url != expected_internal_jwks_url:
        return "jwks_url_mismatch"

    try:
        discovery_response = httpx.get(
            f"{internal_issuer}/.well-known/openid-configuration",
            timeout=_keycloak_timeout(deadline),
        )
        discovery_response.raise_for_status()
        discovery = discovery_response.json()
        if not isinstance(discovery, dict):
            return "malformed_discovery"
        if discovery.get("issuer") != public_issuer:
            return "issuer_mismatch"
        if discovery.get("jwks_uri") != expected_public_jwks_url:
            return "jwks_uri_mismatch"

        response = httpx.get(settings.oidc_jwks_url, timeout=_keycloak_timeout(deadline))
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            return "malformed_jwks"
        keys = payload.get("keys")
        if not isinstance(keys, list):
            return "malformed_jwks"
        if not keys:
            return "keys_missing"

        usable_signing_key = False
        for key in keys:
            if (
                not isinstance(key, dict)
                or not isinstance(key.get("kid"), str)
                or not key["kid"]
                or not isinstance(key.get("kty"), str)
                or not key["kty"]
                or ("use" in key and not isinstance(key["use"], str))
                or ("alg" in key and not isinstance(key["alg"], str))
                or (
                    "key_ops" in key
                    and (
                        not isinstance(key["key_ops"], list)
                        or any(not isinstance(operation, str) for operation in key["key_ops"])
                    )
                )
            ):
                return "malformed_jwks"

            parsed_key = None
            if key["kty"] == "RSA":
                try:
                    parsed_key = jwt.PyJWK.from_dict(key, algorithm="RS256")
                except (jwt.PyJWTError, TypeError, ValueError):
                    return "malformed_jwks"

            if (
                parsed_key is not None
                and key.get("use") in (None, "sig")
                and key.get("alg") in (None, "RS256")
                and ("key_ops" not in key or "verify" in key["key_ops"])
            ):
                usable_signing_key = True

        if not usable_signing_key:
            return "usable_signing_key_missing"
        return _keycloak_client_contract_status(deadline)
    except TimeoutError:
        return "timeout"
    except (httpx.HTTPError, ValueError, TypeError):
        return "unavailable"


def _worker_status() -> str:
    probe = None
    timeout = settings.worker_health_timeout_seconds
    if timeout < 2:
        return "unavailable"
    try:
        connection_timeout = min(2.0, timeout)
        probe = Celery(
            "edw_api_worker_health",
            broker=settings.rabbitmq_url,
            broker_connection_timeout=connection_timeout,
            broker_transport_options={
                "connect_timeout": connection_timeout,
                "socket_timeout": connection_timeout,
            },
        )
        replies = probe.control.broadcast(
            "dependency_readiness",
            arguments={"timeout_seconds": timeout * 0.75},
            destination=[settings.worker_node_name],
            reply=True,
            timeout=timeout,
        )
        expected = [{settings.worker_node_name: {"status": "ready"}}]
        return "ready" if replies == expected else "unavailable"
    except Exception:
        return "unavailable"
    finally:
        if probe is not None:
            try:
                probe.close()
            except Exception:
                pass


def _release_readiness_capacity(_future: Future[str]) -> None:
    _READINESS_CAPACITY.release()


def readiness() -> tuple[bool, dict[str, str]]:
    probes = {
        "postgres": _postgres_status,
        "redis": _redis_status,
        "rabbitmq": _rabbitmq_status,
        "s3": _s3_status,
        "keycloak": _keycloak_status,
        "worker": _worker_status,
    }
    checks = dict.fromkeys(READINESS_PROBE_NAMES, "timeout")
    futures: dict[Future[str], str] = {}
    deadline = time.monotonic() + READINESS_DEADLINE_SECONDS

    for name in READINESS_PROBE_NAMES:
        remaining = max(0.0, deadline - time.monotonic())
        if not _READINESS_CAPACITY.acquire(timeout=remaining):
            continue
        try:
            future = _READINESS_EXECUTOR.submit(probes[name])
        except Exception:
            _READINESS_CAPACITY.release()
            checks[name] = "unavailable"
            continue
        future.add_done_callback(_release_readiness_capacity)
        futures[future] = name

    remaining = max(0.0, deadline - time.monotonic())
    completed, pending = wait(futures, timeout=remaining)
    for future in completed:
        try:
            checks[futures[future]] = future.result()
        except Exception:
            checks[futures[future]] = "unavailable"
    for future in pending:
        future.cancel()

    return all(value == "ready" for value in checks.values()), checks


@app.get("/health/ready")
def ready():
    ok, checks = readiness()
    if not ok:
        raise ApiError(
            503,
            "DEPENDENCY_NOT_READY",
            "一个或多个必需依赖尚未就绪",
            details={"checks": checks},
            retryable=True,
        )
    return {"status": "ready", "checks": checks}


@app.get("/api/v1/me")
def me(token: str = Depends(bearer_token)):
    actor = verifier.verify(token)
    try:
        account = current_account(settings, actor.subject)
    except psycopg.Error as exc:
        raise ApiError(503, "DATABASE_UNAVAILABLE", "身份存储当前不可用", retryable=True) from exc
    if not account:
        raise ApiError(403, "WORKSPACE_ACCESS_DENIED", "当前身份没有活动工作区")
    return {"data": account}
