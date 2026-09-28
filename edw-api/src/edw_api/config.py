from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EID_", extra="ignore")

    environment_marker: str = "eid-local-dev-v1"
    database_url: str = "postgresql://eid_api:local-api-only@postgres:5432/eid_local_dev"
    redis_url: str = "redis://redis:6379/0"
    rabbitmq_url: str = "amqp://eid_api:local-api-broker-only@rabbitmq:5672/eid-local"
    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key: str = "eid-s3-api"
    s3_secret_key: str = "local-s3-api-read-only"
    s3_bucket: str = "eid-local-artifacts"
    oidc_issuer: str = "http://localhost:18080/realms/eid-local"
    oidc_internal_issuer: str = "http://keycloak:8080/realms/eid-local"
    oidc_audience: str = "eid-web"
    oidc_jwks_url: str = "http://keycloak:8080/realms/eid-local/protocol/openid-connect/certs"
    keycloak_admin_url: str = "http://keycloak:8080"
    keycloak_monitor_client_id: str = "eid-readiness-monitor"
    keycloak_monitor_client_secret: str = "local-keycloak-readiness-monitor-only"
    required_schema_revision: str = "0019_section_evidence"
    bge_m3_endpoint: str = ""
    reranker_endpoint: str = ""
    knowledge_gateway_url: str = ""
    knowledge_gateway_key: str = ""
    evidence_wake_key: str = ""
    discovery_policy_environment: Literal["production", "isolated_development"] = "production"
    request_id_header: str = Field(default="X-Request-ID")
    worker_node_name: str = "eid-worker@worker"
    worker_health_timeout_seconds: float = Field(default=2.0, gt=0, le=10)


@lru_cache
def get_settings() -> Settings:
    return Settings()
