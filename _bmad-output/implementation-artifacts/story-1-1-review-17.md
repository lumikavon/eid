# Story 1.1 第十七轮审查处置

结论：changes-required；五项有效问题均已修复并验证，进入第十八轮完整独立审查。

## 处置

- Blind 1：接受。保留已经执行的 0001 历史迁移，追加前向 0002_worker_metadata_only 撤回 Worker 对三张身份/工作区表的 SELECT；初建迁移链最终状态同样收紧。API 与 Worker 要求新版 revision。实际权限负例证明 Worker 可读取迁移 metadata，但三个业务表 SELECT 与成员 UPDATE 都拒绝；业务行不变。
- Blind 2：接受。schema 2 运行镜像清单绑定全部九个服务：三个应用保留源码标签，六个基础设施按镜像锁摘要解析精确 image ID 并绑定容器。采集后重新核验九个实例；日志扫描前后复核全量绑定。六个参数化负例分别替换基础设施 image ID，全部拒绝。
- Edges 1/2：接受。数据库 guard 与 Alembic 实际连接均配置 connect_timeout=3、statement_timeout=5000、lock_timeout=2000；连接参数回归与实际完整迁移链通过。超时保留失败，不自动放宽。
- Edges 3：接受。初始化捕获 nonce 和三个存储服务实例，在每个 broker、Keycloak、bucket 初始化步骤前重新核验；service_container 同时验证实际 nonce 与端口。三个中途替换场景都在后续写入前拒绝，另验证端口匹配但 nonce 外来仍失败。这是写入步骤前的归属/实例复核，不宣称跨 Docker/HTTP 的原子事务，也不自动修复此前完成的部分初始化。
- Verification：无发现。Acceptance：原受审版本的四 AC 与18张图片 approved；本次迁移和重建后需新一轮当前截图批准。

## 根代理验证

迁移前实际 check-only 再次证明 localhost:55432/eid_local_dev、eid-local nonce/marker 和全部现有资源归属。完整 bootstrap exit 0，应用前向迁移并重建，未清理数据库、业务行或卷。Python 291 passed / 11 live-gated skipped；显式实际 live 11 passed (109.83s)；Web 61 passed、lint/typecheck、Ruff 通过；浏览器19 passed (1.7m)。新的18张截图在 2026-09-11T04:08:46.871701+00:00 刷新并绑定九服务schema2，最后日志扫描 2026-09-11T04:11:29.235014+00:00 九服务零配置匹配。

最初旧测试 fixture 只模拟三个应用，扩展九服务后有12项失败；补齐明确隔离的测试边界并新增基础设施错误镜像与存储中途替换回归后通过。实际 NGINX/SeaweedFS 未配置 Docker Health 字段，不能以缺字段声称其不就绪；基础设施必须运行，若有 Health 则必须 healthy，且真实依赖/公开 readiness 另行通过。三个应用仍强制 Docker healthy。对应四个用例固定这一差异，没有豁免实际依赖健康门禁。

## 原始报告 blind

# Story 1.1 independent blind review — round 17

Verdict: **changes-required**

Baseline: `3440d2f89647aaeacf49213285c055dbe365df7d`

Scope reviewed: the complete supplied 146-file unified diff, including all text additions, lock/manifests, and binary visual-evidence entries. `git apply --check --reverse` succeeded against the current working tree, confirming the supplied patch content matches the reviewed files. Production paths, migration/guard behavior, contracts, tests, and current read-only runtime state were inspected. Later business handlers, enterprise federation, production security/capacity/HA, AI behavior, and fault-injection acceptance were excluded as directed.

## Findings

### 1. Medium — the Story 1.1 Worker database role can read all identity and workspace data without an in-scope need

- Evidence: `migrations/versions/0001_identity_workspace.py:38` grants `SELECT` on `identity_account`, `workspace`, and `workspace_membership` to `eid_worker`. The only Worker database use in this Story is the readiness probe at `edw-worker/src/edw_worker/app.py:35-58`, which reads the session identity, database marker, and `alembic_version`; Story 1.1 intentionally has no business handler. The same migration already grants the Worker the `alembic_version` access it needs at `migrations/versions/0001_identity_workspace.py:16`.
- Impact: compromise or accidental code execution in the long-running Worker can enumerate the local identity/workspace mapping despite the separate API/Worker database identities and the stated Worker authorization boundary. The existing live check proves write denial, but it does not make this unnecessary read grant safe.
- Required fix: remove the identity/workspace `SELECT` grant from `eid_worker` and apply a forward, guarded privilege correction to already-initialized Story 1.1 databases without resetting data. Keep only the metadata access needed by the current readiness probe, and add a negative test proving the Worker role cannot read the three identity/workspace tables while its readiness query still succeeds.

### 2. Medium — runtime-image verification omits every pinned infrastructure container

