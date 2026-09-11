# Story 1.1 第六轮独立审查与处置

本轮原始审查结论如下，保留原文后逐项处置。Story 保持 in-progress，修复后的运行验证及新一轮审查尚待完成。

## 原始报告：blind

# Story 1.1 Round 6R Independent Blind Review

**Status: COMPLETE — changes required**

Reviewed the supplied unified diff against baseline `3440d2f89647aaeacf49213285c055dbe365df7d`, the Story 1.1 specification, and its declared Epic context. Encoded binary patches, generated lock metadata, and prior review reports were excluded. No browser run, live fault injection, rebuild, database mutation, commit, or source edit was performed.

## Findings

1. **HIGH — Public readiness remains green when the Web application is unavailable**
   **Evidence:** `edw-api/src/edw_api/main.py:258-267`, `edw-api/src/edw_api/main.py:270-281`, `deployment/nginx/default.conf:13-17`, `contracts/health.schema.json:9-18`
   **Trigger:** Start the complete workspace, then stop or otherwise make `edw-web` unavailable while API, NGINX, Worker, and infrastructure remain healthy. NGINX can still proxy `/health/ready` to API, and API checks only PostgreSQL, Redis, RabbitMQ, S3, Keycloak, and Worker.
   **Impact:** `/health/ready` returns HTTP 200 with every declared check `ready` while `/` cannot serve the SPA (normally 502). Operators and automated gates therefore receive a false workspace-ready result even though one of the three required business projects is unavailable.
   **Fix:** Make the public readiness route a composite workspace check that includes the Web upstream, then add `web` to the checked contract and failure tests. This can be implemented at the NGINX/public-gateway layer or through a bounded Web probe, as long as a failed SPA upstream makes public readiness non-200.

2. **MEDIUM — Runtime readiness does not detect a broken or weakened Keycloak client configuration**
   **Evidence:** `edw-api/src/edw_api/main.py:156-227`, `scripts/verify_local_environment.py:395-453`
   **Trigger:** After bootstrap, use the available local Keycloak administration path to disable `eid-web`, remove its required S256 PKCE setting, change its redirect URI, or enable implicit flow. Discovery and the RS256 JWKS remain valid.
   **Impact:** `_keycloak_status()` still reports `ready`, so `/health/ready` remains green although login is broken or the approved OIDC boundary has been weakened. The bootstrap guard checks the client once, but the runtime endpoint claims current dependency/configuration readiness.
   **Fix:** Add a bounded runtime-safe witness for the required client configuration and include it in `_keycloak_status()`. Avoid placing an administrative credential in API; use a minimal public protocol probe or a bootstrap-produced attestation that is invalidated/rechecked when Keycloak configuration changes. Add drift tests for disabled client, missing S256, redirect mismatch, and implicit flow enabled.

3. **MEDIUM — The runtime log scanner can report success without scanning all owned services or all checked local secrets**
   **Evidence:** `scripts/verify_runtime_logs.py:12-25`, `deployment/compose.yaml:3-40`, `deployment/compose.yaml:88-93`
   **Trigger:** A local credential is emitted by PostgreSQL, RabbitMQ, Redis, or SeaweedFS, or `eid-local-admin` is emitted by one of the five currently scanned services. The scanner scans only `api`, `worker`, `nginx`, `web`, and `keycloak`, and its fixture-secret expression omits the shared Keycloak/PostgreSQL administrator password.
   **Impact:** `passed` can be `true` while an owned runtime log contains a project secret, producing invalid evidence for the Story requirement that tokens and secrets do not appear in ordinary logs.
   **Fix:** Discover and scan every owned Compose service (including PostgreSQL, RabbitMQ, Redis, and SeaweedFS), and derive the secret patterns from a complete explicit local credential inventory that includes `eid-local-admin`. Keep output count-only/redacted and add negative tests proving each service and credential class makes the scan fail.

## Verification boundary

This was a read-only source review. The findings are based on reachable control flow and configuration; prohibited live and browser checks were not run.


## 原始报告：edges

changes-required

1. `edw-api/src/edw_api/main.py:121-129`
   - Trigger: Redis resolves, but TCP connection attempts are black-holed rather than refused.
   - Evidence: `_redis_status()` sets only `socket_timeout=2`; Redis connection establishment uses `socket_connect_timeout`, which is left unbounded.
   - Consequence: `/health/ready` can hang instead of returning the structured retryable 503, and repeated polls can occupy API worker threads.
   - Minimal fix: create the client with `socket_connect_timeout=2` as well as `socket_timeout=2`, and close the client after the probe.

