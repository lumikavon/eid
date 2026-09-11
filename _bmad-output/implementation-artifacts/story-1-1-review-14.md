# Story 1.1 第十四轮审查处置

结论 changes-required；仅一项有效 Web 消费端缺陷待修。Blind 与 Acceptance approved，当前 18 张截图独立批准。


## 原始报告 blind

# Story 1.1 round 14 blind review

Verdict: **approved**

Review target: the complete 143-file unified diff from baseline `3440d2f89647aaeacf49213285c055dbe365df7d`, supplied at `C:/Users/VIRTUA~1/AppData/Local/Temp/eid-story1-1-review14-eddb0677ab2b48dcb3df65f0ef2d2e60.diff`.

## Findings

No valid correctness, security, error-handling, contract, or operability defects were found within Story 1.1's promised local-isolated acceptance scope. No enhancement requests were promoted to findings.

## Coverage

- Reviewed the full change inventory and the complete production implementation across `edw-api`, `edw-web`, `edw-worker`, migrations, Compose/NGINX/Keycloak/PostgreSQL configuration, bootstrap/isolation guards, runtime image binding, runtime log scanning, contracts, and their tests.
- Traced the migration guard into bootstrap, storage initialization, and Alembic; traced OIDC verification into `/api/v1/me`; and traced the browser authorization-code exchange into the application load path.
- Checked the current 1440 shell against its reference and inspected the authenticated workspace capture. The intentional real identity/state substitutions remain within the approved visual method; no current visual defect was identified.
- Ran `uv run --frozen pytest -q`: 267 passed, 11 explicitly opt-in live tests skipped.
- Ran scoped Ruff: passed.
- Ran pinned portable Node Web lint, typecheck, and unit tests: passed; 42 tests passed.

## Evidence boundary

This approval covers code and safe local/static validation for the supplied Story 1.1 diff. It does not independently rerun Docker bootstrap, the opt-in live suite, or the browser suite, and it does not claim enterprise federation, production security/capacity/high availability, AI quality, or Epic completion.


## 原始报告 edges

[
  {
    "location": "scripts/verify_local_environment.py:738-757",
    "trigger_condition": "A later RabbitMQ user or permission write fails after an earlier write",
    "guard_snippet": "state=inspect_each_runtime_user(); resume_only_exact_partial_state(state); verify_rabbitmq()",
    "potential_consequence": "Bootstrap becomes non-retryable and leaves a partially provisioned broker"
  },
  {
    "location": "scripts/migrate_rabbitmq_bootstrap_admin.py:98-122",
    "trigger_condition": "Any migration write fails after the bootstrap administrator is created",
    "guard_snippet": "state=inspect_migration_phases(); resume_from_last_verified_phase(state); verify_rabbitmq()",
    "potential_consequence": "Retry is refused while the Worker may retain administrator privileges"
  }
]


## 原始报告 verification

### Inactive account and membership filtering is only observed by a normally skipped test

- **Changed surface:** `CURRENT_ACCOUNT_SQL` grants a current account only when both `identity_account.active` and `workspace_membership.active` are true — `edw-api/src/edw_api/db.py:10`.
- **Impacted consumer or site:** the authenticated `GET /api/v1/me` route returns the selected account and workspace as its authorization result — `edw-api/src/edw_api/main.py:530`.
- **Existing test evidence:** the default contract test only verifies that `current_account` sends the shared SQL constant and subject parameter to a mocked cursor — `tests/contract/test_health.py:585`; it does not execute the predicates. The only test that executes the query against PostgreSQL and asserts that inactive identities and inactive memberships return no account is gated by `EID_RUN_LIVE_TESTS` — `tests/ops/test_live_current_account.py:16` — and the default `uv run --frozen pytest tests -q -rs` run skipped it while reporting 267 passed and 11 skipped. Whole-repository searches for `CURRENT_ACCOUNT_SQL` and `current_account(` found no other test that observes these authorization semantics.
- **Missing verification:** a normally run test must execute the account query and assert that an inactive identity and an inactive membership cannot produce an account/workspace response.
- **Demonstration:** removing either `i.active` or `m.active` from `edw-api/src/edw_api/db.py:16` still satisfies the mocked query-dispatch assertion and the readiness `EXPLAIN` check, so the default Python suite remains green; the skipped live assertions at `tests/ops/test_live_current_account.py:82` are the only checks that would fail.
- **Consequence:** an inactive user or revoked workspace membership can receive a successful `/api/v1/me` account/workspace mapping without the normal verification path detecting the authorization regression.
- **Disposition:** `patch` — promote `test_current_account_rejects_unmapped_and_inactive_database_identities` into a normally run isolated-PostgreSQL lane (retaining its rollback transaction), so the repository's standard verification observes the real query semantics.

