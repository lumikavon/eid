# Story 1.1 第九轮审查处置

结论 changes-required。Blind 两项、Edge 三项有效；Acceptance 和 Verification approved。

## 原始报告 blind

# Round 9 independent blind code review

Verdict: **changes-required**

Reviewed the supplied full diff against baseline `3440d2f89647aaeacf49213285c055dbe365df7d`, concentrating on the current Story 1.1 runtime and bootstrap behavior. No runtime, browser, live-fault, Git, or status commands were run.

## Findings

### 1. High — the running Worker receives the broker administrator credential used to create users and permissions

- Evidence: `deployment/compose.yaml:26` creates `eid_worker` as RabbitMQ's bootstrap/default user, and `deployment/compose.yaml:72-75` passes that same username/password to the long-running Worker. `scripts/verify_local_environment.py:498-515` authenticates with `eid_worker` and successfully creates `eid_api` plus its permissions through RabbitMQ's management API. The guard at `scripts/verify_local_environment.py:486-494` checks only vhost permission regexes and never rejects management tags on `eid_worker`.
- Trigger: any code executing in the Worker container can reuse its runtime credential against `http://rabbitmq:15672/api/...`; the repository's own bootstrap code demonstrates that this credential can create broker users and change permissions.
- Impact: compromise or misuse of the Worker can rewrite the API identity's restrictions, create additional privileged identities, and administer broker state beyond the Worker's declared runtime role. This defeats the stated independent-identity/resource boundary even though the broker is local and project-owned.
- Required change: use a bootstrap-only RabbitMQ administrator credential that is never present in the Worker container, create a non-management `eid_worker` runtime user with only the exact project-vhost permissions it needs, and have the guard verify both users' tags and exact permissions.

### 2. Medium — framework-generated 404/405 errors bypass the checked-in structured error contract

- Evidence: `edw-api/src/edw_api/main.py:74-96` defines the project envelope, but `edw-api/src/edw_api/main.py:99-111` registers a handler only for the custom `ApiError`. There is no handler for Starlette/FastAPI `HTTPException` (or validation errors), while `edw-api/src/edw_api/main.py:25-27` uses the default FastAPI application behavior.
- Trigger: request an unknown API route such as `GET /api/v1/does-not-exist`, or use an unsupported method on `/api/v1/me`.
- Impact: FastAPI returns its default `{"detail": ...}` body rather than `contracts/error.schema.json`, so clients lose the error code, details, request ID, trace ID, and retryability fields promised by the unified API error contract. The middleware adds correlation headers, but it does not repair the response body.
- Required change: register handlers for framework HTTP/validation errors that call `_error_response`, preserve the appropriate status, and add contract tests for at least unknown-route and method-not-allowed responses.


## 原始报告 edges

[{"location":"edw-api/src/edw_api/main.py:119-152","trigger_condition":"API database URL authenticates as another privileged local role","guard_snippet":"require(current_user == 'eid_api' and required_access is True)","potential_consequence":"API runs with unintended database privileges while reporting ready"},{"location":"edw-worker/src/edw_worker/app.py:35-54","trigger_condition":"Worker database URL authenticates as another privileged local role","guard_snippet":"if current_user != 'eid_worker': raise RuntimeError('Worker database identity mismatch')","potential_consequence":"Worker runs with unintended database privileges while reporting ready"},{"location":"migrations/env.py:17-30","trigger_condition":"PostgreSQL target changes after guard before Alembic opens its connection","guard_snippet":"verify_current_connection(connection, expected_user='eid_migrator', marker='eid-local-dev-v1')","potential_consequence":"Alembic may migrate an unverified database through the second connection"}]


## 原始报告 verification

No verification gaps found.


## 原始报告 acceptance

# Story 1.1 Round 9 Independent Acceptance Audit

Verdict: **approved**

Baseline: `3440d2f89647aaeacf49213285c055dbe365df7d`

Reviewed input: `C:/Users/VIRTUA~1/AppData/Local/Temp/eid-story1-1-review9-9c20cca0cd804cd291e4818eacab386b.diff`

Authoritative inventory: `.local/story-1-1-files.json` (130 paths)

## Acceptance assessment

