---
epic_id: epic-12
status: planned
phase: 3-local-integration-and-readiness-tooling
story_status: backlog
---

## 当前开发与验证边界（2026-09-23）

执行软件层面的开发、代码检查和编译验证；不启动实际运行环境进行功能实测，也不使用已启动的实际环境进行功能实测；不进行实物、硬件或现场运行验证。

本文件统一受[开发与验证规则](development-validation-policy.md)及[总表的软件开发关闭规则](epics.md#binding-completion-contract-and-serial-acceptance-order)约束。Epic 1–12 的当前质量门禁仅为源码实现及审查、静态/契约/配置检查、编译或离线构建、独立代码审查和缺陷修复；不执行测试套件或实际环境功能验证。下文的 Verification、Evidence、L/R/P 及表格中的运行案例均为后续验收计划，不是当前 Story/Epic 关闭门禁，实际结果记录 `not-run`，不计为通过。Epic 13 当前仍暂停，不能以静态或编译结果完成验收。历史证据按原日期保留，不代表本轮通过或继续运行的授权。

# Epic 12: Reconcile local delivery and prepare measurable acceptance

Outcome: all three projects implement delivery/reconciliation, joint-test tooling, load tooling, compatible deployment assets and a complete ledger of static software evidence plus `not-run` runtime cases before any R/P-primary story. All six stories use epics.md's software closure contract. R/P obligations transfer explicitly to epic-13; none is erased or marked done. Legacy stable IDs are retained,not used as claims of real acceptance. No paid APIs,external messages,existing/production database mutations,push or production execution is authorized here.

## Software closure and deferred acceptance

The table retains each Story's planned L runtime evidence for later acceptance; it is not a current software quality gate. Software closure follows epics.md: implement the specified positive/negative behavior and security constraints, complete static checks and compilation/offline build, obtain independent source review, and fix known defects. Every unrun L case remains `not-run` under its source Story; R/P remains with Epic 13. Verification and Evidence below name future acceptance methods, not executed passes.

| Source story / clauses | Deferred L runtime evidence (not current gate) | Retained R/P clause → acceptance owner |
|---|---|---|
| 12-1 Scope,AC1–2,Evidence,L/R/P | Working declared simulator connectors/schema/config/denial | Actual vendors/versions/contracts/endpoints/credentials/capabilities →13-2; real policy/security →13-5 |
| 12-2 Scope,AC1–3,Evidence,L/R/P | Stateful simulator effect/approval/receipt/callback/reconcile/negative tests on real W/A/K | Actual MES/project/archive/KB receipts and all capability cases →13-2; real operator UAT →13-3 |
| 12-3 original real joint-test Scope/AC/Evidence,now protocol AC1–2 | Actual local full C1–8 runner/rehearsal and unsafe-real-target refusal | All original real IdP/ACL/KB/S3/MES/project/archive/return joint chains/negative cases →13-2; specialist/role UAT →13-3 |
| 12-4 original full numerical Scope/AC/Evidence,now harness AC1–3 | Full workload definitions/statistic tests/bounded actual local smoke and non-pass readiness labels | All exact original numerical UI/search/Pack/model/DOCX/full-concurrency criteria →13-4 |
| 12-5 original real rollout/security/recovery Scope/AC/Evidence,now local AC1–4 | Three actual local WPs,each positive/negative and separately reviewed; isolation stop honored | Actual compatible rollout,real security infrastructure,HA/99.9%/RPO≤15min/RTO≤1h/restored-state proof →13-5; alternatives contract/ADR →13-2 and performance →13-4 |
| 12-6 original full-R/P closure Scope/AC/Evidence,now local AC1–3 | Source/static/compile coverage for all local behavior including7-5 deferred rows;exhaustive `not-run` source-clause register; runtime proof deferred to source Story | Actual full three-phase/R/P independent acceptance →13-6,backed by13-1–13-5;no orphan or unrun clause may close that future acceptance |

## Story 12.1: Configure declared enterprise contracts and mappings
**ID:** `12-1-declared-connectors` | **Status:** backlog | **Projects:** W,A,K
As an integration administrator, I want explicit connector capabilities, so that the application cannot promise unknown vendor behavior.
**Scope:** Identity/KB/MES/project/archive/return adapter registration,versioned mapping/payload schemas,classifications,secret references,capability declarations for idempotency/query/callback/reconcile and safe contract health checks. Extend existing identity/KB adapters,not new services. Local profiles explicitly describe simulator capabilities; unknown vendor capability is not inferred.
**Dependencies:** `10-5-tender-integration`, `11-6-form-integration`, `7-2-safe-governance`.
**Traceability:** FR-42,FR-46,FR-47; C-1,C-4,C-8; AD-1,AD-7,AD-15.
**UI reference:** X-20 connector list/version/mapping/validation,X-09 target/contract/environment summary; SUP-4,SUP-5. S connector administration.
**UI fidelity:** Strict inherited source visual/interaction1:1 layout/position/size/spacing/font family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve hierarchy/source; B/R/S/conflicts explicit; X bodies use UX,not invented prototype pixels.
**Acceptance Criteria:**
- **Given** declared local contract/schema and administrator, **When** mapping is validated/activated locally, **Then** supported operations/version/target/secret reference and actual simulator idempotency/receipt/query/callback capabilities are explicit and auditable; malformed mapping cannot activate.
- **Given** unknown vendor/missing endpoint/invalid TLS/classification denial or unapproved outbound operation, **When** health/test/delivery is requested, **Then** blocked/not-configured without paid/production side effects; no invented adapter support,secret exposure or model-directed arbitrary URL.
**Evidence:** T-CONTRACT/T-SEC schema/capability/SSRF/secret/permission cases with local enterprise simulator; T-UX positive configuration/validation and negative states,closing X-20/X-09 entries from7-5.
**L/R/P:** L actual adapters and declared simulator. R actual documented endpoints/credentials/vendor capabilities in13-2; production policy/security/config in13-5. Missing R/P does not pass those stories.

## Story 12.2: Deliver locally approved artifacts and reconcile uncertain receipts
**ID:** `12-2-effect-reconciliation` | **Status:** backlog | **Projects:** W,A,K
As a delivery operator, I want auditable receipt/reconciliation, so that retry after timeout cannot double-apply a business action.
**Scope:** Document/form delivery eligibility,pinned approval policy,EffectIntent/outbox/inbox/EffectReceipt,correlation/partial status,authenticated callbacks/current policy checks and authorized retry/reconcile. Form approval pins schema+instance+canonical snapshot/artifact under declared human policy; Signature field is not approval authority. Local test approvals/assets are labeled and do not grant formal enterprise qualification.
**Dependencies:** `12-1-declared-connectors`, `6-6-trusted-knowledge-return`.
**Traceability:** FR-43,FR-42,FR-41; C-3,C-6,C-7,C-8; AD-3,AD-4,AD-7,AD-14,AD-15.
**UI reference:** X-09 delivery list/attempts/receipt/correlation/retry/reconcile; X-08 send/approval-ready state,X-03 approval,X-19 artifacts; SUP-4,SUP-2,SUP-8. S delivery,R actual status.
**UI fidelity:** Strict source1:1 visual/interaction layout/position/size/spacing/fonts/size/weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve source hierarchy/file; B/R/S/conflicts explicit; X bodies follow UX without original-pixel claim.
**Acceptance Criteria:**
- **Given** currently authorized locally approved pinned document or human-approved form snapshot/artifact and valid local classification/mapping, **When** delivery executes to the stateful simulator, **Then** durable intent/correlation/payload hash precedes external call; receipt result and inbox processed/business outcome commit atomically,source approval/version remains linked and partial per-item outcomes visible.
- **Given** timeout after external success,duplicate outbox/callback,worker crash or forged callback, **When** recovery occurs, **Then** verify callback identity/correlation/hash,query/reconcile according to declared capability,never blind-resend unknown effects. Idempotency key guarantees external dedup only if declared contract supports it; unsupported lookup stays unknown/manual reconcile,not fabricated exactly-once.
- **Given** stale form/document approval,revoked permission,L3 forbidden destination or audit outage, **When** send/retry commits, **Then** current gate denies. Cancellation after possible side effect remains receipt_pending/unknown until reconciled,not fake cancellation success.
**Evidence:** T-CONTRACT/T-TASK/T-SEC capability matrix (idempotent+queryable,callback-only,no query/idempotency),duplicate/partial/restart/unknown/forged-receipt cases against stateful simulator; T-FORM pinned approval and T-UX actual success/partial/unknown/denied navigation,closing delivery controls from7-5.
**L/R/P:** L actual W/A/K+PG/MQ and simulator,not mocked internal chain. R actual MES/project/archive/KB receipts and UAT in13-2/13-3; production operations not authorized.

## Story 12.3: Rehearse the enterprise and specialist joint-test protocol locally
**ID:** `12-3-real-joint-integration` | **Status:** backlog | **Projects:** W,A,K
As an acceptance operator, I want an executable joint-test protocol, so that real acceptance can later run without inventing missing cases.
**Scope:** Local runnable scenario runner/manifests/target-safety checks for IdP/ACL/KB/S3/MES/project/archive/return and document/tender/form chains; receiver correlation,redaction,role/task coverage and explicit route labeling. Legacy ID retained; former real-API and UAT criteria are wholly owned by13-2/13-3,not this story's done criteria.
**Dependencies:** `12-2-effect-reconciliation`, `9-4-evaluation-runs`.
**Traceability:** FR-4,FR-12,FR-31,FR-35–FR-43,FR-48; C-1–C-8; AD-18.
**UI reference:** UJ-1–UJ-6,X-09/X-20 environment/receipt,X-05/X-06,X-07/X-08,X-16; SUP-3,SUP-4,SUP-5,SUP-7.
**UI fidelity:** Strict existing visual/interaction1:1 layout/position/size/spacing/font-family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve source hierarchy/file; B/R/S/conflicts explicit; X bodies use UX not fictitious pixels.
**Acceptance Criteria:**
- **Given** actual W/A/K+local OIDC/PG/MQ/S3 and declared external simulators, **When** SSO→workspace→current-ACL/Evidence→document/tender/form→human test approval→artifact→delivery/return rehearsal runs, **Then** stored versions and observed request/receipt/correlation join; denied,malformed,stale,duplicate,timeout,replay and revocation cases execute for every declared contract.
- **Given** missing real targets/roles/data or unsafe target configuration, **When** protocol evaluates readiness, **Then** real mode refuses execution and identifies13-2/13-3 cases/owners/inputs as blocked/not-run; local runner success never claims vendor integration/UAT. No hidden network call to unknown targets.
**Evidence:** T-CONTRACT/T-TASK/T-SEC/T-TENDER/T-FORM/T-DOC local actual-chain traces,receiver-state assertions and case/role matrix; T-UX working route/error/reconciliation behavior. Small synthetic data is not real-quality evidence.
**L/R/P:** Current software closure requires the runner/protocol implementation, static checks and compilation; L runner/rehearsal execution remains `not-run` under this Story. All real vendor/UAT requirements remain in13-2/13-3; no real-test Story precedes later software work.

## Story 12.4: Implement and rehearse frozen-boundary load measurements
**ID:** `12-4-performance-capacity` | **Status:** backlog | **Projects:** W,A,K
As an operations owner, I want a validated load harness, so that actual capacity acceptance later measures the correct workload and boundaries.
**Scope:** k6/Playwright/worker harness,workload definitions,hardware/network/data/ACL/version manifests,DB/queue/pool/resource telemetry and timing/statistic reports. Local harness/rehearsal only; all original numerical R/P targets transfer unchanged to13-4.
**Dependencies:** `12-3-real-joint-integration`, `9-4-evaluation-runs`, `7-5-ux-regression`.
**Traceability:** FR-48; NFR-8,NFR-9,NFR-10,NFR-11,NFR-14,NFR-15; C-3,C-4,C-5,C-6; AD-18.
**UI reference:** P-00/P-01/P-03/P-04/X-10/X-16/X-19 measured interactions; no new page.
**UI fidelity:** This Story introduces no page. Reuse existing shell/UX contracts; performance collection must not redesign the UI. Full visual baseline remains owned by7-5.
**Acceptance Criteria:**
- **Given** versioned profiles for100online,doc/list20QPS,search5QPS,20chapter jobs/50searches/10whole Reviews and20concurrent30–80-page exports, **When** scheduling/statistic assertions and a bounded local smoke workload run, **Then** desired versus achieved load,queue/provider/pool errors,P50/P95/P99 and exclusions are recorded; reduced rehearsal does not assert full capacity pass.
- **Given** client/server timestamps and artificial timing/failure fixtures, **When** report logic is checked, **Then**1000ms idle debounce is separate from autosave request,TTFT/chapter and50-page DOCX elapsed boundaries are correct (no invented DOCX P95); incomplete/failed/permission-error samples cannot disappear from denominators.
- **Given** unavailable real model/corpus/official fonts/production-equivalent hardware, **When** readiness is reported, **Then**13-4 remains blocked/not-run and no fast-double capacity claim appears.
**Evidence:** T-OPS/T-QUALITY/T-DOC/T-UX runnable workload definitions,statistic unit cases,actual local raw timings and manifest validation. Full SLA execution/evidence belongs to13-4.
**L/R/P:** L harness correctness and bounded rehearsal only. R/P latency/capacity obligation in13-4 remains separate uncompleted work.

## Story 12.5: Package compatible upgrades and rehearse isolated recovery
**ID:** `12-5-safe-rollout-recovery` | **Status:** backlog | **Projects:** W,A,K
As an operations owner, I want testable rollout/recovery assets, so that later real drills start from compatible and protected software.
**Scope:** Three bounded evidence work packages: WP-A single Alembic chain,N/N-1 contracts/events,expand→compatible application→bounded backfill→verify→later contract and isolated migration/rollback; WP-B Helm/config/secret-reference/backup-restore/fault-runbook assets with deferred local smoke restoration; WP-C deferred dangerous-tool/current-ACL/audit security regression. Actual production-equivalent HA/availability/recovery/security certification transfers to13-5. For current software closure, all three WP assets need static/compile checks and independent source review; their runtime manifests/results remain `not-run`.
**Dependencies:** `12-4-performance-capacity`, `7-3-core-degradation`.
**Traceability:** FR-45,FR-48; NFR-6,NFR-7,NFR-12,NFR-13,NFR-18; C-1,C-2,C-3,C-6,C-8; AD-6,AD-12,AD-17,AD-18.
**UI reference:** No new UI; diagnostics reuse X-16/X-20.
**UI fidelity:** Diagnostic UI preserves strict inherited source1:1 layout/position/size/spacing/font family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness and intended interactions. Preserve hierarchy/file; B/R/S/conflicts explicit; X follows UX,not invented prototype pixels.
**Acceptance Criteria:**
- **Given** verified new project-isolated test database and pinned images, **When** WP-A migration/N/N-1 rollout/backfill/rollback rehearsal executes, **Then** old/new contracts remain compatible,pools/grants stay separate,no external call holds a DB transaction,locks/backfill are bounded and irreversible changes have documented restoration path; destructive contract changes occur only in a later verified compatible release.
- **Given** approved local test backup/assets, **When** WP-B smoke restore and configuration validation run, **Then** governed rows/object hashes can be compared and runbooks enumerate RabbitMQ/Worker/Redis/NGINX/CloudNativePG/Barman scenarios; local drill never claims99.9%,RPO≤15min or RTO≤1h acceptance.
- **Given** malicious parse/render/upload/download/diagram/formula fixtures, **When** WP-C runs, **Then** credential-free/network-disabled/non-root/read-only/seccomp/resource/temp isolation,current ACL and audit failclosed are tested; production encryption/retention/secret infrastructure is explicitly13-5,not inferred from a config file.
- **Given** unverified isolation,existing/production data target or missing authorization, **When** preparation detects it, **Then** stop; no database deletion/existing-data cleanup or unauthorized drill. A failed WP static/compile check or known implementation defect blocks software closure; unrun WP smoke/drill cases remain `not-run`.
**Evidence:** Separate WP-A compatibility/migration hashes; WP-B local restore/config/runbook manifest; WP-C T-SEC/T-TASK/T-CONTRACT logs; independent local review.13-5 separately requires full operational/security evidence.
**L/R/P:** L three local WPs only. Enterprise alternative contract/security/performance/recovery+ADR and P cluster/window/drills remain13-2/13-4/13-5.

## Story 12.6: Close software coverage and register every unrun acceptance obligation
**ID:** `12-6-full-acceptance-ledger` | **Status:** backlog | **Projects:** W,A,K
As a local delivery reviewer, I want complete software evidence and explicit unrun acceptance obligations, so that no unimplemented behavior is concealed by a future acceptance ledger.
**Scope:** Software evidence closure for all Epic1–12 owners and a complete source-story-criterion/environment-owner-case ledger for deferred L cases and13-1–13-6. It validates source coverage, static/compile evidence and owner linkage; it does not run any owner behavior or visual suite. Legacy full-acceptance slug is not full L/R/P acceptance.
**Dependencies:** `9-5-real-quality-acceptance`, `10-5-tender-integration`, `11-6-form-integration`, `12-3-real-joint-integration`, `12-4-performance-capacity`, `12-5-safe-rollout-recovery`.
**Traceability:** FR-1–FR-48; NFR-1–NFR-18; C-1–C-8; AD-1–AD-18; all test packages.
**UI reference:** P-00–P-12,SUP-1–SUP-9,X-01–X-20,C00–C36,23components; UJ-1–UJ-6.
**UI fidelity:** No new visual behavior is owned here. Validate only that owner manifests reference their approved visual evidence and conflict status.
**Acceptance Criteria:**
- **Given** local Story manifests, **When** the ledger is inspected, **Then** every delivered capability has one owner, implemented source reference, static/compile result and `not-run` entries for its deferred runtime cases; missing implementation or failed software checks prevent software closure. **Verification:** future manifest referential-integrity checker; current source/ledger review.
- **Given** a real or production clause, **When** the ledger closes, **Then** it has exactly one13-series owner case, required input and blocked/not-run/result status. **Verification:** source-clause ownership checker.
- **Given** a software-closed owner Story, **When** the reviewer inspects the ledger, **Then** it checks that Story's static/compile evidence and unrun acceptance entries without executing its suite. **Verification:** delta-based independent source review record.
**Evidence:** owner source/static/compile manifests, source-clause ownership report, `not-run` runtime ledger and one delta-based independent review; no L/R/P pass claimed.
**L/R/P:** Software-only closure after every local Story's software gate; its L runtime acceptance remains `not-run` under the original owner. R/P-primary13-1–13-6 follow sequentially and remain uncompleted until actual evidence passes. This does not authorize deployment/push/paid/external operations.