### Web readiness does not adopt the Keycloak configuration failure states emitted by the API

- **Changed surface:** Keycloak readiness now emits stable configuration states including `monitor_role_mismatch`, `client_configuration_mismatch`, and `audience_mapper_mismatch` — `edw-api/src/edw_api/main.py:305`.
- **Impacted consumer or site:** `getReadiness` renders only statuses present in `readinessReasons`, but its Keycloak map omits all monitor/client/mapper configuration states and sends an unrecognized status to the generic unknown-state branch — `edw-web/src/app/api.ts:21`.
- **Existing test evidence:** API contract tests assert `client_configuration_mismatch` and `audience_mapper_mismatch` at `tests/contract/test_health.py:894`, and monitor token/role/permission states at `tests/contract/test_health.py:994`. Web tests exercise mapped PostgreSQL/S3/Worker reasons at `edw-web/src/app/api.test.ts:70` and an invalid shape with an extra dependency at `edw-web/src/app/api.test.ts:76`; none supplies an exact six-check payload containing one of the API's Keycloak configuration states. A whole-repository search for the emitted status strings found them only in API implementation and API contract tests, with no Web mapping or consumer assertion.
- **Missing verification:** a table-driven Web assertion that every Keycloak status the API can emit maps to a specific safe, readable remediation message.
- **Demonstration:** with all other checks ready and `keycloak: "client_configuration_mismatch"`, `readinessReasons.keycloak[status]` is undefined at `edw-web/src/app/api.ts:34`, so `getReadiness` reports only that an unknown dependency state was returned; the passing Web tests do not fail.
- **Consequence:** a persisted Keycloak client, readiness-monitor role, or audience-mapper drift reaches the browser as an unknown-state message, hiding the concrete configuration failure that the API already identified and preventing the workspace operator from seeing the intended actionable cause.
- **Disposition:** `patch` — extend `readinessReasons.keycloak` and add a table-driven case in `edw-web/src/app/api.test.ts` covering every status emitted by `_keycloak_status` and `_keycloak_client_contract_status`.


## 原始报告 acceptance

# Story 1.1 round-14 independent acceptance

Verdict: **approved**

Review date: 2026-09-10 (America/New_York)
Baseline and current `HEAD`: `3440d2f89647aaeacf49213285c055dbe365df7d`
Scope: Story 1.1 only; 143-file review diff supplied for round 14.

## Acceptance criteria

| AC | Current verdict | Evidence |
|---|---|---|
| AC1 — isolated pinned W/A/K workspace, real local infrastructure, readiness, PKCE login, database-mapped account | Pass | Read-only `--verify-runtime-images` completed with `verified: true`, exact `eid-local` ownership, `localhost:55432/eid_local_dev`, dedicated bucket/vhost/realm/client, Docker 29.1.3 on linux/amd64, and matching API/Web/Worker image/source/container IDs. Current verification records bootstrap exit 0, 11 explicit live passes, and 19 browser passes. The independently rerun default suite passed 267 tests with 11 opt-in live skips; Web units passed 42 tests. |
| AC2 — invalid OIDC/PKCE and dependency failures fail closed; no privileged fallback or token/secret persistence/logging | Pass | Auth and readiness code checks issuer, audience, exp, optional nbf when present, token type, signature/JWKS rotation, persisted Keycloak client/mapper state, database role/schema, and all six readiness dependencies. Current nine-service log scan completed through the supported module entry point with zero JWT/token/code/Bearer/local-credential matches and exact runtime binding. Browser evidence covers PKCE login/denial, 401/403/transient behavior, POST logout without query data, in-memory token handling, empty persistent browser storage, dependency degradation, and stale-response fencing. |
| AC3 — unsupported tools or unprovable isolation stop before migration/application effects | Pass | Tool/engine/image/database/volume/S3/RabbitMQ/Keycloak guards and bootstrap ordering were inspected. Current read-only guard verification passed. Tests explicitly reject wrong versions, remote/Windows Docker engines, foreign database identity/marker/port/volume, invalid managed-volume attachments, unsafe Keycloak state, broad broker/storage rights, and prove failed guard/readiness/broker probes prevent migration, launch, or runtime-manifest success. |
| AC4 — approved exact CSS/layout method plus independent review of current captures; prototype unchanged | Pass | `git diff --exit-code -- docs/prototype/index.html` passed. All 18 files named in `current-screenshot-metrics.json` exist and match their SHA-256 values. I visually inspected all 18 current files at original detail: six actual shells, six reference shells, the reference shown-toast, and five workspace state captures. The 1920, 1440, 1181, 1180, 1024, and 768 views preserve the inherited shell structure and 1180px boundary; authentication/loading/degraded states remain readable and persistent; hidden/shown toast evidence is visibly distinct and matches the source treatment. No broad pixel threshold or waiver was used. **Current round-14 visual verdict: approved.** |

