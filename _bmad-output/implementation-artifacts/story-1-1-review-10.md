# Story 1.1 第十轮审查处置

结论 changes-required。四层完成：四项接受修复，两项驳回。

## 原始报告 blind

# Story 1.1 blind review 10

Verdict: **changes-required**

Baseline: `3440d2f89647aaeacf49213285c055dbe365df7d`

## Findings

1. **High — `scripts/verify_local_environment.py:583`: the live Keycloak guard never verifies the login fixture.** `verify_keycloak()` checks the realm, SPA client, PKCE settings, redirect URI, and audience mapper, but it never reads or authenticates the `local-member` user declared in `deployment/keycloak/eid-local-realm.json:28`. Trigger: after the persistent `eid-local-keycloak` volume has been initialized, delete or disable that user, change its ID, or change its fixture password, then rerun `scripts/bootstrap.ps1`. The client/discovery/JWKS checks still pass, API readiness reports Keycloak ready, and the runtime image manifest can be recorded even though the documented browser login cannot succeed (or cannot map to the seeded PostgreSQL subject). This violates the Story acceptance path that bootstrap yields a workspace reachable through the real local identity. Fix: before migration/application success, use the admin API to require exactly one live fixture user with the expected ID, username, enabled state, and other identity fields, and add a bounded credential/authentication check for the documented fixture password through the configured OIDC flow; fail closed on any mismatch and do not rewrite the existing realm.

2. **High — `scripts/verify_local_environment.py:435`: the database guard verifies only database metadata, not the required current-account mapping.** The guard query checks `current_database`, `current_user`, and the database marker. API readiness later checks only the Alembic revision, table existence, and SELECT privileges (`edw-api/src/edw_api/main.py:161`). Trigger: on the owned persistent PostgreSQL volume at revision `0001_identity_workspace`, delete or deactivate the seeded `identity_account`/`workspace_membership`, change its Keycloak subject, or remove/change the `eid-local` workspace row, then rerun bootstrap. Alembic has no pending work, all readiness checks can return ready, and bootstrap can record success, while a valid `local-member` token receives `WORKSPACE_ACCESS_DENIED` (or maps to an unintended row) from `/api/v1/me`. Fix: add a read-only, exact fixture query to the pre-migration/full isolation guard for the expected subject, account ID, workspace ID/slug, and active membership; reject drift without inserting, updating, or deleting existing rows.

## Validation

- `uv run --frozen pytest tests -q`: 210 passed, 10 skipped.
- `pnpm --filter edw-web test`: 30 passed.
- `pnpm --filter edw-web lint`: passed.
- `pnpm --filter edw-web typecheck`: passed.
- `uv run --frozen ruff check edw-api edw-worker scripts tests migrations`: passed.
- `git diff --check 3440d2f89647aaeacf49213285c055dbe365df7d --`: passed.

The pnpm commands ran under the currently selected Node `24.12.0` and emitted the expected engine warning for the pinned `24.20.0`; no live/container/browser command was run during this review.

## 原始报告 edges

[]

## 原始报告 verification

### Public dynamic responses have no response-level cache-policy verification

- **Changed surface:** NGINX adds `Cache-Control: no-store` to both public API and health responses at `deployment/nginx/default.conf:13` and `deployment/nginx/default.conf:14`.
- **Impacted consumer or site:** the browser account request in `edw-web/src/app/api.ts:62` and the periodically refreshed readiness request in `edw-web/src/app/api.ts:80`, both reached through the public NGINX entry point.
- **Existing test evidence:** the repository-wide `Cache-Control|cache-control|no-store` search found one test reference, `tests/ops/test_guard.py:127-132`; that test reads `default.conf` as text and checks that the health location line contains a string, so it never requests either endpoint and cannot observe the emitted response header. The browser tests in `tests/ux/shell.spec.ts:86-92`, `tests/ux/shell.spec.ts:95-124`, and `tests/ux/shell.spec.ts:257-287` exercise the public account/readiness paths but do not assert their cache headers.
- **Missing verification:** a request through the running NGINX entry point must assert `Cache-Control: no-store` on both `/health/ready` and `/api/v1/me` responses.
- **Demonstration:** removing either `add_header Cache-Control no-store always` directive would leave the source-text health assertion as the only apparent check for health, leave API caching entirely unchecked, and would not fail any browser assertion read above because those tests only inspect status, body, and UI state.
- **Consequence:** a stale readiness result or current-account response can be reused by a browser or intermediary even though the application expects each poll/account refresh to reflect current dependency and access state.
- **Disposition:** `patch` — extend the existing Playwright public-entry-point coverage in `tests/ux/shell.spec.ts` to request both endpoints and assert the actual `cache-control` response header.

### Runtime-image source fingerprints do not have per-service input coverage