2. `edw-api/src/edw_api/main.py:258-266`, `edw-web/src/app/api.ts:9-16`, `scripts/verify_readiness.py:14-16`
   - Trigger: Several dependencies consume their allowed timeout during the same readiness request.
   - Evidence: readiness runs six probes serially; their configured waits can exceed both the Web's 8-second deadline and the bootstrap verifier's 10-second deadline.
   - Consequence: callers time out before receiving the API's per-dependency failure details, even though every individual probe remains within its own limit.
   - Minimal fix: run independent probes concurrently under one server-side deadline shorter than 8 seconds, preserving a result for every timed-out probe.

3. `edw-api/src/edw_api/auth.py:40-46`
   - Trigger: A client sends a valid `Authorization: bearer <token>` header.
   - Evidence: HTTP authentication schemes are case-insensitive, but `startswith("Bearer ")` accepts only one casing.
   - Consequence: a standards-compliant authenticated request is rejected with `AUTHENTICATION_REQUIRED`.
   - Minimal fix: split the scheme from credentials, compare the scheme case-insensitively, then retain the existing non-empty-token guard.


## 原始报告：verification

# Round 6 independent verification-gap review

Verdict: **changes required**

### Runtime secret-log verification is an unbound dated snapshot

- **Changed surface:** the Story adds safe NGINX log formats that omit query strings (`deployment/nginx/default.conf:1-9`, `deployment/nginx/web.conf:1-5`) and a runtime scanner for JWTs, OAuth authorization codes, bearer values, token fields, and fixture secrets (`scripts/verify_runtime_logs.py:10-56`).
- **Impacted consumer or site:** the Story's no-token/no-secret acceptance evidence is the checked-in scan result at `_bmad-output/implementation-artifacts/story-1-1-runtime-log-scan.json:1-56`, claimed as the current runtime gate by `_bmad-output/implementation-artifacts/story-1-1-verification.md:14-17`; the actual bootstrap completion path ends after public readiness and runtime-image recording without invoking the scanner (`scripts/bootstrap.ps1:23-27`).
- **Existing test evidence:** `Broken-verification gap` — whole-repository searches for `scan_runtime_logs`, `verify_runtime_logs`, `eid_safe`, `access_log`, and `authorization_code_url` found no test that executes the scanner, injects a matching log value, or checks the safe NGINX format. The only scanner references are its definition, the implementation file list, and the dated JSON result. The default Python suite passed with `144 passed, 9 skipped`; Web units passed `26 passed`. The current Playwright attempt could not execute behavior because all 18 cases failed at the initial request with `ERR_CONNECTION_REFUSED`/`ECONNREFUSED` to `localhost:18080`. The checked-in runtime-image fingerprints do match the current API/Worker/Web source, so the prior `18 passed` record is bounded evidence for this source snapshot, but it does not make the log scan self-refreshing or regression-sensitive.
- **Missing verification:** there is no executable test that supplies representative sensitive values in each owned service's captured logs and asserts that `scan_runtime_logs()` returns `passed: false`, and no normal post-login/runtime verification step that refreshes the scan result and binds it to the reviewed runtime/source manifest.
- **Demonstration:** changing either NGINX format from `$uri` to `$request`, or adding an Authorization/token value to an application log, would leave all current Python, Web-unit, and Playwright assertions green because none reads the owned service logs. The already checked-in JSON would still say `passed: true`, so the claimed gate would not fail even though an OAuth code or token was now present in logs.
- **Consequence:** a build can satisfy the recorded Story verification while leaking an authorization code, bearer token, local credential, or fixture secret into an owned runtime log.
- **Disposition:** `patch` — add `tests/ops/test_runtime_logs.py` using recording command shims or monkeypatched Docker output to prove every configured sensitive pattern fails the scanner and foreign ownership is rejected, then invoke the scanner after the real login/live/browser sequence and record a result bound to the same runtime-image/source identifiers used by the review snapshot.

## Verification run

- `uv run --frozen pytest tests -q`: `144 passed, 9 skipped`.
- Portable Node 24.20.0 Web units: `26 passed`.
- Portable Node 24.20.0 Playwright suite: `18 failed`; every failure was connection refusal at `http://localhost:18080`, so no browser assertion ran against the application. No runtime start, rebuild, live-test opt-in, database mutation, source edit, commit, or service stop was performed.


## 原始报告：acceptance

# Story 1.1 round 6 acceptance audit

Verdict: **APPROVED**

Scope: full acceptance audit of `spec-1-1-runnable-workspace.md` against baseline `3440d2f89647aaeacf49213285c055dbe365df7d`, using `C:/Users/VIRTUA~1/AppData/Local/Temp/eid-story1-1-review6-4f515169c94142b6b1b552ccbfc1b694.diff` and `.local/story-1-1-files.json`.

The supplied unified diff is non-empty and resolves to 121 unique files, 10,746 added lines and no deleted lines. Its file set exactly matches the 121-entry inventory, and every inventoried file exists. Binary/base64 bodies were not treated as review text; the corresponding actual files and their recorded hashes were checked where they carry evidence.

