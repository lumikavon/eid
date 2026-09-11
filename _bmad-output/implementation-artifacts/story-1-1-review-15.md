# Story 1.1 第十五轮审查处置

结论：changes-required；三项有效问题均由主线程修复，需第十六轮完整独立审查。

## 处置

- Blind 1：接受。README 的只读核验示例补齐专属迁移 URL，并调用自动选择已安装固定 Node 的 PowerShell wrapper。清除继承变量后实际执行新示例通过；不放宽目标 guard。
- Blind 2：接受。许可证来源改为 POSIX 仓库相对路径；仓库外来源明确标记 external-installation，不输出主机路径。重生成并 check 通过；两个不同临时 checkout 的原始工具/metadata 输入生成完全相同清单，另覆盖外部路径不泄露。
- Verification 1：接受。ID、Refresh、缺少 typ 三种令牌的现有参数化用例新增 status_code == 401；原有生产分支无需修改。
- Edges：无发现。
- Acceptance：原始已落盘报告为 approved，包含当前 18 张截图原始细节检查和哈希。代理在报告落盘后尚未发送终态，催收后被中断；不把中断本身当通过证据，保存实际报告并在下一轮再次核验当前证据。其“无验证缺口”结论不覆盖另一路提出的有效测试缺口。

## 根代理验证

定向 29 passed；完整 Python 269 passed、11 项显式 live 门禁 skipped；Ruff 通过。许可证生成与 --check 通过。文档化 runtime-image 命令 exit 0，三工程 source/image/container 与原清单完全一致；新的只读九服务日志扫描零配置匹配。没有修改应用构建输入、部署配置或依赖锁，不重建容器或重采截图；现有 browser 19、live 11 的实例绑定保持成立。

## 原始报告 blind

# Story 1.1 round-15 blind review

Status: **changes-required**

Scope: baseline `3440d2f89647aaeacf49213285c055dbe365df7d`; supplied 144-file unified diff; Story 1.1 local isolated delivery only. Historical review conclusions were not used as authority.

## Findings

### 1. Documented runtime-image verification fails in a clean shell

- Trigger: follow the documented read-only command `uv run --frozen python scripts/verify_local_environment.py --verify-runtime-images` without first exporting `EID_MIGRATION_DATABASE_URL`.
- Evidence: `README.md:24-28` presents that command as self-contained, while `scripts/verify_local_environment.py:957-959` always calls `verify_migration_target(os.environ.get("EID_MIGRATION_DATABASE_URL", ""))` for this action. In this review the exact command exited nonzero with `隔离检查失败: 迁移地址必须为本项目 localhost:55432/eid_local_dev 的迁移身份`.
- Impact: an operator cannot perform the advertised post-start read-only verification from a fresh PowerShell session, so the handoff/runbook fails at its primary integrity check even when the local stack is healthy.
- Required fix: either set the canonical migration URL in the documented command, as the later check-only example does, or give `--verify-runtime-images` a safe canonical local default while retaining the existing exact-target guard. Add a clean-environment command-level regression test.

### 2. Dependency-license inventory is checkout-path dependent

- Trigger: install the same frozen dependencies in any checkout path other than `D:\\Desktop\\eid`, then run the documented `uv run --frozen python scripts/generate_dependency_licenses.py --check`.
- Evidence: `scripts/generate_dependency_licenses.py:59` and `:79` serialize fully resolved installation directories. The committed inventory consequently contains host checkout paths, for example `deployment/dependency-licenses.json:79` begins with `D:\\Desktop\\eid\\node_modules...`. The check at `scripts/generate_dependency_licenses.py:106-109` requires byte-for-byte equality.
- Impact: the frozen dependency set produces a different tracked artifact solely because the repository was cloned elsewhere; the documented audit check therefore fails on otherwise equivalent workspaces and creates machine-specific churn.
- Required fix: serialize stable repository-relative paths for installations under the checkout (and a deterministic external-location representation if ever needed), regenerate the inventory, and test generation from two different temporary roots.

## Verification performed

- `uv run --frozen pytest tests/contract tests/security tests/ops tests/worker -q`: 267 passed, 11 skipped.
- `uv run --frozen ruff check edw-api edw-worker scripts tests migrations`: passed.
- Fixed Node 24.20.0/Corepack: Web 61 tests passed; lint, typecheck, and build passed.
- Public readiness: all six checks reported `ready`.
- Ownership/resource/runtime-image verification passed after supplying the required canonical migration URL; all nine local services were running and the app containers matched recorded source/image/container identities.
- Runtime log scan passed with zero configured credential/token matches.
- Representative current 1920px and 1180px shell/reference captures plus authenticated and readiness-error states were inspected; no additional visual defect was found within the approved exact-layout/CSS plus independent-image-review method.
- `git diff --exit-code -- docs/prototype/index.html`: passed.