- **Changed surface:** `_source_paths` defines which repository inputs invalidate API, Worker, and Web runtime-image records at `scripts/verify_local_environment.py:239-288`; `source_fingerprint` hashes only that enumeration at `scripts/verify_local_environment.py:291-300`.
- **Impacted consumer or site:** `verify_runtime_images` at `scripts/verify_local_environment.py:350-369`, used by the runtime log gate at `scripts/verify_runtime_logs.py:76-85`, relies on those fingerprints to reject a running image after its source has changed.
- **Existing test evidence:** the repository-wide `_source_paths|source_fingerprint` search found executable coverage only in `tests/ops/test_guard.py:107-124` and `tests/ops/test_guard.py:1026-1067`. The first changes only `.dockerignore`, a shared fixed input, and therefore does not prove that any service-specific source root is included. The runtime-manifest test replaces `source_fingerprint` with lambdas at `tests/ops/test_guard.py:1039` and `tests/ops/test_guard.py:1065`, so it verifies comparison behavior without exercising `_source_paths`.
- **Missing verification:** a mutation check for at least one service-specific source file in each of `edw-api/src`, `edw-worker/src`, and `edw-web/src`, asserting that only the intended runtime-image fingerprint set changes and that `verify_runtime_images` rejects the stale record.
- **Demonstration:** if `ROOT / "edw-api" / "src"` were dropped from the Python `trees` list at `scripts/verify_local_environment.py:250`, changing API implementation code would no longer change either Python image fingerprint. The `.dockerignore` test would still pass, and the runtime-manifest test would still pass because it mocks the fingerprint function.
- **Consequence:** changed application code could coexist with an old built/running image while `verify_runtime_images` and the downstream log gate still report the recorded runtime as source-bound and current.
- **Disposition:** `patch` — add focused `_source_paths`/`source_fingerprint` mutation tests in `tests/ops/test_guard.py` for API, Worker, and Web source files, then assert stale runtime records are rejected through `verify_runtime_images`.

## 原始报告 acceptance

# Story 1.1 independent acceptance audit — round 10

Date: 2026-09-10
Baseline: `3440d2f89647aaeacf49213285c055dbe365df7d`
Verdict: **changes-required**

## Findings

1. **[P1] The preserved failure-state screenshot is stale, so AC4 does not yet have current independent visual evidence.** The specification requires authentication/loading/failure states to be visually checked and screenshots to be saved (`_bmad-output/implementation-artifacts/spec-1-1-runnable-workspace.md:40`, `:66`, `:72`). The archived `story-1-1-visual-evidence/workspace-readiness-error.png` has SHA-256 `331174...` and visibly contains only the old generic text `本地依赖尚未就绪`, while the most recent browser artifact at `test-results/workspace-readiness-error.png` has SHA-256 `a7f048...` and contains the newer actionable PostgreSQL explanation produced by `edw-web/src/app/api.ts:14-20,37-48`. The latter is ignored and absent from `.local/story-1-1-files.json`; the implementation inventory instead names the stale archived image (`.local/story-1-1-files.json:57-61`). The archived 1440 shell capture also differs from the latest test-result hash. This contradicts the round-10 claim that the visual-evidence directory was refreshed (`_bmad-output/implementation-artifacts/spec-1-1-runnable-workspace.md:147-149`). Refresh the preserved current screenshots/metrics from the current source-bound run and obtain the required independent screenshot review; do not treat the historical round-3 approval (`story-1-1-visual-evidence/visual-gate-2026-09-10.md:7,23-25`) as approval of changed artifacts.

2. **[P2] A missing or inaccessible Alembic schema is reported as a database connection outage rather than the actual schema/privilege failure.** `_postgres_status` reads `alembic_version` before its explicit table/privilege probe (`edw-api/src/edw_api/main.py:161-193`), and its broad exception handler maps `UndefinedTable`/`InsufficientPrivilege` to `unavailable` (`edw-api/src/edw_api/main.py:195-196`). The Web then tells the operator to check PostgreSQL service/connectivity for `unavailable`, while reserving the correct isolation/schema/privilege reason for `marker_schema_or_privilege_mismatch` (`edw-web/src/app/api.ts:14-16`). Existing tests cover a returned wrong revision and returned false/none privileges, but not the real exception raised when `alembic_version` is absent or unreadable (`tests/contract/test_health.py:273-307`, `:349-386`). This falls short of the required accurate, actionable readiness semantics for schema mismatch (`_bmad-output/implementation-artifacts/spec-1-1-runnable-workspace.md:24`, `:37`, `:69`). Classify schema/privilege query failures as `marker_schema_or_privilege_mismatch` and add exception-path coverage.

## Acceptance coverage

