---
title: Enterprise Document Workbench Epics and Stories
stage: S4-author
status: planned
development_status_default: backlog
stepsCompleted: [step-01-validate-prerequisites, step-02-design-epics, step-03-create-stories]
workflow_mode: user-directed-auto-author-draft
author_draft: revision-complete-pending-independent-rereview
revision_scope: B1-B2-N1
s4_content_gate: previously-blocked-awaiting-independent-rereview
final_validation: author-content-check-only
mechanical_validation: not-run-tool-refused
workflow_completion_confirmation: not-given
independent_review: pending-coordinator-rereview
s4c_user_confirmation: not-given
main_project_persistence: not-performed
inputDocuments:
  - D:/Desktop/eid/AGENTS.md
  - D:/Desktop/eid/.claude/bmad-interview.md
  - D:/Desktop/eid/_bmad-output/planning-artifacts/prds/prd-eid-2026-09-08/prd.md
  - D:/Desktop/eid/_bmad-output/planning-artifacts/ux-designs/ux-eid-2026-09-08/DESIGN.md
  - D:/Desktop/eid/_bmad-output/planning-artifacts/ux-designs/ux-eid-2026-09-08/EXPERIENCE.md
  - D:/Desktop/eid/_bmad-output/planning-artifacts/architecture.md
  - D:/Desktop/eid/docs/README.md
  - D:/Desktop/eid/docs/01-软件技术规格说明书.md
  - D:/Desktop/eid/docs/02-系统架构与模块设计.md
  - D:/Desktop/eid/docs/03-数据模型与API接口规范.md
  - D:/Desktop/eid/docs/04-LLM-RAG与文档生成编排规范.md
  - D:/Desktop/eid/docs/05-安全权限审计与NFR规范.md
  - D:/Desktop/eid/docs/06-测试验收与实施计划.md
  - D:/Desktop/eid/docs/07-技术栈基线与工程规范.md
  - D:/Desktop/eid/docs/prototype/index.html
---

## 当前开发与验证边界（2026-09-23）

执行软件层面的开发、代码检查和编译验证；不启动实际运行环境进行功能实测，也不使用已启动的实际环境进行功能实测；不进行实物、硬件或现场运行验证。

本文件的执行安排统一受[开发与验证规则](development-validation-policy.md)约束。Epic 1–12 当前软件开发关闭只以源码实现、静态检查、编译/离线构建、独立代码审查和问题修复为门禁；下文涉及启动、部署、迁移、fixture、功能测试、浏览器实测、联调、性能和故障演练的条款仅为后续验收计划，不是当前 Story/Epic 关闭门禁，结果记录为 `not-run`。Epic 13 仍是暂停的真实验收，不以静态或编译结果标记验收完成。历史证据按原日期保留，不代表本轮通过或继续运行的授权。


# Enterprise Document Workbench — Epics and Stories

## Overview

This is the complete three-phase S4 planning draft, not permission to implement. Every epic is **planned** and every story **backlog**. Upstream S1/S2/S3 gates are accepted according to the user's current explicit confirmation; historical draft/pending prose in upstream files does not reopen them. The user requested automatic authoring without repeated interviews. Workflow steps record author work only: no interactive C selection, approval of this proposed decomposition, independent review, S4c confirmation or later-stage authorization is fabricated.

Read AGENTS.md before implementing every future story. Preserve quality **medium**, check → optimize → verify and independent code review. This author task neither performs those product checks nor self-approves them. S4b, sprint-status, S5/S6, code, database actions, Git commits/push, external publication and production execution are outside this task. Output resides only in this authorized worktree; main-project persistence is a separate coordinator action.

### Engineering and execution constraints

Exactly three business projects: **W = edw-web**, **A = edw-api**, **K = edw-worker**. W is one React/TypeScript/Vite SPA with Ant Design styled to the prototype, React Router, TanStack Query, limited Zustand and Tiptap open core/domain AST adapter. A is FastAPI/Pydantic 2, Python 3.12, SQLAlchemy 2/psycopg 3 modular business authority. K is Python/Celery execution with independent pools/grants. Knowledge/LLM Gateways and domain/application/persistence/ports/security/adapters remain internal shared modules, not listening services. `contracts`, `migrations`, `deployment`, `tests`, `evaluation`, `scripts`, `shared/python` are delivery directories, not projects.

PostgreSQL/JSONB owns versions, tasks, approvals and outbox/inbox; Redis is rebuildable only. RabbitMQ quorum transports at least once. Single-active Beat and six queues `generation`, `retrieval`, `review`, `parse_ocr`, `render`, `integration` remain. Dangerous parse/render tools run in isolated subprocess containers without DB/MQ credentials, network, root, writable root or unbounded resource/time/temp access. API exclusively moves document head, permissions, approvals and publication. Worker may stage results and complete permitted task records, never assume API authority.

Confirmed components include NGINX, Keycloak/OIDC, S3/SeaweedFS; local attachment pgvector + FTS + jieba + BGE-M3 + bge-reranker-v2-m3/FlagEmbedding; httpx/Pydantic LLM Gateway, vLLM and Qwen3-32B evaluation candidate; pypdf/python-docx/openpyxl/PaddleOCR, docxtpl/LibreOffice/Mermaid CLI; JSON Schema 2020-12 approved subset and whitelist formulas. Docker/Compose locally, Kubernetes/Helm production configuration, CloudNativePG/Barman Cloud, OTel/Prometheus/Grafana/Loki/Tempo/Alertmanager. No commercial editor dependency, fourth engineering project or forced reindexing of enterprise knowledge. Starter is the architecture's minimal pinned Vite React-TS plus Python service structure, not a downloaded business starter; lock supported Node LTS, pnpm and uv dependencies before implementation.

### Binding completion contract and serial acceptance order