- **AC1 — approved.** The pinned Compose topology starts the three business projects plus real local PostgreSQL, Keycloak, RabbitMQ, Redis, S3-compatible storage and NGINX (`deployment/compose.yaml:1-105`). Public readiness probes PostgreSQL marker/schema/table privileges, Redis, RabbitMQ, S3, Keycloak discovery/JWKS and a directed Worker dependency response (`edw-api/src/edw_api/main.py:119-372`). `/api/v1/me` derives the subject from a verified bearer token and maps it through PostgreSQL rather than a client-supplied or hardcoded actor/workspace (`edw-api/src/edw_api/auth.py:18-44`, `edw-api/src/edw_api/db.py:21-35`, `edw-api/src/edw_api/main.py:375-384`). Bootstrap proves database, Compose ownership, bucket, vhost and Keycloak realm/client boundaries before Alembic runs (`scripts/bootstrap.ps1:13-23`, `scripts/verify_local_environment.py:341-588`).
- **AC2 — approved.** JWT verification constrains RS256, issuer, audience, expiry/not-before semantics, required claims and bearer token type, with bounded refresh-capable JWKS lookup (`edw-api/src/edw_api/auth.py:18-44`). The Web uses random Code + PKCE S256 state/verifier, keeps access/id tokens in module memory, removes callback parameters, distinguishes 401/403/transient states and submits logout hints in a POST body (`edw-web/src/auth/oidc.ts:1-70`, `edw-web/src/app/App.tsx:23-76`). Database or dependency failures produce structured correlated failures and accurate readiness degradation (`edw-api/src/edw_api/main.py:46-111,361-384`). The archived scan is bound to the recorded nine owned containers and reports zero configured token/credential matches (`_bmad-output/implementation-artifacts/story-1-1-runtime-log-scan.json:1-134`).
- **AC3 — approved.** Exact Node, pnpm, Python and uv versions and immutable base-image references are verified before startup (`scripts/verify_local_environment.py:93-195`). Ownership preparation refuses foreign same-name project resources; initialization checks all existing boundaries before its limited API-broker/bucket writes, reruns the complete guard, and only then allows migration (`scripts/verify_local_environment.py:341-588`, `scripts/initialize_local_storage.py:21-55`, `scripts/bootstrap.ps1:15-23`). The migration contains only the initial identity/workspace mapping and is forward-only with no destructive downgrade (`migrations/versions/0001_identity_workspace.py:15-54`).
- **AC4 — approved.** Exact computed CSS/layout, geometry, text-range and pseudo-element comparisons cover the inherited shell at six required viewports, including 1180/1181 behavior and toast hidden/shown timing (`tests/ux/shell.spec.ts:6-84,289-385`). Direct inspection of the archived actual/reference shell, authenticated, readiness-failure and toast screenshots found no contradiction with the approved method of exact layout/CSS plus independent screenshot review. Decoded image differences reflect the authorized real identity/state/body replacements and are retained as observations, not a PNG byte-identity threshold (`_bmad-output/implementation-artifacts/story-1-1-visual-evidence/visual-gate-2026-09-10.md:3-31`). `docs/prototype/index.html` retains the baseline Git blob.

## Inventory and evidence boundaries

- The supplied diff has 130 unique file headers and exactly matches the 130-path authoritative inventory; there are no missing, extra or duplicate paths.
- The recorded verification reports bootstrap success, 186 default Python passes with 10 opt-in skips, 10 explicit live passes including rollback-only clean-schema migration, 30 Web unit passes, 19 browser passes, scoped static/build checks, and a nine-service zero-match log scan (`_bmad-output/implementation-artifacts/story-1-1-verification.md:3-31`). This audit reviewed those artifacts and their supporting source/tests; it did not rerun or mutate the live environment.
- Approval is limited to Story 1.1's isolated local acceptance. It does not claim enterprise IdP federation, enterprise-system semantics, AI quality, production security/capacity/high availability, later Story behavior, or full Epic completion (`_bmad-output/implementation-artifacts/epic-1-context.md:5-29`).

## Findings

No acceptance findings.


## 主控处置

全部五项采纳：为 bootstrap 保留独立 broker 管理员，Worker 运行用户不得持有管理标签，核验两种运行身份的权限；框架 HTTP/验证异常统一结构化响应并保持关联字段；API 与 Worker 实际 DB 会话检查其预期角色；迁移在真正执行 DDL 的连接上再次核验数据库、角色、marker，保留原全量隔离前置检查。不得把管理凭据传入业务容器，不得自动覆盖外来用户，不删除资源或既有数据。本项目既有 bootstrap fixture 的一次性管理身份分离由主线程检查后执行，正常初始化同时支持全新专属环境。

本轮前已通过 Python 186、Web 30、浏览器19、实际环境10。当前 in-progress，未提交。

## 第九轮修复与主控整合

五项有效问题均已修复：API/Worker 验证实际 SQL 会话身份；Alembic 在执行 DDL 的同一连接内核验数据库、角色与 marker；框架 404/405/422 统一错误契约；RabbitMQ 管理身份与两个非管理运行身份分离，并检查精确 vhost 权限和标签。

主控整合修正：受保护账户查询使用 dict_row，身份检查据此按字段取值；Alembic 由 engine.begin 管理外层事务，避免身份 SELECT 自动开启事务后迁移被回滚。Worker 权限覆盖真实绑定方向和 Celery 控制回复、健康检查、事件队列的固定 UUID 命名，仍限于项目资源。

实际旧 broker 身份转换的最终守卫曾失败：仅更新 tags 的管理 API PUT 清空了 Worker 密码。迁移脚本现显式保留既定本地测试密码；主控核实专属容器、管理员、精确用户集合、Worker 空密码状态和预期权限后恢复该已知测试凭据。完整 broker 身份守卫随后通过。未删除用户、数据库或既有业务数据。

一次重建暴露 RabbitMQ ping 早于管理接口就绪，初始化以 RemoteProtocolError 停止。健康检查改为应用、vhost、AMQP listener 及认证后的管理接口均就绪；身份/权限守卫未弱化。后续完整运行结果见 verification 工件。

第二次完整启动和 10 项真实环境测试通过后，浏览器 18 项行为/视觉测试通过，但第 19 项日志门禁发现 Worker 四次明文凭据匹配，因此本次浏览器验收失败。脱敏定位到 Celery quorum 延迟投递拓扑初始化被权限拒绝，第三方警告输出了完整 broker URI。修复加入 Kombu 当前固定的 celery_delayed_0..27 / celery_delayed_delivery 资源，保持精确项目权限，并在 Worker Celery 日志 handler 上遮蔽 AMQP/AMQPS URI 密码，保留错误与 traceback。聚焦测试证明拒绝相邻/外部资源及失败日志脱敏。主控核实非管理 Worker、唯一项目 vhost 及精确旧权限后应用该权限增量；后续重新构建并验证。历史失败容器记录不通过清空日志伪造成功，新镜像/容器记录单独归档。
