# Story 1.1 第十八轮审查处置

结论：两项有效时序问题修复完成，进入第十九轮完整独立审查。

## 处置

- Edges 1：接受。镜像采集完成后、清单写入前再次执行公开 readiness；若依赖在采集中失效，保留此前文件而不生成新通过清单。回归明确覆盖先 ready、完成采集后拒绝的时序。
- Edges 2：接受。每次实际容器 inspect 都检查其 nonce 与采集开始读取的本仓库归属记录一致；结束复查归属记录，拒绝中途更换 nonce。正确镜像且 healthy 的 API/S3 外来 nonce 都拒绝，归属文件中途变化另有负例。仍不宣称跨 Docker/HTTP 原子快照或未来状态不变。
- Blind：拒绝为强制缺陷，记录为未承诺的自动恢复增强建议。其部分 RabbitMQ 创建状态与既定 README“只有两个身份同时缺失才创建、部分既有状态拒绝覆盖”的明确契约相同。失败即停止是本 Story 的现有行为；验收标准并未承诺中断后的自动重试收敛。本次不扩大为部分资源修复协议，不删除/覆盖既有用户。此判断基于实际约束，并非按严重度跳过有效问题。
- Verification：无发现。Acceptance：四项 AC 与当前18PNG独立 approved。

## 根代理验证

Python295 passed/11 live-gated skipped，Ruff通过。使用此前已验证构建的源指纹执行实际 guarded --record-runtime-images 成功；九服务 schema2 与此前归档逐字段相同，未重建应用、改变数据库或替换截图。日志扫描 2026-09-11T04:32:23.996972+00:00 零配置匹配，九服务绑定相同。此前真实live11 (109.83s)、浏览器19 (1.7m)、Web61与静态证据仍适用于未变的应用源/实例。

## 原始报告 blind

# Story 1.1 blind code review — round 18

**Verdict:** changes-required

**Baseline / review input:** `3440d2f89647aaeacf49213285c055dbe365df7d` and `C:/Users/VIRTUA~1/AppData/Local/Temp/eid-story1-1-review18-af32360b867b4c2ba4c4a7e4ec8ab5cf.diff` (148 files). Review was independent of prior review verdicts and limited to Story 1.1's local isolated runnable workspace.

## Finding

### [High] Bootstrap can permanently strand its own fresh RabbitMQ environment in an unrecoverable partial state

- **Location:** `scripts/verify_local_environment.py:775-794`, especially the sequential user/permission writes at lines 783-794; retry rejection at `scripts/verify_local_environment.py:756-771`; caller at `scripts/initialize_local_storage.py:56-58`.
- **Evidence:** `create_rabbitmq_runtime_users()` first creates `eid_api` and grants its permission, then creates and grants `eid_worker`. Any ordinary interruption or HTTP failure after the first successful PUT leaves one runtime identity ready and the other missing. On the next bootstrap, `verify_rabbitmq(allow_missing_runtime=True)` computes `states == {"ready", "missing"}` and rejects it because `len(states) != 1`. The initializer consequently never calls the creation routine again. The repository also forbids cleanup/overwrite, and there is no guarded repair command for this bootstrap-created partial state.
- **Impact:** A first run against an otherwise clean, owned local environment can fail once and become impossible to bootstrap through the supported workflow without manual mutation or prohibited cleanup. This breaks the Story's reproducible runnable-workspace behavior. The final full guard cannot help because it is reached only after this multi-step write completes.
- **Required fix:** Make runtime-user provisioning retry-safe for bootstrap-owned partial creation. A safe implementation must distinguish the exact partial state produced by this initializer from foreign or mismatched existing users, then complete only the missing exact user/grant (or use an atomic/declarative provisioning mechanism). Preserve fail-closed rejection for any existing credential, tag, or permission mismatch. Add a regression test that injects failure after the first user's creation and proves a subsequent invocation safely converges without overwriting either identity.

## Verification performed

- `uv run --frozen pytest tests -q`: **291 passed, 11 skipped**. The skipped tests are opt-in live/fault paths and were not treated as new execution evidence in this read-only review.
- `uv run --frozen ruff check edw-api edw-worker scripts tests migrations`: **passed**.
- Portable Node 24.20.0: Web lint **passed**, typecheck **passed**, and Vitest **61 passed**.
- Guarded read-only runtime verification, `./scripts/verify-local-environment.ps1 --verify-runtime-images`: **passed** for ownership, all external isolation checks, tool capabilities, current source fingerprints, nine running container/image bindings, and schema-2 runtime manifest.
- Visual artifacts were inspected at 1920x1080 and 1180x800. The large body-content pixel differences are expected from the authorized real login/workspace state substitution; inherited shell geometry and the <=1180px notice behavior are consistent with the stated Story boundary. No pixel threshold was inferred.

No repository source, runtime, container, database, broker, or browser state was changed by this review. Only this report was written.


## 原始报告 edges

[{"location":"scripts/verify_local_environment.py:455-469","trigger_condition":"SeaweedFS becomes unavailable after readiness while its container remains running","guard_snippet":"records=current_runtime_images(...); verify_public_readiness(); require(records == current_runtime_images())","potential_consequence":"Bootstrap records success after a required dependency has become unavailable"},{"location":"scripts/verify_local_environment.py:384-452","trigger_condition":"Owned service is replaced by a same-image container with another nonce","guard_snippet":"ownership(); records=current_runtime_images(...); ownership()","potential_consequence":"Runtime manifest can attest a container outside the recorded ownership boundary"}]


