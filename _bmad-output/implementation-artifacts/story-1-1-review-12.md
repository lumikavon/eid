# Story 1.1 第十二轮审查处置

结论 changes-required。Acceptance 四项 AC 和当前 18 张视觉工件 approved；其他层五项修复、一项驳回。

## 原始报告 blind

# Story 1.1 blind review 12

Verdict: **changes-required**

Baseline: `3440d2f89647aaeacf49213285c055dbe365df7d`

## Finding

1. **[P1] PostgreSQL readiness can report `ready` for a structurally incompatible current-revision schema.** In `edw-api/src/edw_api/main.py:172-193`, `_postgres_status` accepts the database when `alembic_version` equals `0001_identity_workspace` and the three expected relation names exist with `SELECT` privilege. The probe never references the columns that `/api/v1/me` actually reads (`identity_account.id/subject/display_name/department/active`, `workspace.id/slug/name`, and `workspace_membership.identity_id/workspace_id/active` at `edw-api/src/edw_api/db.py:28-34`). A concrete trigger is a drifted database whose revision row remains `0001_identity_workspace` and whose three tables still exist, but where `workspace_membership.active` (or another required column) has been dropped or renamed. The relation/privilege query still returns true, so public `/health/ready` reports PostgreSQL and the overall service as ready; the next authenticated `/api/v1/me` fails with `UndefinedColumn` and returns `DATABASE_UNAVAILABLE` (503). This violates the Story requirement that readiness reflect schema compatibility rather than advertise a broken account path. Make the readiness probe execute a bounded zero-row projection/join over the exact Story 1.1 columns (or perform an equivalent explicit column contract check), classify structural SQL errors as `marker_schema_or_privilege_mismatch`, and add a regression case for a present-but-incompatible table shape.

## Review coverage

The supplied unified diff was reviewed as the complete change set. Code review covered OIDC/PKCE and in-memory token handling, JWT/JWKS rejection, current-account mapping, request correlation and structured errors, the six dependency probes, Worker startup/control health, migration ordering, Docker/volume/resource ownership guards, pinned build inputs, RabbitMQ identities and permissions, runtime image/source binding, log scanning, NGINX routing, and Web response bounds/session races. The six current shell viewport captures and the authenticated, loading, dependency-error, and toast captures were directly inspected; no additional visual defect was found.

## Validation

- `uv run --frozen pytest tests -q`: 222 passed, 10 skipped; the skipped tests are explicitly live-gated.
- `uv run --frozen ruff check edw-api edw-worker scripts tests migrations`: passed.
- Portable Node 24.20.0: Web lint and typecheck passed; 39 Vitest tests passed.
- `uv run --frozen python scripts/generate_dependency_licenses.py --check`: passed.
- `git diff --check 3440d2f89647aaeacf49213285c055dbe365df7d --`: passed.

No source, Git, BMAD/status, runtime, container, or browser mutation was performed. The archived bootstrap/live/browser/runtime-log results were treated as supplied local evidence and were not promoted to enterprise federation or production security/capacity/HA acceptance.

## 原始报告 edges

[{"location":"edw-web/src/auth/oidc.ts:56-59","trigger_condition":"Token endpoint streams oversized JSON before the timeout","guard_snippet":"const payload = await boundedJson(response, 64 * 1024, '令牌响应无效');","potential_consequence":"A malicious identity response can exhaust browser memory"},{"location":"edw-api/src/edw_api/main.py:172-194","trigger_condition":"Alembic version table contains the expected row plus another head","guard_snippet":"revisions = {row[0] for row in conn.execute('SELECT version_num FROM alembic_version').fetchall()}; require(revisions == {settings.required_schema_revision})","potential_consequence":"Readiness reports ready for a divergent database schema"},{"location":"edw-worker/src/edw_worker/app.py:42-57","trigger_condition":"Worker URL targets another database carrying copied marker and revision","guard_snippet":"database = conn.execute('SELECT current_database()').fetchone()[0]; if database != 'eid_local_dev': raise RuntimeError('Worker database mismatch')","potential_consequence":"Worker reports ready while connected to the wrong database"},{"location":"scripts/migrate_rabbitmq_bootstrap_admin.py:102-122","trigger_condition":"Any migration PUT fails after an earlier PUT succeeded","guard_snippet":"state = inspect_migration_state(); resume_verified_remaining_steps(state)","potential_consequence":"The one-time migration cannot be safely retried"}]