## Findings

No acceptance findings remain. No source fix, spec decision or deferral is required.

## Acceptance evidence

| Criterion | Result | Evidence | Fix |
|---|---|---|---|
| AC1: pinned three-project workspace, real local infrastructure, public SPA/API, accurate readiness, real PKCE identity mapping, isolation proof before migration | Pass | The normative criterion is `_bmad-output/implementation-artifacts/spec-1-1-runnable-workspace.md:69`. Exact tool and image pins are enforced by `scripts/verify_local_environment.py:81-128`; Compose runs PostgreSQL, Keycloak, RabbitMQ, Redis, SeaweedFS, API, Worker, Web and NGINX in `deployment/compose.yaml:1-104`. Bootstrap runs the complete live-resource guard before Alembic and application launch at `scripts/bootstrap.ps1:13-27`. The guard proves the database target/identity/marker, owned port and volume, unique bucket, RabbitMQ vhost/permissions, and persisted Keycloak realm/client/PKCE/audience configuration at `scripts/verify_local_environment.py:303-465`. API readiness probes PostgreSQL marker/schema plus Redis, RabbitMQ, S3, Keycloak and the running Worker's own dependencies at `edw-api/src/edw_api/main.py:104-281`; `/api/v1/me` derives the subject from the verified token and queries active database identity/membership at `edw-api/src/edw_api/main.py:284-293` and `edw-api/src/edw_api/db.py:16-30`. The current verification ledger records bootstrap exit 0 and the live dependency/current-account evidence at `_bmad-output/implementation-artifacts/story-1-1-verification.md:5-19`. | None |
| AC2: reject invalid OIDC/JWT/PKCE or database failure; no fallback or token leakage | Pass | The criterion is `spec-1-1-runnable-workspace.md:70`. JWT verification restricts RS256 and validates signature, issuer, audience, `exp`, required identity claims, and Bearer token type at `edw-api/src/edw_api/auth.py:16-37`. PyJWT validates `nbf` when present; this Story correctly does not require the optional claim, proved explicitly at `tests/security/test_oidc.py:41-75`. The actual HTTP JWKS cache/rotation path accepts the new `kid` and rejects a wrong signature at `tests/security/test_oidc.py:133-176`. The SPA uses Authorization Code with S256, keeps access/id tokens in module memory, removes the callback query, and sends logout hints only in a POST body at `edw-web/src/auth/oidc.ts:1-70`. Missing/inactive mappings fail closed; database exceptions return structured retryable 503 rather than an account fallback at `edw-api/src/edw_api/main.py:284-293`. The 18-test browser record covers actual login/SSO logout, callback/PKCE denial, 401/403/transient states, delayed-response fencing and persistent-storage emptiness at `_bmad-output/implementation-artifacts/story-1-1-verification.md:8-14`; the owned five-service post-flow log scan reports zero matches for JWT, token, Bearer, authorization-code query and fixture-secret patterns at `_bmad-output/implementation-artifacts/story-1-1-runtime-log-scan.json:1-56`. That log result is accepted only for the captured services, bytes and configured patterns, as bounded by `story-1-1-verification.md:17`. | None |
| AC3: unsupported tools or unprovable isolation stop safely before migration/production action | Pass | The criterion is `spec-1-1-runnable-workspace.md:71`. Migration URLs are restricted to the local migrator on `localhost:55432/eid_local_dev`; the Docker context must be the local Linux engine at `scripts/verify_local_environment.py:57-78`. Exact Node, pnpm, Python, uv, lock and image predicates are checked before ownership/resource work at `scripts/verify_local_environment.py:81-128,468-479`. Existing same-name volumes/containers are never adopted, and all existing owned resources must retain the nonce at `scripts/verify_local_environment.py:271-300`. Alembic's online entrypoint independently invokes the complete migration-target guard at `migrations/env.py:17-30`; the migration creates only the minimal identity/workspace/membership mapping and makes downgrade destructive cleanup impossible at `migrations/versions/0001_identity_workspace.py:15-54`. The orchestration regression verifies a failed full guard makes Alembic, app build and runtime-manifest recording unreachable at `tests/ops/test_bootstrap.py:9-64`. | None |
| AC4: approved prototype fidelity method, six viewport shell/1180 rule, toast and immutable source | Pass | The criterion and approved method are `spec-1-1-runnable-workspace.md:72,78-80`. The automated contract compares exact computed shell styles, geometry, text ranges, icons and pseudo-elements at six required viewports, with no tolerance or ignored region, and verifies 1180/1181 behavior in `tests/ux/shell.spec.ts:5-83,287-384`. The archived round-3 gate records the current shell artifacts and the independent screenshot approval, including repaired shown/hidden 1800 ms toast evidence, at `_bmad-output/implementation-artifacts/story-1-1-visual-evidence/visual-gate-2026-09-10.md:3-31`; the independent review result is also recorded at `_bmad-output/implementation-artifacts/story-1-1-review-3.md:12`. All six current actual/reference screenshot files match the SHA-256 values in `current-screenshot-metrics.json`; this is evidence identity, not a pixel-equality claim. The prototype's current SHA-256 is `C876D444167A999D820BFC27D99C59D091C7AC885E93BC89CDF3B65EA1B4198E`, and it has no diff from the baseline. Later round-4/5 changes affect authorized authentication/degraded states; the current 18-browser record rechecks the unchanged shell and those states at `story-1-1-verification.md:12,21`. | None |

