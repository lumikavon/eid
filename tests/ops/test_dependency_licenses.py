"""Dependency-license inventory tests using raw tool and installed metadata fixtures."""

import hashlib
import json
from pathlib import Path

from scripts import generate_dependency_licenses as licenses


class InstalledDistribution:
    def __init__(self, name: str, version: str, root: Path, **metadata: str):
        self.metadata = {"Name": name, **metadata}
        self.version = version
        self._root = root

    def locate_file(self, path: str) -> Path:
        return self._root / path


def installed_node_package(path, name, version):
    path.mkdir(parents=True, exist_ok=True)
    (path / "package.json").write_text(json.dumps({"name": name, "version": version}), encoding="utf-8")
    return str(path)


def test_build_inventory_classifies_raw_dependency_metadata_and_binds_inputs(
    monkeypatch, tmp_path
):
    input_contents = {
        "uv.lock": b"version = 1\nrevision = 3\n",
        "pnpm-lock.yaml": b"lockfileVersion: '9.0'\n",
        "package.json": b'{"name":"eid-workspace"}\n',
        "edw-web/package.json": b'{"name":"edw-web"}\n',
    }
    for relative_path, content in input_contents.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    images = {
        "base_images": {
            "node": "node:24.20.0@sha256:node-digest",
            "python": "python:3.12.14@sha256:python-digest",
        },
        "build_images": {"api": "eid-local-api:0.1.0"},
    }
    deployment = tmp_path / "deployment"
    deployment.mkdir()
    (deployment / "images.lock.json").write_text(json.dumps(images), encoding="utf-8")

    uv_production = """\
eid-workspace v0.1.0
├── edw-api v0.1.0
│   └── Prod_Pkg[secure] v1.2.3
└── shared-lib v4.5.6
"""
    uv_all = uv_production + """\
├── Dev.Tool v7.8.9 (group: dev)
└── absent_pkg v0.2.0 (group: dev)
"""
    pnpm_production = json.dumps(
        {
            "MIT": [
                {
                    "name": "web-runtime",
                    "versions": ["2.1.0"],
                    "paths": [str(tmp_path / "node_modules/web-runtime")],
                }
            ]
        }
    )
    pnpm_all = json.dumps(
        {
            "MIT": [
                {
                    "name": "web-runtime",
                    "versions": ["2.1.0"],
                    "paths": [str(tmp_path / "node_modules/web-runtime")],
                }
            ],
            "Apache-2.0": [
                {
                    "name": "web-test-tool",
                    "versions": ["3.0.0"],
                    "paths": [str(tmp_path / "node_modules/web-test-tool")],
                }
            ],
        }
    )
    installed_node_package(tmp_path / "node_modules/web-runtime", "web-runtime", "2.1.0")
    installed_node_package(tmp_path / "node_modules/web-test-tool", "web-test-tool", "3.0.0")

    def raw_tool_output(*args: str) -> str:
        if args[:3] == ("uv", "tree", "--frozen"):
            return uv_production if "--no-dev" in args else uv_all
        if args[1:4] == ("pnpm", "licenses", "list"):
            return pnpm_production if "--prod" in args else pnpm_all
        raise AssertionError(f"unexpected dependency metadata command: {args}")

    installed = [
        InstalledDistribution(
            "Prod_Pkg",
            "1.2.3",
            tmp_path / "site-packages",
            **{"License-Expression": "MIT"},
        ),
        InstalledDistribution(
            "shared-lib",
            "4.5.6",
            tmp_path / "site-packages",
            License="BSD-3-Clause",
        ),
        InstalledDistribution(
            "Dev.Tool",
            "7.8.9",
            tmp_path / "site-packages",
            License="Apache-2.0",
        ),
    ]
    monkeypatch.setattr(licenses, "ROOT", tmp_path)
    monkeypatch.setattr(licenses, "_run", raw_tool_output)
    monkeypatch.setattr(licenses.metadata, "distributions", lambda: installed)

    inventory = licenses.build_inventory()

    python_by_name = {record["name"].lower().replace("_", "-"): record for record in inventory["python"]}
    assert python_by_name["prod-pkg"]["scope"] == "production"
    assert python_by_name["shared-lib"]["scope"] == "production"
    assert python_by_name["shared-lib"]["source_path"] == "site-packages"
    assert python_by_name["dev.tool"]["scope"] == "development"
    assert python_by_name["absent-pkg"] == {
        "name": "absent-pkg",
        "scope": "development",
        "version": "unknown",
        "license": "unknown",
        "source_path": "unknown",
        "unknown_reason": "锁定依赖未安装在当前冻结环境",
    }

    node_by_name = {record["name"]: record for record in inventory["node"]}
    assert node_by_name["web-runtime"]["scope"] == "production"
    assert node_by_name["web-test-tool"]["scope"] == "development"
    assert node_by_name["web-runtime"]["source_path"] == "node_modules/web-runtime"

    expected_inputs = {
        name: f"sha256:{hashlib.sha256(content).hexdigest()}"
        for name, content in input_contents.items()
    }
    assert inventory["inputs"] == expected_inputs
    assert inventory["images"] == [
        {
            "component": "node",
            "reference": "node:24.20.0@sha256:node-digest",
            "scope": "image-boundary",
            "license": "unknown",
            "source_path": "deployment/images.lock.json",
            "unknown_reason": "锁清单只固定镜像摘要；未审计镜像内 OS 和工具组件许可证",
        },
        {
            "component": "python",
            "reference": "python:3.12.14@sha256:python-digest",
            "scope": "image-boundary",
            "license": "unknown",
            "source_path": "deployment/images.lock.json",
            "unknown_reason": "锁清单只固定镜像摘要；未审计镜像内 OS 和工具组件许可证",
        },
    ]