- Evidence: `scripts/verify_local_environment.py:401-426` iterates `build_images()`, whose contract contains only `api`, `worker`, and `web`; `scripts/verify_local_environment.py:469-475` likewise requires and rechecks only those three services. `scripts/verify_runtime_logs.py:79-88` verifies all nine owned container IDs but compares image-manifest IDs only for the same three application services. Tests at `tests/ops/test_guard.py:1577-1606` and `tests/ops/test_guard.py:1664-1716` cover image drift only for those built services.
- Impact: `--record-runtime-images`, the documented `--verify-runtime-images`, and the final log evidence can pass after PostgreSQL, Keycloak, RabbitMQ, Redis, SeaweedFS, or NGINX has been replaced by a different image, provided labels/ports and readiness still look acceptable. That leaves the Story's pinned-image runtime claim unverifiable even though the Compose file and lock manifest are correct. The current containers were separately inspected during this review and do match their pinned digest references; the defect is in the reusable guard and evidence contract.
- Required fix: resolve each of the six external service image IDs from the digest-pinned references in `deployment/images.lock.json`, bind their exact running container IDs/image IDs into the runtime manifest, and recheck all nine services at both record and verify/log-scan completion. Add a regression case in which one infrastructure container retains valid ownership/service labels and health but has a different image ID.

## Verification performed

- `uv run --frozen pytest tests -q` — **277 passed, 11 skipped**; all skips are the explicitly gated live suite.
- `uv run --frozen ruff check edw-api edw-worker scripts tests migrations` — **passed**.
- Portable Node 24.20.0 + bundled Corepack pnpm: `pnpm --filter edw-web test` — **61 passed**.
- Portable Node 24.20.0 + bundled Corepack pnpm: Web lint and typecheck — **passed**.
- Documented guarded read-only runtime verification, `./scripts/verify-local-environment.ps1 --verify-runtime-images` with the project migration URL — **passed**; exact ownership, live resources, toolchain, and the three currently recorded application images matched.
- Read-only public probes — `/health/live` and `/health/ready` returned HTTP 200; readiness reported all six checks `ready`; correlation and `Cache-Control: no-store` headers were present where expected.
- Read-only Docker inspection — all nine current containers are running; application images match the recorded IDs and the six infrastructure containers currently use the digest references declared in Compose.
- `git apply --check --reverse <supplied-diff>` — **passed**.

No rebuild, browser run, fault test, live write/rollback test, or infrastructure mutation was performed.


## 原始报告 edges

[
  {
    "location": "scripts/verify_local_environment.py:565-570",
    "trigger_condition": "PostgreSQL accepts connection but stalls the identity query",
    "guard_snippet": "psycopg.connect(..., connect_timeout=3, options=\"-c statement_timeout=2000\")",
    "potential_consequence": "Bootstrap can hang indefinitely before isolation validation completes"
  },
  {
    "location": "migrations/env.py:32-39",
    "trigger_condition": "Migration connection succeeds but its identity query stalls",
    "guard_snippet": "connect_args={\"connect_timeout\": 3, \"options\": \"-c statement_timeout=2000\"}",
    "potential_consequence": "Alembic can hang indefinitely before validating the migration target"
  },
  {
    "location": "scripts/initialize_local_storage.py:23-48",
    "trigger_condition": "Owned service containers are replaced after the initial ownership snapshot",
    "guard_snippet": "ownership(); service_container(...); ownership(); client.create_bucket(Bucket=EXPECTED[\"bucket\"])",
    "potential_consequence": "Bootstrap can mutate a replacement service lacking the recorded owner nonce"
  }
]


## 原始报告 verification

No verification gaps found.


## 原始报告 acceptance

# Story 1.1 round-17 independent acceptance audit

**Terminal verdict:** APPROVED
**Current visual verdict:** APPROVED
**Scope:** local Story 1.1 only; baseline `3440d2f89647aaeacf49213285c055dbe365df7d`

## Findings

No acceptance-blocking findings.

## Acceptance criteria

