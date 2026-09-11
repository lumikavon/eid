# Story 1.1 第八轮审查处置

结论：changes-required，四路已完成。Blind 与 Acceptance approved；Verification 四项有效修复；Edge 一项不采纳自动清理建议。

## 原始报告 blind

# Story 1.1 Round 8 Blind Review

Verdict: **approved**

## Findings

No findings.

## Review scope and evidence

- Reviewed the supplied 127-file unified diff against baseline `3440d2f89647aaeacf49213285c055dbe365df7d`, excluding encoded PNG bodies and historical review-report prose as permitted.
- Inspected the actual API OIDC, request-correlation, account lookup, readiness, and error paths; the Web PKCE/session/account/readiness state machine; Worker startup and dependency control probes; Compose/NGINX/Keycloak/PostgreSQL/S3 configuration; migration guard; bootstrap ordering; runtime-image provenance; and representative contract, security, ops, Worker, and browser tests.
- Checked reachable failure behavior for invalid or rotated JWT keys, stale/missing database schema and privileges, unavailable dependencies, stalled probes, Worker loss, transient/definitive account failures, logout races, pre-existing resource ownership, and migration ordering.
- No runtime, live-fault, or browser commands were run. This was a read-only code and artifact review.

No concrete trigger was found that contradicts Story 1.1's implemented local behavior or acceptance boundary. Broader production hardening and later-story authorization/task semantics were not treated as defects in this review.


## 原始报告 edges

[{"location":"scripts/verify_local_environment.py:506-515","trigger_condition":"权限 PUT 在用户创建成功后失败","guard_snippet":"try: grant_permissions(); except: delete_user_created_by_this_call(); raise","potential_consequence":"后续启动拒绝已有的不完整用户，初始化无法自行恢复"}]


## 原始报告 verification

### The inactive-account SQL regression test is skipped by every documented test command

- **Changed surface:** `current_account` derives the authenticated workspace and rejects inactive identities or memberships through `i.active AND m.active` — `edw-api/src/edw_api/db.py:21`.
- **Impacted consumer or site:** the `/api/v1/me` handler returns that row as the authenticated account/workspace and treats only a missing row as access denied — `edw-api/src/edw_api/main.py:375`.
- **Existing test evidence:** `tests/contract/test_health.py:57` replaces `current_account` with a lambda, so it cannot observe a SQL-filter regression. The only test I found that executes `current_account` against PostgreSQL and asserts inactive identity and membership rejection is `tests/ops/test_live_current_account.py:25`, but the module is skipped unless `EID_RUN_LIVE_TESTS=1` at `tests/ops/test_live_current_account.py:16`; the documented opt-in command runs only `tests/ops/test_live_dependencies.py` at `README.md:77`. Repository-wide searches for `identity_account`, `workspace_membership`, and `0001_identity_workspace` found no other test that exercises these query filters. The default suite therefore reports this test skipped, as confirmed by the current `184 passed, 9 skipped` run.
- **Missing verification:** the documented repeatable live command must include `tests/ops/test_live_current_account.py` (or an equivalent test target that includes both live modules) so the existing inactive-identity and inactive-membership assertions actually run.
- **Demonstration:** remove either `i.active` or `m.active` from `edw-api/src/edw_api/db.py:30`. The contract test still passes because it mocks the query result, and the documented live command never collects `test_live_current_account.py`; an inactive account or membership can then receive workspace data without a verification failure.
- **Consequence:** the shipped authenticated account route can admit an inactive identity or membership while every documented test command remains green.
- **Disposition:** `patch` — change the documented live-suite command to collect both `tests/ops/test_live_dependencies.py` and `tests/ops/test_live_current_account.py`, retaining the existing rollback-only SQL test.

### The RabbitMQ least-privilege regression probe is not part of bootstrap or either test suite