**当前软件开发关闭规则（2026-09-27）：** Epic 1–12 的 Story 完成源码实现、源码/差异及独立代码审查、适用的静态/契约/配置检查、编译或离线构建后，可按软件开发关闭语义标记 `done`。同一断言或 Bug 的修改与验证最多 3 次；第三次后仍失败，停止该问题的修改与验证，记录失败证据并标记 `FORCED_PASSED`，作为强制流程完成状态继续串行开发。`FORCED_PASSED` 不表示验证通过。当前不执行任何测试套件或实际环境功能验证；下文 L 运行验证及 R/P 验收不是当前软件开发关闭条件，结果记为 `not-run`。详见[开发与验证规则](development-validation-policy.md#2026-09-27三次上限与强制收敛)。

**Epic1–12 contain67 software-delivery stories; Epic13 contains6 R/P-primary acceptance stories.** Serial execution advances after `done` or a documented `FORCED_PASSED` and the Story-owned commit. 12-6 closes the software evidence ledger while retaining unexecuted L/R/P entries with their original owners. Epic13 的13-1→13-2→13-3→13-4→13-5→13-6 顺序仅保留为后续验收依赖；当前全部暂停，不因12-6完成或环境就绪而自动执行。 A forced completion carries its failed checks and unresolved defects forward; it is not a pass claim or release approval.

For each Epic1–12 story, **done means software development closed**, not L runtime or real FR/NFR acceptance. Each shard partitions scope, at most five behavior AC, planned evidence and R/P clauses. A local AC retains one observable result and a named future verification method; that method is not executed for the current gate. Actual W/A/K logic, including applicable positive/negative paths and fail-closed behavior, must be implemented and inspected; missing implementation cannot be disguised as an environment gap. Original L runtime cases remain `not-run` under their source stories; R/P clauses remain independently uncompleted in named13-series stories. Retained real/official/numerical language is a future acceptance obligation,not a hidden serial software prerequisite or a waiver. The transfer register below remains normative for later acceptance.

Future test profiles may use explicit isolated synthetic policies/roles/standards/assets and labeled external-port doubles to exercise the **same unchanged hard-gate predicate**,including successful local approval/publication/return. They cannot claim enterprise formal assets/authority,relax a hard gate or enable real operations. UI/artifacts/manifests must expose the test environment when later verified. Real mode with absent official template/theme/critical-Evidence definition+threshold/approval/waiver authority still denies by design and source inspection. Local readiness and numerical timing validation remain `not-run`; no empty/not-configured negative case substitutes for implementing a required positive local function. Exact frozen-workload targets remain uncompleted13-4 obligations.

Stable slugs9-5-real-quality-acceptance,12-3-real-joint-integration,12-4-performance-capacity,12-5-safe-rollout-recovery and12-6-full-acceptance-ledger are retained for traceability,but now describe local protocol/tooling/rehearsal/closure. Their original real-quality,joint-test,UAT,numerical,HA/security and final-acceptance obligations are explicitly owned by13-1–13-6. No deletion of source scope or implicit completion is permitted.

### L/R/P acceptance ledger (applies individually to every story)

- **L — retained local runtime acceptance (当前非软件关闭门禁，not-run):** future actual W/A/K processes with real local OIDC, PostgreSQL, RabbitMQ, S3, REST/SSE, migrations and actual parse/OCR/render when involved. Deterministic doubles would be allowed only at configured external model/enterprise ports and labeled in UI/test manifests. These cases stay with each source Story; no runtime pass is inferred from static checks or compilation.
- **R — real environment (当前暂停，not-run):** approved enterprise IdP/ACL/KB/MES/project/archive contracts and endpoints, permitted credentials, real model/Embedding/Reranker, representative authorized data, official templates/fonts and human UAT. Missing prerequisites mean **blocked/not-run**, not pass or deleted scope. No paid provider calls are authorized here.
- **P — production-equivalent (当前暂停，not-run):** frozen load/hardware/network/cluster/security/fault domains and approved execution for HA, capacity, availability and recovery. Configuration alone is not proof. Production execution needs separate authorization.

当前不执行迁移、fixture 或数据库读写验证。以下数据库授权仅保留其原有边界，不构成当前执行许可。Future local database execution is limited to a newly created project-isolated development/test database. Verify host, database name and project exclusivity before migration or test-data writes; stop if unprovable. No deleting databases, cleaning existing data or touching enterprise/production databases. ENV dependencies are acceptance dependencies, not unresolved product scope.

The user's precise authorization is retained verbatim, not broadened by any story:
> 授权对本项目新建的、与现有业务数据隔离的本地开发/测试数据库执行迁移和测试数据读写，不涉及现有企业数据库或生产环境。
>
> 执行前核对目标地址、库名及项目专用性，无法证实隔离则停止；不得扩展为删除数据库或清理已有数据。无生产部署、push、付费API或外部消息授权。

No database action was executed during this S4 author task.

## Requirements Inventory

### Functional Requirements

These concise inventory statements preserve the upstream PRD as normative detail; story acceptance below must not weaken it.

- FR-1: Authorized workspace/type/template/scope selection creates a document with its own persisted ID and AST; inaccessible choices denied.
- FR-2: Actual recent/created/participating/favorite records, task/status/count/storage data and real loading/empty/error states.
- FR-3: Permission-filtered global lookup, context-preserving navigation, favorites/reference/recycle semantics without physical governed-history deletion.
- FR-4: Authenticated identity/roles mapped to each request and background task; RBAC AND ABAC AND clearance, real SSO separately validated.
- FR-5: Versioned editor-independent domain AST, source-defined blocks and stable relationships; invalid input preserves last valid version.
- FR-6: Correct-selection formatting/insert/undo/redo/save, real save status, history, CAS and recoverable concurrent conflict.
- FR-7: All five template scopes, AND filters, actual preview/details and pinned-template creation.
- FR-8: Authorized upload/validate/version/publish/deprecate template rules; historical references retained, invalid formal usage rejected.
- FR-9: Technical solution mandatory structure/current formal sources/traceable architecture and consistent supported parameters.
- FR-10: PRD structured FR-ID/name/role/scenario/preconditions/normal-exception flow/rules/IO/permissions/NFR/acceptance.
- FR-11: Requirement↔Test Item↔Test Case↔Acceptance links/coverage in Phase 1; measurable technical requirements and immutable approved thresholds.
- FR-12: Enterprise knowledge retrieval pre/post ACL, domain/context/version/classification filtering before any model use.
- FR-13: Nine source authority levels distinct from security classification; current applicability and explicit competing KnowledgeConflict.
- FR-14: Evidence source/version/section/chunk/quote/scores/validity/policy provenance; actual passage navigation and current authorization at every use.
- FR-15: All checkable Claim types with support/conflict/context bindings; critical unsupported facts remain actionable, never verified.
- FR-16: Section-specific deduplicated/authorized/versioned Evidence Packs; insufficient support visible and provenance survives edits.
- FR-17: Controlled upload and isolated parse/OCR/index, partial/failure states, separate local attachment retrieval and idempotent jobs.
- FR-18: Context/facts/glossary/attachments/similar documents and outline proposal; missing info and mandatory human outline confirmation.
- FR-19: Durable section DAG, real stages/errors/retryability, cross-section assembly/checks, BLOCKED_BY_MISSING_INFO.
- FR-20: Complete Copilot operation catalog, explicit selection/context and read-versus-write effect; no silent mutation.
- FR-21: Every AI write is a version-based human-reviewed Patch; selected accept/new version/provenance, reject unchanged and stale conflict.
- FR-22: Located pending facts/resolution/authorized exception history; validated safe tables/diagrams, never arbitrary code.
- FR-23: Eight version-pinned Reviewers with real tasks, findings and rule/model provenance.
- FR-24: Version-specific Review list/detail/count/score/coverage, all combined filters, selected source and history/comparison.
- FR-25: Distinct accept/reject/modify/handled; checked severe resolution or authorized permissible exception, no auto-certification.
- FR-26: Located numeric/name/obsolete-source/missing-section/requirement/ambiguity/terminology/unsupported-fact regression cases.
- FR-27: Pinned human approval request/decision/reason/history; edits invalidate inherited approval.
- FR-28: Persisted document lifecycle DRAFT→CONTEXT_READY→OUTLINE_READY→GENERATING→REVIEWING→USER_REVIEW→APPROVAL_PENDING→PUBLISHED→ARCHIVED; failures/missing inputs distinct from task state.
- FR-29: Atomic fail-closed publication under current version/policy, all required sections/Reviews/pending/Evidence/conflict/ACL/DLP/template/approval/confirmation/audit gates; severe unsupported critical Claims=0.
- FR-30: Actual pinned DOCX/PDF and HTML/Markdown export, all formal fields, safe rendering, current download/share authorization and inspectable failure.
- FR-31: Separate Published-triggered Knowledge Quality Gate, trusted parse/chunk/enrich/return and reconciled duplicates; drafts ineligible.
- FR-32: Complete Phase 2 quality outline/project plan/functional test outline/performance test outline/project summary workflows, not catalog placeholders.
- FR-33: Governed actual quality/coverage/rule definitions, denominators and drill-down, retaining Phase 1 coverage.
- FR-34: Versioned retrieval/generation/Reviewer evaluation, **50–200 representative Golden Queries per document domain**, defect labels and real versus double evidence.
- FR-35: Source-located/correctable qualification/commercial/technical tender requirements and per-page partial/failed parse.
- FR-36: Mandatory/disqualification/scoring clauses and declared real-rule checks; unresolved risk cannot be hidden by scores.
- FR-37: Bidirectional versioned tender requirement↔response↔Evidence matrix, missing/partial/conflicting states and export context.
- FR-38: Residual customer/project names and contradictory bid parameters enter common Review/approval/publication gates.
- FR-39: Independent versioned Form Schemas and eleven field types; reviewed AI SchemaPatch cannot replace active schema directly.
- FR-40: Web/server validation parity, versioned instances, whitelist formulas and last valid record retention.
- FR-41: Identical canonical form values across Web/DOCX/PDF/XLSX/print, barcode/QR/scan and controlled signature/attachments; no e-signature claim.
- FR-42: Declared configurable identity/knowledge/MES/project/archive connector contracts, correlation and authorized diagnostics, local ≠ real vendor support.
- FR-43: Controlled approved-artifact delivery and receipts, duplicate/partial/unknown outcomes reconciled without blind repeat business effects.
- FR-44: Six-category durable tasks/progress/errors/artifacts/cancel/retry; authorized replay and snapshots.
- FR-45: Worker/broker/cache fault recovery, bounded retry/compensation and visible dead-letter/failure without losing business facts.
- FR-46: Critical-action audit includes actor/object/version/workspace/outcome/correlation; authorized inspection without secret disclosure.
- FR-47: Actual notifications/aggregates/admin/configuration states; text and not-configured reasons, no sample production outcomes.
- FR-48: Runnable three-project local configuration/contracts/migrations/tests/evaluation and production configuration; precise DB authorization and separate acceptance ledgers.

### Non-Functional Requirements

- NFR-1: Every access satisfies current RBAC AND ABAC AND classification, including source views, background tasks, export and revoked access.
- NFR-2: OIDC Code+PKCE, short-lived tokens, API verification and separate service identities; NGINX is not authorization.
- NFR-3: Classify→DLP→Policy→Redact→Router; L0/L1 require policy, L1 redaction, L2 defaults internal/no unconfigured exception, L3 never external; no permissive fallback.
- NFR-4: Untrusted KB/tender/attachments separated as data; injection containment, tool whitelist and DLP for secret/personal/customer/project/device/network/technical data.
- NFR-5: 100% critical-action audit; unavailable critical audit blocks permission, approval and publication writes.
- NFR-6: TLS/at-rest/backup encryption, secret manager, no raw sensitive logs, governed restricted Prompt retention, watermark and separate retention/TTL without invented periods.
- NFR-7: Non-root/network-disabled/credential-free safe OCR/render/diagram containers, read-only root, seccomp, bounded resources/time/temp and validated files.
- NFR-8: Key UI, home/list API, AST fetch and autosave request P95<1s; separate 1000ms idle debounce and end-to-end/client/server timings.
- NFR-9: Search P95<3s; typical Evidence Pack P95<8s; permission-error retrieval=0 under frozen corpus/ACL/query/endpoint/reranker/pack settings.
- NFR-10: Real-route TTFT P95<5s, typical chapter P95<60s; model SLA separated, public-network exclusions recorded.
- NFR-11: 50-page DOCX<60s (not specified P95); typography/pagination/tables/references and formal-field Golden snapshots.
- NFR-12: Availability≥99.9%, RPO≤15min, RTO≤1h proven through measured production-equivalent monitoring/drills.
- NFR-13: PG truth survives cache/broker/worker loss; manual work survives model outage; knowledge/Reviewer outages block dependent assertions/releases, render failure preserves version.
- NFR-14: 100 online, doc/list20QPS, search5QPS;20 chapter jobs,50 searches,10 whole-document Reviews;20 simultaneous30–80-page exports. Suggested500DAU/1M versions/10M links is sizing, not measured capacity.
- NFR-15: HTTP→outbox→worker→retrieval/model/Claim/Review/Patch→SSE trace correlation, real latency/queue/usage/retry/resource metrics without sensitive bodies.
- NFR-16: Strict original-page visual and interaction1:1 at matched source state/viewport/fonts; only enumerated B/R/S replacements/supplements, no invented tolerance.
- NFR-17: ≤1180px desktop min-width1180/horizontal scroll/note;1181 boundary; distinct queued/retrieval/streaming/Review/Diff/pending/forbidden/offline/export/approval states.
- NFR-18: Medium quality, locked versions/contracts/migrations, critical tests, independent review and check→optimize→verify; failures remain blocking.

### Additional Requirements

Contracts C-1 identity/context, C-2 AST/version/Patch, C-3 durable tasks/events, C-4 Knowledge/Evidence/Claim, C-5 model/Prompt, C-6 file/render/download, C-7 Review/quality/approval/publication, C-8 form/integration must have positive, denied, malformed, duplicate, stale, timeout and replay tests as applicable. `/api/v1`, snake_case, UTC RFC3339, opaque IDs, exact decimal strings/units, cursor lists and AND filters; server derives actor/scope/classification. Bearer/X-Request-ID/traceparent/Idempotency-Key,201 creation/202 tasks, unified structured error with request/trace/retryability. Same key/different payload409 `IDEMPOTENCY_KEY_REUSED`; replay reauthorizes instead of returning protected historic success. Preserve DOC_VERSION_CONFLICT, TEMPLATE_DEPRECATED, KNOWLEDGE_PERMISSION_DENIED, EVIDENCE_REQUIRED, EVIDENCE_STALE, MODEL_NOT_ALLOWED, REVIEW_GATE_FAILED, MISSING_CONFIRMATION, EXPORT_FAILED. HTTP401/403-or-safe404/409/422/429/503 have specific semantics.

Architecture decision obligations: AD-1 three projects/ownership/grants; AD-2 stable domain AST/immutable versions; AD-3 short atomic transactions/current-state checks; AD-4 at-least-once/inbox semantics; AD-5 durable continuously authorized SSE; AD-6 queue and dangerous-tool isolation; AD-7 current authorization/revocation; AD-8 dual knowledge chains/exact retrieval/authority; AD-9 safe model routing/structured Patch proposals; AD-10 eight Reviewers/human decisions; AD-11 separate publication/return gates; AD-12 controlled objects/current downloads; AD-13 full later-phase types/tender/staleness; AD-14 independent canonical forms; AD-15 EffectIntent/Receipt/unknown/reconciliation; AD-16 original UX/BRS/conflict register; AD-17 compatible upgrade/migration/recovery; AD-18 L/R/P/quality/flag safety.

Test packages are T-AST,T-CONTRACT,T-TASK,T-SEC,T-DOC (explicit HTML/Markdown safety),T-TENDER,T-FORM,T-UX,T-QUALITY,T-OPS. All future evidence manifests include commit/locks/image digests, contract/schema/template/Prompt/model/embedding/reranker/rule/font versions, environment class, data/ACL/load/threshold definitions, timestamps/results/failures/exclusions, artifact hashes/traces and named human reviewer. A local fixture cannot establish real efficacy or production NFR.

### UX Design Requirements

UX-DR1: Implement P-00–P-12 with source selectors and source styles; original prototype immutable. Preserve64px header/266px sidebar,12px shell gaps/padding, editor minmax650+356 and48/48 rows, paper880max/1040min with34/56/60padding, home330rail/142hero, templates310rail/four min180columns, Review350/min420/370, original button38/field39/modal560 geometry.

UX-DR2: Match source cascade/font resolution, not flattened token guesses: font fallback manifest, paper h1/h2/h3=32/25/18, paragraph14/1.85, summary inherited16/1.7, template heading UA2em where source does so. Preserve source artwork/codepoints, shadows/borders/radii/colors/icon proportions. `.userarea` rule is not a wrapper in source markup; do not introduce erroneous spacing. Ant defaults do not override source.

UX-DR3: Implement all23 shared components with DESIGN§Shared visual components and EXPERIENCE behavior: Shell navigation; Button and input; Tabs and filters; Data list/table; Status and task card; Metric summary; Document canvas and toolbar; Copilot and prompt; Evidence and source viewer; Pending item resolver; Template browser/editor; Issue inspector; Dialog and toast; Diff and version comparison; Approval and release gate; Tender workbench; Form Builder; Form instance and scan; Export and artifact viewer; Knowledge and conflict management; Analytics and evaluation; Administration and policy; Context and outline. Numeric ring decoration is not a measured radial gauge.

UX-DR4: Implement the complete C00–C36 action inventory. Preserve six navigation buttons/five home quick-create entries/six baseline Copilot actions/four Review decisions. Bind actual IDs, statuses, dates, counts and denominators. No inert-success toast, first-paragraph citation insertion, fixed selected-source detail or false handled/Review-completed replacement.

UX-DR5: Implement X-01–X-20 supplementary body/overlay contracts, each with its exact UX layout/entry/actions. Mark SUP-1–SUP-9 and B(original visual)/R(demo→real)/S(authorized supplemental) separately. P-10/P-11 only have prototype navigation/shared placeholder, not a pixel baseline for their new bodies.

UX-DR6: Each UI story declares only the loading/empty/ready/failed/forbidden/expired-session/offline or task states introduced or changed by its behavior; a state matrix records inapplicable states and their owner. No sensitive text/token in localStorage/IndexedDB. Keyboard/dialog focus/escape/cancel/reason/announcements follow EXPERIENCE; toast1800ms/200ms/bottom28 is secondary, never sole persistent outcome.

UX-DR7: Functional UI stories test the changed surface at its approved viewport and state. The complete viewport/zoom baseline inventory has one owner (7-5); ledger stories validate its evidence references only. Retain narrow desktop scroll/note, no mobile stack/new dark theme. Freeze browser/OS/zoom/fonts/fixture/source-state. Source hash establishes identity, not visual pass.

UX-DR8: Measure keyboard/screen-reader/focus/contrast/zoom separately. VC-1 contrast/focus and VC-2 fixed-desktop/reflow conflicts are registered with measured selectors/evidence and authorized resolution; never silently restyle the source or falsely claim AA/fidelity. New pages follow UX contract, not nonexistent pixel references.

## FR Coverage Map

| FR | Primary epic(s) | Delivery outcome |
|---|---|---|
| FR-1, FR-2, FR-3, FR-4 | epic-1 | Secure runnable workspace, actual records and access |
| FR-5, FR-6, FR-7, FR-8, FR-18 | epic-2 | Editable versioned documents and template/context setup |
| FR-12, FR-13, FR-14, FR-15, FR-16, FR-17 | epic-3 | Traceable authorized knowledge and attachments |
| FR-19, FR-20, FR-21, FR-22 | epic-4 | Controlled generation, proposals and human resolution |
| FR-9, FR-10, FR-11, FR-23, FR-24, FR-25, FR-26 | epic-5 | Four complete Phase 1 types and expert Review |
| FR-27, FR-28, FR-29, FR-30, FR-31 | epic-6 | Formal approval, safe output and separate trusted reuse |
| FR-44, FR-45, FR-46, FR-47, FR-48 | epic-1,epic-7,epic-12,epic-13 | Actual local tasks/operations and local closure;separate real acceptance inepic-13 |
| FR-32 | epic-8 | Five complete Phase 2 document-type workflows |
| FR-33, FR-34 | epic-9,epic-13 | Local governance/runner tools;actual per-domain Golden quality and POC inepic-13 |
| FR-35, FR-36, FR-37, FR-38 | epic-10 | Tender analysis through compliant response/release |
| FR-39, FR-40, FR-41 | epic-11 | Controlled schemas, instances, print and scan |
| FR-42, FR-43 | epic-12,epic-13 (identity/knowledge start epic-1/3) | Local declared connectors/stateful reconciliation;actual enterprise delivery and receiver receipts in13-2 |

## Epic List

All entries below are **planned**. Their author-proposed sequence is not user approval. Detailed story dependency IDs govern execution; no epic requires a later epic for its initial local functional value. End-to-end real acceptance and production measurement are follow-on evidence, not prerequisites for local authoring. Backend-only tasks still have a user-visible or operator-verifiable outcome; tables are introduced only when used by that story, never the entire domain schema upfront.

| Stable ID | Phase | User outcome | Dependencies | Detail file |
|---|---|---|---|---|
| epic-1 | 1 | Users enter an isolated, secure workspace and retain requested work durably | none | epic-1-secure-workspace.md |
| epic-2 | 1 | Authors create template-based documents, edit safely and confirm context/outline | epic-1 | epic-2-controlled-authoring.md |
| epic-3 | 1 | Authors find, inspect and bind trustworthy authorized Evidence | epic-1, epic-2 | epic-3-trustworthy-evidence.md |
| epic-4 | 1 | Authors obtain bounded AI proposals and accept only intended changes | epic-1–3 | epic-4-controlled-ai.md |
| epic-5 | 1 | Experts find real issues across all four core document types | epic-1–4 | epic-5-review-core-types.md |
| epic-6 | 1 | Approvers release a fixed version, export it safely and return eligible knowledge | epic-1–5 | epic-6-formal-delivery.md |
| epic-7 | 1, ongoing | Operators diagnose/recover work and demonstrate the actual three-project core chain | epic-1–6 | epic-7-observable-core.md |
| epic-8 | 2 | Teams complete five additional project/quality document workflows | epic-1–6 | epic-8-project-document-types.md |
| epic-9 | 2, baseline1 | Quality owners use actual local metrics/rules/datasets/runners and rehearse quality acceptance | epic-1–8 | epic-9-quality-evaluation.md |
| epic-10 | 3 | Bid specialists correct tender clauses and release compliant responses | epic-1–7 | epic-10-tender-compliance.md |
| epic-11 | 3 | Production users manage schemas, enter consistent data and confirm scanned proposals | epic-1–7 | epic-11-production-forms.md |
| epic-12 | 3, local cross-phase | Teams reconcile local delivery,prepare joint/load/rollout tools and close all local behavior | epic-1–11 | epic-12-integration-readiness.md |
| epic-13 | Cross-phase R/P acceptance | Owners establish real quality/POC,enterprise receipts,official output/UAT,capacity/security/recovery and final acceptance | all local epic-1–12;13-1→13-2→13-3→13-4→13-5→13-6 | epic-13-real-acceptance.md |

### Story index (73 stories; every status is backlog)

| Epic / shard | Enumerated story keys |
|---|---|
| [epic-1](epic-1-secure-workspace.md) | 1-1-runnable-workspace; 1-2-current-access; 1-3-workspace-discovery; 1-4-durable-submission; 1-5-fenced-recovery; 1-6-task-observation |
| [epic-2](epic-2-controlled-authoring.md) | 2-1-template-creation; 2-2-domain-editor; 2-3-version-conflicts; 2-4-template-governance; 2-5-project-context; 2-6-outline-confirmation |
| [epic-3](epic-3-trustworthy-evidence.md) | 3-1-safe-attachments; 3-2-authorized-retrieval; 3-3-source-governance; 3-4-section-evidence; 3-5-claim-citation |
| [epic-4](epic-4-controlled-ai.md) | 4-1-safe-model-routing; 4-2-section-generation; 4-3-copilot-operations; 4-4-reviewed-patches; 4-5-pending-safe-graphics |
| [epic-5](epic-5-review-core-types.md) | 5-1-pinned-reviewers; 5-2-review-inspection; 5-3-issue-disposition; 5-4-technical-solution; 5-5-prd-composition; 5-6-test-traceability; 5-7-measurable-requirements |
| [epic-6](epic-6-formal-delivery.md) | 6-1-human-approval; 6-2-atomic-publication; 6-3-docx-pdf-rendering; 6-4-html-markdown-export; 6-5-controlled-artifacts; 6-6-trusted-knowledge-return |
| [epic-7](epic-7-observable-core.md) | 7-1-audit-observability; 7-2-safe-governance; 7-3-core-degradation; 7-4-core-integration; 7-5-ux-regression |
| [epic-8](epic-8-project-document-types.md) | 8-1-quality-outline; 8-2-project-plan; 8-3-functional-test-outline; 8-4-performance-test-outline; 8-5-project-summary |
| [epic-9](epic-9-quality-evaluation.md) | 9-1-quality-analytics; 9-2-review-rule-center; 9-3-golden-datasets; 9-4-evaluation-runs; 9-5-real-quality-acceptance |
| [epic-10](epic-10-tender-compliance.md) | 10-1-tender-intake; 10-2-tender-risk-rules; 10-3-compliance-matrix; 10-4-bid-review-release; 10-5-tender-integration |
| [epic-11](epic-11-production-forms.md) | 11-1-form-schema; 11-2-schema-patches; 11-3-form-instances; 11-4-form-multiformat; 11-5-form-scan-proposals; 11-6-form-integration |
| [epic-12](epic-12-integration-readiness.md) | 12-1-declared-connectors; 12-2-effect-reconciliation; 12-3-real-joint-integration; 12-4-performance-capacity; 12-5-safe-rollout-recovery; 12-6-full-acceptance-ledger |
| [epic-13](epic-13-real-acceptance.md) | 13-1-real-quality-poc; 13-2-real-enterprise-integration; 13-3-real-output-ux-uat; 13-4-real-performance-capacity; 13-5-real-security-recovery; 13-6-full-real-acceptance |

The file boundaries follow user journeys and feedback/security boundaries, not W/A/K layers. Shared AST, tasks, review and artifact facilities are extended rather than copied into later-type, tender or form services. Each shard supplies story-specific scope, direct earlier dependencies, Given/When/Then behavior requirements, security/state outcomes, exact UI references, deferred evidence and L/R/P dependencies. Story IDs are immutable `N-M-slug`; numeric `N-M` shorthand in coverage tables resolves to that shard's unique ID. This planning edit does not change sprint status.

## Complete Delivery Traceability

Ranges below are inclusive story keys, not new IDs. Primary implementation owns the requirement; integrated acceptance references do not replace implementation. All requirements remain effective in later phases. Every L, test, rerun, browser, fixture and actual-environment reference in the following traceability tables is a deferred acceptance plan, not a current software closure gate or an executed pass.

### Engineering project → stories

| Project | Complete story allocation | Boundary |
|---|---|---|
| edw-web | 1-1,1-2,1-3,1-6; 2-1–2-6; 3-1–3-5; 4-1–4-5; 5-1–5-7; 6-1–6-6; 7-1–7-5; 8-1–8-5; 9-1–9-5; 10-1–10-5; 11-1–11-6; 12-1–12-6; 13-1–13-6 (71) | Unified SPA/REST/SSE/OIDC, no direct DB/MQ/model/enterprise access.12-5 owns local build/config compatibility; Epic13 evaluates existing W behavior,not another SPA. |
| edw-api | Every story1-1–13-6 (all73) | Authoritative domain/ACL/versions/approval/publication and durable contracts; migrations introduced incrementally. |
| edw-worker | 1-1,1-2,1-4,1-5,1-6; 2-4; 3-1–3-5; 4-1–4-5; 5-1,5-3,5-4,5-5,5-6,5-7; 6-2,6-3,6-4,6-6; 7-1,7-2,7-3,7-4; 8-1–8-5; 9-1,9-2,9-4,9-5; 10-1–10-5; 11-2,11-4,11-5,11-6; 12-1–12-6; 13-1–13-6 (60) | Six execution queues and separately restricted parse/render containers; no head/ACL/approval/publication authority. |

Cross-project integration implementation stories are **7-4 core four-type flow**, **10-5 tender flow**, **11-6 forms flow**, **12-2 stateful external-effect local integration**, **12-3 local enterprise joint-test rehearsal**,followed only after all software work by **13-2 actual enterprise joint testing**. Their retained L runtime acceptance would require actual W/A/K plus local infrastructure rather than all-mock chains; those runs are `not-run` and are not software closure gates. Shared/runtime/deployment directories do not inflate the project count.

### Functional requirements → primary stories and integration evidence

| Requirement | Primary local story keys | Local integration; separately uncompleted real acceptance |
|---|---|---|
| FR-1 | 1-2,2-1 | L7-4; R13-2/13-3 |
| FR-2 | 1-3 | L7-4/7-5; R13-3 |
| FR-3 | 1-3 | L7-5; R13-2/13-3 |
| FR-4 | 1-1,1-2 | L12-3; R13-2/13-5 |
| FR-5 | 2-2 | L7-4; R13-3 |
| FR-6 | 2-2,2-3 | L7-4; R13-3/13-4 |
| FR-7 | 2-1 | L7-4/8-5; R13-3 |
| FR-8 | 2-4 | L7-4; R13-3/13-5 |
| FR-9 | 5-4 | L7-4/9-5; R13-1 POC/13-3 |
| FR-10 | 5-5 | L7-4/9-5; R13-1/13-3 |
| FR-11 | 5-6,5-7 | L7-4/8-3/8-4; R13-1/13-3 |
| FR-12 | 3-2 | L9-4/12-3; R13-1/13-2 |
| FR-13 | 3-2,3-3 | L7-4/9-4; R13-1/13-2/13-3 |
| FR-14 | 3-3,3-4,3-5 | L7-4/12-3; R13-1/13-2/13-3 |
| FR-15 | 3-5 | L5-1/9-4; R13-1/13-3 |
| FR-16 | 3-4,3-5 | L7-4/9-4; R13-1/13-2/13-4 |
| FR-17 | 3-1,3-2 | L7-4/10-5/11-6; R13-1/13-2/13-3/13-5 |
| FR-18 | 2-5,2-6,3-4,4-2 | L7-4; R13-1/13-2/13-3 |
| FR-19 | 4-2 | L7-4; R13-1/13-4 |
| FR-20 | 4-3,4-5,5-6 | L7-4/7-5; R13-1/13-3/13-5 |
| FR-21 | 4-4 | L7-4/11-2; R13-1/13-3 |
| FR-22 | 2-5,3-5,4-5 | L7-4; R13-1/13-2/13-3/13-5 |
| FR-23 | 5-1 | L7-4/9-4; R13-1/13-4 |
| FR-24 | 5-2 | L7-4/7-5; R13-3 |
| FR-25 | 5-3 | L7-4; R13-3/13-5 |
| FR-26 | 5-1,5-4,5-7 | L9-2/9-4/10-4; R13-1/13-3 |
| FR-27 | 6-1 | L7-4/12-2; R13-2/13-3/13-5 |
| FR-28 | 2-5,2-6,4-2,5-1,6-1,6-2 | L7-4; R13-2/13-3/13-5 |
| FR-29 | 6-2 | L7-4/10-4/12-2; R13-2/13-3/13-5 |
| FR-30 | 6-3,6-4,6-5 | L7-4/10-5; R13-2/13-3/13-4/13-5 |
| FR-31 | 6-6 | L7-4/12-3; R13-2/13-3/13-5 |
| FR-32 | 8-1,8-2,8-3,8-4,8-5 | L9-5/12-6; R13-1/13-3 |
| FR-33 | 5-6,9-1,9-2 | L9-4/12-6; R13-1/13-3 |
| FR-34 | 7-4 baseline,9-3,9-4,9-5 | L10-5/11-6/12-6 eligibility tooling; actual real50–200/domain curation/evaluation13-1,role outcomes13-3,final13-6 |
| FR-35 | 10-1 | L10-5/12-3; R13-1/13-2/13-3 |
| FR-36 | 10-2,10-4 | L10-5; R13-1/13-3 |
| FR-37 | 10-3 | L10-5; R13-2/13-3 |
| FR-38 | 10-4 | L10-5; R13-1/13-3 |
| FR-39 | 11-1,11-2 | L11-6/12-3; R13-1/13-2/13-3 |
| FR-40 | 11-3 | L11-6; R13-3/13-5 |
| FR-41 | 11-4,11-5 | L11-6/12-3; R13-2/13-3/13-4/13-5 |
| FR-42 | 1-1,1-2,3-2,12-1 | L12-3; R13-2 |
| FR-43 | 6-6,12-2 | L12-3; R13-2/13-3 |
| FR-44 | 1-4,1-5,1-6 | L7-3/7-4/10-5/11-6; R13-2/13-4/13-5 |
| FR-45 | 1-4,1-5 | L7-3/12-5; R/P13-5 |
| FR-46 | 1-2,4-1,6-5,7-1,7-2 | L12-3/12-5; R13-2/13-5 |
| FR-47 | 1-3,1-6,7-1,7-2,9-1 | L7-5 delivered-only/12-6; R13-2/13-3/13-5 |
| FR-48 | 1-1,7-4,7-5,12-1–12-6 | L12-6; R/P13-1–13-5; all-phase closure13-6 |

### Non-functional requirements → stories

| Requirement | Local implementation/proof; separate real acceptance owners |
|---|---|
| NFR-1 | L1-2,3-2,3-3,3-5,6-2,6-5,12-2/12-5 deny/revoke; R13-2 current adapters,13-5 security |
| NFR-2 | L1-1/1-2; real IdP13-2,security13-5 |
| NFR-3 | L4-1,7-2,12-1,12-2/12-3/12-5; actual route/model13-1/13-2 and governed egress security13-5 |
| NFR-4 | L3-1,4-1,4-3,4-5,6-4,11-1,11-3/12-5; real model injection13-1,security13-5 |
| NFR-5 | L1-2,1-4,5-3,6-1,6-2,7-1,7-2,12-2/12-5; real audit failure/tamper13-5 |
| NFR-6 | L3-1,4-1,6-3,6-5,7-1,7-2,9-3,12-5 tooling; actual TLS/encryption/secret/retention13-5 |
| NFR-7 | L3-1,4-5,6-3,6-4,11-4,11-5,12-5; real official-output13-3 and tool/resource security13-5 |
| NFR-8 | L1-3/2-3 timing boundaries,12-4 harness; actual frozen-workload UI/API/autosaveP95<1s13-4 |
| NFR-9 | L3-2,3-4,9-4,9-5,12-4 tooling; actual quality13-1,enterpriseACL13-2,search<3s/Pack<8s/permission-zero13-4 |
| NFR-10 | L4-2,9-4,9-5,12-4 tooling; real model efficacy13-1 and TTFT/chapter SLA13-4 |
| NFR-11 | L6-3,11-4 outputs,12-4 timing harness; actual formal samples13-3 and50-page elapsed<60s13-4 |
| NFR-12 | L7-3/12-5 rehearsal; actual production-equivalent99.9%/HA/RPO≤15min/RTO≤1h13-5 |
| NFR-13 | L1-4,1-5,1-6,2-3,4-2,7-3,12-5; real outage semantics13-2 and recovery13-5 |
| NFR-14 | L12-4 full profile definitions/bounded rehearsal; actual full office/AI/export peaks13-4 |
| NFR-15 | L1-5,7-1,9-4,12-4; real correlated full-load metrics13-4,operational recovery13-5 |
| NFR-16 | Each UI story validates its changed control/state;7-5 owns full inventory/visual-route contracts;12-6/13-6 validate immutable evidence references; actual fonts/users/VC13-3 |
| NFR-17 | L1-1,1-6,2-3,4-2,7-3,7-5; deferred states8-5/9-1/10-5/11-6/12-1/12-2,all12-6; real UX13-3 |
| NFR-18 | L1-1,7-4,7-5,9-5,12-5,12-6; every story uses one independent, risk-based review of its diff and applicable regressions; R/P13-1–13-5,final13-6 |

### Cross-project contracts → stories

| Contract | Local implementation/integration; separate real acceptance |
|---|---|
| C-1 | L1-1,1-2,1-6,3-2/7-4/12-3; R13-2/13-5 |
| C-2 | L2-1–2-6,4-4/7-4/10-5; R13-2/13-3/13-5 |
| C-3 | L1-4,1-5,1-6,4-2,5-1,6-3/7-3/7-4/12-2; R13-2/13-4/13-5 |
| C-4 | L3-1–3-5/7-4/9-4/10-5/12-3; R13-1/13-2/13-3/13-4 |
| C-5 | L4-1–4-4,9-4,11-2/7-4/9-5/12-3; R13-1/13-2/13-4/13-5 |
| C-6 | L3-1,4-5,6-3–6-5,11-4,11-5/7-4/11-6; R13-2/13-3/13-4/13-5 |
| C-7 | L5-1–5-7,6-1,6-2,6-6,9-1,9-2,10-4,12-2/7-4/12-6; R13-1/13-2/13-3/13-5 |
| C-8 | L6-6,11-1–11-6,12-1,12-2/12-3; R13-1/13-2/13-3/13-5 |

Owner stories retain complete local contract evidence. 12-6 checks the owner, manifest hash, environment class and result are present;13-2 owns applicable real denied/malformed/duplicate/stale/timeout/replay/current-ACL cases;13-6 reconciles the evidence matrix without re-running owner suites.

### Architecture decisions → stories

| Decision | Local implementation/proof; retained real acceptance |
|---|---|
| AD-1 | L1-1,1-2,4-2,4-4,12-1; Worker grants1-2/7-4; R13-2/13-5 |
| AD-2 | L2-2,2-3,4-4,11-1,11-2; immutable regressions7-4/11-6; R13-3/13-5 |
| AD-3 | L1-4,1-5,2-3,4-2,4-4,6-1,6-2,12-2; races7-3; R13-2/13-5 |
| AD-4 | L1-4,1-5,6-6,12-2; received≠processed/replay/unknown7-3/12-3; real13-2/13-5 |
| AD-5 | L1-6,7-3,12-4/12-5 harness; actual continuousACL13-2 and load/failover13-4/13-5 |
| AD-6 | L1-4,3-1,4-5,6-3,6-4,11-4,12-5; real queues/tool security13-5 |
| AD-7 | L1-2,1-6,3-2–3-5,6-2,6-5,12-2/12-3/12-5; actual revocation13-2/13-5 |
| AD-8 | L3-2–3-5,5-4,9-4/9-5/12-3; real sources/quality13-1/13-2 |
| AD-9 | L4-1–4-5,5-1,9-2,11-2; real model13-1,injection/policy13-5 |
| AD-10 | L5-1,5-2,5-3,6-1,6-2,9-1,9-2,10-4; real quality13-1,roles/policy13-3/13-5 |
| AD-11 | L6-2,6-6/7-4/12-3; actual separate gates/return13-2/13-3 |
| AD-12 | L3-1,6-3,6-4,6-5,11-4/12-5; real current Range/storage13-2,output13-3,security13-5 |
| AD-13 | L8-1–8-5,10-1–10-5/12-6; real full-type/tender13-1/13-2/13-3 |
| AD-14 | L11-1–11-6,12-2/12-3; real canonical/forms/device13-3 and delivery13-2 |
| AD-15 | L6-6,12-1,12-2,12-3 actual internal+stateful simulator; real receiver/capability reconciliation13-2 |
| AD-16 | All UI stories;7-5 inventory/delivered-only behavior;12-6 full L; real B/R/S/font/VC13-3 |
| AD-17 | L12-5 compatible upgrade/restore assets and isolated rehearsal; actual compatible rollout/restore13-5 |
| AD-18 | L7-2,7-4,9-3–9-5,12-3–12-6; separate R/P13-1–13-5 and final independent13-6 |

### UX pages and supplements → stories

Every P-00–P-12,SUP-1–SUP-9,X-01–X-20 row retains the local implementation owners below and independently uncompleted real UX/official-asset acceptance in13-3,with final evidence reconciliation13-6.13-2 additionally validates actual IdP/KB/delivery/source-control routes.7-5 does not test future bodies as implemented behavior.

| UX surface | Primary local stories |
|---|---|
| P-00 | 1-1,1-2,1-3,1-6 |
| P-01 | 1-3,2-1,5-4–5-7,8-5,9-1 |
| P-02 | 2-1,2-5,8-1–8-5 |
| P-03 | 2-2,2-3,3-5,4-3,4-4 |
| P-04 | 4-1,4-2,4-3,4-5 |
| P-05 | 3-2,3-3,3-4,3-5 |
| P-06 | 4-5 |
| P-07 | 2-1,2-4,8-1–8-5,11-1 |
| P-08 | 5-1,5-2,5-3,6-3,6-5 |
| P-09 | 2-3,3-5,5-2 |
| P-10 | 3-2,3-3 (navigation only baseline; body X-10) |
| P-11 | 9-1 (navigation only baseline; body X-12) |
| P-12 | 1-1,1-6,7-5 |
| SUP-1 | 2-3,4-4,11-2 |
| SUP-2 | 6-1,6-2,12-2 |
| SUP-3 | 10-1–10-5 |
| SUP-4 | 11-1–11-6,12-1,12-2 |
| SUP-5 | 3-2–3-5,6-6,7-1,7-2,9-1–9-5 |
| SUP-6 | 2-1,2-4,2-5,2-6,3-1,3-4,5-4–5-7,8-1–8-5 |
| SUP-7 | 1-4,1-5,1-6,7-1–7-3,12-1–12-6 |
| SUP-8 | 1-3,2-1,2-2,3-5,4-3,5-2,5-3,6-3–6-5 |
| SUP-9 | 1-3,1-6,2-1,4-2,5-2,7-1,9-1,7-5,12-6 |
| X-01 | 4-4,5-3,11-2 |
| X-02 | 2-3,4-4,11-2 |
| X-03 | 6-1,12-2 |
| X-04 | 6-2,10-4 |
| X-05 | 10-1,10-2 |
| X-06 | 10-2,10-3,10-4 |
| X-07 | 11-1,11-2 |
| X-08 | 11-3,11-4,11-5,12-2 |
| X-09 | 12-1,12-2,12-3 |
| X-10 | 3-1–3-5 |
| X-11 | 3-3,6-6 |
| X-12 | 5-6,9-1,9-4,9-5 |
| X-13 | 9-2,9-3,9-4,9-5 |
| X-14 | 2-4 |
| X-15 | 2-5,2-6,3-1,3-4,4-2 |
| X-16 | 1-6,7-1,7-3 |
| X-17 | 1-3 |
| X-18 | 1-1,1-2,1-3 |
| X-19 | 6-3,6-4,6-5,11-4 |
| X-20 | 1-2,4-1,7-1,7-2,12-1 |

### Exact original control groups → stories

Source is `D:/Desktop/eid/docs/prototype/index.html`; EXPERIENCE C inventory governs finer control variants.7-5 checks the complete control inventory/original position/visual/route contracts,but actual positive-negative behavior only for delivered Epic1–7 functionality. Later sub-actions are `not-yet-implemented` with exact owner below,not passed by an empty/disabled/not-configured view. Each owner supplies actual behavior proof;12-6 verifies the owner manifest and13-3 validates real users/assets;13-6 closes the complete evidence ledger.

| Control | Exact page/region/entry | Stories |
|---|---|---|
| C00 | P-00 six `[data-page]` top/side entries | 1-1,1-2 |
| C01 | P-00 `#globalSearch` Enter | 1-3 |
| C02 | P-00 `.project-card/.side-title` project selection | 1-2 |
| C03 | P-00 `.bell/.avatar/.uinfo` | 1-1,1-2,1-6 |
| C04 | P-00 favorite/reference/recycle `.side-item`,`.storage` | 1-3,3-1 |
| C05 | P-01 four `.kpis .kpi` | 1-3,9-1 |
| C06 | P-01 four `.quad .mini-card` records/More | 1-3 |
| C07 | P-01 `.recent-table .tabs` four tabs/rows | 1-3 |
| C08 | P-01 five `[data-create]` quick entries | 2-1,5-4,5-5,5-6;summary8-5;bid10-1/10-5 |
| C09 | P-01 quick More/`.ai-rec` refresh/Use/Create | 1-3,2-1,3-4 |
| C10 | P-02 modal name/type/unnamed scope/create/cancel | 2-1,2-5;Phase2 types8-1–8-5 with all-five closure8-5 |
| C11 | P-03 `#docTree` all section/subsection buttons | 2-2 |
| C12 | P-03 `.paper/#docTitle/#crumbTitle/.doc-top` save/version/status | 2-2,2-3 |
| C13 | P-03 `.doc-toolbar` undo/redo | 2-2 |
| C14 | P-03 toolbar style/size/B/I/U/color/alignment/list | 2-2 |
| C15 | P-03 toolbar link/table/image | 2-2,4-5 |
| C16 | P-03 `#insertCite` selection bookmark | 3-5 |
| C17 | P-03 toolbar More/context chooser | 2-3,4-3,6-3,6-4 |
| C18 | P-04–P-06 three `[data-aitab]` | 4-3 |
| C19 | P-04 six `[data-ai]` and authorized expanded chooser | 4-2,4-3,4-5,5-7 |
| C20 | P-04 `#aiPrompt/#sendAi/#aiResponse` | 4-3 |
| C21 | P-04 Evidence More/quality and P-05 Pack/source | 3-4,3-5,9-1 |
| C22 | P-06 three sample-item Process entries→actual located items | 4-5 |
| C23 | P-07 `#templateSearch`,scope tabs,type select,`#chips` | 2-1;Phase2 types8-1–8-5/all-five closure8-5 |
| C24 | P-07 `.tcard[data-name]` and detail metadata/outline | 2-1;Phase2 types8-1–8-5/closure8-5;bid10-1/10-5;forms11-1/11-6 |
| C25 | P-07 card/detail previews,`.use-template/#detailUse` | 2-1;Phase2 types8-1–8-5/all-five closure8-5 |
| C26 | P-07 `#uploadTpl` | 2-4 |
| C27 | P-08 download/share/`#rerunReview` | 5-1,6-3,6-4,6-5 |
| C28 | P-09 four Review `.seg-tabs` | 5-2,2-3 |
| C29 | P-08 `.filter`,section/status selects,keyword input | 5-2 |
| C30 | P-08 `.issue[data-issue="0".."6"]` and all selected detail IDs | 5-2 |
| C31 | P-08 `.issue-action[data-act="接受"]` | 5-3,4-4 |
| C32 | P-08 `.issue-action[data-act="拒绝"]` | 5-3 |
| C33 | P-08 `.issue-action[data-act="修改"]` | 5-3 |
| C34 | P-08 `.issue-action[data-act="标记已处理"]` | 5-3 |
| C35 | P-08 `.trace/.source/.excerpt` selected source, P-09 trace | 3-5,5-2 |
| C36 | P-12 `#toast/.mobile-note`,P-02 backdrop/focus/close | 1-1,1-6,2-1,7-5 |

### Deferred behavior closure (7-5 inventory is not behavior acceptance)

| Exact deferred surface/sub-action | Implementation owner and deferred positive-negative proof | Future acceptance review |
|---|---|---|
| C08 summary quick-create→summary workflow | 8-5 | 12-6 local;13-3 real |
| C10/C23/C24/C25 Phase2 type chooser/filter/card/preview/use and complete own-type pipeline | 8-1,8-2,8-3,8-4,8-5; all-five closure8-5 | 12-6;13-3 |
| C05 quality KPIs/C21 quality navigation and P-11→X-12 filters/denominators/drilldown | 9-1 | 12-6;13-3 |
| X-13 rule/dataset/run lifecycle and Analytics/evaluation component | 9-2,9-3,9-4,9-5 | 12-6;13-3 |
| C08 bid quick-create/C24 bid template and X-05/X-06 intake/correction/risk/matrix/response/release | 10-1–10-4; full deferred-action closure10-5 | 12-6;13-3 |
| C24 production-form template and X-07/X-08 Builder/instance/eleven fields/five outputs/scan/confirm | 11-1–11-5; full deferred-action closure11-6 | 12-6;13-3 |
| X-20/X-09 connectors/mappings and X-08/X-03/X-09 approved delivery/receipts/reconcile | 12-1,12-2 with actual local stateful simulator | 12-6;13-2 receiver proof and13-3 UX |

Any other later sub-action in a shared component must carry its exact later implementation story from the tables,not an ownerless umbrella.7-5 can close its software inventory while later rows retain named implementation owners. For current software closure,12-6 checks that each row has implemented source coverage, static/compile evidence and an explicit `not-run` entry for deferred positive/negative runtime cases; it does not require those cases to execute. Real evidence remains separate uncompleted13-series work.

### Shared components and UX design rules → stories

Component names retain DESIGN's23-item inventory.7-5 inventories every component and its visual/route contract,while runtime behavior proof for delivered foundations remains `not-run`. Later analytics/evaluation,tender,forms,delivery and type-specific sub-actions retain named implementation owners; they are not Phase1 positive passes. Owner-story positive/negative runtime evidence is deferred, and12-6 checks the source/ledger without rerunning behavior;13-3 later checks real assets/users. All component rows below inherit13-3 and final13-6 acceptance ownership.

| Component | Implementation owners |
|---|---|
| Shell navigation | 1-1,1-2,1-3 |
| Button and input | 1-1,2-1,2-2; specialized controls10-1,11-1 |
| Tabs and filters | 1-3,2-1,4-3,5-2,9-1,10-3 |
| Data list/table | 1-3,5-2,9-3,10-3,11-3 |
| Status and task card | 1-6,4-2,5-1,6-3,12-2 |
| Metric summary | 1-3,5-2,5-6,9-1 |
| Document canvas and toolbar | 2-2,2-3,3-5,4-3 |
| Copilot and prompt | 4-1,4-2,4-3,4-5 |
| Evidence and source viewer | 3-2,3-4,3-5,5-2 |
| Pending item resolver | 4-5 |
| Template browser/editor | 2-1,2-4;later type controls8-1–8-5/10-1/11-1 and deferred closure8-5/10-5/11-6 |
| Issue inspector | 5-1,5-2,5-3 |
| Dialog and toast | 1-1,1-6,2-1,4-5,6-1,6-2 |
| Diff and version comparison | 2-3,4-4,11-2 |
| Approval and release gate | 6-1,6-2,10-4,12-2 |
| Tender workbench | 10-1,10-2,10-3,10-4;full deferred behavior closure10-5 |
| Form Builder | 11-1,11-2;full deferred behavior closure11-6 |
| Form instance and scan | 11-3,11-4,11-5;full deferred behavior closure11-6 |
| Export and artifact viewer | 6-3,6-4,6-5,11-4 |
| Knowledge and conflict management | 3-1,3-2,3-3,6-6 |
| Analytics and evaluation | 5-6,9-1,9-3,9-4,9-5 |
| Administration and policy | 1-2,2-4,4-1,7-1,7-2,9-2,12-1 |
| Context and outline | 2-5,2-6,3-1,3-4,4-2 |

| UX rule | Story-level responsibility |
|---|---|
| UX-DR1 | 1-1 shell;2-1/2-2/5-2 original page geometry;every UI story's explicit fidelity paragraph;7-5 delivered measurement,12-6 full L,13-3 real,13-6 closure |
| UX-DR2 | 1-1 baseline assets/font manifest;2-1/2-2 source cascade;every UI story;7-5/12-6 local font/conflict evidence,13-3 real assets/dispositions,13-6 closure |
| UX-DR3 | All23 rows;7-5 inventory/visual-route contracts and delivered-only behavior;later owners→12-6 full L→13-3 real |
| UX-DR4 | Every C00–C36 row;7-5 full inventory,not future behavior pass;8-5/9-1/10-5/11-6/12-1/12-2 deferred closure;12-6 all L actions;13-3 real |
| UX-DR5 | Every X-01–X-20 and SUP-1–SUP-9 row above;story-local B/R/S references;7-5 delivered/12-6 all L,13-3 real,13-6 closure |
| UX-DR6 | Every UI story's positive/negative states plus general EXPERIENCE profiles;1-6/2-3/4-2/7-3 for durable/offline;7-5 delivered/12-6 all L interactions,13-3 actual users,13-6 closure |
| UX-DR7 | 1-1 source responsive shell;all UI stories preserve breakpoint behavior;7-5 viewport/zoom/VC measurement;12-6 all L/dispositions,13-3 real assets/users and authorized resolutions,13-6 closure |
| UX-DR8 | Every UI story inherits keyboard/focus/announcements and authorized conflict handling;7-5 measures screen-reader/contrast/reflow and VC-1/VC-2;12-6 checks full local specialist evidence,13-3 real evidence/authorized dispositions,13-6 closure;not an unsupported AA claim |

### Test package → deferred proof-producing stories

| Package | Retained coverage / L owners / separate R/P owners |
|---|---|
| T-AST | All legal/unknown nodes,roundtrip/stable IDs/selection,CAS/merge/immutable Published,Patch subset/base/hash/provenance: L2-2,2-3,3-5,4-4,5-6/7-4/11-6/12-6; real document/form samples13-3,final13-6 |
| T-CONTRACT | C-1–C-8 unified errors/status/idempotency/version/policy/fault paths: L1-1–1-6,2-1–2-6,3-1–3-5,4-1–4-5,5-1–5-7,6-1–6-6,11-1–11-6,12-1–12-3; Lclosure12-6; actual vendor contracts13-2,security/compatibility13-5,final13-6 |
| T-TASK | Confirm/crash/Inbox received≠processed/fence/lease/ACK-loss/DB retry/cancel both orders/SSE snapshot/replay/revoke: L1-4,1-5,1-6,7-3,12-2; actual receiver unknown/receipt13-2,multi-node recovery13-5,final13-6 |
| T-SEC | RBAC+ABAC+clearance/revocation,DLP/injection,grants,audit failclosed,secret/retention,malicious upload/diagram/formula,HTML/Markdown/Range/download: L1-2,3-1,4-1,4-5,6-2,6-4,6-5,7-1,11-1,11-3,12-2,12-5; real model13-1,ACL13-2,official output13-3,infrastructure13-5,final13-6 |
| T-DOC | Actual parse/OCR/DOCX/PDF and **HTML/Markdown semantic/active-content safety**: L3-1,6-3–6-5,7-4,8-1–8-5,10-5,11-4,12-4 harness; real POC13-1,official assets/Golden layout13-3,50-page timing13-4,final13-6 |
| T-TENDER | Page/correction/mandatory-disqualification-scoring/bidirectional matrix/stale/name/parameter/common-release: L10-1–10-5/12-3; real Golden13-1,enterprise13-2,domain UAT/outputs13-3,final13-6 |
| T-FORM |11fields/independent schema/SchemaPatch/parity/formula/canonical5formats/print/barcode-scan-human confirm/approved delivery: L11-1–11-6,12-2,12-3; real AI13-1,receipts13-2,official device/output/UAT13-3,security13-5,final13-6 |
| T-UX | All P/SUP/X/C/23components,B/R/S,states,viewport/fonts/1:1/keyboard/ARIA/VC: every UI story;7-5 inventory/delivered-only behavior;8-5/9-1/10-5/11-6/12-1/12-2 later closure;12-6 full L;13-3 actual assets/users/all behavior;final13-6 |
| T-QUALITY | Lbaseline7-4;9-3–9-5 runner/eligibility/metrics;10-5/11-6 specialist eligibility,12-6 Lclosure. Actual **50–200 representative Golden Queries/domain** with ACL/source/defect/human labels,Recall@K/MRR/nDCG/Top3/citation/criticalClaim/coverage/HumanEditDistance/Reviewer FP-FN and source POC →13-1; real-role outcomes13-3,final13-6 |
| T-OPS | L1-1,7-1,7-3 reproducible startup/locks/trace/faults;12-4 harness;12-5 three local upgrade/restore/security WPs;12-6 closure. Actual full load13-4,N/N-1 rollout/security/encryption/HA/99.9%/RPO/RTO13-5,final13-6 |

## Source-story R/P transfer register

Each row binds the corresponding shard's deferred L evidence table and original Scope/ordered AC/Evidence/L/R/P clauses. These runtime clauses are future acceptance,not current software closure gates. The test-package table above is likewise a future coverage map; it does not require test execution for software closure. `13-x` is an **uncompleted acceptance owner**,not a local dependency or an executed pass.13-1 owns actual quality/corpora/POC;13-2 actual contracts/current authorization/receipts;13-3 official assets/real devices/domain policy interpretation/UAT/UX;13-4 numerical timing/full capacity;13-5 security/operational policy/HA/recovery.13-6 reconciles every row and original clause. Current Story statuses are tracked separately; this planning index does not change them.

For future evidence,retain `source_story + source_field + AC ordinal/subclause + verbatim obligation + environment + accepting_story + case_id + input_owner + actual result/artifact`. Split conjunctive obligations into individual cases,not one broad passed row.12-6 registers planned and `not-run` cases without requiring runtime results for software closure;13-6 cannot pass an unrun/failed/blocked acceptance case. The detailed shard tables supply specific boundaries; this complete index permits cross-file reconciliation without treating a coarse epic label as coverage.

| Source | Retained clauses and independently uncompleted owners |
|---|---|
| 1-1 | Federation13-2;production startup/security13-5 |
| 1-2 | Enterprise membership/ACL mapping/revocation13-2;security13-5 |
| 1-3 | Project-source mapping13-2;UAT13-3;aggregate/load13-4 |
| 1-4 | Enterprise effects13-2;multi-node quorum13-5 |
| 1-5 | Real external cancellation/receipt13-2;production recovery13-5 |
| 1-6 | Source-system notifications13-2;connections/load13-4;failover13-5 |
| 2-1 | Official templates/role UAT13-3;load13-4 |
| 2-2 | Enterprise document/asset samples13-3;large versions13-4 |
| 2-3 | Coauthor UAT13-3;AC3 autosaveP95<1s under acceptance load13-4 |
| 2-4 | Official template/font/theme/policy validation13-3;hardening13-5 |
| 2-5 | Authoritative project facts13-2;load13-4 |
| 2-6 | Enterprise type-template owner validation13-3 |
| 3-1 | Enterprise scan corpus interpretation13-3;storage adapter13-2;limits/TTL/hardening13-5 |
| 3-2 | Actual embedding/reranker/quality13-1;KB/ACL13-2;load/permission-zero13-4 |
| 3-3 | Authority/validity mapping13-2;policy interpretation13-3;load13-4 |
| 3-4 | Real retrieval/Pack quality13-1;contracts13-2;search<3s/Pack<8s13-4 |
| 3-5 | Model Claim support/human gold labels13-1;user assessment13-3;load13-4 |
| 4-1 | Actual endpoints/weights/GPU/precision/capability13-1;policy/egress security13-5;throughput13-4 |
| 4-2 | Actual generation13-1;TTFT<5s/chapter<60s/exclusions/load13-4 |
| 4-3 | Operation efficacy13-1;user assessment13-3;peak13-4 |
| 4-4 | Real proposals13-1;human assessment13-3 |
| 4-5 | Real graphics quality13-1;company conventions/exception policy13-3;tool limits13-5 |
| 5-1 | Actual eight-Reviewer recall/FP-FN/severity13-1;10 concurrent Reviews13-4 |
| 5-2 | Expert source-interpretability UAT13-3;large-run load13-4 |
| 5-3 | Waiver-role/policy/defect-resolution UAT13-3;real safety policy13-5 |
| 5-4 | Model/technical-source quality13-1;technical-role3–5 tasks/official assets13-3;load13-4 |
| 5-5 | Actual data/model13-1;product-role3–5 tasks13-3;load13-4 |
| 5-6 | Requirement-to-test quality13-1;test-role3–5 tasks13-3;trace load13-4 |
| 5-7 | Real model recall13-1;requirements/quality UAT13-3;load13-4 |
| 6-1 | Approval policy/official roles/UAT13-3;audit durability13-5 |
| 6-2 | AC1 actual formal assets/current threshold/approval and waiver interpretations13-3;real ACL13-2;security/policy/durability13-5 |
| 6-3 | AC1 all official output fields/font/theme/Golden samples13-3;Evidence50-page<60s and20 simultaneous30–80-page exports13-4 |
| 6-4 | Enterprise style/resource/document review13-3;actual sourceACL13-2;security13-5/load13-4;HTML AND Markdown safety remains mandatory locally and really |
| 6-5 | Enterprise object-store/lifecycle13-2;encryption/retention/access operations13-5 |
| 6-6 | AC1 actual KB verified receipt/currentACL13-2;business quality-policy13-3;durability13-5 |
| 7-1 | Enterprise audit/retention/tamper/encryption13-5 |
| 7-2 | Enterprise contracts13-2;business policy13-3;deployment/security/retention policy13-5 |
| 7-3 | Enterprise outage semantics13-2;HA/availability/backup recovery13-5 |
| 7-4 | Real quality13-1;enterprise13-2;official output/UAT13-3;load13-4;HA/security13-5 |
| 7-5 | Real users/deployment fonts/authorized VC decisions13-3;browser performance13-4;later local behavior owner stories→12-6,not falsely passed here |
| 8-1 | Real quality13-1;quality template/rules/quality-role3–5 tasks13-3;load13-4 |
| 8-2 | Real quality13-1;project facts13-2;plan rules/PM3–5 tasks13-3;capacity13-4 |
| 8-3 | Real generation/coverage13-1;official tests/test-role3–5 tasks13-3;load13-4 |
| 8-4 | Real model13-1;official criteria/expert3–5 tasks13-3;executed NFR13-4 |
| 8-5 | Real source/model13-1;outcome records13-2;official assets/PM/relevant-role3–5 tasks13-3;load13-4/security13-5 |
| 9-1 | Enterprise metric definitions/data/UAT13-3;projection load13-4 |
| 9-2 | Subject-matter/actual model effects13-1/13-3;safe config policy13-5 |
| 9-3 | AC1 actual50–200/domain representative authorized human-adjudicated Golden sets,AC2 real eligibility denial and human-curation Evidence13-1;data governance13-5 |
| 9-4 | Actual approved model/Embedding/Reranker/KB/Golden efficacy/reproducibility13-1;endpoint/currentACL13-2;capacity13-4 |
| 9-5 | Original real evaluation/threshold governance/monthly improvements13-1;role UAT/official outputs13-3;capacity13-4/security-recovery13-5 |
| 10-1 | Real tender corpus/extraction13-1;bid specialist13-3;tool security13-5/load13-4 |
| 10-2 | Real domain Golden labels13-1;legal/business interpretation13-3;no legal/award guarantee retained |
| 10-3 | Real tender/response adjudication/official sample13-3;matrix load13-4 |
| 10-4 | Real model/defect efficacy13-1;bid policy/official templates13-3;security13-5/load13-4 |
| 10-5 | AC2 actual50–200 tender queries/defectACL labels/model13-1;enterprise13-2;bid-role3–5 complete tasks13-3;production13-4/13-5 |
| 11-1 | Official schemas/policy/users13-3;scale13-4/security13-5 |
| 11-2 | Real SchemaPatch efficacy13-1;official type policy13-3;no automatic activation retained |
| 11-3 | Company units/date/formula/recording UAT13-3;actual formula limits13-5 |
| 11-4 | Official paper/fonts/output samples/operator13-3;output peak13-4 |
| 11-5 | Real printer/scanner/camera/paper/operator correction13-3;device/storage security13-5 |
| 11-6 | AC2 actual50–200 form queries/ACL-defect labels/model13-1;enterprise delivery13-2;official forms/devices/recorder UAT13-3;capacity13-4/security13-5 |
| 12-1 | Actual declared vendor/endpoints/credentials/capabilities13-2;real config/security policy13-5 |
| 12-2 | Actual MES/project/archive/KB receipts and denied/unknown/reconcile13-2;human delivery UAT13-3 |
| 12-3 | Original actual IdP/KB/S3/MES/project/archive/return C1–8 joint tests13-2;specialist/role UAT13-3 |
| 12-4 | Original full office/AI/export profiles and exact NFR8/9/10/11/14 numerical criteria13-4 |
| 12-5 | Original real N/N-1 rollout/security/HA/99.9%/RPO15min/RTO1h/restore13-5;alternative-contract ADR13-2,alternative-performance13-4 |
| 12-6 | Original all-phase/full-R/P acceptance and exhaustive independent evidence reconciliation13-6;actual preceding evidence13-1–13-5 |

N1 source POC is explicitly13-1: technical solution as one type,3–5 excellent historical solutions,one real project knowledge set,1–2 real LLMs,existingKB→Evidence→chapter→actualDOCX (PRD§9.3 lines364–368;docs/06§13 lines342–358). It follows all local development,does not replace full per-domain Golden/UAT or grant provider authorization.12-5 requires static/compile evidence and independent source review for all three WP assets; their runtime cases remain `not-run`.13-5 still requires actual acceptance evidence for its three WPs before that future acceptance Story can complete.

## Dependency and Acceptance Planning Notes

1. Direct dependencies are earlier stories only. Binding serial order completes all Epic1–12 software development before Epic13 R/P acceptance. Missing real assets allow only labeled future test-profile local proofs/development previews,not enterprise formal publication;real-mode hard gates remain denied until supplied. No failed software gate or known implementation defect can be skipped; unrun L/R/P cases remain explicit acceptance gaps rather than software closure blockers.
2. Story granularity follows one cohesive implementation concern/type extension; reused pipelines are future regression scope,not rebuilt layers.12-5 has three separately specified local WPs;13-5 three separately evidenced real WPs.12-6 aggregates static implementation coverage and exhaustive `not-run` L/R/P obligations;13-6 aggregates actual full acceptance. Neither hides unfinished feature implementation.
3. ENV IDs retain architecture§Acceptance dependencies exactly: ENV-1 enterprise IdP/ACL/KB/MES/project/archive APIs/version/authentication/idempotency/query/callback →local12-1/12-3 tooling,actual13-2; ENV-2 real model/Embedding/Reranker/GPU/corpora/license revisions →local4-1/9-3/9-5/12-4 tooling,actual13-1/13-4; ENV-3 production cluster/network/storage/backup fault domains →local12-5 assets,actual13-5; ENV-4 DLP/classification/retention/TTL/resource limits/OCR-trigger policy →local3-1/4-1/7-2/12-5 configuration,actual13-5 (business interpretation13-3); ENV-5 official templates/fonts/theme/Golden samples →local2-4/6-3/11-4/7-5 paths,actual13-3; ENV-6 benchmark samples/metric definitions/environment/concurrency window →local9-3/9-4/9-5/12-4 tooling,actual13-1/13-3/13-4. Missing real inputs keep named13-series cases blocked/not-run; these are ownership assignments,not changed upstream environment definitions.
4. Any truly new scope/architecture conflict goes back to the coordinator as NEEDS_INPUT; existing environment blockers do not reopen confirmed interviews or remove Phase2/3. Unconfigured L2 external exception,critical-Evidence thresholds or waiver authority is deny/block, not permission to choose defaults.
5. Formal release severe unsupported critical Claim=0,permission-error retrieval=0,severe unresolved Issue=0 remain hard obligations. Suggested evaluation thresholds require governed freeze and never override these gates. FR-34 per-domain50–200 count is mandatory,not a recommendation.
6. Every UI story inherits EXPERIENCE general state/interaction profiles in addition to its specific GWT cases:loading/empty/ready/failure/forbidden/session-expired/offline; pertinent queued/retrieving/streaming/Review/Diff/stale/pending/approval/export/receipt states; focus/keyboard/screen-reader and persistent status text. Profile cases apply only where semantically relevant,not a fabricated universal state machine.
7. Configuration/scripts supplied in later implementation stories must observe exact database/external-operation authorization. This S4 plan performs no test/build/database/production operation and grants none. User S4c confirmation is still required before subsequent development stages.

## Author Check and Handoff

**Author B1/B2/N1 revision complete; independent re-review pending.** The previous independent S4_CONTENT_GATE was BLOCKED; this author revision does not supersede that gate with a self-issued PASS. This section records manual author observations only,not approval or executed product tests.

| Author check | Actual evidence and limits |
|---|---|
| Artifact count and story inventory | Thirteen authored epic shards plus this index =14 planning files. Manual inventory:6+6+5+5+7+6+5+5+5+5+6+6+6=73 stories (67 L-delivery+6 R/P-primary). All use explicit stable IDs and backlog status; epics remain planned. No machine-certified count claimed. |
| Requirement coverage | Author compared inventory and acceptance text and supplied separate rows for FR-1–48,NFR-1–18,C-1–8,AD-1–18,P-00–12,SUP-1–9,X-01–20,C00–36,UX-DR1–8,23 shared components and all10 test packages. Fine-grained story ownership is above,not only epic labels. Independent reviewer must judge semantic sufficiency. |
| Engineering allocation | Manual allocation from story Projects fields: W71,A73,K60; added13-1–13-6 each include W/A/K. W excludes backend-only1-4/1-5; A owns all; K excludes1-3,2-1/2-2/2-3/2-5/2-6,5-2,6-1/6-5,7-5,9-3,11-1/11-3. Exact lists above are authoritative; no fourth business project. |
| Story fields and dependencies | Author read story scopes/direct dependency keys/GWT positive-negative criteria/UI reference/evidence/L/R/P paragraphs and inspected numeric order against the story index. No forward direct dependency was identified in this manual pass. This is not an executed graph/uniqueness validator. |
| Hidden dependency refinement |2-2 owns minimal safe image insertion without future OCR/graphics.2-5/2-6 work manually before AI;4-2 proposes before4-4 acceptance. B1:9-5/12-3 are local protocols,12-4 local harness,12-5 local WPs,12-6 local closure;all R/P-primary stories follow inEpic13. Every earlier shard has per-story AC/Evidence/RP completion partition and exact13-owner. No failed local story may be skipped. |
| B2 behavior correction |7-5 full inventory/visual-route contracts are distinct from delivered-only positive-negative proof.8-5/9-1/10-5/11-6 and12-1/12-2 own explicit deferred behaviors;9-2–9-5 own evaluation/rule controls. The former 12-6 local rerun expectation is now deferred under the current validation rule;12-6 checks source and ledger coverage, and13-3 real UX acceptance remains open. Empty/not-configured is not a missing-function positive pass. |
| N1 acceptance sizing |13-1 retains source POC one technical-solution type,3–5 excellent historical solutions,one real project knowledge set,1–2 realLLMs;full per-domain50–200 Golden obligations remain.12-5 and13-5 split evidence into three required individually reviewed WPs. |
| Architecture/foundation | Architecture does not select a replacement business starter;1-1 retains minimal pinned React-TS/Python setup and initial identity/workspace tables only. Each story introduces required entities/migrations incrementally. Current authorization,API business ownership,fence/atomic commits,real transport,distinct release/return gates and unknown external effects remain explicit. |
| File overlap and story size | Shared AST/task/gate code necessarily evolves, but early bounded manual/transport/proposal/review/release outcomes allow feedback before specialist additions. Later types add type registry/rules/tests,not duplicate core stacks; tender/form add distinct domain modules. Integration/load/acceptance stories produce bounded evidence. Independent reviewer should still assess dev-agent sizing,especially1-1,4-2,6-3,12-5; no author self-approval implied. |
| UX fidelity | Every W-bearing story explicitly states strict inherited1:1 dimensions/styles/interactions and UX-only basis for new X bodies;12-5 also states diagnostic-screen inheritance although no new UI. Exact C inventory was cross-checked with EXPERIENCE; prototype was read but never modified. No screenshot/render/browser/visual compliance test was run. |
| Source corrections during author check | ENV-1–6 assignments were aligned with architecture's exact register; UX-DR8 mapping aligned to accessibility/VC obligations. User database authorization is retained verbatim. No upstream PRD/UX/architecture file was rewritten. |
| Mechanical author validation | An inline read-only Python validation command was submitted once. The tool refused it because worktree isolation could not verify the complex command; it did not execute. **No alternate command,script,PowerShell or other channel was used to bypass that refusal.** ID uniqueness,dependency DAG,mapping-target and file-scope automation therefore remain **not-run-tool-refused**,not pass. |
| Actual execution boundary | Only planning documents were authored in the authorized worktree. No application code,build/test run,database migration/data write,sprint-status,S4b,S5/S6,commit,push,external publication or production operation occurred. Story Evidence paragraphs are future acceptance requirements,not executed results. |

### Coordinator handoff

1. Independently re-review these14 planning files,including semantic completeness,story sizing/dependencies and precise prototype/UX references. Mechanical checks remain disclosed as not-run; any later validation must operate through normally permitted tools,not circumvent this denial.
2. Return concrete corrections to this author lane if needed. The author has not performed or delegated the independent approval pass.
3. Worktree draft completion and main-project persistence are distinct: **draft complete here; main project not written**. Persistence requires the coordinator's applicable authorization/gate process and is not requested or executed by this document.
4. No final interactive workflow C or S4c confirmation was given. `stepsCompleted` stops at authored stories; step-04 content was read and author-level checks above performed,but complete-workflow/development-readiness confirmation is not recorded. No terminal workflow automation/help/next-stage action was invoked.
5. Stop after handoff. All13 epics remain planned and73 stories backlog. Separate Epic13 R/P prerequisite absences remain future acceptance blockers,not removed scope or invented approvals. The previous BLOCKED gate remains awaiting independent re-review;this author does not self-approve.
6. Ordinary Edit Read-before-write precondition errors were resolved by normal Read→Edit,not treated as isolation denials. The earlier genuinely refused mechanical command was not retried,no shell or alternate execution channel was used during this revision. Counts/order/clause checks are manual only.