## Evidence integrity and boundary checks

- The preserved runtime-image evidence is byte-identical to `.local/runtime-images.json`. Recomputing the documented source-fingerprint algorithm from the current files matched all three archived fingerprints (`api`, `worker`, `web`). The manifest records the current container/image/source identities at `_bmad-output/implementation-artifacts/story-1-1-runtime-images.json:1-24`.
- The current six actual/reference shell screenshots all match their archived SHA-256 entries. The recorded decoded pixel differences remain observations for the already completed independent visual review, not an invented tolerance.
- The original prototype remains unchanged and outside the Story inventory/diff.
- The local completion boundary is stated consistently: Epic 1 local completion proves only the isolated local chain at `_bmad-output/implementation-artifacts/epic-1-context.md:5-7`; Story 1.1 retains enterprise federation and production security under Epic 13 at `_bmad-output/planning-artifacts/epic-1-secure-workspace.md:11-18,35-40`; current verification explicitly disclaims enterprise IdP, production/security-capacity/HA, AI quality and full Epic completion at `_bmad-output/implementation-artifacts/story-1-1-verification.md:25`. Sprint state remains Story `review`, later Stories `backlog`, and Epic 13 `backlog` at `_bmad-output/implementation-artifacts/sprint-status.yaml:78-87,194-203`.

## Audit method boundary

This round performed source, diff/inventory, artifact/hash and acceptance-boundary inspection only. It did not run browser or test suites, rebuild images, mutate runtime services or databases, commit changes, or edit source/spec/status files. The runtime/test conclusions above are bounded to the preserved evidence cited; this audit independently checked their consistency with the current implementation and evidence identities.


## 主控处置

- Blind 1：不采纳增加第七项 Web 检查。现有契约明确为 API 的六项依赖就绪，Web 有独立容器健康检查；bootstrap 同时要求九服务健康、公共就绪和运行镜像清单通过。API 依赖就绪不等同于整个工作区持续可用性。扩展公共契约和增加 API→Web 循环依赖不属于本 Story 的必要修复。
- Blind 2：不采纳持续管理员配置漂移监控。启动核验实际 client 的 PKCE、redirect、implicit flow 与 audience；运行检查 discovery、issuer、audience/JWKS。本地管理员在验收后改动安全配置属于新的配置变更，需重新执行启动核验；不向 API 引入管理权限或未经定义的配置证明机制。
- Blind 3 与 Verification：采纳。日志扫描覆盖九个归属匹配的服务，明确列出本地凭据类别，校验运行容器与当前镜像/源指纹；增加六项负向及归属测试，并加入浏览器流程末尾自动门禁。两种本地管理员密码已区分并更新到已核实专用环境，避免用户名与密码同值造成误判。
- Edges 1：原始“连接无界”结论不成立。已核实安装的 redis AbstractConnection 在 socket_connect_timeout 为 None 时继承 socket_timeout。仍补充显式连接期限与客户端关闭，以清楚表达资源约束。
- Edges 2：采纳。六探针并发执行，共享六秒请求期限，执行器和排队容量有界；超时逐项保留并返回结构化 503。新增并发停滞与排队取消测试。
- Edges 3：采纳。HTTP Bearer scheme 大小写不敏感，仍拒绝空凭据及其他 scheme。

## 当前主控验证

- Python：162 passed, 9 skipped；跳过项是显式 opt-in 的真实环境测试，随后单独执行。
- Web 单元测试：26 passed。
- 项目代码 Ruff：通过。全仓扫描另在预存 .agents/.claude/_bmad 中报告 5 项 lint，未修改这些外部工作流文件。
- 专用存储与容器归属、数据库名称/身份/marker、Keycloak 实际配置重新通过。
- bootstrap 退出 0，九服务健康，六项公共依赖就绪，重新记录当前镜像与源指纹。
- 上轮独立浏览器运行因本地服务全部停止而连接拒绝，该失败保留；旧运行证据不当作此次修复后的通过证据。