## 原始报告 verification

### Worker delivery durability can regress without any failing verification

- **Changed surface:** the Worker config declares six durable quorum queues, enables publisher confirms, restricts serialization to JSON, and enables task events — `edw-worker/src/edw_worker/app.py:17`.
- **Impacted consumer or site:** the real Worker process passes this Celery app to `worker_main` at `edw-worker/src/edw_worker/__main__.py:20`, and the Compose Worker consumes the generation, retrieval, review, and integration queues at `deployment/compose.yaml:83`.
- **Existing test evidence:** `test_worker_main_runs_dependency_gate_before_consumer` replaces `app.worker_main` and asserts only call order and CLI arguments at `tests/worker/test_worker_health.py:286`; the dependency tests at `tests/worker/test_worker_health.py:71` exercise PostgreSQL, Redis, and S3 probes rather than `app.conf`; `test_worker_broker_permissions_cover_only_declared_task_and_control_entities` checks permission regexes at `tests/ops/test_guard.py:479`; and the real Worker tests only assert ping and `dependency_readiness` replies at `tests/ops/test_live_dependencies.py:31`. A whole-repository search for `x-queue-type`, `confirm_publish`, `task_default_queue`, `task_serializer`, `accept_content`, and `worker_send_task_events` found the runtime assignments and planning text but no test assertion or broker inspection of those settings.
- **Missing verification:** no executable check asserts that all six configured queues remain durable quorum queues, that `integration` remains the default, or that publisher confirms, JSON-only serialization, and task events remain enabled; the live broker checks also do not inspect the declared queues' durable/type arguments.
- **Demonstration:** changing the queue construction to `Queue(name)` and removing `confirm_publish` would make the running Worker declare classic/default queues and publish without the intended confirm setting, while every test above would still pass because they observe dependency probes, process arguments, permission regexes, and control replies only.
- **Consequence:** a Worker image can pass the current verification while using weaker queue durability or delivery settings, so accepted background work can lose the RabbitMQ persistence and confirm guarantees defined for this workspace.
- **Disposition:** `patch` — add a Worker configuration test that reads the effective Celery app configuration and asserts the exact six queue names, durable/quorum arguments, default queue, confirm setting, serializers, and event flag; extend the existing explicit RabbitMQ live probe to inspect the consumed queues' durable/type arguments.

## 原始报告 acceptance

# Story 1.1 Round 12 Acceptance Audit

**Verdict: approved**

**Current visual verdict: approved.** This verdict applies to the refreshed run-19 images only. The historical round-3 approval was not used as current approval.

## Scope and integrity

- Audited baseline `3440d2f89647aaeacf49213285c055dbe365df7d` against the supplied complete unified diff and the frozen Story 1.1 specification.
- The inventory contains 138 unique paths. The unified diff contains exactly the same 138 paths: no missing inventory entry, no unlisted diff path, and no `docs/prototype/index.html` diff.
- Independently recomputed SHA-256 for all 18 artifacts listed in `current-screenshot-metrics.json`; every hash matched lines 30-48.
- Recomputed `docs/prototype/index.html` SHA-256 as `C876D444167A999D820BFC27D99C59D091C7AC885E93BC89CDF3B65EA1B4198E`, matching `story-1-1-verification.md:15`; `git diff --exit-code -- docs/prototype/index.html` returned 0.
- Ran the documented read-only runtime/source binding check with the pinned Node path and the exact migration URL. It returned exit 0 and matched the archived API, Web, and Worker container IDs, image IDs, image refs, and source fingerprints in `story-1-1-runtime-images.json:3-23` and `current-screenshot-metrics.json:6-28`.

