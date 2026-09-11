import os
from pathlib import Path
import shutil
import subprocess

import pytest


def test_failed_full_isolation_guard_stops_before_migration_and_application_launch(tmp_path):
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("需要 PowerShell 7 执行 bootstrap 编排测试")

    source = Path(__file__).parents[2] / "scripts" / "bootstrap.ps1"
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile(source, scripts / "bootstrap.ps1")
    local = tmp_path / ".local"
    local.mkdir()
    (local / "ownership.json").write_text('{"nonce":"test-owner"}', encoding="utf-8")
    stale_manifest = local / "runtime-images.json"
    stale_manifest.write_text('{"stale":true}', encoding="utf-8")

    shims = tmp_path / "shims"
    shims.mkdir()
    log = tmp_path / "commands.log"
    (shims / "docker.cmd").write_text(
        '@echo off\r\necho docker %*>>"%EID_SHIM_LOG%"\r\nexit /b 0\r\n',
        encoding="utf-8",
    )
    (shims / "uv.cmd").write_text(
        "@echo off\r\n"
        'echo uv %*>>"%EID_SHIM_LOG%"\r\n'
        'echo %* | findstr /C:"--source-fingerprints" >nul\r\n'
        "if not errorlevel 1 (echo {\"source_fingerprints\":{\"api\":\"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"worker\":\"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"web\":\"sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc\"}} & exit /b 0)\r\n"
        'echo %* | findstr /C:"verify_local_environment.py" >nul\r\n'
        "if errorlevel 1 exit /b 0\r\n"
        'echo %* | findstr /C:"--prepare" >nul\r\n'
        "if not errorlevel 1 exit /b 0\r\n"
        "exit /b 23\r\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PATH"] = f"{shims}{os.pathsep}{env['PATH']}"
    env["EID_SHIM_LOG"] = str(log)
    env.pop("EID_MIGRATION_DATABASE_URL", None)

    result = subprocess.run(
        [pwsh, "-NoLogo", "-NoProfile", "-File", str(scripts / "bootstrap.ps1")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    calls = log.read_text(encoding="utf-8")
    assert result.returncode != 0
    assert "verify_local_environment.py --prepare" in calls
    assert "scripts.initialize_local_storage" in calls
    assert "verify_local_environment.py" in calls
    assert "alembic upgrade head" not in calls
    assert "--build" not in calls
    assert "--record-runtime-images" not in calls
    assert not stale_manifest.exists()


def test_failed_final_public_readiness_prevents_runtime_image_record(tmp_path):
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("需要 PowerShell 7 执行 bootstrap 编排测试")

    source = Path(__file__).parents[2] / "scripts" / "bootstrap.ps1"
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile(source, scripts / "bootstrap.ps1")
    local = tmp_path / ".local"
    local.mkdir()
    (local / "ownership.json").write_text('{"nonce":"test-owner"}', encoding="utf-8")
    stale_manifest = local / "runtime-images.json"
    stale_manifest.write_text('{"stale":true}', encoding="utf-8")

    shims = tmp_path / "shims"
    shims.mkdir()
    log = tmp_path / "commands.log"
    (shims / "docker.cmd").write_text(
        '@echo off\r\necho docker %*>>"%EID_SHIM_LOG%"\r\nexit /b 0\r\n',
        encoding="utf-8",
    )
    (shims / "uv.cmd").write_text(
        "@echo off\r\n"
        'echo uv %*>>"%EID_SHIM_LOG%"\r\n'
        'echo %* | findstr /C:"--source-fingerprints" >nul\r\n'
        "if not errorlevel 1 (echo {\"source_fingerprints\":{\"api\":\"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"worker\":\"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"web\":\"sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc\"}} & exit /b 0)\r\n"
        'echo %* | findstr /C:"scripts.verify_readiness" >nul\r\n'
        "if errorlevel 1 exit /b 0\r\n"
        "exit /b 24\r\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PATH"] = f"{shims}{os.pathsep}{env['PATH']}"
    env["EID_SHIM_LOG"] = str(log)
    env.pop("EID_MIGRATION_DATABASE_URL", None)

    result = subprocess.run(
        [pwsh, "-NoLogo", "-NoProfile", "-File", str(scripts / "bootstrap.ps1")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    calls = log.read_text(encoding="utf-8")
    assert result.returncode != 0
    assert "alembic upgrade head" in calls
    assert "nginx -s reload" in calls
    assert "scripts.verify_readiness" in calls
    assert "--record-runtime-images" not in calls
    assert not stale_manifest.exists()


def test_failed_rabbitmq_api_access_probe_prevents_readiness_and_runtime_image_record(tmp_path):
    pwsh = shutil.which("pwsh")
    if pwsh is None:
        pytest.skip("需要 PowerShell 7 执行 bootstrap 编排测试")

    source = Path(__file__).parents[2] / "scripts" / "bootstrap.ps1"
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile(source, scripts / "bootstrap.ps1")
    local = tmp_path / ".local"
    local.mkdir()
    (local / "ownership.json").write_text('{"nonce":"test-owner"}', encoding="utf-8")
    stale_manifest = local / "runtime-images.json"
    stale_manifest.write_text('{"stale":true}', encoding="utf-8")

    shims = tmp_path / "shims"
    shims.mkdir()
    log = tmp_path / "commands.log"
    (shims / "docker.cmd").write_text(
        '@echo off\r\necho docker %*>>"%EID_SHIM_LOG%"\r\nexit /b 0\r\n',
        encoding="utf-8",
    )
    (shims / "uv.cmd").write_text(
        "@echo off\r\n"
        'echo uv %*>>"%EID_SHIM_LOG%"\r\n'
        'echo %* | findstr /C:"--source-fingerprints" >nul\r\n'
        "if not errorlevel 1 (echo {\"source_fingerprints\":{\"api\":\"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"worker\":\"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\",\"web\":\"sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc\"}} & exit /b 0)\r\n"
        'echo %* | findstr /C:"scripts.verify_rabbitmq_api_access" >nul\r\n'
        "if errorlevel 1 exit /b 0\r\n"
        "exit /b 25\r\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["PATH"] = f"{shims}{os.pathsep}{env['PATH']}"
    env["EID_SHIM_LOG"] = str(log)
    env.pop("EID_MIGRATION_DATABASE_URL", None)

    result = subprocess.run(
        [pwsh, "-NoLogo", "-NoProfile", "-File", str(scripts / "bootstrap.ps1")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    calls = log.read_text(encoding="utf-8")
    assert result.returncode != 0
    assert "--build" in calls
    assert "nginx -s reload" in calls
    assert "scripts.verify_rabbitmq_api_access" in calls
    assert "scripts.verify_readiness" not in calls
    assert "--record-runtime-images" not in calls
    assert not stale_manifest.exists()
