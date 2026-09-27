---
epic_id: epic-1
status: planned
phase: 1
story_status: backlog
---

## 当前开发与验证边界（2026-09-23）

执行软件层面的开发、代码检查和编译验证；不启动实际运行环境进行功能实测，也不使用已启动的实际环境进行功能实测；不进行实物、硬件或现场运行验证。

本文件统一受[开发与验证规则](development-validation-policy.md)及[总表的软件开发关闭规则](epics.md#binding-completion-contract-and-serial-acceptance-order)约束。Epic 1–12 的当前质量门禁仅为源码实现及审查、静态/契约/配置检查、编译或离线构建、独立代码审查和缺陷修复；不执行测试套件或实际环境功能验证。下文的 Verification、Evidence、L/R/P 及表格中的运行案例均为后续验收计划，不是当前 Story/Epic 关闭门禁，实际结果记录 `not-run`，不计为通过。Epic 13 当前仍暂停，不能以静态或编译结果完成验收。历史证据按原日期保留，不代表本轮通过或继续运行的授权。

# Epic 1: Enter a secure workspace and retain requested work

Users can authenticate, select their actual projects and discover their records; operators can prove a submitted local operation is durable. W/A/K mean edw-web/edw-api/edw-worker. Read epics.md for normative requirements, L/R/P ledger and source paths. No development approval is implied.

## Software closure and deferred acceptance

The table retains each Story's planned L runtime evidence for later acceptance; it is not a current software quality gate. Software closure follows epics.md: implement the specified positive/negative behavior and security constraints, complete static checks and compilation/offline build, obtain independent source review, and fix known defects. Every unrun L case remains `not-run` under its source Story; R/P remains with Epic 13. Verification and Evidence below name future acceptance methods, not executed passes.

| Source story / clauses | Deferred L runtime evidence (not current gate) | Retained R/P clause → acceptance owner |
|---|---|---|
| 1-1 AC1–3,Evidence,L/R/P | Real isolated bootstrap,PKCE and negative safety checks | Enterprise federation →13-2; production startup/security →13-5 |
| 1-2 AC1–3,Evidence,L/R/P | Actual current-policy/grant/revocation matrix using local identities | Enterprise mapping/revocation semantics →13-2; real security →13-5 |
| 1-3 AC1–3,Evidence,L/R/P | Real record/filter/visibility positive-negative cases; baseline timings recorded | Project mapping →13-2; real-user validation →13-3; numerical load →13-4. Later quality metrics are explicitly owned by9-1,not passed here |
| 1-4 AC1–3,Evidence,L/R/P | Actual PG/broker durable inventory and failpoint proofs | Real external effects →13-2 after local12-1/12-2; multi-node quorum →13-5 |
| 1-5 AC1–3,Evidence,L/R/P | Actual fence/retry/cancel transaction tests; declared effect simulator | Actual external cancellation/receipts →13-2; production recovery →13-5 |
| 1-6 AC1–3,Evidence,L/R/P | Actual transport/replay/UI for six category envelopes with declared local handlers | Source-system notifications →13-2; long-connection/load →13-4; failover →13-5. Future business handlers are not certified by envelope tests |

## Story 1.1: Open the isolated three-project workspace
**ID:** `1-1-runnable-workspace` | **Status:** backlog | **Projects:** W,A,K

As a project member, I want a reproducible authenticated local workspace, so that I can enter the real application rather than a static prototype.

**Scope:** Minimal Vite React-TS/Python scaffold, lockfiles, Compose/NGINX/OIDC/PG/S3/MQ connections, health/readiness and initial authenticated identity route; only initial identity/workspace tables. Lock only the versions required to run this workspace; no full-domain schema, compatibility matrix or framework abstraction upfront.
**Dependencies:** none.
**Traceability:** FR-4,FR-48; NFR-2,NFR-18; C-1; AD-1,AD-16,AD-18.
**UI reference:** P-00 `.app/.topbar/#topnav/#sidebar`, P-12 `#toast/.mobile-note`; X-18 account; C00,C03,C36; SUP-8,SUP-9. B shell, R identity, S account/readiness.
**UI fidelity:** Validate only the changed P-00/P-12 shell controls and named authentication states against the approved baseline. Preserve source hierarchy and source file; record B/R/S deltas and conflicts. The full viewport/control inventory belongs to7-5.

**Acceptance Criteria:**
- **Given** a verified new isolated local database, **When** Compose starts W/A/K and a user completes PKCE, **Then** `/api/v1/me` returns the database-mapped account and workspace. **Verification:** browser end-to-end test with environment-guard evidence.
- **Given** invalid OIDC/JWT or PKCE input, **When** a protected API is called, **Then** it returns an unauthorized response with no account/workspace data. **Verification:** parameterized API contract test.
- **Given** any required local dependency is unavailable, **When** health endpoints are queried, **Then** live and ready report their distinct states and protected requests do not fake success. **Verification:** parameterized dependency-outage integration test for PostgreSQL, Worker, NGINX, RabbitMQ, Redis and S3.
- **Given** a declared toolchain or isolation guard failure, **When** bootstrap runs, **Then** it exits nonzero before migration. **Verification:** parameterized guard test.
- **Given** approved shell baseline conditions, **When** the changed authentication shell is reviewed, **Then** it matches the baseline or a registered difference. **Verification:** fixed-environment screenshot review.
**Evidence:** one result per AC: browser E2E, API contract, dependency-outage integration, guard test and screenshot review; lock/image manifest is build provenance.
**L/R/P:** L real local processes and Keycloak; R enterprise IdP federation remains blocked pending contract/credentials; P production startup/security is not proven by Compose.

## Story 1.2: Enforce current project membership and clearance
**ID:** `1-2-current-access` | **Status:** backlog | **Projects:** W,A,K

As a project owner, I want access checked at each use, so that role or membership changes immediately constrain work.

**Scope:** Workspace picker/membership under policy, server-derived authorization context, service identity, RBAC+ABAC+classification and fresh authorization on each use. The current implementation retains policy epoch; AC judges the fresh authorization outcome rather than requiring an extra cache mechanism. API/Worker DB grants prohibit Worker head/ACL/approval/publication writes.
**Dependencies:** `1-1-runnable-workspace`.
**Traceability:** FR-1,FR-4,FR-46; NFR-1,NFR-2,NFR-5; C-1; AD-1,AD-3,AD-7.
**UI reference:** P-00 project card/sidebar; X-18 project/account/membership; X-20 users/roles/scopes; C02,C03; SUP-8,SUP-5. R actual context, S administration.
**UI fidelity:** Validate the changed project/account controls and named authorization states; preserve source hierarchy and register R/S supplements. New X bodies follow UX; the full visual inventory remains owned by7-5.

**Acceptance Criteria:**
- **Given** a finite role × operation × resource-attribute matrix, **When** protected APIs are called, **Then** current RBAC, ABAC and clearance decide and client actor/scope cannot enlarge access. **Verification:** table-driven API contract test.
- **Given** a member is revoked after a UI or restricted worker context exists, **When** its next protected use occurs, **Then** it is denied and Web clears controlled data. **Verification:** revoke-between-uses integration test.
- **Given** Worker DB credentials, **When** they directly write ACL/head/approval/publication, **Then** PostgreSQL rejects them. **Verification:** real DB negative-grant test.
- **Given** a permission update, **When** policy or audit persistence fails, **Then** neither commits. **Verification:** injected audit-failure transaction test.
- **Given** a project switch or protected deep link, **When** its named UI state is reached, **Then** the current persistent state is shown. **Verification:** browser state regression.
**Evidence:** the five AC-specific test results above; project-switch screenshots are UI evidence, not an additional gate.
**L/R/P:** L local identities and ACL fixtures; R actual enterprise mapping/revocation latency needs real IdP/KB contracts; P production security validation remains separate.

## Story 1.3: Find actual workspace records and retained collections
**ID:** `1-3-workspace-discovery` | **Status:** backlog | **Projects:** W,A

As a member, I want accurate lists, search and collections, so that I open the intended authorized record.

**Scope:** Dashboard four KPI/card areas, recent/created/participating/favorite tabs, global search, project navigation, reference/favorite/recycle/storage projections. Initial document/metric datasets may be empty; future generation metrics remain unevaluated, never sample scores.
**Dependencies:** `1-2-current-access`.
**Traceability:** FR-2,FR-3,FR-47; NFR-1,NFR-8,NFR-16,NFR-17; C-1; AD-7,AD-16.
**UI reference:** P-01 `#page-home .kpis/.quad/.recent-table/.rightcol`, P-00 `#globalSearch/.side-bottom`; X-17/X-18; C01,C04,C05,C06,C07,C09; SUP-8,SUP-9. R data/actions, S destination lists.
**UI fidelity:** Strict source visual/interaction1:1 for layout/position/size/spacing/font family-size-weight/color/radius/shadow/border/icon/image proportion/button-input states/responsiveness; preserve hierarchy/source. Mark R/S additions and conflicts; X bodies follow UX without invented source pixels.

**Acceptance Criteria:**
- **Given** authorized records with different ownership/status/favorites and inaccessible counterexamples, **When** tabs/search/project/card More links are used, **Then** filters combine AND, cursor results/counts/storage use the same authorized dataset and open actual IDs/context; current request wins over stale search response.
- **Given** no records, API error, expired session or lost membership, **When** the page loads, **Then** distinct empty/loading/error/reauth/forbidden states appear without illustrative rows/KPIs or secret existence leaks.
- **Given** archived/recycled/favorite records, **When** authorized remove-favorite/restore-visibility actions run, **Then** only intended visibility changes are persisted/audited; governed versions are never physically deleted. Unavailable More/recommendations state why instead of success toast.
**Evidence:** T-UX/T-SEC browser filter/navigation/error tests and screenshots; API projection/cursor tests; baseline NFR-8 timings, no claimed production load.
**L/R/P:** L fixture records through real API/PG; R real project-source mapping and UAT pending enterprise data; P aggregate/load targets measured in13-4.

## Story 1.4: Preserve a submitted operation through durable transport
**ID:** `1-4-durable-submission` | **Status:** backlog | **Projects:** A,K

As an operator, I want accepted work durably recorded and delivered, so that broker interruption cannot erase the user's request.

**Scope:** C-3 Task/Attempt/DAG/Outbox/Inbox core and relay; small read-only authorized project inventory task proves a useful result. Six routing categories declared now; business handlers added in their stories. No generic executor or remote shell.
**Dependencies:** `1-2-current-access`.
**Traceability:** FR-44,FR-45,FR-48; NFR-5,NFR-13; C-1,C-3; AD-3,AD-4,AD-6.
**UI reference:** No new UI; API task result is future X-16 input.

**Acceptance Criteria:**
- **Given** an authorized request and Idempotency-Key, **When** API accepts it, **Then** task/state/audit/outbox commit atomically and return202+task_id; relay publishes only committed work using lease+publisher confirm. Same-key/same-payload reauthorizes and returns identity; different payload409 IDEMPOTENCY_KEY_REUSED.
- **Given** crash before commit, after commit/before publish or after broker confirm/before outbox update, **When** recovery runs, **Then** respectively no task or eventual at-least-once delivery occurs, never a lost committed request. Broker unavailable leaves queued durable work.
- **Given** duplicate envelope `(consumer,event_id)`, **When** received is persisted but processing crashed, **Then** received is not treated as processed; completion/result/processed marker/outbox/event transaction must succeed before ACK. Unknown incompatible envelope versions are inspectable, not executed.
**Evidence:** T-TASK/T-CONTRACT actual PG/RabbitMQ failpoint and duplicate tests, row/envelope/confirm traces; separate API/Worker pool bounds.
**L/R/P:** L real broker and PG with deterministic inventory handler; local enterprise-effect implementation/rehearsal is12-1/12-2,while actual enterprise effects remain independently uncompleted13-2; P quorum multi-node failover13-5.

## Story 1.5: Recover or cancel execution without stale results
**ID:** `1-5-fenced-recovery` | **Status:** backlog | **Projects:** A,K

As an operator, I want bounded restart/cancel behavior, so that a late worker cannot overwrite a newer result.

**Scope:** Monotonic fence/lease ownership, attempts/staging, DB next_retry_at, timeout/single-active Beat reconciliation, cancellation commit checks and dead-letter inspection.
**Dependencies:** `1-4-durable-submission`.
**Traceability:** FR-44,FR-45; NFR-13,NFR-15; C-3; AD-3,AD-4,AD-6,AD-7.
**UI reference:** No new UI; task state feeds X-16.

**Acceptance Criteria:**
- **Given** running work is killed or loses lease, **When** scanner claims expired work, **Then** a higher fence starts a new attempt with separate staging. Old worker completion cannot commit; result/task-terminal/next-step/event/inbox-processed changes are one short transaction checking fence,lease,base/hash,policy and cancel.
- **Given** transient versus permission/classification/missing-input/schema errors, **When** retry is scheduled, **Then** DB next_retry_at is the single bounded exponential-backoff schedule; permanent denials do not retry, schema repair at most once, exhausted work becomes inspectable failed/dead-letter.
- **Given** completion and cancel race, **When** each wins in separate tests, **Then** committed completion remains completed or earlier cancel blocks completion; Celery revoke is not truth. External already-sent effects retain receipt_pending/unknown rather than false cancelled; only declared safe compensation is possible.
**Evidence:** T-TASK/T-SEC crash/ACK-loss/lease-expiry/double-Beat/cancel-both-orders tests and timestamps; verify no DB transaction spans slow external calls.
**L/R/P:** L real task storage and worker termination; R actual external effect cancellation semantics13-2 (local simulator12-2); P multi-node/production recovery13-5.

## Story 1.6: Follow actual tasks and notifications after reconnect
**ID:** `1-6-task-observation` | **Status:** backlog | **Projects:** W,A,K

As an author, I want replayable authorized progress, so that closing a tab does not lose my work or reveal others' results.

**Scope:** Task center/notification list/read/open; persisted ordered TaskEvent, fetch-streaming Bearer SSE through non-buffered NGINX, snapshot/reset, supported retry/cancel controls.
**Dependencies:** `1-3-workspace-discovery`, `1-5-fenced-recovery`.
**Traceability:** FR-44,FR-45,FR-47; NFR-1,NFR-13,NFR-17; C-1,C-3; AD-5,AD-7,AD-16.
**UI reference:** P-00 `.bell`, P-12 toast; X-16 category/state/list/attempt/event/detail, X-18 reauth; C03,C36; SUP-7,SUP-9. R bell/actions, S task body.
**UI fidelity:** Inherit strict source visual/interaction1:1 for layout, position, size, spacing, font family/size/weight, color, radii, shadow, border, icons, image proportions, button/input states and responsiveness. Preserve hierarchy/source, record B/R/S changes/conflicts; new X bodies use UX, not nonexistent prototype pixels.

**Acceptance Criteria:**
- **Given** all six task categories with real states, **When** user opens notification, disconnects and reconnects with Last-Event-ID, **Then** task-scoped monotonic seq events replay, duplicates are ignored and REST snapshot fills retention gaps; final artifact identity is preserved. Unknown progress is null, not fabricated percentage.
- **Given** malformed/future cursor or access revoked mid-stream, **When** another event would be emitted, **Then** cursor rejects or stream closes and protected data clears; tokens never occur in URL and SSE excludes full documents/Evidence/secrets.
- **Given** unsupported cancel/retry or failed/dead-letter work, **When** controls render, **Then** reason is persistent, supported actions reauthorize and outcome is not a toast-only success. Notification read-state does not alter task state.
**Evidence:** T-UX/T-TASK/T-SEC real API→queue→K→PG→NGINX→browser replay/revocation tests, categorized state screenshots and event-size/cursor cases.
**L/R/P:** L actual transport and browser chain; R source-system notification integrations pending declared contracts; P long-connection/load/failover13-4/13-5.