def test_inventory_is_identical_in_relocated_checkouts(monkeypatch, tmp_path):
    inventories = []
    for checkout in (tmp_path / "first", tmp_path / "different location" / "second"):
        for relative in ("uv.lock", "pnpm-lock.yaml", "package.json", "edw-web/package.json"):
            target = checkout / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("{}", encoding="utf-8")
        (checkout / "deployment").mkdir()
        (checkout / "deployment/images.lock.json").write_text('{"base_images":{}}', encoding="utf-8")
        monkeypatch.setattr(licenses, "ROOT", checkout)
        installed_node_package(checkout / "node_modules/example", "example", "1.0.0")
        installed = [InstalledDistribution("example", "1.0.0", checkout / ".venv/site-packages", License="MIT")]
        monkeypatch.setattr(licenses.metadata, "distributions", lambda: installed)

        def raw_tool_output(*args):
            if args[0] == "uv":
                return "example v1.0.0\n"
            return json.dumps({"MIT": [{"name": "example", "versions": ["1.0.0"], "paths": [str(checkout / "node_modules/example")]}]})

        monkeypatch.setattr(licenses, "_run", raw_tool_output)
        inventories.append(licenses.build_inventory())

    assert inventories[0] == inventories[1]
    assert inventories[0]["python"][0]["source_path"] == ".venv/site-packages"
    assert inventories[0]["node"][0]["source_path"] == "node_modules/example"


def test_external_installation_does_not_leak_host_path(monkeypatch, tmp_path):
    monkeypatch.setattr(licenses, "ROOT", tmp_path / "checkout")
    assert licenses._source_path(tmp_path / "private-host-directory/package") == "external-installation"


def test_node_versions_bind_to_matching_metadata_not_path_order(monkeypatch, tmp_path):
    monkeypatch.setattr(licenses, "ROOT", tmp_path)
    first = installed_node_package(tmp_path / "node_modules/first", "example", "1.0.0")
    second = installed_node_package(tmp_path / "node_modules/second", "example", "2.0.0")
    wrong = installed_node_package(tmp_path / "node_modules/wrong", "another-package", "3.0.0")
    raw = {"MIT": [{"name": "example", "versions": ["1.0.0", "2.0.0", "3.0.0"], "paths": [second, wrong, first, str(tmp_path / "missing")]}]}
    monkeypatch.setattr(licenses, "_run", lambda *args: json.dumps(raw))
    records = licenses._pnpm_packages(production=False)
    assert records[("example", "1.0.0")]["source_path"] == "node_modules/first"
    assert records[("example", "2.0.0")]["source_path"] == "node_modules/second"
    assert records[("example", "3.0.0")]["source_path"] == "unknown"
    assert records[("example", "3.0.0")]["source_path_unknown_reason"]
