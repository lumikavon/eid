# Story 1.1 第十六轮审查处置

结论：changes-required；三项有效问题已修复，进入第十七轮完整独立审查。

## 处置与根代理验证

- Acceptance：接受多版本许可证路径绑定错误。逐个读取所列安装目录的 package.json，按实际 name/version 关联，不能证明则明确 unknown 与原因；不假定 versions/paths 顺序一致。原始两版本逆序目录与错名/缺失路径用例覆盖。296 条实际 Node 清单逐条比对名称和版本，零错配、零未知。重生成/check 通过。
- Edges 1：接受。Compose 经 YAML 解析后按服务读取实际 image；Python/Web Dockerfile 按有效 FROM 指令的完整序列匹配，注释和额外基础阶段不能充当锁匹配。三个隔离副本负例证明保留正确注释但活动镜像为 latest 时拒绝。使用已有冻结 uvicorn[standard] 依赖中的 PyYAML，不新增包或改变锁文件。
- Edges 2：接受。完成三工程采集后再次查询各服务容器 ID、运行/健康状态及镜像 ID；替换、停止、不健康、换镜像均拒绝。四个确定性竞态回归覆盖。这是采集窗口复核，不宣称跨 Docker 调用的原子快照或未来不可变化。
- Blind 和 Verification：无有效发现。
- Current visual：Acceptance 再次独立审看并批准全部 18 张当前 PNG。

定向 111 passed；完整 Python 277 passed、11 live-gated skipped；Ruff 通过。修复后的实际只读 guard/runtime 检查通过；应用源指纹及镜像/容器与前次完全一致，未重建或重拍。既有 browser 19、live 11 实例证据保持有效。

## 原始报告 blind

# Story 1.1 independent blind review — round 16

## Verdict

`approved`

## Findings

[]

## Review basis

- Reviewed the complete supplied 145-file patch against baseline `3440d2f89647aaeacf49213285c055dbe365df7d`; `git apply --check --reverse` succeeded, proving the patch, including binary evidence, matches the current workspace.
- Checked the frozen Story intent and edge-case matrix in `_bmad-output/implementation-artifacts/spec-1-1-runnable-workspace.md:14`, the acceptance criteria at `:68`, and the current implementation file inventory at `:174` without treating earlier review verdicts as authority.
- Traced the runtime paths from browser PKCE/token handling through `/api/v1/me`, API dependency readiness, Worker control probes, migration isolation, storage/bootstrap guards, and source-bound running-image verification.
- Verified the API enforces issuer, audience, signature, expiry/not-before and access-token type before server-side subject lookup (`edw-api/src/edw_api/auth.py:18`, `edw-api/src/edw_api/main.py:530`).
- Verified readiness distinguishes process liveness from all six required dependencies and fails closed on probe errors/timeouts (`edw-api/src/edw_api/main.py:160`, `edw-api/src/edw_api/main.py:477`, `edw-worker/src/edw_worker/app.py:104`).
- Verified migration execution performs the complete ownership/database/external-resource guard before connecting and rechecks the connected database identity (`migrations/env.py:28`, `scripts/verify_local_environment.py:937`).
- Verified the documented read-only runtime-image command supplies the dedicated local migration URL (`README.md:24`) and that source fingerprints, image labels, image IDs and running container IDs are compared (`scripts/verify_local_environment.py:369`, `scripts/verify_local_environment.py:442`).

## Executed verification

- `git apply --check --reverse <review16.diff>` — passed.
- `uv run --frozen pytest tests -q` — 269 passed, 11 explicitly live-gated tests skipped.
- `uv run --frozen ruff check edw-api edw-worker scripts tests migrations` — passed.
- Pinned `.local/tools/node-v24.20.0-win-x64/node.exe` plus its Corepack `pnpm.js`: `pnpm --filter edw-web test` — 61 passed; lint and typecheck — passed.
- `docker compose -f deployment/compose.yaml config --quiet` with review-only required interpolation values — passed.
- Pinned Node path plus `uv run --frozen python scripts/generate_dependency_licenses.py --check` — passed.
- With the dedicated `EID_MIGRATION_DATABASE_URL`, `./scripts/verify-local-environment.ps1 --verify-runtime-images` — passed for the owned `eid-local` resources and the current API/Web/Worker image, source and container bindings.
- `uv run --frozen python -m scripts.verify_readiness` — passed; PostgreSQL, Redis, RabbitMQ, S3, Keycloak and Worker all reported `ready` through the public NGINX route.

## Evidence boundary

This review did not rebuild images, rerun browser tests, perform dependency fault injection, or execute the opt-in live database mutation suite. The approval covers the current local Story 1.1 implementation and the read-only evidence above; it makes no enterprise, production, AI, or Epic-level claim.


## 原始报告 edges

[
  {
    "location": "scripts/verify_local_environment.py:259-268",
    "trigger_condition": "Expected image text appears in comments while active Compose image differs",
    "guard_snippet": "parsed = yaml.safe_load(compose); require(parsed['services'][name]['image'] == expected, 'image mismatch')",
    "potential_consequence": "Bootstrap accepts an unpinned or unintended runtime image"
  },
  {
    "location": "scripts/verify_local_environment.py:396-421",
    "trigger_condition": "Previously inspected container is replaced before all service records finish",
    "guard_snippet": "require(requery_container_ids_and_images() == records, 'runtime containers changed during inspection')",
    "potential_consequence": "Manifest records a stopped or superseded container as verified"
  }
]