- **AC1 — substantially evidenced, pending Finding 2:** Compose defines exactly W/A/K plus real PostgreSQL, Keycloak, RabbitMQ, Redis, SeaweedFS and NGINX with pinned images (`deployment/compose.yaml:1-121`). Bootstrap orders full isolation guard before migration and final public readiness before runtime-image recording (`scripts/bootstrap.ps1:13-29`). `/api/v1/me` derives the subject from a verified access token and maps it through PostgreSQL (`edw-api/src/edw_api/auth.py:18-44`; `edw-api/src/edw_api/db.py:24-38`). Archived runtime source fingerprints independently recompute exactly for API, Worker and Web.
- **AC2 — evidenced:** JWT issuer/audience/time/signature/type checks are implemented (`edw-api/src/edw_api/auth.py:18-44`); PKCE state/verifier and memory-only tokens are implemented (`edw-web/src/auth/oidc.ts:14-58`); database errors/denials fail closed (`edw-api/src/edw_api/main.py:417-426`). The archived log scan binds the same runtime IDs and reports zero configured secret/token matches (`_bmad-output/implementation-artifacts/story-1-1-runtime-log-scan.json:16-49`, `:51-134`).
- **AC3 — evidenced:** exact tool/lock/image checks stop on mismatch (`scripts/verify_local_environment.py:124-226`); ownership refuses pre-existing unowned volumes/containers (`scripts/verify_local_environment.py:372-401`); database, bucket, broker and Keycloak ownership are checked before migration (`scripts/verify_local_environment.py:404-653`; `migrations/env.py:29-42`). No cleanup/down migration is supplied (`migrations/versions/0001_identity_workspace.py:53-54`).
- **AC4 — blocked by Finding 1:** the original prototype is unchanged from the baseline and its SHA-256 is `C876D444167A999D820BFC27D99C59D091C7AC885E93BC89CDF3B65EA1B4198E`. Exact computed CSS/layout comparison covers six viewports, source icon text and pseudo-elements (`tests/ux/shell.spec.ts:6-83`, `:355-385`), including the 1180/1181 breakpoint. The preserved current failure-state artifact is not synchronized with the latest run.

## Inventory and review boundary

The supplied patch contains 136 paths; `.local/story-1-1-files.json` contains the same 136 paths, with no additions, omissions or missing disk files. The prototype has no baseline diff. This audit was read-only/static except for this requested report; it did not rerun or mutate containers, browser sessions, source, Git, sprint status or BMAD status. Historical runtime results were checked for internal consistency and source-fingerprint binding, but were not promoted to independent approval. Enterprise IdP federation and production security/capacity/HA remain later Epic 13 acceptance boundaries and are not local Story 1.1 failures.

## 逐项主控处置

| ID | 来源 | 判定 | 路由与依据 |
|---|---|---|---|
| 1 | blind | false | 驳回：停用/删除身份或更改凭据后登录被拒绝是预期的认证行为，不是基础设施未就绪。AC2 要求非法身份被拒绝；bootstrap 的资源/客户端配置核验不等于用户级登录验收，实际登录已有独立浏览器门禁。没有证据显示该变化造成权限回退或错误地返回某个硬编码成员；不把一个演示用户永久有效提升为系统就绪条件。 |
| 2 | blind | false | 驳回：数据库内账户/成员 active 与映射就是服务端权威数据；停用或无映射时 WORKSPACE_ACCESS_DENIED 正是预期行为。tests/ops/test_live_current_account.py:82-93 以真实回滚事务验证未映射、停用账户/成员被拒绝，活动映射返回其实际工作区；并无“种子人员永久拥有固定工作区”的运行契约。隔离 marker/schema/角色与用户授权是不同检查。 |
| 3 | verification | medium | patch：补充通过 NGINX 实际响应断言 /api/v1/me 与 /health/ready 的 no-store。 |
| 4 | verification | medium | patch：补充 API、Worker、Web 源文件变化的实际指纹变更及过期记录拒绝覆盖。 |
| 5 | acceptance | medium | patch：刷新当前截图/指标并由下一轮独立审查，不将历史视觉结论冒充当前截图审批。 |
| 6 | acceptance | medium | patch：UndefinedTable/InsufficientPrivilege 应报告 schema/privilege mismatch，补充真实异常类型路径测试。 |

审查方在 Node 24.12.0 下执行的 Web 单元检查单独保留为审查证据；主控已有固定 24.20.0 下的正式验证，不以旧版本结果代替工具门禁。

## 修复验证

四项有效问题已实施并由主控验证：Python 216 passed、真实环境 10 passed (120.97s)、浏览器 19 passed (1.3m)、完整 bootstrap/scoped Ruff 成功，九服务零配置日志匹配。18 张当前截图及差异指标已刷新且绑定本次运行镜像；当前截图与全部差异进入第十一轮独立审查。