- **Changed surface:** `verify_rabbitmq_api_access.main` proves the restricted API broker identity can complete the Worker control request/reply and is denied a passive declaration of the `generation` business queue — `scripts/verify_rabbitmq_api_access.py:14`.
- **Impacted consumer or site:** API readiness dispatches `dependency_readiness` using the restricted broker identity configured in Compose — `edw-api/src/edw_api/main.py:283` and `deployment/compose.yaml:49`.
- **Existing test evidence:** `tests/ops/test_guard.py:356` checks the permission regex against locally constructed Celery entity names, and `tests/ops/test_guard.py:385` exercises `verify_rabbitmq` with HTTP/AMQP fakes; neither runs the passive-declare denial. The full-repository search for `verify_rabbitmq_api_access`, `edw_api_broker_permission_probe`, and `passive=True` found the executable only in its own module plus manual documentation at `README.md:28`; `scripts/bootstrap.ps1:15` through `scripts/bootstrap.ps1:28` never invokes it, and neither live test module imports it. The archived one-off probe on RabbitMQ 4.2.6 is valid current evidence, but it is not repeated by bootstrap, the default suite, or the documented live suite.
- **Missing verification:** bootstrap needs to run `python -m scripts.verify_rabbitmq_api_access` after the Worker is healthy and before public readiness/runtime-image recording, with an orchestration test proving a failed probe prevents recording success.
- **Demonstration:** regress the pinned RabbitMQ image to the previously observed 4.1.4 authorization behavior, or otherwise make passive business-queue metadata readable while leaving the configured regexes unchanged. `verify_rabbitmq` still sees the expected strings and can connect, API/Worker readiness still exchanges its control message, and bootstrap records a successful runtime because the only check that issues the denied passive declaration is omitted.
- **Consequence:** a runtime can be archived as verified even though the API broker identity can read business-queue metadata, the exact authorization regression that the patched 4.2.6 probe was introduced to catch.
- **Disposition:** `patch` — invoke the existing probe from `scripts/bootstrap.ps1` and extend `tests/ops/test_bootstrap.py` with a failing-probe shim assertion that `--record-runtime-images` is not reached.

### Re-running bootstrap on an existing volume does not verify the new migration from an empty database

- **Changed surface:** the initial migration creates the three identity/workspace tables, grants the API and Worker read access, and inserts the seed mapping — `migrations/versions/0001_identity_workspace.py:15`.
- **Impacted consumer or site:** bootstrap applies `alembic upgrade head` before starting the applications — `scripts/bootstrap.ps1:22`; a fresh checkout relies on that migration to populate the named PostgreSQL volume declared at `deployment/compose.yaml:95`.
- **Existing test evidence:** the graph search for the qualified `upgrade`/`downgrade` functions returned only their definitions, and repository-wide test searches for the migration revision and its tables found no test that applies the migration. `tests/ops/test_live_dependencies.py:20` and `tests/ops/test_live_current_account.py:25` inspect an already migrated runtime; the latter inserts only rollback fixtures. A successful bootstrap rerun does not execute the body again once `alembic_version` is already at `0001_identity_workspace`.
- **Missing verification:** an isolated clean-state acceptance must apply the checked-in migration to a newly created owned PostgreSQL database/volume, then assert the revision, tables, seed row, and API/Worker privileges before discarding that test-owned runtime.
- **Demonstration:** break the seed insert, a `GRANT`, or a table definition in `upgrade`. The current named volume remains at revision `0001_identity_workspace`, so bootstrap reports `alembic upgrade head` success and the live tests continue observing the old applied schema; a first-time bootstrap from the changed file then fails or produces an unusable workspace.
- **Consequence:** the Story can pass on the retained local runtime while a clean checkout cannot reproduce the promised identity/workspace environment.
- **Disposition:** `patch` — add an opt-in clean-volume migration acceptance beside the existing live operational tests, using a uniquely named owned Compose project and asserting the post-migration contract before cleanup.

### The license-inventory check can certify output produced by a broken classifier

