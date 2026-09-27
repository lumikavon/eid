---
epic_id: epic-4
status: planned
phase: 1
story_status: backlog
---

## 当前开发与验证边界（2026-09-23）

执行软件层面的开发、代码检查和编译验证；不启动实际运行环境进行功能实测，也不使用已启动的实际环境进行功能实测；不进行实物、硬件或现场运行验证。

本文件统一受[开发与验证规则](development-validation-policy.md)及[总表的软件开发关闭规则](epics.md#binding-completion-contract-and-serial-acceptance-order)约束。Epic 1–12 的当前质量门禁仅为源码实现及审查、静态/契约/配置检查、编译或离线构建、独立代码审查和缺陷修复；不执行测试套件或实际环境功能验证。下文的 Verification、Evidence、L/R/P 及表格中的运行案例均为后续验收计划，不是当前 Story/Epic 关闭门禁，实际结果记录 `not-run`，不计为通过。Epic 13 当前仍暂停，不能以静态或编译结果完成验收。历史证据按原日期保留，不代表本轮通过或继续运行的授权。

# Epic 4: Obtain controlled AI proposals without silent edits

Outcome: authors obtain source-grounded plans/sections and choose exact changes. Global W/A/K, L/R/P and source requirements in epics.md apply.

## Software closure and deferred acceptance

The table retains each Story's planned L runtime evidence for later acceptance; it is not a current software quality gate. Software closure follows epics.md: implement the specified positive/negative behavior and security constraints, complete static checks and compilation/offline build, obtain independent source review, and fix known defects. Every unrun L case remains `not-run` under its source Story; R/P remains with Epic 13. Verification and Evidence below name future acceptance methods, not executed passes.

| Source story / clauses | Deferred L runtime evidence (not current gate) | Retained R/P clause → acceptance owner |
|---|---|---|
| 4-1 AC1–3,Evidence,L/R/P | Actual Gateway/worker/schema/DLP/egress-denial and retry tests | Approved real model capability/weights/GPU/precision/efficacy →13-1; actual enterprise policy/egress security →13-5; throughput →13-4 |
| 4-2 AC1–2,Evidence,L/R/P | Actual durable generation DAG/proposals with declared model double; local boundaries measured | Real generation quality →13-1; real TTFTP95<5s/chapterP95<60s/exclusions and load →13-4 |
| 4-3 AC1–2,Evidence,L/R/P | Every catalog action positive/negative through actual internal chain | Real operation efficacy →13-1; user assessment →13-3; model peak →13-4 |
| 4-4 AC1–2,Evidence,L/R/P | Actual selected Patch/CAS/current ACL and reject/no-change tests | Real-proposal quality →13-1; human assessment →13-3; no implied efficacy from local pass |
| 4-5 AC1–2,Evidence,L/R/P | Actual pending resolver and isolated Mermaid/graphics pipeline | Real model graphics quality →13-1; company conventions/exception-authority interpretation →13-3; real tool/resource-limit security →13-5 |

## Story 4.1: Use a policy-approved model and versioned Prompt
**ID:** `4-1-safe-model-routing` | **Status:** backlog | **Projects:** W,A,K
As a security/model administrator, I want policy-constrained model routes, so that generation never exports prohibited material.
**Scope:** Shared httpx/Pydantic LLM Gateway, versioned Prompt Registry/Model Profiles, quotas/budgets/context/capability/timeout, output schema validation and at most one repair; restricted provenance, no raw ordinary logs.
**Dependencies:** `3-4-section-evidence`, `1-6-task-observation`.
**Traceability:** FR-20,FR-46,FR-47; NFR-3,NFR-4,NFR-5,NFR-6; C-5; AD-9.
**UI reference:** X-20 Model Profiles/Prompt Registry/routing-DLP/validation; P-04 status/errors; SUP-5,SUP-7. S configuration,R real failure.
**UI fidelity:** Inherit strict source visual/interaction1:1 layout/position/size/spacing/font-family-size-weight/color/radius/shadow/border/icon/image proportions/button-input states/responsiveness. Preserve hierarchy/source; mark R/S/conflicts without self-resolution; X bodies follow UX, not imaginary source pixels.
**Acceptance Criteria:**
- **Given** versioned policies and allowed route, **When** request runs, **Then** Classify→DLP→Policy→Redact→Router order is enforced, token/context/capability/cost limits checked and GenerationRun records Prompt/provider/model/input-output hashes/usage with safe retention; candidate Qwen3-32B is not labeled production-approved without evaluation.
- **Given** L3 external,L2 unconfigured exception,L1 no redaction,secret/JWT/private-key/personal/customer/IP/MAC/domain/project/device/technical-data fixture or prompt injection in KB/tender/attachments, **When** model use is attempted, **Then** deny or approved redaction occurs before egress, no less restrictive fallback, untrusted data cannot grant tools/ACL or shell access.
- **Given** malformed output or network error, **When** handler recovers, **Then** schema repair occurs at most once; persistent schema failure preserved and transient retries use DB schedule, never hidden uncontrolled retries. Raw sensitive Prompt/secret must not appear in browser storage/logs/config UI.
**Evidence:** T-SEC/T-CONTRACT/T-QUALITY route matrix, wire-capture egress denial, injection/output schema fixtures, redacted audit; T-UX not-configured states.
**L/R/P:** L deterministic provider with actual Gateway/policy/worker; R approved real endpoints/model capability/GPU/weights/precision required; P throughput/security13-4/13-5.

## Story 4.2: Propose an outline and generate bounded sections
**ID:** `4-2-section-generation` | **Status:** backlog | **Projects:** W,A,K
As an author, I want controlled section tasks, so that long generation is inspectable and respects my confirmed outline.
**Scope:** AI outline proposal via existing confirmation contract, DAG stages/context/Evidence/section generation/validation, saved proposals and full-document assembly/cross-section checks. Worker never moves document head.
**Dependencies:** `4-1-safe-model-routing`, `3-5-claim-citation`, `2-6-outline-confirmation`.
**Traceability:** FR-18,FR-19,FR-28,FR-44; NFR-10,NFR-13; C-2,C-3,C-4,C-5; AD-1,AD-3,AD-9.
**UI reference:** P-04 `[data-ai="生成本章节"]/#aiResponse`, X-15 outline proposal/confirm,X-16 DAG steps; C19,C20; SUP-6,SUP-7,SUP-9. R actual streaming/proposal,S stage details.
**UI fidelity:** Strict original1:1 visual/interaction across layout/position/size/spacing/fonts/size/weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Source hierarchy/file unchanged; B/R/S/conflicts tracked; X pages use UX contract without source-pixel claims.
**Acceptance Criteria:**
- **Given** current context/confirmed outline/template and section Pack, **When** generation starts, **Then**202/task_id progresses through persisted retrieval/Evidence/generation/validation; validated result exposes content AST,Claims,citations,assumptions,missing info and provenance as proposal. Assembly runs cross-section consistency checks, not a monolithic free-text shortcut.
- **Given** unconfirmed outline/missing fact/changed base/revoked source/model outage/cancel, **When** a stage executes or commits, **Then** BLOCKED_BY_MISSING_INFO/failed/conflict/cancelled is accurate; no generated fact invention, no direct head mutation, manual edit remains available. Final transaction checks lease/fence/policy/base/hash/cancel.
**Evidence:** T-TASK/T-CONTRACT actual DAG persistence/restart tests and worker-grant denial; T-QUALITY structured outputs; T-UX changed stage-state matrix; structured timing events only. Real TTFT/chapter numerical acceptance is owned by13-4.
**L/R/P:** L full actual three-project chain with labeled model double; R real generation/TTFTP95<5s/chapterP95<60s and exclusions mandatory13-1/13-4; P load later.

## Story 4.3: Target the complete Copilot operation catalog
**ID:** `4-3-copilot-operations` | **Status:** backlog | **Projects:** W,A,K
As an author, I want the requested operation to act on the intended selection, so that queries and edits have predictable effects.
**Scope:** A shared target-resolution contract and four behavior families: read-only query, Patch proposal, located finding/pending item, and structured table/diagram result. The operation catalog maps to one family; capability gate uses target/permission/input and writes remain Patch proposals. New operation families require a new Story.
**Dependencies:** `4-2-section-generation`.
**Traceability:** FR-20,FR-21,FR-22; C-2,C-4,C-5; AD-2,AD-9,AD-16.
**UI reference:** P-04 `[data-aipanel="copilot"]/[data-ai]/#aiPrompt/#sendAi/#aiResponse`, P-03 More, three `[data-aitab]`; C17,C18,C19,C20; SUP-1,SUP-9. B six buttons,R operation effects,S chooser.
**UI fidelity:** Strict source visual/interaction1:1 layout/position/size/spacing/font family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve source hierarchy/file, no seventh arbitrary baseline button; R/S/conflicts explicit, chooser follows UX without invented pixels.
**Acceptance Criteria:**
- **Given** a read-only catalog operation and resolved target, **When** it executes, **Then** it does not mutate the AST. **Verification:** parameterized AST-hash contract test.
- **Given** a write catalog operation and resolved target, **When** it executes, **Then** it returns a Patch proposal or a located finding/pending item, never a direct AST mutation. **Verification:** family-based API contract test.
- **Given** missing target, invalid input, denied permission or unsafe provider output, **When** an operation is requested, **Then** a named failure state is returned and no action occurs. **Verification:** negative contract test.
- **Given** an original Copilot control, **When** its mapped family is available, **Then** its approved label and entry remain available. **Verification:** changed-control browser test.
**Evidence:** one parameterized contract table per family plus the changed-control browser test; no per-operation duplicate test suite.
**L/R/P:** L actual actions/API/worker with deterministic provider; R real operation efficacy13-1 and user assessment13-3; P model peak13-4.

## Story 4.4: Accept only selected, current AI changes
**ID:** `4-4-reviewed-patches` | **Status:** backlog | **Projects:** W,A,K
As an author, I want a precise AI Diff, so that I can reject or accept individual proposed changes without losing manual prose.
**Scope:** Stable-target Patch schema, expected target hashes/base revision, selected accept/reject, provenance-linked new immutable version, stale conflict handoff.
**Dependencies:** `4-3-copilot-operations`, `2-3-version-conflicts`.
**Traceability:** FR-21,FR-25; C-2,C-4,C-5; AD-1,AD-2,AD-3.
**UI reference:** X-01 before/after/selection/provenance/accept/reject,X-02 stale compare; P-03 status; SUP-1. S Diff,R actual version.
**UI fidelity:** Strict inherited source visual/interaction1:1 for layout/position/size/spacing/font-family-size-weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve hierarchy/source; document R/S/conflicts; X-01/02 use UX contract not source pixel fiction.
**Acceptance Criteria:**
- **Given** multiple proposed stable-target edits, **When** authorized author accepts a subset, **Then** API checks base/revision/target hashes/current ACL and creates exactly one new version with only selected changes and GenerationRun/EvidencePack/Prompt/model/hash/token provenance. Reject changes no AST.
- **Given** stale/deleted target, malicious arbitrary JSON pointer to ACL/metadata, wrong workspace,revocation or concurrent accept, **When** accept runs, **Then** transaction fails safely/409 with retained proposal and conflict path; no Worker head update or unselected change. Duplicate idempotency reauthorizes and cannot double-apply.
**Evidence:** T-AST/T-CONTRACT selected-subset/provenance/CAS/hash/idempotency tests; T-SEC privilege-target tests; T-UX paired Diff/conflict screenshots.
**L/R/P:** L actual stores and API acceptance; R actual model proposal quality13-1 and human assessment13-3; P no efficacy inferred here.

## Story 4.5: Resolve pending facts and safely propose tables or diagrams
**ID:** `4-5-pending-safe-graphics` | **Status:** backlog | **Projects:** W,A,K
As an author, I want explicit fact resolution and safe structured graphics, so that unresolved assumptions and executable content cannot enter a formal document unnoticed.
**Scope:** Located pending reason/proposed value/current state/history/authorized exception; validated table AST and Mermaid rendering in safe render worker. PlantUML requests are parsed/proposed through approved supported conversion or explicit unsupported result, not new executable runtime.
**Dependencies:** `4-4-reviewed-patches`, `3-1-safe-attachments`.
**Traceability:** FR-20,FR-22; NFR-4,NFR-7; C-2,C-6,C-7; AD-6,AD-9,AD-10.
**UI reference:** P-06 `[data-aipanel="todo"]` Process28px buttons, P-04 table/diagram chooser, X-01 proposal; C22,C17,C19; SUP-1,SUP-9. R real resolver/count,S reason/preview.
**UI fidelity:** Strict existing visual/interaction1:1 covers layout/position/size/spacing/fonts/size/weight/colors/radii/shadows/borders/icons/image proportions/button-input states/responsiveness. Preserve source hierarchy/file; R/S/conflicts explicit; added resolver follows UX, not claimed original pixels.
**Acceptance Criteria:**
- **Given** pending item with reason/location/evidence and allowed resolution policy, **When** user supplies confirmed fact or expressly allowed exception, **Then** audit/actor/reason/version/count update; unknown waiver authority denies and non-waivable hard gates remain blocked.
- **Given** table/diagram proposal, **When** validated and rendered, **Then** stable AST/resource/hash enters a reviewable Patch; Mermaid syntax/node/text/options are allowlisted and tool has no network/DB/MQ credentials. **And** malicious directives,remote URLs,resource exhaustion or unsupported syntax result in explicit failure, not arbitrary execution or silent successful replacement.
**Evidence:** T-SEC malicious Mermaid/file/network/timeout cases; T-AST table/diagram Patch tests; T-CONTRACT pending policy/count/history; T-UX resolver/preview/failure.
**L/R/P:** L real isolated Mermaid/image pipeline and resolver; R approved company graphic conventions and real model proposal quality; P tool limits validated13-5.
