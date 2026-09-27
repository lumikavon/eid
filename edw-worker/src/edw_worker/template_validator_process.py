"""凭据隔离的模板解析子进程；仅由 Worker 调用，不提供发布权限。"""
import base64
import json
import os
from pathlib import Path
import sys


def main():
    # Production validation is Linux-only: do not silently omit memory/CPU limits.
    if os.name != "posix":
        print(json.dumps({"error": "VALIDATOR_ISOLATION_UNAVAILABLE"}))
        return
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))
    # stdout is an unlinked file owned by the supervisor; cap its kernel size before
    # the parent reads it. This is not a filesystem or network sandbox.
    resource.setrlimit(resource.RLIMIT_FSIZE, (12 * 1024 * 1024, 12 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    # -I discards PYTHONPATH; load only the trusted sibling parser, not upload paths.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from template_assets import MAX_PACKAGE, PackageRejected, validate_template_package
    try:
        raw = sys.stdin.buffer.read(MAX_PACKAGE + 1)
        result = validate_template_package(raw)
        report = {"source_sha256": result.source_sha256,
                  "manifest_sha256": result.manifest_sha256,
                  "validator_version": result.validator_version,
                  "development_only": True, "manifest": result.manifest,
                  "assets": [{"name": asset.name, "source_sha256": asset.source_sha256,
                              "sha256": asset.normalized_png_sha256,
                              "width": asset.width, "height": asset.height,
                              "png_base64": base64.b64encode(asset.normalized_png).decode("ascii")}
                             for asset in result.assets]}
        print(json.dumps({"report": report}, ensure_ascii=True, separators=(",", ":")))
    except PackageRejected as exc:
        print(json.dumps({"error": exc.code}))
    except Exception:
        # No untrusted image/parser details or environment values in diagnostics.
        print(json.dumps({"error": "VALIDATOR_FAILED"}))


if __name__ == "__main__":
    main()