- **Changed surface:** `_uv_names`, `_python_packages`, `_pnpm_packages`, and `build_inventory` classify locked packages as production/development and bind package/image metadata into the audit artifact — `scripts/generate_dependency_licenses.py:27` and `scripts/generate_dependency_licenses.py:85`.
- **Impacted consumer or site:** `deployment/dependency-licenses.json` is the Story's auditable dependency/license inventory, documented as recording installed paths, scope, unknown fields, and image boundaries — `README.md:57`.
- **Existing test evidence:** `main --check` rebuilds the inventory with the same functions and checks only byte equality with the checked-in file — `scripts/generate_dependency_licenses.py:102`; it passed in the current review. Graph searches for `build_inventory`, `_pnpm_packages`, and `_python_packages` returned only their definitions, and a repository-wide search for `generate_dependency_licenses`/`dependency-licenses` found no test. Thus regeneration followed by `--check` cannot detect a shared logic error in the generator.
- **Missing verification:** fixture-driven assertions are absent for production/development classification, missing installed metadata, input digests, and explicit image-boundary unknown records.
- **Demonstration:** make `_pnpm_packages(production=True)` return the all-dependency set, then regenerate the artifact. Every Node dependency is labelled production and `--check` passes because it uses the same regressed classifier; the Python and web suites do not import the generator.
- **Consequence:** the checked-in audit inventory can materially misstate dependency scope while all stated verification remains green.
- **Disposition:** `patch` — add focused unit tests for `build_inventory` with mocked uv/pnpm/installed metadata inputs that distinguish production from development and assert the image-boundary records, without mirroring every parsing branch.

Verdict: changes-required


## 原始报告 acceptance

# Story 1.1 Round 8 Independent Acceptance Audit

Verdict: **approved**

Baseline: `3440d2f89647aaeacf49213285c055dbe365df7d`

Reviewed input: `C:/Users/VIRTUA~1/AppData/Local/Temp/eid-story1-1-review8-3223d09c15684b93b01dbd6e94ab6016.diff`

Authoritative inventory: `.local/story-1-1-files.json` (127 paths)

## Acceptance assessment

- **AC1 — approved.** The delivered Compose topology starts the three business projects and the required local infrastructure behind NGINX (`deployment/compose.yaml:1-105`, `deployment/nginx/default.conf:1-18`). Public readiness checks PostgreSQL marker/schema/table privileges, Redis, RabbitMQ, S3, Keycloak discovery/JWKS and the directed Worker dependency response (`edw-api/src/edw_api/main.py:119-372`). `/api/v1/me` derives the subject from the verified bearer token and resolves the account/workspace from PostgreSQL (`edw-api/src/edw_api/auth.py:18-44`, `edw-api/src/edw_api/db.py:21-35`, `edw-api/src/edw_api/main.py:375-384`). The migration target guard checks the local database identity/marker and the bucket, broker vhost/permissions and Keycloak realm/client before Alembic runs (`scripts/verify_local_environment.py:341-588`, `scripts/bootstrap.ps1:15-23`).
- **AC2 — approved.** JWT verification constrains RS256, issuer, audience, expiry/not-before semantics, required claims and access-token type, while the JWKS client has a bounded timeout and refresh-capable key lookup (`edw-api/src/edw_api/auth.py:18-44`). PKCE uses a random verifier/state and S256; tokens remain module memory, callback parameters are removed from the URL, and logout submits its token hint in a POST body (`edw-web/src/auth/oidc.ts:1-70`). API errors are structured and correlated without exception text, database loss degrades `/me` and readiness, and the Web keeps authentication, authorization and transient dependency states distinct (`edw-api/src/edw_api/main.py:46-111,361-384`, `edw-web/src/app/App.tsx:23-76`). The archived nine-service scan is explicitly bounded to the recorded containers/patterns and reports zero token/credential matches (`_bmad-output/implementation-artifacts/story-1-1-runtime-log-scan.json:1-134`).
- **AC3 — approved.** Exact Node, pnpm, Python and uv versions plus immutable base-image references are checked before startup (`scripts/verify_local_environment.py:93-195`). The bootstrap runs ownership preparation, starts only the isolated infrastructure, initializes permitted empty project resources, reruns the full guard, and only then invokes Alembic (`scripts/bootstrap.ps1:13-28`, `scripts/initialize_local_storage.py:21-55`). Foreign URLs, remote engines, mismatched ownership, mixed S3 inventories, persisted Keycloak deviations and broker permission mismatches fail closed. The migration is forward-only and provides no destructive downgrade (`migrations/versions/0001_identity_workspace.py:15-54`).
- **AC4 — approved.** Exact computed layout/style/geometry/text-range and pseudo-element checks cover the required shell at 1920, 1440, 1181, 1180, 1024 and 768 widths, including the 1180/1181 breakpoint and toast hidden/shown timing (`tests/ux/shell.spec.ts:6-84,289-385`). Independent inspection of the archived actual/reference shell captures and the authenticated, dependency-error and toast captures found no shell-layout contradiction or visible regression. The large decoded image differences are expected body/state replacements and are recorded as observations rather than a byte-equality gate (`_bmad-output/implementation-artifacts/story-1-1-visual-evidence/visual-gate-2026-09-10.md:3-31`). `docs/prototype/index.html` has the same Git blob as the declared baseline.

