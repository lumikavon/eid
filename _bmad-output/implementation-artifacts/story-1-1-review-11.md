# Story 1.1 第十一轮审查处置

结论 changes-required。Blind approved；五项修复、两项驳回。

## 原始报告 blind

# Story 1.1 blind review 11

Verdict: **approved**

Baseline: `3440d2f89647aaeacf49213285c055dbe365df7d`

## Findings

No evidence-backed defects found.

The full supplied unified diff was reviewed as the change-set input. The executable and operational surface was checked against the frozen Story 1.1 boundaries: OIDC Code + PKCE and memory-only tokens, JWT/JWKS rejection behavior, server-derived account/workspace mapping, structured correlation errors, six-dependency readiness, Worker dependency/identity probes, migration and ownership isolation, pinned build/runtime inputs, RabbitMQ runtime privilege separation, runtime source/image/container binding, public cache policy, and log redaction evidence. The refreshed current screenshots were independently inspected across all six required viewports plus authenticated, account-loading, dependency-error, and toast states; the inherited shell geometry, narrow-width overflow/notice behavior, and authorized Story 1.1 state substitutions are coherent with the supplied reference artifacts.

## Validation

- `uv run --frozen pytest tests -q -p no:cacheprovider`: 216 passed, 10 skipped; the skipped cases are explicitly live-gated.
- `uv run --frozen ruff check edw-api edw-worker scripts tests migrations --no-cache`: passed.
- Portable Node 24.20.0: Web lint and typecheck passed; 30 Vitest tests passed.
- `uv run --frozen python scripts/generate_dependency_licenses.py --check`: passed.
- `git diff --check 3440d2f89647aaeacf49213285c055dbe365df7d --`: passed.
- All 18 files named by `current-screenshot-metrics.json` match their recorded SHA-256 values.

No live/container/browser mutation was performed. The archived bootstrap, 10-test live suite, 19-test browser suite, and nine-service runtime-log scan were assessed as supplied evidence rather than rerun or promoted beyond their stated local Story 1.1 scope. Enterprise federation and production security, capacity, HA, and AI-quality acceptance remain outside Story 1.1.

## 原始报告 edges

[{"location":"edw-web/src/auth/oidc.ts:37-39","trigger_condition":"Stored OIDC transaction is malformed JSON or lacks string fields","guard_snippet":"try { const tx = parseAndValidateTransaction(raw); } catch { throw new Error(\"登录事务无效\"); }","potential_consequence":"Callback exposes parser errors and cannot complete authentication"},{"location":"edw-web/src/app/api.ts:63-71","trigger_condition":"Account endpoint returns a rapidly streamed oversized JSON body","guard_snippet":"const body = await boundedJson(response, MAX_ACCOUNT_BODY_BYTES);","potential_consequence":"Browser memory grows without limit while loading account data"},{"location":"scripts/verify_local_environment.py:569-580","trigger_condition":"Second RabbitMQ user creation or permission grant fails after the first succeeds","guard_snippet":"persist each phase; verify exact completed state and resume remaining PUTs","potential_consequence":"Bootstrap leaves partial identities that every later run refuses to repair"},{"location":"scripts/migrate_rabbitmq_bootstrap_admin.py:102-121","trigger_condition":"Any RabbitMQ migration PUT after administrator creation fails","guard_snippet":"persist each phase; verify exact intermediate state before resuming migration","potential_consequence":"Migration becomes non-rerunnable while privileges remain partially changed"}]

## 原始报告 verification

### Keycloak self-registration can be enabled without any verification failing

- **Changed surface:** the local realm disables self-registration with `"registrationAllowed": false` at `deployment/keycloak/eid-local-realm.json:5`.
- **Impacted consumer or site:** the public Keycloak authorization flow launched by `beginLogin` at `edw-web/src/auth/oidc.ts:14` reaches the persisted `eid-local` realm and its login UI.
- **Existing test evidence:** the repository-wide `registrationAllowed|sslRequired|self.?registration|register` search found no executable test reference to the realm setting. The live browser path at `tests/ux/shell.spec.ts:99` proves an existing user can log in, and the negative request at `tests/ux/shell.spec.ts:358` proves PKCE is required, but neither checks whether registration is offered or accepted. The persisted-Keycloak guard tests at `tests/ops/test_guard.py:904`, `tests/ops/test_guard.py:956`, and `tests/ops/test_guard.py:1009` exercise client and audience-mapper fields only; `verify_keycloak` itself accepts the realm after checking only its name at `scripts/verify_local_environment.py:587`.
- **Missing verification:** an executable persisted-realm check must assert `registrationAllowed` is false, or a browser/HTTP negative test must prove a new user cannot self-register.
- **Demonstration:** changing the imported or persisted realm to `"registrationAllowed": true` leaves the existing-user login, PKCE rejection, client checks, mapper checks, and readiness behavior unchanged, so every test read above can still pass while Keycloak exposes self-registration.
- **Consequence:** bootstrap can approve a local identity realm that permits identities to be created outside the fixed project fixture and its reviewed initialization path.
- **Disposition:** `patch` — extend `verify_keycloak` and `tests/ops/test_guard.py` with a persisted realm-representation assertion that rejects `registrationAllowed != false`.

