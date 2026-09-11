---
title: 'Story 1.1：打开隔离的三工程工作区'
type: 'feature'
created: '2026-09-09'
status: 'done'
baseline_commit: '3440d2f89647aaeacf49213285c055dbe365df7d'
route: 'dispatch'
review_loop_iteration: 19
context:
  - '_bmad-output/implementation-artifacts/epic-1-context.md'
  - '_bmad-output/planning-artifacts/epic-1-secure-workspace.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem：** 当前仓库还没有可复现运行的 `edw-web`、`edw-api`、`edw-worker` 三工程工作区，项目成员无法通过真实本地身份进入应用，也无法区分进程存活与依赖已就绪。

**Approach：** 建立最小且版本锁定的三工程骨架与本地 Compose 环境，经 NGINX 提供 SPA/API 入口，使用真实 Keycloak Authorization Code + PKCE S256 登录，并以 PostgreSQL 中的最小身份/工作区记录返回当前账户；启动、迁移和就绪检查均先验证环境及数据隔离并安全失败。

## Boundaries & Constraints

**Always：** 仓库仅有三个业务工程；共享 Python 代码只能作为工程内库，不能形成第四个监听服务。Docker 29.1.3 已知可用；实施时必须核验并锁定 Python 3.12 的精确补丁版、受支持 Node LTS、pnpm 精确版本、Python/Node 锁文件及全部镜像摘要或不可变版本，禁止 `latest`。本地验收必须使用真实 Keycloak、PostgreSQL、RabbitMQ、Redis、S3 兼容存储与 NGINX，并启动真实 W/A/K。OIDC 使用 Code + PKCE S256，令牌仅驻留内存；API 校验签名、issuer、audience、exp/nbf 与 JWKS 轮换。`/health/live` 只表示进程存活，`/health/ready` 必须反映数据库、schema、必需配置及本 Story 依赖的实际状态。API 路径使用 `/api/v1`，服务端推导当前 actor/workspace；错误响应结构化并携带 `X-Request-ID`/`traceparent`。原型 P-00/P-12 壳层按匹配 viewport、字体与缩放保留 64px 顶栏、266px 侧栏、12px 间距、六个导航入口、通知/账户位置、toast 与 1180px 窄屏规则；原始 `docs/prototype/index.html` 不得修改。

迁移前必须验证目标是新建且专属于 `eid` 的本地开发/测试环境：主机、数据库名、Compose project、数据库 marker、bucket、RabbitMQ vhost、Keycloak realm/client 全部匹配；任何一项不可证明即停止。只允许创建初始身份、工作区及关联表和必要审计/迁移元数据。

**Never：** 不建立完整领域 schema，不实现 Story 1.2 之后的成员策略、记录发现、任务或 SSE；不使用 mock 代替上述本地基础设施，不回退到样例用户、共享凭据、硬编码人员或特权工作区；不把 token/秘密写入 URL、浏览器持久存储或普通日志；不清理、覆盖或迁移既有数据，不连接生产或企业数据库。企业 IdP 联邦及生产启动、安全、容量和高可用证据留待 Epic 13。

## I/O & Edge-Case Matrix

| 场景 | 输入 / 状态 | 预期输出 / 行为 | 错误处理 |
|---|---|---|---|
| 隔离环境启动 | 全部隔离标记有效，锁与镜像受支持 | Compose 启动真实 W/A/K 与基础设施；NGINX 服务 SPA/API；live 与 ready 含义准确 | 任一依赖未就绪时 ready 降级并给出可操作原因 |
| PKCE 登录 | 真实 Keycloak 授权码与有效 S256 verifier | SPA 内存持有令牌；`GET /api/v1/me` 返回数据库映射的当前账户/工作区 | state、verifier 或交换失败时拒绝并保留可读认证状态 |
| 非法 JWT | 错误 issuer/audience、过期/尚未生效或轮换后无效签名 | API 拒绝访问，不返回账户或工作区数据 | 结构化 401/403；无样例或特权回退，无敏感日志 |
| 数据库不可用 | API 已启动但 PG 断开或 schema 不匹配 | live 可保持成功，ready 失败；受保护请求不伪造成功 | 返回结构化依赖错误，恢复后重新探测真实状态 |
| 启动版本不支持 | Node/Python/pnpm/依赖或镜像不符合 manifest | 在安装、启动或迁移前停止 | 输出实际值、要求值和修复方法，不产生迁移副作用 |
| 隔离不可证明 | 数据库/Compose/realm/client/vhost/bucket 任一归属不匹配 | guard 失败，迁移和写入均不执行 | 明确列出失败检查；禁止清理或自动修复既有目标 |
| 壳层保真 | 固定 viewport/字体/缩放及认证、加载、失败状态 | P-00/P-12 布局与响应规则匹配，真实账户和状态替换演示数据 | 差异形成可复现视觉失败，不修改原型源文件 |