## Inventory and evidence boundaries

- The diff contains exactly the same 127 paths as `.local/story-1-1-files.json`: no missing, extra or duplicate diff headers.
- The Story implementation file list also enumerates those 127 paths (`_bmad-output/implementation-artifacts/spec-1-1-runnable-workspace.md:162-290`). Historical review reports were treated as audit history rather than current source.
- This audit did not rerun the browser, live-fault, runtime or source test suites. It reviewed the implementation, contracts, tests, archived evidence and the root-recorded runtime results. The recorded runtime evidence remains local acceptance only (`_bmad-output/implementation-artifacts/story-1-1-verification.md:3-29`).
- Approval does not claim enterprise IdP federation, enterprise-system semantics, AI quality, production security, capacity, high availability, or full Epic completion; those boundaries remain explicitly retained for later acceptance (`_bmad-output/implementation-artifacts/epic-1-context.md:5-29`).

## Findings

No acceptance findings.


## 主控逐项处置

- Edge 初始化半完成状态：确认当前行为为安全失败，符合冻结规范“任一隔离边界无法证明即停止，禁止自动清理既有目标”。不采纳自动 delete_user 补偿建议；启动脚本没有承诺在部分管理写入后自动修复未知目标。保留明确异常而不是伪造成功。
- Verification 1：采纳 README 文档缺口。本轮主控已经显式运行两个 live 模块共 9 passed，但 README 的可重复命令遗漏账户 SQL 模块，需补齐，不能仅依赖会话证据。
- Verification 2：采纳。现有真实 broker 正反探针加入 bootstrap 最终门禁，失败不得记录成功镜像；用失败编排 shim 验证。
- Verification 3：采纳迁移回归覆盖需求。采用已核实专属库中的唯一空 schema 和单一回滚事务，运行真实 Alembic 迁移链并验证 revision、表、种子和角色权限；不 drop 数据库、不删除卷、不影响已提交 public schema。测试只证明空状态迁移本体；最初环境创建的证据和隔离守卫仍独立保留。
- Verification 4：采纳。独立 fixtures 测试生产/开发分类、未安装元数据、输入摘要、镜像未知边界，避免仅依赖同一生成器的 --check。

实现代码与新测试完成后再次执行必要验证及全新独立审查；当前 in-progress，未提交。

## 修复验证

四项有效验证修复已完成。默认 Python 186 passed/10 opt-in skips；实际组合 live 命令 10 passed (117.42s)，含真实 Alembic 空 schema 迁移与整体事务回滚。完整 bootstrap exit 0，自动 broker 正反权限门禁通过。业务源代码未因本轮验证补齐而改变。
