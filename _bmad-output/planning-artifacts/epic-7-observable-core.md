---
epic_id: epic-7
status: planned
phase: 1-and-ongoing
story_status: backlog
---

## 当前开发与验证边界（2026-09-23）

执行软件层面的开发、代码检查和编译验证；不启动实际运行环境进行功能实测，也不使用已启动的实际环境进行功能实测；不进行实物、硬件或现场运行验证。

本文件统一受[开发与验证规则](development-validation-policy.md)及[总表的软件开发关闭规则](epics.md#binding-completion-contract-and-serial-acceptance-order)约束。Epic 1–12 的当前质量门禁仅为源码实现及审查、静态/契约/配置检查、编译或离线构建、独立代码审查和缺陷修复；不执行测试套件或实际环境功能验证。下文的 Verification、Evidence、L/R/P 及表格中的运行案例均为后续验收计划，不是当前 Story/Epic 关闭门禁，实际结果记录 `not-run`，不计为通过。Epic 13 当前仍暂停，不能以静态或编译结果完成验收。历史证据按原日期保留，不代表本轮通过或继续运行的授权。

# Epic 7: Diagnose and demonstrate the actual core workflow

Outcome: operators can trace durable business outcomes, safely govern availability and recover core document work. These are bounded operational-user stories, not an API/frontend/infrastructure epic. W/A/K follow epics.md.

## Software closure and deferred acceptance

The table retains each Story's planned L runtime evidence for later acceptance; it is not a current software quality gate. Software closure follows epics.md: implement the specified positive/negative behavior and security constraints, complete static checks and compilation/offline build, obtain independent source review, and fix known defects. Every unrun L case remains `not-run` under its source Story; R/P remains with Epic 13. Verification and Evidence below name future acceptance methods, not executed passes.

| Source story / clauses | Deferred L runtime evidence (not current gate) | Retained R/P clause → acceptance owner |
|---|---|---|
| 7-1 AC1–2,Evidence,L/R/P | Actual audit/telemetry for implemented critical actions,denial/tamper/log and atomic failure tests; later actions extend inventory in their owners and12-6 | Enterprise restricted audit/retention/encryption →13-5 |
| 7-2 AC1–2,Evidence,L/R/P | Actual safe config/truth-table/last-valid behavior with explicit fixtures | Real enterprise contracts →13-2; business-policy interpretation →13-3; security/retention/deployment policy →13-5 |
| 7-3 AC1–3,Evidence,L/R/P | Actual isolated core fault/recovery/race proofs | Real enterprise outage semantics →13-2; HA/availability/backup recovery →13-5 |
| 7-4 AC1–2,Evidence,L/R/P | Actual four-type W/A/K/infrastructure/parser/render chain with labeled test policies and external doubles | Real model/Golden efficacy →13-1; enterprise integration →13-2; official output/UAT →13-3; numerical load →13-4; HA/security →13-5 |
| 7-5 AC1–2,Evidence,L/R/P | Complete inventory/visual/route-contract ledger plus actual delivered Epic1–7 behaviors; explicit owner/not-yet-implemented rows for later behavior,not false passes | Enterprise users/fonts/authorized VC resolutions →13-3; browser performance →13-4. Later local behavior closes in owner story and12-6 before13-3 |

## Story 7.1: Inspect critical audit and correlated operational data
**ID:** `7-1-audit-observability` | **Status:** backlog | **Projects:** W,A,K
As an authorized operator, I want correlated audit/trace/metrics, so that failures can be explained without exposing sensitive document content.
**Scope:** Complete critical-action audit inventory and protected viewer; OTel HTTP/outbox/queue/worker/retrieval/rerank/Evidence/model/Claim/Review/Patch/SSE spans and Prometheus/Loki/Tempo linkage.
**Dependencies:** `6-6-trusted-knowledge-return`.
**Traceability:** FR-46,FR-47; NFR-5,NFR-6,NFR-15; C-1,C-3; AD-3,AD-7,AD-18.
**UI reference:** X-20 audit,X-16 task diagnostics,P-01 actual counters; C05,C03; SUP-5,SUP-7. S diagnostics,R counters.
**UI fidelity:** Strict existing visual/interaction1:1 layout/position/size/spacing/fonts/size/weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve source hierarchy/file; R/S/conflicts explicit; new X bodies follow UX contract not fabricated pixels.
**Acceptance Criteria:**
- **Given** critical login/knowledge/Evidence/model/Prompt/generation/Patch/Review/waive/template/approval/publication/export/return actions, **When** inspected, **Then**100% inventory actions have actor/action/object/version/workspace/outcome/time/request/trace/task audit and correlated latency/queue/retry/provider tokens-cost/resource metrics; counts derive from actual records and definitions.
- **Given** denied audit viewer,tamper attempt,audit interruption or sensitive Prompt/token fixture, **When** reading or critical writes execute, **Then** access/tampering denied,permission/approval/publication fail closed atomically and ordinary logs/spans never expose secrets/raw protected body; missing spans/metrics reported, not fabricated.
**Evidence:** T-SEC/T-OPS audit completeness/fault/tamper/log scans, collector→Prometheus/Loki/Tempo traces and T-UX diagnostics filters.
**L/R/P:** L actual local telemetry/audit; R enterprise restricted audit/retention rules needed; P tamper-resistant retention/encryption/security evaluation13-5.

## Story 7.2: Govern flags and configuration without bypassing permission
**ID:** `7-2-safe-governance` | **Status:** backlog | **Projects:** W,A,K
As a system administrator, I want versioned safe configuration, so that enabling a feature cannot authorize prohibited work.
**Scope:** Scoped Feature Flags,policy/retention settings,secret references and connector/model availability diagnostics; validated auditable changes, safe defaults and last-valid configuration.
**Dependencies:** `7-1-audit-observability`.
**Traceability:** FR-46,FR-47,FR-48; NFR-3,NFR-5,NFR-6,NFR-18; C-1,C-5,C-8; AD-9,AD-18.
**UI reference:** X-20 policy/retention/flag/connector sections; P-11 analytic availability; SUP-5,SUP-7. S governance,R real not-configured.
**UI fidelity:** Strict source1:1 visuals/interactions for layout/position/size/spacing/font-family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve hierarchy/source; R/S/conflicts explicit; X bodies use UX contract, not original pixels.
**Acceptance Criteria:**
- **Given** authorized admin and valid configuration, **When** changes are validated/activated, **Then** version/scope/actor/reason audit persists and effective permission equals `flag_enabled AND current_authorization AND mandatory_gates`; disabling feature does not erase historical data/tasks.
- **Given** flag-on but denied role/hard gate,unconfigured L2 exception/missing threshold/unknown connector,invalid policy or audit outage, **When** operation/config change runs, **Then** deny or not-configured; no default allow,no raw secret reveal,no deployment authorization implied. Invalid config retains last valid version.
**Evidence:** T-CONTRACT/T-SEC flag×role×gate truth table and policy rollback tests; T-UX admin masking/denied states.
**L/R/P:** L actual config store/local adapters; R real policies/contracts remain prerequisites, not invented choices; P deployment changes need separate approval.

## Story 7.3: Recover core work under dependency loss
**ID:** `7-3-core-degradation` | **Status:** backlog | **Projects:** W,A,K
As an author and operator, I want safe degraded behavior, so that outages do not erase edits or fake verified output.
**Scope:** Bounded core fault suite and observable recovery paths for model/knowledge/Reviewer/render/audit/cache/broker/worker/proxy loss; reuse1-5, not a new task engine.
**Dependencies:** `7-2-safe-governance`.
**Traceability:** FR-44,FR-45,FR-48; NFR-12,NFR-13,NFR-15; C-3,C-6,C-7; AD-3,AD-4,AD-5,AD-6.
**UI reference:** P-03 saved/offline,P-04 generation,P-06 pending,P-08 Review,X-16,X-19; SUP-7,SUP-9. R real degraded states.
**UI fidelity:** Strict original1:1 layout/position/size/spacing/fonts/size/weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness and interactions. Keep source hierarchy/file; mark R/S/conflicts; new states follow UX, no source-pixel fiction.
**Acceptance Criteria:**
- **Given** committed versions/approvals/tasks and isolated failpoints, **When** Redis resets,worker dies,broker/proxy restarts or client reconnects, **Then** PG truth survives,task recovery/fencing/replay preserves identity and approved business effects; stuck/dead-letter work is visible.
- **Given** model unavailable, **When** author edits/searches/cites/uses templates/versions or meets approval/export prerequisites, **Then** independent operations remain available. **Given** knowledge/required Reviewer unavailable, **When** new verified generation/release is requested, **Then** dependent assertions/gates block; export failure preserves source version and audit outage blocks critical writes.
- **Given** cancel vs completion and permission revocation vs completion, **When** both race orders are tested, **Then** persisted transaction order is honored with no stale output leak; tests never describe local recovery as99.9%/RPO/RTO proof.
**Evidence:** T-TASK/T-OPS/T-SEC real process/network fault traces, before-after row/artifact hashes; T-UX degraded/reconnect state matrix.
**L/R/P:** L actual infrastructure failpoints in verified isolated environment; R enterprise outage semantics13-2 (local protocol12-3); P HA/backup metrics13-5.

## Story 7.4: Demonstrate complete four-type three-project document chains
**ID:** `7-4-core-integration` | **Status:** backlog | **Projects:** W,A,K
As a delivery reviewer, I want executable full workflows, so that separate unit passes cannot disguise a broken integrated product.
**Scope:** Four Phase1 type parameterized E2E suites using actual W/A/K,OIDC,PG,MQ,S3,NGINX/SSE,parsers/renderers and domain APIs. Only external enterprise/model ports may be deterministic doubles. Baseline evaluation manifest is created now for Phase1, before9 governance.
**Dependencies:** `7-3-core-degradation`, `5-4-technical-solution`, `5-5-prd-composition`, `5-6-test-traceability`, `5-7-measurable-requirements`.
**Traceability:** FR-9,FR-10,FR-11,FR-18–FR-31,FR-34,FR-48; C-1,C-2,C-3,C-4,C-5,C-6,C-7,C-8; AD-18.
**UI reference:** UJ-1/UJ-2/UJ-3; P-00–P-09,P-12 and X-01–X-04,X-10,X-11,X-14–X-16,X-19; SUP-1,SUP-2,SUP-5,SUP-6,SUP-7,SUP-8,SUP-9. R actual complete chain.
**UI fidelity:** Explicit strict existing visual/interaction1:1 for layout/position/size/spacing/font family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve source hierarchy/file; classify R/S/conflicts; new X screens use UX not nonexistent pixel references.
**Acceptance Criteria:**
- **Given** each of technical solution,PRD,test plan,technical requirements with authorized fixture facts/templates, **When** create→attach/parse→context→human outline→Evidence→sections→Claim/Review→selected Diff→pending resolution→human approval→publish→DOCX/PDF/HTML/Markdown→separate return runs, **Then** own IDs/version/provenance/audit/artifact hashes join across actual three processes and user receives genuine downloadable artifacts; Phase1 requirement coverage is present.
- **Given** stale Patch,severe unsupported Claim,unknown coverage policy,denied Evidence,audit outage or duplicate return, **When** repeated full-chain runs execute, **Then** corresponding fail-closed state is demonstrable with no fake success or uncontrolled duplicate. Container/API/SSE traces prove chain is not all mocked.
**Evidence:** T-AST/T-CONTRACT/T-TASK/T-SEC/T-DOC/T-UX/T-QUALITY/T-OPS run manifests, Playwright traces and actual output files; fixture model/KB labels required.
**L/R/P:** L complete actual chain required; R actual model/enterprise/official output/UAT remain independently uncompleted in13-1/13-2/13-3; local12-3/9-5 are protocols,not real acceptance; P targets not inferred from functional pass.

## Story 7.5: Verify original fidelity and accessible interaction separately
**ID:** `7-5-ux-regression` | **Status:** backlog | **Projects:** W,A
As a user, I want faithful and usable controls, so that real functionality does not quietly redesign the approved workbench.
**Scope:** Full C00–C36/P-00–P-12/23-component inventory and original entry/position/visual/route contracts; actual positive/negative behavior tests only for delivered Epic1–7 functionality. Later behavior has a not-yet-implemented owner row and is not counted as functional pass. 12-6/13-6 reconcile evidence rather than rerun this inventory.
**Dependencies:** `7-4-core-integration`.
**Traceability:** FR-47,FR-48; NFR-16,NFR-17,NFR-18; AD-16,AD-18; UX-DR1–UX-DR8.
**UI reference:** All P-00–P-12/C00–C36 and implemented X/SUP; DESIGN component inventory; VC-1/VC-2; SUP-9.
**UI fidelity:** This story explicitly requires strict source visual/interaction1:1 comparison of layout/position/size/spacing/fonts/family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve source hierarchy/file; enumerate authorized R/S differences and unresolved conflicts. New pages are UX-contract comparisons only, never fabricated source pixel baselines.
**Acceptance Criteria:**
- **Given** the frozen visual environment, **When** the viewport baseline suite runs, **Then** every B control has one inventory/route/visual disposition and an owner. **Verification:** baseline manifest validator.
- **Given** delivered Epic1–7 controls, **When** their owner behavior runs, **Then** positive and negative evidence is linked to the control; later controls remain not-yet-implemented and are excluded from pass counts. **Verification:** control-to-owner evidence checker.
- **Given** a VC-1 or VC-2 conflict, **When** it is measured, **Then** the result is registered without claiming the conflicting fidelity or accessibility outcome. **Verification:** conflict-register completeness check.
**Evidence:** baseline manifest, control-to-owner evidence map and conflict register. Individual functional Stories test only their changed controls/states.
**L/R/P:** L only full inventory plus delivered behavior proof and complete deferred-owner ledger; later local behaviors are not prerequisites here and must pass their owners then12-6. R actual enterprise users/fonts/authorized conflict resolutions remain uncompleted13-3; P browser performance13-4. No R/P pass inferred.