</frozen-after-approval>

## Code Map

- `package.json`, `pnpm-workspace.yaml`, `pnpm-lock.yaml`, `.python-version`, `pyproject.toml`, `uv.lock` -- 根级工具链与三工程工作区锁定；实施时记录精确 Node/pnpm/Python 3.12 版本。
- `edw-web/` -- React/TypeScript/Vite SPA；在 `src/auth/` 实现内存 OIDC/PKCE，在 `src/app/` 复刻 P-00/P-12 壳与持久认证/依赖状态。
- `edw-api/src/edw_api/` -- FastAPI 组合根、配置、OIDC/JWKS 校验、请求上下文、`/api/v1/me`、live/ready；不得接受客户端传入 actor/workspace 作为权威值。
- `edw-worker/src/edw_worker/` -- Celery 最小真实进程与 DB/broker/S3 配置探测；本 Story 不增加业务 handler。
- `migrations/` -- 单一 Alembic metadata/迁移链，仅创建 identity、workspace、membership 最小映射及环境 marker；迁移身份与运行身份分离。
- `deployment/compose.yaml`, `deployment/nginx/`, `deployment/keycloak/`, `deployment/postgres/` -- 固定真实基础设施、NGINX 路由、专属 realm/client/vhost/bucket/数据库与健康检查；无 mock profile。
- `scripts/verify-local-environment.*`, `scripts/bootstrap.*` -- 在迁移前核验版本、锁、镜像和全部隔离标记；失败时不得继续。
- `contracts/` -- `/api/v1/me`、健康/就绪与结构化错误契约，供 Web/API 跨工程校验。
- `tests/contract/`, `tests/security/`, `tests/ops/`, `tests/ux/` -- 真实基础设施契约、JWT/PKCE 负例、DB/隔离 guard 故障及原型壳保真证据。
- `docs/prototype/index.html` -- 只读视觉基线，禁止修改。

## Tasks & Acceptance

**Execution：**
- [x] 根级锁文件及 `edw-web/`、`edw-api/`、`edw-worker/` -- 创建最小三工程并锁定实施机验证通过的精确工具链和依赖版本，生成可审计 lock/image manifest。
- [x] `deployment/` 与 `scripts/verify-local-environment.*` -- 编排真实 Keycloak/PG/RabbitMQ/Redis/S3/NGINX，建立专属命名和 marker guard，并保证 guard 是迁移的硬前置。
- [x] `migrations/` -- 创建最小身份/工作区 schema 和种子映射；只在全量隔离检查成功后迁移新库。
- [x] `edw-api/src/edw_api/` 与 `contracts/` -- 实现真实 OIDC/JWKS 验证、服务端账户映射、`/api/v1/me`、结构化错误和准确 live/ready。
- [x] `edw-web/` -- 接入 Code + PKCE S256、内存 token 与真实账户路由，复刻 P-00/P-12 壳并呈现持久认证、加载、失败和降级状态。
- [x] `edw-worker/` -- 启动真实最小 Worker 并验证独立配置/身份可连接所需本地依赖，不提前加入领域任务。
- [x] `tests/contract/`, `tests/security/`, `tests/ops/`, `tests/ux/` -- 覆盖矩阵全部正反场景，保存日志、截图、锁与镜像清单；检查日志、URL 和浏览器存储无 token/秘密。

