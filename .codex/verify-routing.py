"""Read-only routing verification; no model inference or credential copying.

Run: python .codex/verify-routing.py
Use --codex-bin PATH after changing the local Codex installation.
"""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import tempfile
import threading
import tomllib

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "default": ("gpt-6-luna", "low"),
    "eid_coder": ("gpt-6-sol", "medium"),
    "eid_tester": ("gpt-6-sol", "medium"),
    "eid_reviewer": ("gpt-6-sol", "xhigh"),
    "eid_debugger": ("gpt-6-sol", "xhigh"),
    "eid_architect": ("gpt-6-sol", "xhigh"),
    "eid_high_risk": ("gpt-6-sol", "xhigh"),
}


def read_config(binary, env, strict):
    cmd = [binary, "app-server"] + (["--strict-config"] if strict else [])
    process = subprocess.Popen(cmd, cwd=ROOT, env=env, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8")
    messages = queue.Queue()
    errors = []

    def read_stdout():
        for line in process.stdout:
            try:
                messages.put(json.loads(line))
            except ValueError:
                continue
        messages.put(None)

    def read_stderr():
        for line in process.stderr:
            errors.append(line)

    threading.Thread(target=read_stdout, daemon=True).start()
    threading.Thread(target=read_stderr, daemon=True).start()

    def rpc(identifier, method, params):
        process.stdin.write(json.dumps({"id": identifier, "method": method, "params": params}) + "\n")
        process.stdin.flush()
        while True:
            message = messages.get(timeout=45)
            if message is None:
                raise RuntimeError("App Server exited: " + "".join(errors)[-1200:])
            if message.get("id") == identifier:
                if "error" in message:
                    raise RuntimeError(str(message["error"]))
                return message["result"]

    try:
        rpc(1, "initialize", {"clientInfo": {"name": "eid_routing_verify", "version": "1.0"},
                              "capabilities": {"experimentalApi": True}})
        result = rpc(2, "config/read", {"cwd": str(ROOT), "includeLayers": True})
        config = result["config"]
        assert config["agents"]["default_subagent_model"] == "gpt-6-luna", "Project defaults not loaded"
        assert config["agents"]["default_subagent_reasoning_effort"] == "low"
        assert config["agents"]["enabled"] is True
        assert config["agents"]["max_concurrent_threads_per_session"] == 10
        flags = config["features"]["multi_agent_v2"]
        assert flags["hide_spawn_agent_metadata"] is False
        assert flags["expose_spawn_agent_model_overrides"] is False
        origin = result["origins"]["agents.default_subagent_model"]["name"]
        assert origin["type"] == "project", origin
        return {"model": config.get("model"), "effort": config.get("model_reasoning_effort"),
                "agents": config["agents"], "role_selection": flags, "origin": origin}
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-bin", default="D:/npm-global/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe")
    args = parser.parse_args()
    binary = str(Path(args.codex_bin).resolve(strict=True))
    version = subprocess.check_output([binary, "--version"], text=True).strip()
    catalog = json.loads(subprocess.check_output([binary, "debug", "models"], cwd=ROOT, text=True, encoding="utf-8", timeout=60))
    models = {m["slug"]: m for m in catalog["models"]}
    for role, (model, effort) in EXPECTED.items():
        data = tomllib.loads((ROOT / ".codex/agents" / (role + ".toml")).read_text(encoding="utf-8"))
        assert set(data) <= {"name", "description", "developer_instructions", "model", "model_reasoning_effort", "sandbox_mode"}, role
        assert data["name"] == role and data["description"] and data["developer_instructions"], role
        assert (data["model"], data["model_reasoning_effort"]) == (model, effort), role
        assert model in models, (role, "model absent from active catalog")
        assert effort in {v["effort"] for v in models[model]["supported_reasoning_levels"]}, role
    actual = read_config(binary, os.environ.copy(), False)
    # Only a temporary child-process home is changed; real user configuration and auth stay untouched.
    with tempfile.TemporaryDirectory(prefix="eid-routing-verify-", ignore_cleanup_errors=True) as tmp:
        home = Path(tmp)
        (home / "config.toml").write_text("[projects." + json.dumps(str(ROOT)) + "]\ntrust_level = \"trusted\"\n", encoding="utf-8")
        env = dict(os.environ, CODEX_HOME=str(home))
        read_config(binary, env, True)
        # Validate each role's actual configuration keys with the native strict parser too.
        for role in EXPECTED:
            data = tomllib.loads((ROOT / ".codex/agents" / (role + ".toml")).read_text(encoding="utf-8"))
            values = {k: v for k, v in data.items() if k not in {"name", "description"}}
            text = "\n".join(k + " = " + json.dumps(v, ensure_ascii=False) for k, v in values.items())
            text += "\n[projects." + json.dumps(str(ROOT)) + "]\ntrust_level = \"trusted\"\n"
            (home / "config.toml").write_text(text, encoding="utf-8")
            resolved = read_config(binary, env, True)
            assert (resolved["model"], resolved["effort"]) == EXPECTED[role], role
    print(json.dumps({"status": "PASS", "cli": version, "roles": EXPECTED,
                      "checks": ["TOML and role fields", "active catalog model/effort", "effective project config", "isolated native strict config and all role settings"],
                      "effective": actual,
                      "temporary_cleanup": "complete" if not Path(tmp).exists() else "Windows still holds temporary files: " + tmp,
                      "scope": "Configuration validation only; live inference evidence is recorded separately."}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