### The `.python-version` bootstrap rejection branch is not exercised

- **Changed surface:** `verify_versions` requires the checked-in version-manager pin to equal Python `3.12.14` at `scripts/verify_local_environment.py:188`.
- **Impacted consumer or site:** `scripts/bootstrap.ps1:15` invokes the environment verifier before starting infrastructure or migrations, so this branch is the bootstrap gate for a divergent `.python-version` file.
- **Existing test evidence:** the repository-wide `.python-version|requires-python =|lockfileVersion|packageManager|engines` search found executable coverage only in `tests/ops/test_guard.py` and the unrelated dependency-inventory fixture. `test_verify_versions_rejects_wrong_toolchain_predicates` at `tests/ops/test_guard.py:69` varies `node`, `pnpm`, the running Python tuple, `uv`, `packageManager`, and `.nvmrc`; its `.python-version` fixture stays `3.12.14` at `tests/ops/test_guard.py:81` in every case. The inbound graph trace for `verify_versions` found no other direct test of its rejection predicates.
- **Missing verification:** a negative `verify_versions` case that writes a non-`3.12.14` `.python-version` while keeping the observed interpreter and other manifest values valid, then asserts bootstrap verification stops.
- **Demonstration:** deleting or weakening the `.python-version` check at `scripts/verify_local_environment.py:188` would not make the parameterized test fail because no case changes that fixture. A host already running Python 3.12.14 would then pass the runtime-version check even when the repository tells version managers to select another interpreter.
- **Consequence:** the pre-start verifier can regress to approving contradictory host setup metadata, so another checkout or developer can select a different Python despite a successful bootstrap verification result.
- **Disposition:** `patch` — add a `python-version-file` case to `test_verify_versions_rejects_wrong_toolchain_predicates` in `tests/ops/test_guard.py`.

## 原始报告 acceptance

# Story 1.1 independent acceptance audit — round 11

Date: 2026-09-10
Baseline: `3440d2f89647aaeacf49213285c055dbe365df7d`
Verdict: **changes-required**

## Finding

1. **[P1] The current screenshots show an inherited-shell geometry regression in the project card and sidebar navigation, while the exact-layout test omits the affected geometry.** AC4 requires the P-00/P-12 shell's position, size, spacing and responsive behavior to remain faithful while real identity/state and the Story 1.1 body replace prototype data (`_bmad-output/implementation-artifacts/spec-1-1-runnable-workspace.md:24,40,72`; `_bmad-output/implementation-artifacts/epic-1-context.md:41-43`). In the directly inspected current `actual-shell-1920x1080.png`, the project card spans approximately y=126..189 (64 px) and the first side-menu item starts at y=200; in the paired current `reference-shell-1920x1080.png`, the card spans y=126..229 (104 px) and the first item starts at y=240. The same 40 px upward shift is visible at every unauthenticated viewport; `workspace-authenticated.png` still has a shorter card (approximately 83 px) and a roughly 19 px shift. This is shell layout, not the authorized workspace-body replacement. The dynamic strings in `edw-web/src/app/App.tsx:81` allow the inherited `.project-card` height to collapse under the unchanged source rule (`edw-web/src/app/prototype.css:31-33`; original at `docs/prototype/index.html:37-39`). The test declares `.project-card`, `.project-icon`, `.status`, and `.side-menu` as shell selectors but excludes them from `layoutSelectors`, so it compares their CSS values without their rectangles; it only separately checks the icon's 38x38 size (`tests/ux/shell.spec.ts:28-39,378-379`). Fix the project-card/side-menu geometry for unauthenticated and authenticated real states, add rectangle/offset coverage for the affected containers, refresh the current screenshots and metrics, and obtain independent review of those refreshed images.

## Acceptance coverage

- **AC1 — approved for this review:** Compose contains exactly W/A/K plus real PostgreSQL, Keycloak, RabbitMQ, Redis, SeaweedFS and NGINX with pinned infrastructure images (`deployment/compose.yaml:1-121`). Bootstrap runs isolation validation before migration and final public readiness before runtime-image recording (`scripts/bootstrap.ps1:13-29`). `/api/v1/me` verifies the token subject and maps the current account/workspace from PostgreSQL (`edw-api/src/edw_api/auth.py:18-44`; `edw-api/src/edw_api/db.py:24-38`). The archived verification records a successful complete bootstrap and real login path (`_bmad-output/implementation-artifacts/story-1-1-verification.md:7-13`).
- **AC2 — approved for this review:** issuer/audience/time/signature/type validation and PKCE/state/memory-only token handling are implemented (`edw-api/src/edw_api/auth.py:18-44`; `edw-web/src/auth/oidc.ts:14-70`). Database denial/unavailability fails closed (`edw-api/src/edw_api/main.py:419-428`). The source-bound nine-service log scan records zero configured token/credential matches (`_bmad-output/implementation-artifacts/story-1-1-verification.md:14,17`).
- **AC3 — approved for this review:** exact tool/lock/image validation and local-engine checks fail closed (`scripts/verify_local_environment.py:110-226`); owned volumes/containers, database identity/marker, bucket, broker identities/vhost, and Keycloak client are checked before migration (`scripts/verify_local_environment.py:372-442,464-558,583-653`; `migrations/env.py:28-42`). The migration is forward-only and supplies no cleanup path (`migrations/versions/0001_identity_workspace.py:53-54`).
- **AC4 — changes required by Finding 1:** the original prototype is unchanged and has SHA-256 `C876D444167A999D820BFC27D99C59D091C7AC885E93BC89CDF3B65EA1B4198E`; the 1180/1181 warning transition, top bar, 266 px sidebar, real-state body, failure explanation, and shown/hidden toast states are visually coherent. The current project-card/navigation geometry does not preserve the inherited source shell.