**Acceptance Criteria：**
- Given 已验证的新隔离本地数据库与固定 locks/images，when Compose 启动 W/A/K 和真实本地基础设施，then NGINX 服务 SPA，readiness 报告真实依赖健康，Code + PKCE 登录到数据库映射的当前账户而非硬编码人员；证据在迁移前标识 host/database/project 独占性。
- Given issuer、audience、expiry/nbf、签名/JWKS 或 PKCE 无效，或数据库不可用，when 尝试登录/API 访问，then 访问被拒绝或 readiness 准确降级，不出现样例工作区或特权回退，URL、浏览器持久存储及日志中没有 token。
- Given Node/依赖版本不支持或数据库隔离无法证明，when bootstrap validation 运行，then 以可操作原因停止，不执行既有数据清理、迁移或任何生产目标操作。
- Given 固定视觉条件和真实身份/状态，when 比对实现壳与 P-00/P-12，then 布局、位置、尺寸、间距、字体、颜色、圆角、阴影、边框、图标、控件状态及 1180px 响应规则通过保真检查，且原型源文件保持不变。

## Implementation Notes

2026-09-11：Story1.1本地隔离范围完成。第十九轮完整独立审查收敛，当前18PNG获独立批准，所有有效问题已修复。Python295、Web61、真实live11 (109.83s)、浏览器19 (1.7m)、Ruff/静态与完整bootstrap通过；审查后根代理关键156项及九服务实际运行绑定复核通过。原型未变，未推进后续Story或扩展真实企业/生产/AI验收。

## Spec Change Log

2026-09-10 用户明确批准视觉验证方法：精确布局/CSS 核验＋独立截图差异审查替代 PNG 完全一致断言。保留原型与差异证据，修复实际视觉偏离；不引入统一像素容差，不豁免安全/功能测试或独立代码审查。

## Review Triage Log

Round 1: changes-required. Five layers completed; 12 grouped patches, 0 human decisions, 0 deferrals, 1 rejected finding. Full per-finding verdicts and evidence: [story-1-1-review-1.md](story-1-1-review-1.md). User's autonomous repair instruction applies; no routine confirmation is needed.

### Review Findings

Round 19: [story-1-1-review-19.md](story-1-1-review-19.md). All valid findings resolved; current independent acceptance and visual verdict approved.

Rejected: automated live-body CSS coverage is an enhancement to the explicitly approved exact-layout plus independent-image review method. The claimed ability to ship solely on 19 green browser tests is contradicted by the required and completed independent screenshot/acceptance gate.

Round 18: [story-1-1-review-18.md](story-1-1-review-18.md).

- [x] Recheck public readiness after image collection, preserving the prior manifest on failure.
- [x] Verify each running container against the captured owner nonce and reject ownership-record drift.

Rejected: partial RabbitMQ setup auto-recovery is not promised by the explicit fail-closed initialization contract; no existing identity is overwritten.

Round 17: [story-1-1-review-17.md](story-1-1-review-17.md).

- [x] Forward-only Worker metadata privilege hardening with real denied-read tests.
- [x] Bind and recheck all nine running images and container IDs.
- [x] Bound database guard and migration statement/lock waits.
- [x] Recheck storage ownership and instance identity before initialization writes.

Round 16: [story-1-1-review-16.md](story-1-1-review-16.md).

- [x] Bind pnpm versions to verified installed package metadata, independent of path ordering.
- [x] Validate active Compose images and Dockerfile FROM instructions, excluding comments.
- [x] Recheck earlier runtime containers after collecting all three services.

Round 15: [story-1-1-review-15.md](story-1-1-review-15.md).

- [x] Document a self-contained guarded runtime-image verification command.
- [x] Generate checkout-relative dependency locations and prove relocated inventories match.
- [x] Pin HTTP 401 for all rejected non-access token types.

Round 14: [story-1-1-review-14.md](story-1-1-review-14.md).

- [x] [Review][Patch] Map every emitted Keycloak readiness failure to a safe actionable Web message and test complete six-dependency 503 payloads, including unknown-state non-reflection.

Rejected: the inactive-account/membership SQL path was exercised by the explicit 11-test PostgreSQL/live run; an opt-in infrastructure gate is not missing execution evidence. Automatic retry of partially provisioned RabbitMQ identities or the exact-old-state administrative migration is not promised; both intentionally fail closed without overwriting existing state.

Round 5: [story-1-1-review-5.md](story-1-1-review-5.md). All valid findings implemented; checked tasks do not imply independent approval.