The initial Corepack invocation used a repository-relative script path and failed before any project command ran; the prescribed portable Node script at `.local/tools/node-v24.20.0-win-x64/node_modules/corepack/dist/pnpm.js` was then used successfully. `docker compose ps` also requires Compose interpolation variables; supplying the already-recorded owner and source fingerprints made the read-only inspection succeed. Neither setup issue is an implementation finding beyond finding 1 above.


## 原始报告 edges

[]


## 原始报告 verification

### Non-access tokens can change from authentication failure to durable workspace denial without a failing test

- **Changed surface:** `OidcVerifier.verify` rejects a decoded token whose `typ` is not `Bearer` with an HTTP 401 `ApiError` — `edw-api/src/edw_api/auth.py:42`.
- **Impacted consumer or site:** `/api/v1/me` calls the verifier before loading the account at `edw-api/src/edw_api/main.py:530`, and the Web account client classifies HTTP 401 as authentication rejection but HTTP 403 as durable workspace denial at `edw-web/src/app/api.ts:68`; `App.load` clears the in-memory session only for the former and blocks scheduled account refresh for the latter at `edw-web/src/app/App.tsx:37`.
- **Existing test evidence:** `test_rejects_non_access_token_types` exercises ID, refresh, and missing-`typ` tokens but asserts only `caught.value.code == "INVALID_TOKEN"` at `tests/security/test_oidc.py:140`. The whole-repository `OidcVerifier`/`INVALID_TOKEN` reference search also found the live malformed-token request at `tests/ops/test_live_dependencies.py:25`; it asserts HTTP 401 for the separate JWT-decode exception branch and does not reach the decoded non-`Bearer` branch. Web tests independently pin the differing 401 and 403 classifications at `edw-web/src/app/api.test.ts:144` and `edw-web/src/app/api.test.ts:155`, but none execute the API's non-access-token branch through that boundary.
- **Missing verification:** No assertion pins `caught.value.status_code == 401` for ID, refresh, or missing-`typ` tokens.
- **Demonstration:** Changing the branch at `edw-api/src/edw_api/auth.py:42` to raise the same `INVALID_TOKEN` code with status 403 leaves every verifier assertion passing, and the live `Bearer invalid` request still exercises the earlier decode-exception branch at `edw-api/src/edw_api/auth.py:40`. The Web would then preserve the rejected token, present a workspace-access denial, and suppress its scheduled account retry instead of clearing the invalid session.
- **Consequence:** A cryptographically valid ID or refresh token submitted to `/api/v1/me` can ship with workspace-denial semantics and remain in the browser session rather than being treated as an authentication failure.
- **Disposition:** `patch` — extend `test_rejects_non_access_token_types` in `tests/security/test_oidc.py` to assert status 401 for every parameterized non-access-token case; the existing Web 401/403 tests already cover the downstream classification split.


## 原始报告 acceptance

# Story 1.1 round-15 independent acceptance review

**Verdict: APPROVED**
**Current visual verdict: APPROVED**
**Review date:** 2026-09-10 (America/New_York)

## Scope and review input

- Reviewed the complete Story specification and both declared context documents.
- Reviewed the supplied 144-file unified diff against baseline `3440d2f89647aaeacf49213285c055dbe365df7d` and the matching claims file.
- Diff identity: 7,081,324 bytes, 110,757 PowerShell-counted lines, SHA-256 `D8431ED23ACFFD3B2297A8A0077151E29B95989324F97CB4A7E2ECF6C4D4A57C`.
- The diff inventory is exactly 144 files and exactly matches the Story Implementation File List: no missing or extra paths.
- Applying the diff into an empty temporary repository reconstructed all 144 files. All binary bytes and normalized text content match the current workspace. The 88 raw-byte-only differences are CRLF/LF working-tree conversion, with zero semantic or binary mismatches.
- `docs/prototype/index.html` is outside the diff, has no Git difference from the baseline, and currently hashes to `C876D444167A999D820BFC27D99C59D091C7AC885E93BC89CDF3B65EA1B4198E`.

## Acceptance criteria

### AC1 — isolated runnable W/A/K workspace and real account: pass

The bootstrap orders ownership/tool/image checks before infrastructure initialization, performs the complete migration-target guard before Alembic, then builds W/A/K, validates NGINX and public readiness, and records runtime bindings only at the end (`scripts/bootstrap.ps1:19-38`). The guard fixes the migration endpoint and identity, rejects remote Docker, verifies database/volume ownership and marker, and verifies the exact S3 bucket, RabbitMQ vhost/users, Keycloak realm/client/mapper (`scripts/verify_local_environment.py:152-180`, `464-560`, `630-735`, `831-940`). The API maps the verified token subject through PostgreSQL and returns 403 when no active mapping exists (`edw-api/src/edw_api/db.py:10-38`, `edw-api/src/edw_api/main.py:530-539`).

Fresh read-only runtime verification passed. It proved owner nonce, `localhost:55432/eid_local_dev`, project `eid-local`, exact bucket/vhost/realm/client, Docker Server 29.1.3 on local linux/amd64, all nine current services running, and current public readiness with all six checks ready. The current API/Web/Worker container IDs, image IDs, and source fingerprints exactly match `story-1-1-runtime-images.json:3-21`.