| Criterion | Verdict | Evidence |
|---|---|---|
| AC1 — isolated runnable W/A/K workspace, real local dependencies, PKCE, and database-mapped current account | Pass | The criterion is frozen at `_bmad-output/implementation-artifacts/spec-1-1-runnable-workspace.md:68-70`. Fresh execution of the README's self-contained read-only guard command (`README.md:24-29`) proved ownership and the exact `localhost:55432/eid_local_dev`, `eid-local` bucket/vhost/realm/client boundaries, Docker `29.1.3` on `linux/amd64`, and the current API/Web/Worker source-image-container bindings. Fresh public readiness returned all six required checks ready. The retained explicit live result is 11 passed and the retained browser result is 19 passed (`story-1-1-verification.md:8-14,43`); both remain bound to the unchanged runtime IDs below. |
| AC2 — invalid authentication/dependency behavior rejects safely and tokens/secrets stay out of URL, persistent storage, and logs | Pass | API verification validates signature, issuer, audience, time claims and access-token type before subject lookup (`edw-api/src/edw_api/auth.py:18-44`); `/api/v1/me` maps the verified subject through the database and denies missing membership (`edw-api/src/edw_api/main.py:530-539`). The browser contract covers real PKCE exchange, empty persistent storage, POST logout without query data, 401/403, callback, readiness, race and retry behavior (`tests/ux/shell.spec.ts:126-407`). A fresh nine-service log scan passed with zero configured JWT, token-value, authorization-code URL, Bearer-value, or local-credential matches and revalidated the same runtime bindings. |
| AC3 — unsupported tools or unprovable isolation stop before migration/write/production action | Pass | Exact Node/pnpm/Python/uv and image locks are checked before bootstrap work (`scripts/verify_local_environment.py:218-287`). Migration target verification requires the dedicated localhost database identity and then all external ownership boundaries (`scripts/verify_local_environment.py:537-575,946-955`); Alembic runs that complete guard before opening its migration connection and rechecks database/user/marker on that connection (`migrations/env.py:11-42`). No cleanup, production target, build, browser run, fault injection, or live mutation was performed by this audit. |
| AC4 — P-00/P-12 fidelity under the user-approved exact CSS/layout plus independent visual method | Pass | I opened and inspected all 18 current manifested PNGs at original detail. The six actual/reference pairs preserve the inherited 64 px top bar, 266 px sidebar, 12 px shell gap/padding, navigation/account/notification placement, typography, colors, borders, radii, shadows, icons, controls, and fixed desktop canvas. The narrow-screen note is present at 1180 px and below and absent at 1181 px. Loading, authenticated, dependency-error, and toast shown/hidden states are readable and preserve the shell; body differences are the authorized real identity/readiness replacement. The Playwright contract compares exact computed styles, geometry, text ranges, pseudo-elements and responsive state (`tests/ux/shell.spec.ts:15-124,409-471`). No PNG-equality assertion, pixel threshold, ignored region, or other waiver was used. |

## Diff and evidence integrity

- Supplied patch: 7,124,712 bytes, 111,546 lines, SHA-256 `AABB34FDD4FECBA5926C13CC5B4F4FE9DE4A4EDED4B1D023AED433902D366413`.
- The patch has exactly 146 unique paths: 110 text and 36 binary. They exactly match the 146-entry Implementation File List (`spec-1-1-runnable-workspace.md:180-327`), with no missing or extra path. `git apply --check --reverse` succeeds against the current workspace, binding every text and binary target to the supplied diff.
- `docs/prototype/index.html` exists at the baseline and is absent from the patch. Its current SHA-256 is unchanged: `C876D444167A999D820BFC27D99C59D091C7AC885E93BC89CDF3B65EA1B4198E` (`story-1-1-verification.md:15`).
- All 18 current PNG SHA-256 values match `current-screenshot-metrics.json:30-48`; capture time remains `2026-09-11T01:49:00.047117+00:00`. The metrics bind them to API container `906e6a4ad0b6`, Web `2a1f9cec57a0`, Worker `d4241a24e75b`, their exact image IDs, and source fingerprints (`current-screenshot-metrics.json:3-28`).
- The archived post-repair scan at `2026-09-11T02:41:29.382332+00:00` contains the same source/image/container bindings and zero configured matches across all nine services (`story-1-1-runtime-log-scan.json:2-53,55-138`). Fresh guard, readiness, and log-scan execution independently returned the same bindings and clean result.
- Dependency inventory regeneration/check passed. An independent walk found 296 Node records and 67 Python records, with every listed installed source resolving to the recorded package name/version; zero name/version/path mismatches and zero unknown installed versions. Eight image entries remain explicitly bounded as unaudited image components, as documented (`README.md:73-80`).

## Executed verification

- `uv run --frozen pytest tests -q` — 277 passed, 11 explicitly live-gated skips.
- `uv run --frozen ruff check edw-api edw-worker scripts tests migrations` — passed.
- Portable Node `24.20.0` plus Corepack pnpm: Web units — 61 passed; lint and typecheck — passed.
- `uv run --frozen python scripts/generate_dependency_licenses.py --check` — passed; independent installed-metadata comparison — 296 Node and 67 Python records, zero mismatches.
- README guarded `./scripts/verify-local-environment.ps1 --verify-runtime-images` — passed against the owned current runtime.
- `uv run --frozen python -m scripts.verify_readiness` — passed, six of six ready through public NGINX.
- `uv run --frozen python -m scripts.verify_runtime_logs` — passed, nine services, zero configured matches, unchanged source/image/container bindings.
- All 18 current PNGs — independently inspected at original detail and approved.

The explicit 11-test live suite and 19-test browser suite were not rerun because this audit was limited to safe unit/static/guard actions and prohibited browser/fault mutations. Their retained results remain valid for the current bytes and instances because the fresh guard and log scan reproduce the exact source fingerprints, image IDs and container IDs recorded by the runtime, screenshot and verification artifacts.

## Retained boundaries

This approval covers the isolated local Story 1.1 acceptance criteria only. It does not approve enterprise IdP federation, enterprise-system integration, production startup/security/capacity/high availability, AI/model quality, Story 1.2+ authorization/domain/task/SSE behavior, the rest of Epic 1, release readiness, or legal sufficiency of license metadata (`epic-1-context.md:5-29`; `story-1-1-verification.md:25`).