- [x] Enforce access-token type, required claims and actual JWKS rotation.
- [x] End Keycloak SSO with POST logout and distinguish workspace denial.
- [x] Validate mutually exclusive CLI actions and final public readiness.
- [x] Explicitly forbid implicit flow and verify fixed logout return URI.
- [x] Exercise tool/engine/database identity rejection and Worker delivery settings.
- [x] Exercise real account SQL rejection, API DB/RabbitMQ failures, callback error and periodic recovery.
- [x] Scan actual owned runtime logs for configured token/secret patterns.


Round 4: [story-1-1-review-4.md](story-1-1-review-4.md).

- [x] Add invalid request-ID and all-zero trace/span regression tests.
- [x] Validate discovery and runtime OIDC configuration consistency.
- [x] Preserve session across transient account failures and test recovery/rejection.
- [x] Support Space notification activation and test it.
- [x] Reconcile visual approval ledger.


Round 3: [story-1-1-review-3.md](story-1-1-review-3.md).

- [x] Bound OIDC exchange through body consumption and reject malformed tokens.
- [x] Require exactly six Web readiness checks.
- [x] Probe dependencies inside the running Worker and verify actual role-loss/recovery.
- [x] Repair stale bootstrap test assertion and rerun complete Python suite.


Round 2 findings: [story-1-1-review-2.md](story-1-1-review-2.md), 11 grouped patches. Earlier checked items remain implementation history; Story is reopened until these defects and verification gaps are repaired and independently reviewed.

- [x] [Review2][Patch] Require final public readiness before runtime manifest success.
- [x] [Review2][Patch] Verify persisted Keycloak audience mapper.
- [x] [Review2][Patch] Require usable supported signing JWK material.
- [x] [Review2][Patch] Correlate safe structured unexpected-500 responses.
- [x] [Review2][Patch] Bound Web requests and pending polls.
- [x] [Review2][Patch] Prove all existing resource boundaries before creating S3 bucket.
- [x] [Review2][Patch] Reconcile final visual evidence narrative.
- [x] [Review2][Patch] Capture and independently verify deterministic toast shown/hidden states.
- [x] [Review2][Patch] Exercise Worker entrypoint and Redis/S3 rejection gates.
- [x] [Review2][Patch] Exercise Redis/S3 API readiness failures.
- [x] [Review2][Patch] Exercise /me database exception envelope.

- [x] [Review][Patch] Include globally ignored bootstrap Python sources in delivery and review.
- [x] [Review][Patch] Preserve validated request correlation through NGINX.
- [x] [Review][Patch] Fail readiness safely for malformed JWKS response shapes.
- [x] [Review][Patch] Fence stale account responses after logout, with a race regression test.
- [x] [Review][Patch] Require Worker database schema/marker compatibility.
- [x] [Review][Patch] Gate bootstrap and readiness on an observable healthy Worker; test failure.
- [x] [Review][Patch] Complete structured errors and trace generation/propagation.
- [x] [Review][Patch] Record and verify source-bound built/running image content IDs.
- [x] [Review][Patch] Enforce checked-in JSON response schemas in executable tests.
- [x] [Review][Patch] Execute bootstrap guard-failure orchestration with recording command shims.
- [x] [Review][Patch] Restore inherited P-12 toast and test hidden/shown feedback states.
- [x] [Review][Patch] Include pseudo-element inset and content in exact visual checks.

Rejected: E3 missing parse_ocr/render consumers is not reachable in Story 1.1, which intentionally has no business producer/handler; heavy-workload execution and isolation are later-scope requirements, not a reason to consume heavy queues in the normal seed Worker.

2026-09-10：进入第 1 轮独立审查。主线程完整执行 `scripts/bootstrap.ps1` 成功（包括实际资源隔离、已存在项目 schema 核验和三个显式版本镜像重建）；26 项 Python 测试通过，3 项真实环境测试另行显式运行通过；Ruff 通过；4 项 OIDC 单元测试通过；重建后的 10 项浏览器测试通过（19.3 秒）。截图差异仍待独立审查，不宣称 PNG 一致。

## Verification

Final round 19: independent full review and current screenshot approval are complete; post-review critical tests and current runtime bindings were rechecked. Evidence and scope are in `story-1-1-verification.md`, `story-1-1-runtime-images.json`, and the refreshed visual-evidence directory.