### AC2 — negative authentication/dependency behavior and secret containment: pass

The verifier enforces RS256 signature, issuer, audience, expiry, required claims, Bearer token type and JWKS retrieval (`edw-api/src/edw_api/auth.py:18-44`). API readiness probes real PostgreSQL marker/schema/privileges, Redis, RabbitMQ, S3, persisted Keycloak configuration and the Worker, with a bounded shared deadline and structured 503 output (`edw-api/src/edw_api/main.py:165-216`, `219-470`, `477-527`). The SPA uses Code + PKCE S256, keeps tokens in module memory, removes callback query data before validation/exchange, bounds token/account/readiness bodies and timeouts, and performs POST logout (`edw-web/src/auth/oidc.ts:3-11`, `28-38`, `46-87`; `edw-web/src/http/bounded-json.ts:1-14`). Readiness consumer text is allowlisted; unknown server states are not reflected (`edw-web/src/app/api.ts:13-57`).

The archived scan is timestamped `2026-09-11T01:49:08.759547+00:00`, binds the same three app runtime records and all nine container IDs, and records zero matches for JWT, token values, authorization codes in URLs, Bearer values and configured local credentials (`story-1-1-runtime-log-scan.json:19-53`, `54-137`). Its SHA-256 is `BBD0D0E500BB1FBE297685087481C1AF580F3754D712595522EE8828898435E8`. A fresh read-only scan during this review again found nine services and zero total configured matches.

### AC3 — unsupported tools or unprovable isolation stop before migration/write: pass

Exact Node 24.20.0, pnpm 10.17.1, Python 3.12.14, uv 0.11.23, locks, immutable image digests, local Docker context/platform and required Docker capabilities are checked fail-closed (`scripts/verify_local_environment.py:166-278`). Ownership creation refuses pre-existing same-name containers/volumes; subsequent checks require the recorded repository/project nonce and exact volume attachments (`scripts/verify_local_environment.py:464-519`). Storage initialization first proves the database and all existing external boundaries; it only creates both missing runtime broker users, the incomplete dedicated Keycloak monitor, or an empty-project bucket, then re-runs the complete guard (`scripts/initialize_local_storage.py:22-52`). No cleanup, downgrade, production target or enterprise target path is present; the migration explicitly refuses downgrade cleanup (`migrations/versions/0001_identity_workspace.py:53-54`).

### AC4 — P-00/P-12 shell fidelity under the approved method: pass

The explicit approval permits exact CSS/layout verification plus independent screenshot review instead of PNG byte equality. No other waiver was applied. I independently opened all 18 currently manifested PNGs at original detail. All six actual/reference viewport pairs preserve the 64px top bar, 266px sidebar, 12px shell spacing, six navigation entries, account/notification placement, card/sidebar geometry, typography, colors, borders, radii and shadows. At 1180px and below the fixed desktop canvas and narrow-screen note appear; at 1181px the note is absent. The authenticated, loading, dependency-error and toast shown/hidden images remain readable and preserve the shell. Main-body differences are the authorized real authentication/readiness states rather than shell drift.

All 18 current PNG SHA-256 values match `current-screenshot-metrics.json:30-49`; capture time is `2026-09-11T01:49:00.047117+00:00` (`current-screenshot-metrics.json:2-5`). The large decoded RGB differences from the historical populated prototype body are observations, not a tolerance or waiver; visual acceptance is based on the approved exact shell/layout checks plus this current independent review. Historical approvals were not reused.

## Verification record and review findings

The current recorded gates are consistent with the inspected source and runtime: Python 267 passed / 11 gated skipped, separate real live 11 passed in 78.87s, Web 61 passed with lint/typecheck, browser 19 passed in 1.0m, bootstrap exit 0, and scoped Ruff passed (`story-1-1-verification.md:5-15`, `43`). I did not rebuild images or rerun browsers, as prohibited for this review. Fresh checks were limited to read-only guard/runtime-image verification, public readiness, current container inventory, log scan, file/diff/hash verification and image inspection.

No valid code, acceptance, edge-case or verification-gap findings remain. The round-14 Web repair covers all currently emitted Keycloak non-ready statuses and rejects unknown status reflection (`edw-web/src/app/api.test.ts:70-118`).

## Retained boundaries

This approval is local Story 1.1 acceptance only. It does not approve enterprise IdP federation or enterprise-system integration, production startup/security/capacity/high availability, AI/model quality, later Story 1.2+ authorization/domain/task/SSE behavior, the rest of Epic 1, or release readiness. Those boundaries remain explicitly owned by later stories and Epic 13 (`_bmad-output/implementation-artifacts/epic-1-context.md:7`, `20-29`, `46-53`; `_bmad-output/planning-artifacts/epic-1-secure-workspace.md:11-22`, `35-40`).

No source, specification, sprint status or Story status was changed by this review.
