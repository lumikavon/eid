"""验证经 NGINX 暴露的最终公共就绪响应。"""

import json
import sys

import httpx

from scripts.verify_local_environment import IsolationError, require

READINESS_URL = "http://localhost:18080/health/ready"
EXPECTED_CHECKS = {"postgres", "redis", "rabbitmq", "s3", "keycloak", "worker"}


def verify_public_readiness():
    response = httpx.get(READINESS_URL, timeout=10)
    require(response.status_code == 200, f"公共 readiness 返回 HTTP {response.status_code}")
    payload = response.json()
    require(isinstance(payload, dict), "公共 readiness JSON 必须为对象")
    require(set(payload) == {"status", "checks"}, "公共 readiness JSON 字段不匹配")
    require(payload.get("status") == "ready", "公共 readiness status 必须为 ready")
    checks = payload.get("checks")
    require(isinstance(checks, dict), "公共 readiness checks 必须为对象")
    require(set(checks) == EXPECTED_CHECKS, "公共 readiness checks 集合不完整")
    require(all(value == "ready" for value in checks.values()), "公共 readiness 存在未就绪依赖")
    return payload


def main():
    print(json.dumps(verify_public_readiness(), sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (IsolationError, httpx.HTTPError, ValueError, TypeError) as exc:
        print(f"最终公共就绪检查失败: {exc}", file=sys.stderr)
        sys.exit(1)