**Commands：**
- `docker version --format '{{.Server.Version}}'` -- expected: 服务端为已知可用的 29.1.3；随后由 bootstrap 记录并校验精确 Node LTS、pnpm、Python 3.12、uv 与锁文件版本。
- `uv run --frozen python scripts/verify_local_environment.py --check-only` -- expected: 输出 host/database/Compose project/marker/bucket/vhost/realm/client 的专属证据；任一负例非零退出且零迁移/零写入。
- `docker compose -f deployment/compose.yaml config --quiet && docker compose -f deployment/compose.yaml up -d --wait` -- expected: 固定镜像配置有效，真实基础设施与 W/A/K 健康；无 `latest`、无 mock 服务。
- `uv run --frozen alembic -c alembic.ini upgrade head` -- expected: 仅在 guard 成功后迁移新专用库，schema 到 head；对 guard 失败目标命令不可达。
- `pnpm --filter edw-web lint && pnpm --filter edw-web typecheck && pnpm --filter edw-web test` -- expected: Web 静态检查、PKCE 状态与壳层测试通过。
- `uv run pytest tests/contract tests/security tests/ops` -- expected: `/api/v1/me`、health/readiness、issuer/audience/exp/nbf/JWKS、DB 不可用及隔离负例全部通过。
- `pnpm exec playwright test tests/ux` -- expected: 真实浏览器完成 Keycloak PKCE 登录/拒绝路径，P-00/P-12 匹配截图与 1180/1181px 行为通过，token 不出现在 URL 或持久存储。
- `git diff --exit-code -- docs/prototype/index.html` -- expected: 原型基线文件未修改。


## Final post-format gate

Approved independent delta and fresh18-image review; see [story-1-1-final-validation.md](story-1-1-final-validation.md). Current bootstrap, browser19, live11, log scan and root critical156 checks pass. First failed browser run retained truthfully in verification history. Only Story1.1 local scope is done.

## Implementation File List