## Acceptance criteria

### AC1 — isolated runnable workspace, real W/A/K, readiness, PKCE, database-mapped account

**Pass.** `deployment/compose.yaml:1-121` defines the three application services and six real local dependencies with pinned images, owned volumes, health checks, and localhost-only published ports. `scripts/bootstrap.ps1:13-29` orders environment verification, infrastructure startup, guarded storage initialization, migration, application rebuild/start, public readiness, and final runtime-image recording. `edw-api/src/edw_api/main.py:154-416` probes PostgreSQL marker/schema/role, Redis, RabbitMQ, S3, Keycloak configuration/JWKS, and the live Worker dependency control response. `edw-web/src/auth/oidc.ts:25-68` performs Authorization Code + PKCE S256 and keeps tokens in module memory; `edw-api/src/edw_api/db.py:24-38` maps the verified token subject through active database identity/membership rows. The live verification ledger records successful bootstrap, 10 explicit live tests, and 19 browser tests at `story-1-1-verification.md:5-17`.

### AC2 — invalid identity/dependency failures reject or degrade safely; no fallback or token persistence/log leakage

**Pass.** `edw-api/src/edw_api/auth.py:18-44` constrains JWT validation to RS256 with issuer, audience, required expiry/issued-at/subject claims and access-token type; invalid material becomes structured 401. `edw-api/src/edw_api/main.py:419-428` derives the actor server-side, returns 403 when no active workspace mapping exists, and returns retryable 503 for database errors. `edw-web/src/app/api.ts:63-95` separates 401, 403, transient, invalid-response, timeout, and exact readiness states; `edw-web/src/app/App.tsx:23-76` clears rejected sessions, preserves transient in-memory sessions, fences stale responses after logout, and keeps durable readable failure states. Browser coverage at `tests/ux/shell.spec.ts:139-340` exercises real login/logout, 503 recovery, 401 clearing, 403 persistence, callback rejection, logout races, and dependency degradation. The current nine-service scan reports zero JWT/token/code/Bearer/local-credential matches and is bound to the same runtime at `story-1-1-runtime-log-scan.json:16-49,51-134`.

### AC3 — unsupported tools or unprovable isolation stop before migration/destructive effects

**Pass.** `scripts/verify_local_environment.py:110-226` enforces the exact local migration target, local Docker context/platform, pinned toolchain/locks, and immutable/versioned image manifest. Ownership and database checks at `scripts/verify_local_environment.py:372-442` refuse pre-existing unowned volumes/containers, require the owned PostgreSQL container/volume/localhost binding, and confirm database, migration role, and marker. External guards at `scripts/verify_local_environment.py:464-678` require the exclusive bucket, exact RabbitMQ vhost/users/grants, and persisted Keycloak realm/client/PKCE/audience settings. `scripts/initialize_local_storage.py:21-54` performs all existing-boundary checks before the only bucket/runtime-user creation and reruns the full guard afterward. The forward-only migration refuses cleanup at `migrations/versions/0001_identity_workspace.py:53-54`.

### AC4 — P-00/P-12 shell fidelity and 1180px behavior; current independent screenshot review

**Pass.** I inspected all 18 refreshed PNGs: six actual shell captures, six matching reference captures, authenticated/loading/readiness-failure states, hidden/shown implementation toast, and shown reference toast. Across 1920x1080, 1440x900, 1181x800, 1180x800, 1024x768, and 768x1024, the shell retains the 64px topbar, 266px sidebar, 12px shell gap/padding, six top and side navigation entries, notification/account placement, sidebar/project-card/menu/storage geometry, and source flex behavior. The expected fixed-desktop wrapping below the wide viewport is present in both actual and reference images. The warning appears at 1180px and below and is absent at 1181px. The authenticated, account-loading, dependency-failure, and toast states are readable and stable; the dark-blue toast matches the source position, shape, color, and shown/hidden behavior. Differences are confined to the authorized real identity/status copy and Story 1.1 body replacement; no visible shell regression was found.

