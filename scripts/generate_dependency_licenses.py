"""从本地冻结安装元数据生成可复核的依赖/许可证清单。"""

import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "deployment" / "dependency-licenses.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_path(path: str | Path) -> str:
    """Keep checkout locations portable without exposing external host paths."""
    value = Path(path)
    if not value.is_absolute():
        value = ROOT / value
    try:
        return value.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return "external-installation"


def _run(*args: str) -> str:
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError(f"无法读取本地依赖元数据: {' '.join(args)}")
    return result.stdout


def _uv_names(*, production: bool) -> set[str]:
    args = ["uv", "tree", "--frozen"]
    if production:
        args.append("--no-dev")
    output = _run(*args)
    return {
        name.lower().replace("_", "-")
        for name in re.findall(
            r"^[^A-Za-z0-9_.-]*([A-Za-z0-9_.-]+)(?:\[[^]]+\])? v[^\s]+",
            output,
            re.MULTILINE,
        )
        if name not in {"eid-workspace", "edw-api", "edw-worker"}
    }


def _python_packages() -> list[dict]:
    production = _uv_names(production=True)
    locked = _uv_names(production=False)
    installed = {dist.metadata["Name"].lower().replace("_", "-"): dist for dist in metadata.distributions() if dist.metadata.get("Name")}
    records = []
    for name in sorted(locked):
        dist = installed.get(name)
        if dist is None:
            records.append({"name": name, "scope": "production" if name in production else "development", "version": "unknown", "license": "unknown", "source_path": "unknown", "unknown_reason": "锁定依赖未安装在当前冻结环境"})
            continue
        license_value = (dist.metadata.get("License-Expression") or dist.metadata.get("License") or "").strip()
        records.append({
            "name": dist.metadata["Name"],
            "scope": "production" if name in production else "development",
            "version": dist.version,
            "license": license_value or "unknown",
            "source_path": _source_path(dist.locate_file("")),
            "unknown_reason": None if license_value else "已安装 Python metadata 未声明许可证字段",
        })
    return records


def _pnpm_packages(*, production: bool) -> dict[tuple[str, str], dict]:
    args = ["corepack.cmd" if __import__("os").name == "nt" else "corepack", "pnpm", "licenses", "list"]
    if production:
        args.append("--prod")
    args.extend(["--json", "--filter", "edw-web"])
    grouped = json.loads(_run(*args))
    records = {}
    for license_name, packages in grouped.items():
        for package in packages:
            installed_paths = {}
            for path in package.get("paths") or []:
                directory = Path(path)
                if not directory.is_absolute():
                    directory = ROOT / directory
                try:
                    installed = json.loads((directory / "package.json").read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if isinstance(installed, dict) and installed.get("name") == package["name"]:
                    version = installed.get("version")
                    if isinstance(version, str):
                        installed_paths.setdefault(version, []).append(_source_path(directory))
            for version in package.get("versions", []):
                paths = sorted(set(installed_paths.get(version, [])))
                records[(package["name"], version)] = {
                    "name": package["name"], "version": version,
                    "license": package.get("license") or license_name or "unknown",
                    "source_path": paths[0] if paths else "unknown",
                    "source_path_unknown_reason": None if paths else "安装目录 metadata 无法匹配包名称和版本",
                    "unknown_reason": None if (package.get("license") or license_name) else "已安装 pnpm metadata 未声明许可证字段",
                }
    return records


def build_inventory() -> dict:
    prod_node = _pnpm_packages(production=True)
    all_node = _pnpm_packages(production=False)
    node = []
    for key, record in sorted(all_node.items()):
        node.append({**record, "scope": "production" if key in prod_node else "development"})
    images = json.loads((ROOT / "deployment" / "images.lock.json").read_text(encoding="utf-8"))
    return {
        "schema_version": 1,
        "notice": "许可证字段来自本地已安装包 metadata；本清单是审计输入，不构成法律结论。",
        "inputs": {name: f"sha256:{_sha256(ROOT / name)}" for name in ("uv.lock", "pnpm-lock.yaml", "package.json", "edw-web/package.json")},
        "python": _python_packages(),
        "node": node,
        "images": [{"component": name, "reference": reference, "scope": "image-boundary", "license": "unknown", "source_path": "deployment/images.lock.json", "unknown_reason": "锁清单只固定镜像摘要；未审计镜像内 OS 和工具组件许可证"} for name, reference in sorted(images["base_images"].items())],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    encoded = json.dumps(build_inventory(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != encoded:
            raise SystemExit("依赖许可证清单与当前锁定安装元数据不一致；请重新生成")
        return
    OUTPUT.write_text(encoded, encoding="utf-8")


if __name__ == "__main__":
    main()