- `.dockerignore`
- `.gitignore`
- `.nvmrc`
- `.python-version`
- `README.md`
- `_bmad-output/implementation-artifacts/epic-1-context.md`
- `_bmad-output/implementation-artifacts/spec-1-1-runnable-workspace.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/implementation-artifacts/story-1-1-execution-checkpoint.md`
- `_bmad-output/implementation-artifacts/story-1-1-final-validation.md`
- `_bmad-output/implementation-artifacts/story-1-1-review-1.md`
- `_bmad-output/implementation-artifacts/story-1-1-review-10.md`
- `_bmad-output/implementation-artifacts/story-1-1-review-11.md`
- `_bmad-output/implementation-artifacts/story-1-1-review-12.md`
- `_bmad-output/implementation-artifacts/story-1-1-review-13.md`
- `_bmad-output/implementation-artifacts/story-1-1-review-14.md`
- `_bmad-output/implementation-artifacts/story-1-1-review-15.md`
- `_bmad-output/implementation-artifacts/story-1-1-review-16.md`
- `_bmad-output/implementation-artifacts/story-1-1-review-17.md`
- `_bmad-output/implementation-artifacts/story-1-1-review-18.md`
- `_bmad-output/implementation-artifacts/story-1-1-review-19.md`
- `_bmad-output/implementation-artifacts/story-1-1-review-2.md`
- `_bmad-output/implementation-artifacts/story-1-1-review-3.md`
- `_bmad-output/implementation-artifacts/story-1-1-review-4.md`
- `_bmad-output/implementation-artifacts/story-1-1-review-5.md`
- `_bmad-output/implementation-artifacts/story-1-1-review-6.md`
- `_bmad-output/implementation-artifacts/story-1-1-review-7.md`
- `_bmad-output/implementation-artifacts/story-1-1-review-8.md`
- `_bmad-output/implementation-artifacts/story-1-1-review-9.md`
- `_bmad-output/implementation-artifacts/story-1-1-runtime-images.json`
- `_bmad-output/implementation-artifacts/story-1-1-runtime-log-scan.json`
- `_bmad-output/implementation-artifacts/story-1-1-verification.md`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/actual-header-1024.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/actual-header-1180.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/actual-header-1181.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/actual-header-1440.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/actual-header-1920.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/actual-header-768.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/actual-shell-1024x768.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/actual-shell-1180x800.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/actual-shell-1181x800.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/actual-shell-1440x900.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/actual-shell-1920x1080.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/actual-shell-768x1024.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/current-screenshot-metrics.json`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/difference-shell-1024x768.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/difference-shell-1180x800.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/difference-shell-1181x800.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/difference-shell-1440x900.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/difference-shell-1920x1080.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/difference-shell-768x1024.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/reference-header-1024.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/reference-header-1180.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/reference-header-1181.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/reference-header-1440.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/reference-header-1920.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/reference-header-768.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/reference-shell-1024x768.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/reference-shell-1180x800.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/reference-shell-1181x800.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/reference-shell-1440x900.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/reference-shell-1920x1080.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/reference-shell-768x1024.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/reference-toast-shown.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/screenshot-diff-metrics.json`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/visual-gate-2026-09-10.md`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/workspace-account-loading.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/workspace-authenticated.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/workspace-readiness-error.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/workspace-toast-hidden.png`
- `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/workspace-toast-shown.png`
- `alembic.ini`
- `contracts/error.schema.json`
- `contracts/health.schema.json`
- `contracts/me.schema.json`
- `deployment/compose.yaml`
- `deployment/dependency-licenses.json`
- `deployment/images.lock.json`
- `deployment/keycloak/eid-local-realm.json`
- `deployment/nginx/default.conf`
- `deployment/nginx/web.conf`
- `deployment/postgres/001-isolated-database.sql`
- `deployment/python.Dockerfile`
- `deployment/seaweedfs/s3.json`
- `deployment/web.Dockerfile`
- `edw-api/pyproject.toml`
- `edw-api/src/edw_api/__init__.py`
- `edw-api/src/edw_api/auth.py`
- `edw-api/src/edw_api/config.py`
- `edw-api/src/edw_api/db.py`
- `edw-api/src/edw_api/errors.py`
- `edw-api/src/edw_api/keycloak_contract.py`
- `edw-api/src/edw_api/main.py`
- `edw-web/eslint.config.js`
- `edw-web/index.html`
- `edw-web/package.json`
- `edw-web/src/app/App.tsx`
- `edw-web/src/app/api.test.ts`
- `edw-web/src/app/api.ts`
- `edw-web/src/app/prototype.css`
- `edw-web/src/app/workspace.css`
- `edw-web/src/auth/oidc.test.ts`
- `edw-web/src/auth/oidc.ts`
- `edw-web/src/http/bounded-json.ts`
- `edw-web/src/main.tsx`
- `edw-web/tsconfig.app.json`
- `edw-web/tsconfig.json`
- `edw-web/tsconfig.node.json`
- `edw-web/vite.config.ts`
- `edw-worker/pyproject.toml`
- `edw-worker/src/edw_worker/__init__.py`
- `edw-worker/src/edw_worker/__main__.py`
- `edw-worker/src/edw_worker/app.py`
- `edw-worker/src/edw_worker/health.py`
- `edw-worker/src/edw_worker/log_safety.py`
- `migrations/env.py`
- `migrations/script.py.mako`
- `migrations/versions/0001_identity_workspace.py`
- `migrations/versions/0002_worker_metadata_only.py`
- `package.json`
- `playwright.config.ts`
- `pnpm-lock.yaml`
- `pnpm-workspace.yaml`
- `pyproject.toml`
- `scripts/__init__.py`
- `scripts/bootstrap.ps1`
- `scripts/generate_dependency_licenses.py`
- `scripts/initialize_local_storage.py`
- `scripts/migrate_rabbitmq_bootstrap_admin.py`
- `scripts/verify-local-environment.ps1`
- `scripts/verify_local_environment.py`
- `scripts/verify_rabbitmq_api_access.py`
- `scripts/verify_readiness.py`
- `scripts/verify_runtime_logs.py`
- `tests/contract/test_health.py`
- `tests/contract/test_keycloak_contract.py`
- `tests/ops/test_bootstrap.py`
- `tests/ops/test_dependency_licenses.py`
- `tests/ops/test_guard.py`
- `tests/ops/test_live_current_account.py`
- `tests/ops/test_live_dependencies.py`
- `tests/ops/test_live_migration.py`
- `tests/ops/test_migration_connection.py`
- `tests/ops/test_rabbitmq_admin_migration.py`
- `tests/ops/test_readiness.py`
- `tests/ops/test_runtime_logs.py`
- `tests/security/test_oidc.py`
- `tests/ux/shell.spec.ts`
- `tests/worker/test_worker_health.py`
- `tests/worker/test_worker_log_safety.py`
- `uv.lock`