The exact automated contract covers computed styles, geometry, text ranges, icons, and pseudo-elements at `tests/ux/shell.spec.ts:15-124,343-445`. The source CSS establishes the inherited geometry and responsive rule at `edw-web/src/app/prototype.css:13-35,60-63`; the only supplemental layout rule keeps the live project-card copy geometry stable at `edw-web/src/app/workspace.css:1-7`. Current metrics deliberately define no pixel threshold and mark independent review pending at `current-screenshot-metrics.json:1-5`; this audit supplies that current review. The historical diagnostic metrics remain correctly excluded by `visual-gate-2026-09-10.md:7-11`.

## Findings

No valid acceptance finding. No spec edit or waiver is required. The Story 1.1 local acceptance criteria are satisfied by the reviewed diff and current bound evidence; enterprise federation and production security/capacity/HA remain outside this Story as stated in `story-1-1-verification.md:25`.

## 逐项主控处置

| ID | 来源 | 判定 | 路由与依据 |
|---|---|---|---|
| 1 | blind | medium | patch：现有表存在与 SELECT 权限探针不证明账户查询引用的列/关联可用；复用权威账户 SQL 做不读取业务行的有界计划/零行检查，结构错误归入 schema/privilege mismatch，增加异常负例。 |
| 2 | edge | medium | patch：令牌交换响应仍使用无体积限制的 JSON 读取；复用或抽取已有有界读取函数，保留 8 秒期限与无令牌泄漏语义。 |
| 3 | edge | medium | patch：单一迁移链必须只有一个预期 revision 行，读取全部版本行并严格核对；API 和 Worker 一并处理同根因，不能接受额外 head 或空表。 |
| 4 | edge | high | patch：Worker 在同一 SQL 连接核验实际数据库名与角色，再检查 marker/revision，拒绝复制 marker 的错误数据库。 |
| 5 | edge | false | 驳回：一次性管理员分离脚本的精确旧状态前置条件在部分执行后不再满足，拒绝重复运行是既定安全失败行为；自动覆盖/续写未经核实中间态不属于承诺。此前逐项记录及窄恢复证据仍有效，没有清理或删除用户来模拟幂等。 |
| 6 | verification | medium | patch：直接验证有效 Celery 配置的六个 durable/quorum 队列、默认队列、confirm、JSON-only 与事件设置，并在显式 live 模块只读检查实际消费的四个普通队列。配置声明不冒充 broker 实测。 |

当前视觉审批来自第十二轮独立审查的实际 18 张图片与哈希/绑定核验，不依赖第三轮历史结论；后续代码变化仍按完整独立审查闭环推进。

Round-12 repair validation: shared current-account SQL is planned with EXPLAIN on the verified API connection without reading business rows; structural errors reject readiness. API and Worker require exactly one expected revision row, and Worker verifies the actual database and role on the same connection. Token exchange now uses the shared 64 KiB streamed/declared response bound with cancellation and the existing deadline. Effective Celery configuration is asserted, and the guarded read-only live test inspects four consumed durable quorum queues. Root validation: full bootstrap exit 0; Python 232 passed / 11 live-gated skipped; explicit live 11 passed in 130.94s; pinned Node Web 42 passed; browser 19 passed in 1.3m; scoped Ruff and Web static/build checks passed. Refreshed 18 screenshots at 2026-09-10T21:49:55.894527+00:00; final nine-service zero-match scan at 2026-09-10T21:50:11.539767+00:00. These repairs require fresh independent round 13 before done or commit.