## 原始报告 verification

No verification gaps found.


## 原始报告 acceptance

# Story 1.1 round 18 acceptance audit

Verdict: **approved**

Current visual verdict: **approved**

Scope: fresh acceptance audit of the complete 148-file binary unified diff
`C:/Users/VIRTUA~1/AppData/Local/Temp/eid-story1-1-review18-af32360b867b4c2ba4c4a7e4ec8ab5cf.diff`
against baseline `3440d2f89647aaeacf49213285c055dbe365df7d`, the full Story 1.1 specification,
both declared context files, the current runtime/image/log evidence, and all 18 current PNG artifacts.

## Findings

No acceptance-blocking or change-required finding was found.

## Acceptance criteria

1. **AC1 — pass.** The reviewed implementation provides exactly three business projects, pinned Python/Node/pnpm/uv dependencies and image digests, real PostgreSQL/Keycloak/RabbitMQ/Redis/SeaweedFS/NGINX services, real Web/API/Worker processes, NGINX routing, dependency-based readiness, Code + PKCE S256, and database-derived `/api/v1/me`. The guarded runtime check independently passed in this audit and returned the expected owned `eid-local` target, `localhost:55432/eid_local_dev`, bucket/vhost/realm/client, Docker 29.1.3 on linux/amd64, and schema-2 bindings for all nine current service images/containers. API/Web/Worker source fingerprints match the current files and current containers.
2. **AC2 — pass.** The verifier checks RS256 signature, issuer, audience, temporal claims and Bearer access-token type; the Web keeps tokens in module memory, removes callback parameters before validation/exchange completes, uses bounded token/account/readiness bodies, distinguishes 401/403/transient states, and fences delayed account responses after logout. Readiness separately probes PostgreSQL/schema/role, Redis, RabbitMQ, S3, Keycloak persisted contracts and the real Worker dependency control reply. The supplied explicit live record is 11 passed in 109.83s, including dependency loss/recovery, Worker role denials, inactive-account/membership filtering and forward migration behavior. The current archived log scan at `2026-09-11T04:11:29.235014Z` binds the same nine runtime instances and reports zero JWT/token/Bearer/code/fixture-secret matches for every service.
3. **AC3 — pass.** Bootstrap validates exact supported tool versions, local Docker context/platform/capabilities, lock/image manifests and ownership before infrastructure or migration steps. Database migration is limited to the exact localhost port/database/migrator identity and requires the owned project nonce, marker, volume attachment, bucket, RabbitMQ vhost/users/permissions and Keycloak realm/client configuration. Existing mismatches fail closed; no destructive cleanup or downgrade path exists. Initialization rechecks nonce and the three affected container IDs immediately before each broker, Keycloak or bucket write, and the online migration re-runs the complete isolation guard with bounded connection/statement/lock waits.
4. **AC4 — pass.** I opened all 18 artifacts from `current-screenshot-metrics.json` individually at original detail. The six current implementation shells and six original-prototype references preserve the shell geometry and visual system at 1920x1080, 1440x900, 1181x800, 1180x800, 1024x768 and 768x1024. The exact 1180/1181 prompt boundary is visible and correct. The six state images clearly show account loading, authenticated identity, actionable PostgreSQL readiness failure, and toast hidden/shown states. I found no actual shell, state, clipping, alignment, spacing, typography, color, border, radius, shadow, icon or control-state defect. This uses the user-approved exact CSS/layout plus independent screenshot review method; it does not use PNG equality, a pixel threshold, an ignored region or another waiver. All 18 independently computed SHA-256 hashes match the current metric ledger, with files written in the recorded `2026-09-11T04:08:46.8549039Z`–`04:08:46.8711767Z` capture window. The shown toast differs from the hidden hash. `docs/prototype/index.html` remains unchanged at SHA-256 `C876D444167A999D820BFC27D99C59D091C7AC885E93BC89CDF3B65EA1B4198E` and has no baseline diff.

## Inventory and verification

- The specification declares exactly 148 implementation paths; the supplied diff contains exactly those same 148 unique paths, with no omission, addition, duplicate or missing disk file.
- `git apply --check --reverse --binary` succeeds, confirming the supplied full diff matches the current working files and binary artifacts.
- HEAD remains the declared baseline. The work remains uncommitted and untracked; this audit did not change Git, source, BMAD/sprint status, containers, browser state or infrastructure. This report is the only audit write.
- Independent safe reruns: Python `291 passed, 11 skipped`; the 11 skips are the explicitly live-gated cases whose supplied current explicit run is `11 passed, 109.83s`. Web unit tests `61 passed`; scoped Ruff passed. The read-only runtime/image/isolation guard passed against the current nine containers. No build, browser run, live fault injection or live mutation suite was executed in this audit.
- The current supplied build/browser evidence remains: bootstrap exit 0, Web lint/typecheck/build pass, browser `19 passed` in 1.7m, and the final nine-service log scan described above. Its runtime IDs and source fingerprints match the independently rechecked current runtime manifest.

This approval is limited to local Story 1.1 acceptance. It does not approve enterprise IdP federation, enterprise-system integration, production startup/security/capacity/high availability, AI/model quality, Story 1.2+ authorization/domain/task/SSE behavior, the remainder of Epic 1, release readiness, or legal sufficiency of dependency-license metadata.