## Evidence integrity and review boundary

All 18 files named in `current-screenshot-metrics.json` were opened and reviewed. Their on-disk SHA-256 values have zero mismatches with the manifest. The manifest's API/Worker/Web image IDs, container IDs and source fingerprints exactly match both `story-1-1-runtime-images.json` and `.local/runtime-images.json`; independently recomputed source fingerprints are `sha256:0024e75abbf574202e6fe7292c33b9eaaa532a784aa805c0bd3ba17b50cee03b` for API/Worker and `sha256:10c75dfab70bcf13392b1138ef75906e96a49cad7b16280ea4a64649cf360e99` for Web. The supplied unified diff and `.local/story-1-1-files.json` each contain the same 137 paths, with no missing, extra, or absent-on-disk entries. `git diff --check` passes.

**Current visual verdict: changes-required.** Historical round-3 approval was not used. The refreshed images are current and reviewable, but they are not approved because of Finding 1.

This audit did not mutate source, Git, sprint/BMAD status, runtime, containers, or browser state. Enterprise IdP federation and production security/capacity/HA remain Epic 13 boundaries rather than Story 1.1 local failures.

## 逐项主控处置

| ID | 来源 | 判定 | 路由与依据 |
|---|---|---|---|
| 1 | edge | low | patch：损坏事务本来应拒绝认证；保留拒绝/清理/重新登录路径，将原生 JSON/类型异常替换为可读的无效事务错误，增加字段类型验证。 |
| 2 | edge | medium | patch：账户读取虽已有 8 秒期限，但读取体积未限制；以明确大小上限拒绝过量成功/错误响应，避免快速流在期限内耗费过多内存。 |
| 3 | edge | false | 驳回：当前初始化明确拒绝部分已有身份，禁止自动覆盖未知现状。脚本未承诺失败事务的自动恢复；在部分创建后停止且要求先核实实际目标符合隔离守卫设计。新增持久化恢复日志/自动续写属于额外恢复机制，非本 Story 启动必需条件。不得删除/回滚既有用户制造幂等。 |
| 4 | edge | false | 驳回：该工具是对已核实精确旧身份状态的一次性管理员分离操作，失败后新状态不再符合旧前置条件，因此再次运行必须拒绝。第九轮已记录主控针对经核实中间态的窄恢复；脚本不承诺自动续跑所有管理员变更，也不得假设中间态仍由本次操作独占。 |
| 5 | verification | medium | patch：核验持久 realm registrationAllowed 为 false，并验证 true/缺失拒绝，保留现有身份管理边界。 |
| 6 | verification | low | patch：补充 .python-version 文件单独漂移的现有版本门禁负例。 |
| 7 | acceptance | medium | patch：项目卡片高度因动态文案缩短而回缩，真实影响侧栏导航位置。修复未登录/已登录状态的继承几何，增加矩形/偏移断言，刷新截图并重新独立审批。 |

## 主控整合与实际失败记录

前端事务验证与响应大小限制通过 39 项 Web 单元；环境守卫与其负例修复后，Python 默认套件 222 passed / 10 live-gated skipped。

首次实际启动暴露注册配置检查误用了不包含 registrationAllowed 的公共 realm 响应。改为公共 realm 名核验后，从已认证管理端点读取持久 realm 配置并严格核验 false；测试区分两个真实响应结构。74 项守卫测试和实际只读 Keycloak 核验通过，随后完整 bootstrap 成功。没有改写 realm 配置。

第一次侧栏修复使卡片恢复 104px，登录状态切换几何检查通过，但完整浏览器只有 12 passed / 7 failed。新增精确矩形检查揭示原型图标被 flex 挤压到 34.531px，产品仍为 38px，status margin 也不同。继续保留失败断言，按六视口浏览器测得的原型文字列固有宽度约束产品列，保留 80px 高度预留与真实文案，并用实际引用测量替代早期误设的 38px 名义图标宽度断言。六视口内存探针及静态检查通过；仍需最终重建与完整浏览器通过后刷新视觉工件。

## 最终修复验证

最后一次完整重建与 bootstrap 成功；Python 222 passed、Web 39 passed、浏览器 19 passed (1.3m)、真实环境 10 passed (123.08s)，scoped Ruff 与 Web 静态检查通过。原型无修改。18 张当前截图及指标已刷新，最终九服务日志零配置匹配；进入第十二轮独立审查，不将开发侧通过视为独立视觉审批。