## Diff and evidence integrity

- `git apply --numstat` parsed all 143 diff entries. The Story implementation inventory also contains 143 unique paths, with no missing or extra path in either direction.
- `git apply --check --reverse` passed, proving the complete supplied diff matches the current workspace content, including binary artifacts.
- The archived runtime manifest, `.local/runtime-images.json`, current log-scan runtime object, and current screenshot-metrics runtime object are exactly equal.
- Current screenshot capture: `2026-09-11T01:19:02.331213+00:00`; bound post-flow log scan: `2026-09-11T01:19:10.282503+00:00`.
- Independent reruns: Python `267 passed, 11 skipped`; scoped Ruff passed; Web `42 passed`; Web lint and typecheck passed; read-only runtime binding passed; current nine-service log scan passed with zero configured matches.

## Review findings

```json
[]
```

No valid adversarial, edge-path, verification-gap, inventory, runtime-binding, or current visual findings remain in Story 1.1.

This approval is limited to the real isolated local Story 1.1 implementation and its current evidence. It does not approve enterprise IdP federation, enterprise-system integration, production security/capacity/high availability, AI quality, later stories, or Epic 1 completion.


## 主控逐项处置

| ID | 判定 | 依据与处理 |
|---|---|---|
| E1 | rejected / unpromised enhancement | 新建 RabbitMQ 用户的部分状态按明确契约拒绝自动覆盖；没有承诺任意中途失败可自动续写，失败也不会计为启动完成。此前同类处置及守卫负例保留。 |
| E2 | rejected / unpromised enhancement | 一次性旧状态管理员分离脚本只接受精确已核实旧状态；部分执行后拒绝重试是已记录的安全失败策略。未删除/覆盖身份或降低权限门禁，不新增自动阶段恢复承诺。 |
| V1 | rejected / evidence overlooked | 真实 PostgreSQL 账户过滤测试不是未运行：本轮显式完整 live 命令已 11 passed (71.55s)，包含 rollback-only 的 inactive identity/membership 语义测试。默认套件跳过真实基础设施操作是明确授权开关；README 完整 live 命令与每轮实际门禁保留。复制一个替身/SQL 文本测试不会增加同等真实语义证据，不取消隔离显式门禁。 |
| V2 | medium / patch | API 新增 Keycloak monitor/client/mapper 状态确实落入 Web 未知状态提示。补齐每个实际发出码的安全中文处理提示，并以完整六依赖 503 响应测试消费端映射。 |

修复只触及 Web 原因映射及其测试；不修改认证语义、API、基础设施权限或原型。修复后按影响范围验证并重新完整独立审查。

Round-14 repair verification: Web now maps all 18 emitted non-ready Keycloak states, including the 8 new monitor/client/mapper failures, to safe actionable messages. Complete six-check 503 consumer cases and a separate unknown-state non-reflection case pass. Pinned Node Web units 61 passed, lint/typecheck passed; full bootstrap exit 0. API/Worker source fingerprints remained unchanged, but the build produced new image/container IDs, so the explicit live suite was rerun against those instances: 11 passed in 78.87s. Browser 19 passed (1.0m); all 18 screenshots were refreshed at 2026-09-11T01:49:00.047117+00:00. Final nine-service scan at 2026-09-11T01:49:08.759547+00:00 has zero configured matches and binds the same runtime. Python 267/default tests and scoped Ruff remain valid for unchanged Python sources and were independently rerun in round 14. Current visual approval and complete independent round 15 remain pending; no done or commit yet.
