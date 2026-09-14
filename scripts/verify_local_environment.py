"""本地环境归属守卫；任何无法验证的事实均阻止写入。"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
import httpx
import yaml
from edw_api.keycloak_contract import (
    MONITOR_CLIENT_ID,
    MONITOR_EFFECTIVE_REALM_MANAGEMENT_ROLES,
    MONITOR_CLIENT_SECRET,
    MONITOR_REALM_MANAGEMENT_ROLES,
    audience_mapper_contract_matches,
    monitor_client_contract_matches,
    monitor_roles_from_token,
    realm_contract_matches,
    web_client_contract_matches,
)
from kombu import Connection as BrokerConnection
from kombu.transport.native_delayed_delivery import (
    CELERY_DELAYED_DELIVERY_EXCHANGE,
    MAX_LEVEL as CELERY_DELAYED_DELIVERY_MAX_LEVEL,
    level_name as celery_delayed_delivery_level_name,
)

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    # Keep the documented direct-script entry point compatible with package helpers.
    sys.path.insert(0, str(ROOT))
    sys.modules["scripts.verify_local_environment"] = sys.modules[__name__]
STATE = ROOT / ".local" / "ownership.json"
PROJECT = "eid-local"
VOLUMES = {"eid-local-postgres", "eid-local-seaweedfs", "eid-local-keycloak"}
VOLUME_SERVICES = {
    "eid-local-postgres": "postgres",
    "eid-local-seaweedfs": "seaweedfs",
    "eid-local-keycloak": "keycloak",
}
IMAGE_LOCK = ROOT / "deployment" / "images.lock.json"
COMPOSE_FILE = ROOT / "deployment" / "compose.yaml"
RUNTIME_IMAGE_MANIFEST = ROOT / ".local" / "runtime-images.json"
BUILD_SOURCE_ENV = {
    "api": "EID_API_SOURCE_FINGERPRINT",
    "worker": "EID_WORKER_SOURCE_FINGERPRINT",
    "web": "EID_WEB_SOURCE_FINGERPRINT",
}
EXPECTED = dict(
    database_host="localhost",
    database_name="eid_local_dev",
    compose_project=PROJECT,
    marker="eid-local-dev-v1",
    bucket="eid-local-artifacts",
    rabbitmq_vhost=PROJECT,
    keycloak_realm=PROJECT,
    keycloak_client="eid-web",
)
RABBITMQ_ADMIN_USER = "eid_broker_admin"
RABBITMQ_ADMIN_PASSWORD = "local-rabbitmq-bootstrap-admin-only"
RABBITMQ_ADMIN_PERMISSIONS = {"configure": ".*", "write": ".*", "read": ".*"}
RABBITMQ_API_USER = "eid_api"
RABBITMQ_API_PASSWORD = "local-api-broker-only"
# Celery 5.5.3 / Kombu 5.5.4 control path: celery.pidbox plus one UUID reply queue.
RABBITMQ_API_PERMISSIONS = {
    "configure": (
        r"^(celery\.pidbox|reply\.celery\.pidbox|"
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
        r"\.reply\.celery\.pidbox)$"
    ),
    # queue.bind requires write on the UUID reply queue and read on its exchange.
    "write": (
        r"^(celery\.pidbox|"
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
        r"\.reply\.celery\.pidbox)$"
    ),
    "read": (
        r"^(reply\.celery\.pidbox|"
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
        r"\.reply\.celery\.pidbox)$"
    ),
}
RABBITMQ_WORKER_USER = "eid_worker"
RABBITMQ_WORKER_PASSWORD = "local-worker-only"
_WORKER_QUEUES = r"generation|retrieval|review|integration|parse_ocr|render"
_CONTROL_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_NATIVE_DELAYED_DELIVERY_RESOURCES = "|".join(
    (
        re.escape(CELERY_DELAYED_DELIVERY_EXCHANGE),
        *(
            re.escape(celery_delayed_delivery_level_name(level))
            for level in range(CELERY_DELAYED_DELIVERY_MAX_LEVEL + 1)
        ),
    )
)
_WORKER_RESOURCES = (
    rf"^({_WORKER_QUEUES}|celery\.pidbox|reply\.celery\.pidbox|celeryev|"
    rf"eid-worker@worker\.celery\.pidbox|{_CONTROL_UUID}\.reply\.celery\.pidbox|"
    rf"celeryev\.{_CONTROL_UUID}|{_NATIVE_DELAYED_DELIVERY_RESOURCES})$"
)
# Queue binding checks write permission on the queue and read on the exchange.
# The Worker health CLI/mingle also create UUID reply queues; gossip uses UUID event queues.
RABBITMQ_WORKER_PERMISSIONS = {
    operation: _WORKER_RESOURCES for operation in ("configure", "write", "read")
}
S3_CONFIG = ROOT / "deployment" / "seaweedfs" / "s3.json"
S3_IDENTITIES = {
    "bootstrap": {
        "name": "eid-s3-bootstrap",
        "access_key": "eid-s3-bootstrap",
        "secret_key": "local-s3-bootstrap-admin-only",
        "actions": ["Admin", "Read:eid-local-artifacts"],
    },
    "api": {
        "name": "eid-s3-api",
        "access_key": "eid-s3-api",
        "secret_key": "local-s3-api-read-only",
        "actions": ["Read:eid-local-artifacts"],
    },
    "worker": {
        "name": "eid-s3-worker",
        "access_key": "eid-s3-worker",
        "secret_key": "local-s3-worker-read-only",
        "actions": ["Read:eid-local-artifacts"],
    },
}


class IsolationError(RuntimeError):
    pass


def require(condition, reason):
    if not condition:
        raise IsolationError(reason)


def command(*args):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=30)
    require(result.returncode == 0, f"{args[0]} {args[1]} 检查失败；请检查本地工具/引擎")
    return result.stdout.strip()


def validate_url(value):
    target = urlsplit(value.replace("postgresql+psycopg:", "postgresql:"))
    require(
        target.scheme == "postgresql"
        and target.hostname == "localhost"
        and target.port == 55432
        and target.path == "/eid_local_dev"
        and target.username == "eid_migrator"
        and not target.query
        and not target.fragment,
        "迁移地址必须为本项目 localhost:55432/eid_local_dev 的迁移身份",
    )


def verify_engine():
    context = json.loads(command("docker", "context", "inspect"))[0]
    require(context["Name"] == "desktop-linux", "只允许本机 desktop-linux context")
    endpoint = context["Endpoints"]["docker"]["Host"]
    require(endpoint.startswith("npipe://"), "拒绝远程 Docker 引擎")
    try:
        server = json.loads(command("docker", "version", "--format", "{{json .Server}}"))
    except (json.JSONDecodeError, TypeError) as exc:
        raise IsolationError("无法读取 Docker Server 平台；需要 linux/amd64") from exc
    actual_platform = f"{server.get('Os', 'unknown')}/{server.get('Arch', 'unknown')}"
    require(
        actual_platform == "linux/amd64",
        f"Docker Server 平台不支持: actual={actual_platform}; required=linux/amd64; "
        "remedy=在 Docker Desktop 切换到 Linux amd64 containers",
    )
    return server


def _require_version(tool, actual, required, remedy):
    require(
        actual == required,
        f"{tool} 版本不支持: actual={actual}; required={required}; remedy={remedy}",
    )


def verify_docker_capabilities():
    server = verify_engine()
    compose_version = command("docker", "compose", "version", "--short")
    compose_help = command("docker", "compose", "up", "--help")
    require(
        "--wait" in compose_help and "--wait-timeout" in compose_help,
        "Docker Compose 缺少启动能力: actual=不支持 --wait/--wait-timeout; "
        "required=支持 --wait 与 --wait-timeout; remedy=升级 Docker Compose plugin",
    )
    buildx_version = command("docker", "buildx", "version")
    require(
        bool(buildx_version),
        "Docker 构建能力缺失: actual=buildx 不可用; required=BuildKit/buildx; "
        "remedy=启用 Docker Desktop BuildKit/buildx",
    )
    return {
        "docker_server": server.get("Version", "unknown"),
        "docker_api": server.get("ApiVersion", "unknown"),
        "docker_platform": f"{server.get('Os')}/{server.get('Arch')}",
        "compose": compose_version,
        "compose_wait": True,
        "compose_wait_timeout": True,
        "buildx": buildx_version,
    }


def verify_versions():
    capabilities = verify_docker_capabilities()
    _require_version("Node", command("node", "--version"), "v24.20.0", "使用 .nvmrc 安装并切换 Node")
    corepack = "corepack.cmd" if os.name == "nt" else "corepack"
    _require_version("pnpm", command(corepack, "pnpm", "--version"), "10.17.1", "运行 corepack prepare pnpm@10.17.1 --activate")
    python_actual = ".".join(map(str, sys.version_info[:3]))
    _require_version("Python", python_actual, "3.12.14", "按 .python-version 安装并切换 Python")
    uv_actual = command("uv", "--version").split()[1]
    _require_version("uv", uv_actual, "0.11.23", "安装 uv==0.11.23 后重试")
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    require(package.get("packageManager") == "pnpm@10.17.1", "package.json 必须锁定 pnpm 10.17.1")
    require(package.get("engines") == {"node": "24.20.0", "pnpm": "10.17.1"}, "package.json 工具链版本不匹配")
    require((ROOT / ".nvmrc").read_text(encoding="utf-8").strip() == "24.20.0", ".nvmrc 版本不匹配")
    require((ROOT / ".python-version").read_text(encoding="utf-8").strip() == "3.12.14", ".python-version 版本不匹配")
    uv_lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    pnpm_lock = (ROOT / "pnpm-lock.yaml").read_text(encoding="utf-8")
    require('requires-python = "==3.12.14"' in uv_lock, "uv.lock 未锁定 Python 3.12.14")
    require("lockfileVersion: '9.0'" in pnpm_lock, "pnpm-lock.yaml 格式或冻结状态不符合 pnpm 10")
    verify_image_manifest()
    return capabilities


def verify_image_manifest():
    try:
        manifest = json.loads(IMAGE_LOCK.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IsolationError(f"镜像锁清单不可读: {exc}") from exc
    require(manifest.get("schema_version") == 1, "镜像锁清单 schema_version 必须为 1")
    require(manifest.get("validated_platform") == "linux/amd64", "镜像锁清单平台必须为 linux/amd64")
    base_images = manifest.get("base_images")
    build_images = manifest.get("build_images")
    require(isinstance(base_images, dict) and isinstance(build_images, dict), "镜像锁清单结构无效")
    require(set(base_images) == {"python", "node", "postgres", "keycloak", "rabbitmq", "redis", "seaweedfs", "nginx"}, "基础镜像清单不完整")
    require(set(build_images) == {"api", "worker", "web"}, "构建镜像清单不完整")
    digest_ref = re.compile(r"^[^\s@:]+(?:/[^\s@:]+)*:[^\s@]+@sha256:[0-9a-f]{64}$")
    for name, image in base_images.items():
        require(isinstance(image, str) and digest_ref.fullmatch(image), f"{name} 必须同时锁定版本与 sha256 摘要")
        require(":latest" not in image, f"{name} 禁止使用 latest")
    versioned_ref = re.compile(r"^[a-z0-9][a-z0-9._/-]*:[0-9]+\.[0-9]+\.[0-9]+$")
    for name, image in build_images.items():
        require(isinstance(image, str) and versioned_ref.fullmatch(image), f"{name} 构建镜像必须使用显式版本")

    compose = COMPOSE_FILE.read_text(encoding="utf-8")
    try:
        parsed_compose = yaml.safe_load(compose)
    except yaml.YAMLError as exc:
        raise IsolationError("Compose YAML 无法解析") from exc
    require(isinstance(parsed_compose, dict), "Compose 结构无效")
    services = parsed_compose.get("services")
    require(isinstance(services, dict), "Compose 缺少 services")
    python_dockerfile = (ROOT / "deployment" / "python.Dockerfile").read_text(encoding="utf-8")
    web_dockerfile = (ROOT / "deployment" / "web.Dockerfile").read_text(encoding="utf-8")
    for name in ("postgres", "keycloak", "rabbitmq", "redis", "seaweedfs", "nginx"):
        require(isinstance(services.get(name), dict) and services[name].get("image") == base_images[name], f"Compose 的 {name} 镜像未匹配锁清单")
    for name, image in build_images.items():
        require(isinstance(services.get(name), dict) and services[name].get("image") == image, f"Compose 的 {name} 构建镜像未显式版本化")
    def from_instructions(source):
        return [line.strip() for line in source.splitlines() if re.match(r"^\s*FROM\s", line, re.IGNORECASE)]
    require(from_instructions(python_dockerfile) == [f"FROM {base_images['python']}"], "Python Dockerfile 基础镜像未匹配锁清单")
    require(from_instructions(web_dockerfile) == [f"FROM {base_images['node']} AS build", f"FROM {base_images['nginx']}"], "Web Dockerfile 基础镜像未匹配锁清单")
    require(
        all(f"EID_{service.upper()}_SOURCE_FINGERPRINT" in compose for service in ("api", "worker", "web")),
        "Compose 构建未逐服务绑定源指纹参数",
    )
    for name, dockerfile in (("Python", python_dockerfile), ("Web", web_dockerfile)):
        require("ARG EID_SOURCE_FINGERPRINT" in dockerfile, f"{name} Dockerfile 缺少源指纹构建参数")
        require(
            'LABEL io.eid.source-fingerprint="${EID_SOURCE_FINGERPRINT}"' in dockerfile,
            f"{name} Dockerfile 缺少不可变源指纹标签",
        )


def build_images():
    try:
        manifest = json.loads(IMAGE_LOCK.read_text(encoding="utf-8"))
        images = manifest["build_images"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise IsolationError(f"无法读取构建镜像清单: {exc}") from exc
    require(isinstance(images, dict) and set(images) == {"api", "worker", "web"}, "构建镜像清单不完整")
    return images


def infrastructure_images():
    verify_image_manifest()
    images = json.loads(IMAGE_LOCK.read_text(encoding="utf-8"))["base_images"]
    return {service: images[service] for service in ("postgres", "keycloak", "rabbitmq", "redis", "seaweedfs", "nginx")}


def _source_paths(service):
    dockerignore = ROOT / ".dockerignore"
    if service in {"api", "worker"}:
        fixed = [
            dockerignore,
            ROOT / "deployment" / "python.Dockerfile",
            ROOT / "pyproject.toml",
            ROOT / "uv.lock",
            ROOT / "edw-api" / "pyproject.toml",
            ROOT / "edw-worker" / "pyproject.toml",
        ]
        trees = [ROOT / "edw-api" / "src", ROOT / "edw-worker" / "src"]
    elif service == "web":
        fixed = [
            dockerignore,
            ROOT / "deployment" / "web.Dockerfile",
            ROOT / "deployment" / "nginx" / "web.conf",
            ROOT / "package.json",
            ROOT / "pnpm-workspace.yaml",
            ROOT / "pnpm-lock.yaml",
            ROOT / "edw-web" / "package.json",
            ROOT / "edw-web" / "index.html",
            ROOT / "edw-web" / "eslint.config.js",
            ROOT / "edw-web" / "tsconfig.app.json",
            ROOT / "edw-web" / "tsconfig.json",
            ROOT / "edw-web" / "tsconfig.node.json",
            ROOT / "edw-web" / "vite.config.ts",
        ]
        trees = [ROOT / "edw-web" / "src"]
        public = ROOT / "edw-web" / "public"
        if public.is_dir():
            trees.append(public)
    else:
        raise IsolationError(f"未知应用镜像服务: {service}")

    paths = list(fixed)
    excluded_parts = {"node_modules", "dist", "__pycache__"}
    for tree in trees:
        paths.extend(
            path
            for path in tree.rglob("*")
            if path.is_file()
            and not excluded_parts.intersection(path.relative_to(ROOT).parts)
            and path.suffix != ".tsbuildinfo"
        )
    unique = sorted(set(paths), key=lambda path: path.relative_to(ROOT).as_posix())
    for path in unique:
        require(path.is_file(), f"镜像源文件缺失: {path.relative_to(ROOT).as_posix()}")
        require(path.resolve().is_relative_to(ROOT.resolve()), "镜像源文件必须位于当前仓库")
    return unique


def source_fingerprint(service):
    digest = hashlib.sha256()
    for path in _source_paths(service):
        relative = path.relative_to(ROOT).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return f"sha256:{digest.hexdigest()}"


def source_fingerprints():
    return {service: source_fingerprint(service) for service in build_images()}


def expected_build_source_fingerprints():
    fingerprint_pattern = re.compile(r"sha256:[0-9a-f]{64}")
    fingerprints = {service: os.environ.get(variable) for service, variable in BUILD_SOURCE_ENV.items()}
    require(
        all(isinstance(value, str) and fingerprint_pattern.fullmatch(value) for value in fingerprints.values()),
        "缺少有效的构建前源指纹；请通过 bootstrap 构建并记录运行镜像",
    )
    return fingerprints


def _recorded_owner_nonce():
    data = json.loads(STATE.read_text(encoding="utf-8"))
    require(isinstance(data, dict) and data.get("root") == str(ROOT) and data.get("project") == PROJECT, "运行镜像归属记录不属于当前工作区")
    require(isinstance(data.get("nonce"), str) and bool(data["nonce"]), "运行镜像归属 nonce 缺失")
    return data["nonce"]


def _runtime_container_id(service, image_id, *, require_health=True, expected_owner=None):
    owner = _recorded_owner_nonce() if expected_owner is None else expected_owner
    container_ids = command(
        "docker", "ps", "-q", "--filter",
        f"label=com.docker.compose.project={PROJECT}", "--filter",
        f"label=com.docker.compose.service={service}",
    ).splitlines()
    require(len(container_ids) == 1, f"需要恰好一个正在运行的 {service} 容器")
    container = json.loads(command("docker", "inspect", container_ids[0]))[0]
    labels = (container.get("Config") or {}).get("Labels") or {}
    require(labels.get("io.eid.owner") == owner, f"{service} 运行容器归属不匹配")
    state = container.get("State") or {}
    require(state.get("Running") is True, f"{service} 容器未运行")
    health = (state.get("Health") or {}).get("Status")
    require(health == "healthy" or (not require_health and health is None), f"{service} 容器未通过健康检查")
    require(container.get("Image") == image_id, f"{service} 运行容器未使用当前构建镜像 ID")
    return container_ids[0]


def current_runtime_images(expected_source_fingerprints=None):
    owner = _recorded_owner_nonce()
    current_source_fingerprints = source_fingerprints()
    if expected_source_fingerprints is not None:
        require(
            expected_source_fingerprints == current_source_fingerprints,
            "源文件与构建前指纹不匹配；拒绝记录运行镜像",
        )
    def inspect_application(service, image_ref):
        try:
            image = json.loads(command("docker", "image", "inspect", image_ref))[0]
        except (json.JSONDecodeError, IndexError, TypeError) as exc:
            raise IsolationError(f"{service} 构建镜像元数据无效") from exc
        image_id = image.get("Id")
        require(re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is not None, f"{service} 构建镜像 ID 无效")
        image_fingerprint = ((image.get("Config") or {}).get("Labels") or {}).get(
            "io.eid.source-fingerprint"
        )
        require(
            image_fingerprint == current_source_fingerprints[service],
            f"{service} 构建镜像缺少或不匹配当前源指纹标签；请重新运行 bootstrap",
        )
        if expected_source_fingerprints is not None:
            require(
                image_fingerprint == expected_source_fingerprints[service],
                f"{service} 构建镜像未绑定构建前源指纹",
            )
        container_id = _runtime_container_id(service, image_id, expected_owner=owner)
        return {
            "image_ref": image_ref,
            "image_id": image_id,
            "container_id": container_id,
            "source_fingerprint": image_fingerprint,
        }
    def inspect_infrastructure(service, image_ref):
        image = json.loads(command("docker", "image", "inspect", image_ref))[0]
        image_id = image.get("Id")
        require(isinstance(image_id, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", image_id), f"{service} 基础镜像 ID 无效")
        return {
            "image_ref": image_ref,
            "image_id": image_id,
            "container_id": _runtime_container_id(service, image_id, require_health=False, expected_owner=owner),
        }
    def recheck_container(service, record):
        require(
            _runtime_container_id(service, record["image_id"], require_health=service in current_source_fingerprints, expected_owner=owner) == record["container_id"],
            f"{service} 容器在运行镜像核验期间已替换",
        )
    # Each read retains its own ownership, health and image checks. Finish the
    # complete first pass before the replacement-detection pass begins.
    with ThreadPoolExecutor(max_workers=3) as executor:
        initial = {service: executor.submit(inspect_application, service, image_ref)
                   for service, image_ref in build_images().items()}
        initial.update({service: executor.submit(inspect_infrastructure, service, image_ref)
                        for service, image_ref in infrastructure_images().items()})
        records = {service: future.result() for service, future in initial.items()}
        final_checks = [executor.submit(recheck_container, service, record)
                        for service, record in records.items()]
        for future in final_checks:
            future.result()
    require(
        source_fingerprints() == current_source_fingerprints,
        "运行镜像核验期间源文件已变化；请重新运行 bootstrap",
    )
    require(_recorded_owner_nonce() == owner, "运行镜像核验期间归属记录已变化")
    return records


def record_runtime_images():
    # 延迟导入，避免 verify_readiness 顶层反向导入本模块时形成循环。
    from scripts.verify_readiness import verify_public_readiness

    verify_public_readiness()
    records = current_runtime_images(expected_build_source_fingerprints())
    verify_public_readiness()
    manifest = {
        "schema_version": 2,
        "source_fingerprint_algorithm": "sha256",
        "services": records,
    }
    RUNTIME_IMAGE_MANIFEST.parent.mkdir(exist_ok=True)
    temporary = RUNTIME_IMAGE_MANIFEST.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(RUNTIME_IMAGE_MANIFEST)
    return manifest


def verify_runtime_images():
    try:
        recorded = json.loads(RUNTIME_IMAGE_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IsolationError(f"运行镜像清单不可读；请重新运行 bootstrap: {exc}") from exc
    require(
        set(recorded) == {"schema_version", "source_fingerprint_algorithm", "services"},
        "运行镜像清单只允许记录版本、指纹算法和服务标识",
    )
    require(recorded.get("schema_version") == 2, "运行镜像清单 schema_version 必须为 2；请重新运行 bootstrap")
    require(recorded.get("source_fingerprint_algorithm") == "sha256", "运行镜像清单指纹算法无效")
    services = recorded.get("services")
    applications = set(build_images())
    require(isinstance(services, dict) and set(services) == applications | set(infrastructure_images()), "运行镜像服务清单不完整")
    base_fields = {"image_ref", "image_id", "container_id"}
    require(
        all(isinstance(record, dict) and set(record) == base_fields | ({"source_fingerprint"} if name in applications else set()) for name, record in services.items()),
        "运行镜像服务记录包含非白名单字段",
    )
    require(recorded.get("services") == current_runtime_images(), "运行镜像或源文件已变化；请重新运行 bootstrap")
    return recorded


def ownership(create=False):
    verify_engine()
    existing_volumes = set(command("docker", "volume", "ls", "--format", "{{.Name}}").splitlines())
    all_container_ids = command("docker", "ps", "-aq").splitlines()
    all_containers = {}
    # Keep the full host inventory, including stopped/foreign volume attachments.
    # Batch CLI calls only; every returned identity and all existing guards still apply.
    for offset in range(0, len(all_container_ids), 100):
        batch = all_container_ids[offset:offset+100]
        rows = json.loads(command("docker", "inspect", *batch))
        require(isinstance(rows, list) and len(rows)==len(batch), "容器检查清单不完整")
        for cid, metadata in zip(batch, rows, strict=True):
            require(isinstance(metadata, dict) and isinstance(metadata.get("Id"), str)
                    and metadata["Id"].startswith(cid), "容器检查身份不匹配")
            all_containers[cid] = metadata
    existing_containers = {
        cid: metadata
        for cid, metadata in all_containers.items()
        if ((metadata.get("Config") or {}).get("Labels") or {}).get(
            "com.docker.compose.project"
        )
        == PROJECT
    }
    if not STATE.exists():
        require(create, "缺少初建归属记录，请先运行 bootstrap 预检")
        require(
            not (existing_volumes & VOLUMES) and not existing_containers,
            "发现预存同名容器或卷；拒绝接管或清理",
        )
        STATE.parent.mkdir(exist_ok=True)
        data = {"root": str(ROOT), "nonce": str(uuid.uuid4()), "project": PROJECT}
        with STATE.open("x", encoding="utf-8") as stream:
            json.dump(data, stream)
    data = json.loads(STATE.read_text(encoding="utf-8"))
    require(data["root"] == str(ROOT) and data["project"] == PROJECT, "归属记录不属于当前工作区")
    for volume in existing_volumes & VOLUMES:
        metadata = json.loads(command("docker", "volume", "inspect", volume))[0]
        labels = metadata.get("Labels") or {}
        require(
            labels.get("com.docker.compose.project") == PROJECT
            and labels.get("io.eid.owner") == data["nonce"],
            "存储卷归属标记不匹配",
        )
    for metadata in existing_containers.values():
        labels = (metadata.get("Config") or {}).get("Labels") or {}
        require(labels.get("io.eid.owner") == data["nonce"], "容器归属不匹配")
    for volume in existing_volumes & VOLUMES:
        attachments = [
            metadata
            for metadata in all_containers.values()
            if any(
                mount.get("Type") == "volume" and mount.get("Name") == volume
                for mount in metadata.get("Mounts") or []
            )
        ]
        require(len(attachments) == 1, f"受管卷 {volume} 必须恰好挂载到一个预期容器")
        labels = (attachments[0].get("Config") or {}).get("Labels") or {}
        require(
            labels.get("com.docker.compose.project") == PROJECT
            and labels.get("com.docker.compose.service") == VOLUME_SERVICES[volume]
            and labels.get("io.eid.owner") == data["nonce"],
            f"受管卷 {volume} 存在外部、错误服务或错误 nonce 挂载",
        )
    return data


def verify_database(value):
    validate_url(value)
    data = ownership()
    ids = command(
        "docker",
        "ps",
        "-q",
        "--filter",
        f"label=com.docker.compose.project={PROJECT}",
        "--filter",
        "label=com.docker.compose.service=postgres",
    ).splitlines()
    require(len(ids) == 1, "需要恰好一个本项目 PostgreSQL 容器")
    info = json.loads(command("docker", "inspect", ids[0]))[0]
    require(
        info["HostConfig"]["PortBindings"].get("5432/tcp")
        == [{"HostIp": "127.0.0.1", "HostPort": "55432"}],
        "数据库端口映射不匹配",
    )
    require(
        any(
            m.get("Name") == "eid-local-postgres" and m["Destination"] == "/var/lib/postgresql/data"
            for m in info["Mounts"]
        ),
        "数据库实际存储卷不匹配",
    )
    import psycopg

    with psycopg.connect(
        value.replace("postgresql+psycopg:", "postgresql:"), connect_timeout=3,
        options="-c statement_timeout=5000 -c lock_timeout=2000",
    ) as conn:
        row = conn.execute(
            "SELECT current_database(), current_user, shobj_description(oid, 'pg_database') FROM pg_database WHERE datname=current_database()"
        ).fetchone()
        require(
            row == ("eid_local_dev", "eid_migrator", EXPECTED["marker"]),
            "实际数据库名称/身份/marker不匹配",
        )
    return data


def service_container(service, container_port, host_port):
    ids = command(
        "docker",
        "ps",
        "-q",
        "--filter",
        f"label=com.docker.compose.project={PROJECT}",
        "--filter",
        f"label=com.docker.compose.service={service}",
    ).splitlines()
    require(len(ids) == 1, f"需要恰好一个本项目 {service} 容器")
    info = json.loads(command("docker", "inspect", ids[0]))[0]
    expected_owner = json.loads(STATE.read_text(encoding="utf-8"))["nonce"]
    labels = (info.get("Config") or {}).get("Labels") or {}
    require(labels.get("io.eid.owner") == expected_owner, f"{service} 容器归属不匹配")
    require(
        info["HostConfig"]["PortBindings"].get(f"{container_port}/tcp")
        == [{"HostIp": "127.0.0.1", "HostPort": str(host_port)}],
        f"{service} 端口映射不匹配",
    )
    return ids[0]


def verify_s3_configuration():
    try:
        payload = json.loads(S3_CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IsolationError(f"SeaweedFS S3 身份配置不可读: {exc}") from exc
    expected = [
        {
            "name": identity["name"],
            "credentials": [
                {
                    "accessKey": identity["access_key"],
                    "secretKey": identity["secret_key"],
                }
            ],
            "actions": identity["actions"],
        }
        for identity in S3_IDENTITIES.values()
    ]
    require(payload == {"identities": expected}, "SeaweedFS S3 身份或精确授权不匹配")


def s3_client(role, *, endpoint_url="http://localhost:58333"):
    identity = S3_IDENTITIES[role]
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=identity["access_key"],
        aws_secret_access_key=identity["secret_key"],
        region_name="us-east-1",
        config=Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 0}),
    )


def _require_s3_access_denied(operation, label):
    try:
        operation()
    except ClientError as exc:
        error = exc.response.get("Error") or {}
        metadata = exc.response.get("ResponseMetadata") or {}
        require(
            error.get("Code") in {"AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch"}
            or metadata.get("HTTPStatusCode") == 403,
            f"S3 {label} 负例未以授权拒绝结束",
        )
        return
    raise IsolationError(f"S3 {label} 越权请求未被拒绝")


def verify_bucket():
    service_container("seaweedfs", 8333, 58333)
    verify_s3_configuration()
    bootstrap = s3_client("bootstrap")
    buckets = {item["Name"] for item in bootstrap.list_buckets().get("Buckets", [])}
    require(buckets == {EXPECTED["bucket"]}, "对象存储实际 bucket 不是本项目专属 bucket")
    bootstrap.head_bucket(Bucket=EXPECTED["bucket"])
    for role in ("api", "worker"):
        runtime = s3_client(role)
        runtime.head_bucket(Bucket=EXPECTED["bucket"])
        _require_s3_access_denied(
            lambda client=runtime: client.list_objects_v2(
                Bucket=EXPECTED["bucket"], MaxKeys=1
            ),
            f"{role} bucket 对象清单",
        )
        _require_s3_access_denied(
            lambda client=runtime: client.get_bucket_acl(Bucket=EXPECTED["bucket"]),
            f"{role} bucket ACL 读取",
        )
        _require_s3_access_denied(
            lambda client=runtime: client.head_bucket(Bucket="eid-local-foreign"),
            f"{role} 跨 bucket 读取",
        )


def _rabbitmq_tags(payload) -> set[str]:
    tags = payload.get("tags")
    if tags in (None, ""):
        return set()
    if isinstance(tags, str):
        return {tag.strip() for tag in tags.split(",") if tag.strip()}
    require(isinstance(tags, list) and all(isinstance(tag, str) for tag in tags), "RabbitMQ 用户标签格式无效")
    return set(tags)


def _rabbitmq_user_state(
    client, *, user_name: str, password: str, permissions: dict[str, str],
    label: str, expected_tags: set[str], allow_missing: bool,
) -> str:
    user = client.get(f"/api/users/{user_name}")
    if user.status_code == 404:
        require(allow_missing, f"RabbitMQ {label}专属用户不存在")
        return "missing"
    require(user.status_code == 200 and user.json().get("name") == user_name, f"无法核验 RabbitMQ {label}专属用户")
    actual_tags = _rabbitmq_tags(user.json())
    if expected_tags:
        require(actual_tags == expected_tags, f"RabbitMQ {label}专属用户管理标签不匹配")
    else:
        require(not actual_tags, f"RabbitMQ {label}专属用户不得拥有管理标签")
    permission_response = client.get(f"/api/users/{user_name}/permissions")
    require(permission_response.status_code == 200, f"无法核验 RabbitMQ {label}专属用户权限")
    grants = permission_response.json()
    require(
        len(grants) == 1
        and grants[0].get("vhost") == EXPECTED["rabbitmq_vhost"]
        and all(grants[0].get(key) == value for key, value in permissions.items()),
        f"RabbitMQ {label}专属用户权限不匹配，拒绝覆盖",
    )
    try:
        with BrokerConnection(
            f"amqp://{user_name}:{password}"
            "@localhost:55672/eid-local",
            connect_timeout=3,
        ) as broker:
            broker.connect()
    except Exception as exc:
        raise IsolationError(f"RabbitMQ {label}专属用户 fixture 凭据不匹配，拒绝覆盖") from exc
    return "ready"


def verify_rabbitmq(*, allow_missing_runtime: bool = False) -> str:
    service_container("rabbitmq", 15672, 55673)
    auth = httpx.BasicAuth(RABBITMQ_ADMIN_USER, RABBITMQ_ADMIN_PASSWORD)
    with httpx.Client(base_url="http://localhost:55673", auth=auth, timeout=5) as client:
        whoami = client.get("/api/whoami")
        require(
            whoami.status_code == 200
            and whoami.json().get("name") == RABBITMQ_ADMIN_USER
            and _rabbitmq_tags(whoami.json()) == {"administrator"},
            "RabbitMQ bootstrap 管理员 fixture 凭据或标签不匹配",
        )
        vhost = client.get("/api/vhosts/eid-local")
        require(vhost.status_code == 200 and vhost.json().get("name") == EXPECTED["rabbitmq_vhost"], "RabbitMQ 实际 vhost 不匹配")
        _rabbitmq_user_state(
            client, user_name=RABBITMQ_ADMIN_USER, password=RABBITMQ_ADMIN_PASSWORD,
            permissions=RABBITMQ_ADMIN_PERMISSIONS, label="bootstrap 管理员",
            expected_tags={"administrator"}, allow_missing=False,
        )
        states = {
            _rabbitmq_user_state(
                client, user_name=RABBITMQ_API_USER, password=RABBITMQ_API_PASSWORD,
                permissions=RABBITMQ_API_PERMISSIONS, label="API",
                expected_tags=set(), allow_missing=allow_missing_runtime,
            ),
            _rabbitmq_user_state(
                client, user_name=RABBITMQ_WORKER_USER, password=RABBITMQ_WORKER_PASSWORD,
                permissions=RABBITMQ_WORKER_PERMISSIONS, label="Worker",
                expected_tags=set(), allow_missing=allow_missing_runtime,
            ),
        }
        require(
            len(states) == 1,
            "RabbitMQ 运行用户清单处于部分初始化状态，拒绝自动修复",
        )
        return states.pop()


def create_rabbitmq_runtime_users():
    """仅在两个运行身份都缺失时创建它们；绝不修改既有用户。"""
    require(
        verify_rabbitmq(allow_missing_runtime=True) == "missing",
        "RabbitMQ 运行用户已存在，拒绝覆盖",
    )
    auth = httpx.BasicAuth(RABBITMQ_ADMIN_USER, RABBITMQ_ADMIN_PASSWORD)
    with httpx.Client(base_url="http://localhost:55673", auth=auth, timeout=5) as client:
        for user_name, password, permissions, label in (
            (RABBITMQ_API_USER, RABBITMQ_API_PASSWORD, RABBITMQ_API_PERMISSIONS, "API"),
            (RABBITMQ_WORKER_USER, RABBITMQ_WORKER_PASSWORD, RABBITMQ_WORKER_PERMISSIONS, "Worker"),
        ):
            created = client.put(
                f"/api/users/{user_name}", json={"password": password, "tags": ""},
            )
            require(created.status_code in (201, 204), f"创建 RabbitMQ {label}专属用户失败")
            granted = client.put(
                f"/api/permissions/eid-local/{user_name}", json=permissions,
            )
            require(granted.status_code in (201, 204), f"设置 RabbitMQ {label}专属用户权限失败")


def _keycloak_json(response, reason):
    try:
        return response.json()
    except (TypeError, ValueError) as exc:
        raise IsolationError(reason) from exc


def _keycloak_admin_headers(client):
    response = client.post(
        "/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": "eid-local-admin",
            "password": "local-keycloak-admin-only",
        },
    )
    payload = _keycloak_json(response, "本地 Keycloak 管理核验令牌格式无效")
    token = payload.get("access_token") if isinstance(payload, dict) else None
    require(response.status_code == 200 and isinstance(token, str) and token, "无法取得本地 Keycloak 管理核验令牌")
    return {"Authorization": f"Bearer {token}"}


def _keycloak_monitor_state(client, auth_headers, *, allow_incomplete):
    clients_response = client.get(
        f"/admin/realms/{EXPECTED['keycloak_realm']}/clients",
        params={"clientId": MONITOR_CLIENT_ID},
        headers=auth_headers,
    )
    clients = _keycloak_json(clients_response, "Keycloak readiness monitor client 表示格式无效")
    require(clients_response.status_code == 200 and isinstance(clients, list), "无法核验 Keycloak readiness monitor client")
    if not clients:
        require(allow_incomplete, "Keycloak readiness monitor client 不存在")
        users_response = client.get(
            f"/admin/realms/{EXPECTED['keycloak_realm']}/users",
            params={"username": f"service-account-{MONITOR_CLIENT_ID}", "exact": "true"},
            headers=auth_headers,
        )
        users = _keycloak_json(users_response, "Keycloak readiness monitor 用户清单格式无效")
        require(users_response.status_code == 200 and users == [], "readiness monitor client 缺失但 service account 残留，拒绝修复")
        return "missing", {}
    require(len(clients) == 1 and monitor_client_contract_matches(clients[0]), "Keycloak readiness monitor client 配置不匹配，拒绝覆盖")
    monitor = clients[0]
    monitor_id = monitor.get("id")
    require(isinstance(monitor_id, str) and monitor_id, "Keycloak readiness monitor client 缺少持久化 ID")

    token_response = client.post(
        f"/realms/{EXPECTED['keycloak_realm']}/protocol/openid-connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": MONITOR_CLIENT_ID,
            "client_secret": MONITOR_CLIENT_SECRET,
        },
    )
    token_payload = _keycloak_json(token_response, "Keycloak readiness monitor 令牌格式无效")
    token = token_payload.get("access_token") if isinstance(token_payload, dict) else None
    require(token_response.status_code == 200 and isinstance(token, str) and token, "Keycloak readiness monitor fixture secret 不匹配，拒绝覆盖")
    roles = monitor_roles_from_token(token)
    require(
        roles.issubset(MONITOR_EFFECTIVE_REALM_MANAGEMENT_ROLES),
        "Keycloak readiness monitor 含非只读 realm-management 角色",
    )
    if roles != MONITOR_EFFECTIVE_REALM_MANAGEMENT_ROLES:
        require(allow_incomplete, "Keycloak readiness monitor 缺少精确只读角色")
        return "roles-missing", {
            "monitor_id": monitor_id,
            "missing_roles": MONITOR_REALM_MANAGEMENT_ROLES - roles,
        }
    return "ready", {"monitor_id": monitor_id}


def _verify_keycloak(client, *, allow_incomplete_monitor):
    realm = client.get(f"/realms/{EXPECTED['keycloak_realm']}")
    realm_payload = _keycloak_json(realm, "Keycloak 实际 realm 表示格式无效")
    require(realm.status_code == 200 and isinstance(realm_payload, dict) and realm_payload.get("realm") == EXPECTED["keycloak_realm"], "Keycloak 实际 realm 不存在或不匹配")
    auth_headers = _keycloak_admin_headers(client)
    admin_realm = client.get(f"/admin/realms/{EXPECTED['keycloak_realm']}", headers=auth_headers)
    admin_realm_payload = _keycloak_json(admin_realm, "Keycloak 管理 realm 表示格式无效")
    require(admin_realm.status_code == 200 and realm_contract_matches(admin_realm_payload), "Keycloak 管理 realm 实际配置不匹配或未禁用自助注册")
    clients_response = client.get(
        f"/admin/realms/{EXPECTED['keycloak_realm']}/clients",
        params={"clientId": EXPECTED["keycloak_client"]},
        headers=auth_headers,
    )
    clients = _keycloak_json(clients_response, "Keycloak client 表示格式无效")
    require(clients_response.status_code == 200 and isinstance(clients, list) and len(clients) == 1 and web_client_contract_matches(clients[0]), "Keycloak client 实际配置不满足本项目 Code + PKCE S256 边界")
    client_id = clients[0].get("id")
    require(isinstance(client_id, str) and client_id, "Keycloak client 缺少持久化 ID")
    mappers_response = client.get(
        f"/admin/realms/{EXPECTED['keycloak_realm']}/clients/{client_id}/protocol-mappers/models",
        headers=auth_headers,
    )
    mappers = _keycloak_json(mappers_response, "Keycloak client mapper 表示格式无效")
    require(mappers_response.status_code == 200 and audience_mapper_contract_matches(mappers), "Keycloak client 缺少与导入配置一致的 access-token audience mapper")
    state, details = _keycloak_monitor_state(client, auth_headers, allow_incomplete=allow_incomplete_monitor)
    return state, details, auth_headers


def verify_keycloak(*, allow_incomplete_monitor=False):
    service_container("keycloak", 8080, 58080)
    with httpx.Client(base_url="http://localhost:58080", timeout=5) as client:
        state, _details, _headers = _verify_keycloak(
            client, allow_incomplete_monitor=allow_incomplete_monitor
        )
        return state


def provision_keycloak_readiness_monitor():
    """Create only the named read-only monitor or finish its missing role mapping."""
    service_container("keycloak", 8080, 58080)
    with httpx.Client(base_url="http://localhost:58080", timeout=5) as client:
        state, details, auth_headers = _verify_keycloak(client, allow_incomplete_monitor=True)
        if state == "ready":
            return
        if state == "missing":
            created = client.post(
                f"/admin/realms/{EXPECTED['keycloak_realm']}/clients",
                headers=auth_headers,
                json={
                    "clientId": MONITOR_CLIENT_ID,
                    "name": "EID readiness monitor",
                    "enabled": True,
                    "publicClient": False,
                    "secret": MONITOR_CLIENT_SECRET,
                    "serviceAccountsEnabled": True,
                    "standardFlowEnabled": False,
                    "implicitFlowEnabled": False,
                    "directAccessGrantsEnabled": False,
                    "redirectUris": [],
                    "webOrigins": [],
                },
            )
            require(created.status_code == 201, "创建 Keycloak readiness monitor client 失败")
            state, details, auth_headers = _verify_keycloak(client, allow_incomplete_monitor=True)
        require(state == "roles-missing", "Keycloak readiness monitor 部分状态不可安全补全")
        monitor_id = details["monitor_id"]
        service_user_response = client.get(
            f"/admin/realms/{EXPECTED['keycloak_realm']}/clients/{monitor_id}/service-account-user",
            headers=auth_headers,
        )
        service_user = _keycloak_json(service_user_response, "readiness monitor service account 格式无效")
        service_user_id = service_user.get("id") if isinstance(service_user, dict) else None
        require(service_user_response.status_code == 200 and isinstance(service_user_id, str) and service_user_id, "无法定位 readiness monitor service account")
        realm_management_response = client.get(
            f"/admin/realms/{EXPECTED['keycloak_realm']}/clients",
            params={"clientId": "realm-management"},
            headers=auth_headers,
        )
        realm_management = _keycloak_json(realm_management_response, "realm-management client 表示格式无效")
        require(realm_management_response.status_code == 200 and isinstance(realm_management, list) and len(realm_management) == 1, "无法唯一定位 realm-management client")
        realm_management_id = realm_management[0].get("id")
        require(isinstance(realm_management_id, str) and realm_management_id, "realm-management client 缺少持久化 ID")
        role_representations = []
        for role_name in sorted(details["missing_roles"]):
            response = client.get(
                f"/admin/realms/{EXPECTED['keycloak_realm']}/clients/{realm_management_id}/roles/{role_name}",
                headers=auth_headers,
            )
            role = _keycloak_json(response, f"Keycloak {role_name} 角色表示格式无效")
            require(response.status_code == 200 and isinstance(role, dict) and role.get("name") == role_name, f"无法读取 Keycloak {role_name} 角色")
            role_representations.append(role)
        mapped = client.post(
            f"/admin/realms/{EXPECTED['keycloak_realm']}/users/{service_user_id}/role-mappings/clients/{realm_management_id}",
            headers=auth_headers,
            json=role_representations,
        )
        require(mapped.status_code == 204, "设置 Keycloak readiness monitor 只读角色失败")
        final_state, _details, _headers = _verify_keycloak(client, allow_incomplete_monitor=False)
        require(final_state == "ready", "Keycloak readiness monitor 创建后核验失败")


def verify_external_isolation():
    verify_bucket()
    verify_rabbitmq()
    verify_keycloak()


def verify_migration_target(value):
    data = verify_database(value)
    verify_external_isolation()
    return data


def main():
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--check-only", action="store_true")
    parser.add_argument("--skip-versions", action="store_true")
    action.add_argument("--record-runtime-images", action="store_true")
    action.add_argument("--verify-runtime-images", action="store_true")
    action.add_argument("--source-fingerprints", action="store_true")
    args = parser.parse_args()
    capabilities = None
    if not args.skip_versions:
        capabilities = verify_versions()
    data = ownership(create=args.prepare)
    if not args.prepare and not args.source_fingerprints:
        verify_migration_target(os.environ.get("EID_MIGRATION_DATABASE_URL", ""))
    live_resources_verified = not args.prepare and not args.source_fingerprints
    result = {
        "project": PROJECT,
        "owner": data["nonce"],
        "ownership_verified": True,
        "live_resources_verified": live_resources_verified,
        "verified": live_resources_verified,
    }
    if live_resources_verified:
        result.update(
            host="localhost:55432",
            database="eid_local_dev",
            bucket=EXPECTED["bucket"],
            rabbitmq_vhost=EXPECTED["rabbitmq_vhost"],
            keycloak_realm=EXPECTED["keycloak_realm"],
            keycloak_client=EXPECTED["keycloak_client"],
        )
    if capabilities:
        result["tool_capabilities"] = capabilities
    if args.record_runtime_images:
        result["runtime_images"] = record_runtime_images()
    elif args.verify_runtime_images:
        result["runtime_images"] = verify_runtime_images()
    elif args.source_fingerprints:
        result["source_fingerprints"] = source_fingerprints()
    print(
        json.dumps(result)
    )


if __name__ == "__main__":
    try:
        main()
    except (
        IsolationError,
        BotoCoreError,
        ClientError,
        httpx.HTTPError,
        ValueError,
        KeyError,
        OSError,
        subprocess.TimeoutExpired,
    ) as exc:
        print(f"隔离检查失败: {exc}", file=sys.stderr)
        sys.exit(1)