## 原始报告 verification

No verification gaps found.


## 原始报告 acceptance

# Story 1.1 round-16 independent acceptance audit

**Terminal verdict:** CHANGES REQUIRED
**Current visual verdict:** APPROVED
**Review scope:** local Story 1.1 only; baseline `3440d2f89647aaeacf49213285c055dbe365df7d`

## Finding

### [Medium] Multi-version pnpm packages are bound to the wrong installed source path

`scripts/generate_dependency_licenses.py:85-91` iterates every version reported for a pnpm package but assigns `paths[0]` to every version. The actual pinned `pnpm licenses list --json --filter edw-web` output contains ten package records with two versions and two distinct paths. Consequently, each second version is recorded against the first version's installation directory. For example, `deployment/dependency-licenses.json:797-801` records `@vitest/pretty-format` version `3.2.7` under the `@vitest+pretty-format@3.2.4` path; the same defect affects `brace-expansion 2.1.4`, `globals 16.3.0`, `ignore 7.0.9`, `js-tokens 9.0.1`, `picomatch 4.0.7`, `eslint-visitor-keys 4.2.1`, `glob-parent 6.0.2`, `minimatch 9.0.9`, and `semver 7.8.5`.

The documented generator check still exits 0 because it reproduces the same incorrect mapping. The portability tests at `tests/ops/test_dependency_licenses.py:162-185` use only one version/path per package and therefore do not exercise the raw multi-version shape. This makes the dependency audit inventory materially inaccurate even though it is checkout-portable, so the Story's auditable frozen-dependency evidence is not complete.

Required repair: bind each reported version to its corresponding installed path (and fail closed or mark the path unknown when the association is ambiguous), add a raw two-version/two-path regression fixture, regenerate `deployment/dependency-licenses.json`, and rerun the license generation/check plus focused and complete project tests.

## Acceptance criteria

- **AC1 — isolated runnable W/A/K workspace and current database account:** functional/runtime evidence passes. The README's guarded `--verify-runtime-images` command exited 0 and freshly proved the owned `eid-local` resources, `localhost:55432/eid_local_dev`, Docker 29.1.3 on linux/amd64, and exact API/Web/Worker source, image, and container bindings. Public `/health/ready` returned HTTP 200, `Cache-Control: no-store`, and all six checks (`postgres`, `redis`, `rabbitmq`, `s3`, `keycloak`, `worker`) ready. The dependency-inventory defect above keeps the complete Story evidence gate open.
- **AC2 — invalid authentication/dependency behavior and secret containment:** pass. The current security test pins HTTP 401 for ID, refresh, and missing-token-type rejection at `tests/security/test_oidc.py:140-155`. A fresh read-only nine-service log scan passed with zero configured JWT, token, authorization-code URL, Bearer, or local-credential matches and revalidated the exact runtime bindings.
- **AC3 — unsupported tools or unprovable isolation stop before writes:** pass on inspected source and retained execution evidence. The guarded command re-proved the dedicated migration identity and all external ownership boundaries. No cleanup, production, or enterprise target was exercised in this audit.
- **AC4 — P-00/P-12 fidelity under the approved method:** pass. I independently opened all 18 currently manifested PNGs at original detail. The six actual/reference viewport pairs preserve the 64 px top bar, 266 px sidebar, 12 px shell spacing, navigation/account/notification placement, typography, colors, borders, radii, and shadows. The fixed desktop canvas and narrow-screen note are visible at 1180 px and below and absent at 1181 px. Loading, authenticated, dependency-error, and toast shown/hidden states are readable and preserve the shell. Main-body content differences are the authorized real identity/readiness replacements. No pixel threshold or other waiver was used.

## Evidence integrity and verification

- Supplied diff: 7,093,199 bytes; 110,943 PowerShell-counted lines; SHA-256 `2604A677DA7EC125FFD43395B620135DE3DB45FF8A552520EA4C268DBA00E350`.
- The diff contains exactly 145 unique paths and exactly matches the 145-entry Implementation File List. All 109 text files reconstruct to the current normalized contents, and all 36 binary target Git object hashes match the current files.
- `docs/prototype/index.html` has no difference from the baseline.
- All 18 PNG hashes match `current-screenshot-metrics.json`; capture time remains `2026-09-11T01:49:00.047117+00:00`. The visual verdict above applies to these current bytes.
- Fresh guarded runtime verification: exit 0. Fresh public readiness: six of six ready. Fresh runtime log scan: exit 0, nine services, zero configured matches, exact archived API/Web/Worker source-image-container IDs.
- Raw pnpm metadata comparison found 10 version-to-source-path mismatches. `generate_dependency_licenses.py --check` nevertheless exited 0. Focused license/security tests passed (`29 passed`), demonstrating the missing regression rather than disproving it.
- No rebuild, browser run, live fault test, repository source/status change, container mutation, or original-prototype change was performed.

## Retained boundaries

This review does not approve enterprise IdP federation, enterprise-system integration, production startup/security/capacity/high availability, AI/model quality, Story 1.2+ authorization/domain/task/SSE behavior, the rest of Epic 1, release readiness, or legal sufficiency of license metadata.
